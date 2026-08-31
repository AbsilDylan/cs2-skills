using System;
using System.Buffers;
using System.Globalization;
using System.Text;
using System.Threading;
using Sharp.Shared;
using Sharp.Shared.GameEntities;

namespace ModSharpAg2NpcExample.Animation;

/// <summary>
/// Game-thread-only typed AG2 writer. Native calls remain disabled until an
/// exact ModSharp gamedata resolution and a live Bool / Float / ID parameter
/// probe have both succeeded.
/// </summary>
internal sealed class Ag2ParameterWriter
{
    private const byte BoolType = 1;
    private const byte IdType = 2;
    private const byte FloatType = 3;
    private const int MaximumCachedSymbols = 128;
    private const int StackUtf8Bytes = 256;

    private readonly Ag2NativeBindings _bindings;
    private readonly Ag2SymbolRegistry? _symbols;
    private readonly int _ownerThreadId;
    private int _probePassed;
    private string _probeStatus;

    private Ag2ParameterWriter(Ag2NativeBindings bindings)
    {
        _bindings = bindings;
        _ownerThreadId = Environment.CurrentManagedThreadId;
        _probeStatus = bindings.IsResolved ? "probe-required" : "probe-unavailable";
        _symbols = bindings.IsResolved
            ? new Ag2SymbolRegistry(
                MakeGlobalSymbol,
                MaximumCachedSymbols,
                _ownerThreadId)
            : null;
    }

    internal bool IsResolved => _bindings.IsResolved;
    internal bool IsAvailable => IsResolved && Volatile.Read(ref _probePassed) == 1;
    internal string Status => _bindings.Status;

    internal static Ag2ParameterWriter Resolve(
        IModSharp modSharp,
        IGameData gameData)
        => new(Ag2NativeResolver.Resolve(modSharp, gameData));

    internal static Ag2ParameterWriter Unavailable(string status)
        => new(new Ag2NativeBindings(status));

    internal string Describe()
        => $"native={_bindings.Status} activation={Volatile.Read(ref _probeStatus)}";

    internal bool TryActivate(IBaseModelEntity entity, out string status)
    {
        if (!IsResolved)
        {
            status = _bindings.Status;
            return false;
        }

        if (!IsOwnerThread())
        {
            status = "wrong-game-thread";
            return false;
        }

        if (Volatile.Read(ref _probePassed) == 1)
        {
            status = Volatile.Read(ref _probeStatus);
            return true;
        }

        if (!TryGetEntityPointer(entity, out var entityPointer, out status))
        {
            return false;
        }

        try
        {
            var boolType = ReadParameterType(entityPointer, "in_air", out var boolStatus);
            var floatType = ReadParameterType(entityPointer, "time_scale", out var floatStatus);
            var idType = ReadParameterType(entityPointer, "base_action", out var idStatus);
            status =
                $"probe:bool={FormatType(boolType)}({boolStatus}),float={FormatType(floatType)}({floatStatus}),id={FormatType(idType)}({idStatus})";
            if (boolType != BoolType
                || floatType != FloatType
                || idType != IdType)
            {
                Volatile.Write(ref _probeStatus, status);
                return false;
            }

            Volatile.Write(ref _probeStatus, "probe-passed");
            Volatile.Write(ref _probePassed, 1);
            status = "probe-passed";
            return true;
        }
        catch (Exception exception)
        {
            status = $"probe-error:{exception.GetType().Name}";
            Volatile.Write(ref _probeStatus, status);
            return false;
        }
    }

    internal unsafe Ag2WriteResult Apply(
        IBaseModelEntity entity,
        Ag2Parameter parameter)
    {
        if (!IsResolved)
        {
            return new Ag2WriteResult(false, _bindings.Status);
        }

        if (!IsAvailable)
        {
            return new Ag2WriteResult(false, "runtime-probe-required");
        }

        if (!IsOwnerThread())
        {
            return new Ag2WriteResult(false, "wrong-game-thread");
        }

        if (!TryGetEntityPointer(entity, out var entityPointer, out var entityStatus))
        {
            return new Ag2WriteResult(false, entityStatus);
        }

        try
        {
            if (!_symbols!.TryGetOrCreate(parameter.Name, out var parameterSymbol))
            {
                return new Ag2WriteResult(false, $"{parameter.Name}:symbol-missing");
            }

            var parameterRef = stackalloc nint[1];
            parameterRef[0] = parameterSymbol;
            var actualType =
                ((delegate* unmanaged<nint, nint, byte>)_bindings.GetParameterType)(
                    entityPointer,
                    (nint)parameterRef);
            var expectedType = GetNativeType(parameter.Type);
            if (actualType != expectedType)
            {
                return new Ag2WriteResult(
                    false,
                    $"{parameter.Name}:expected-{FormatType(expectedType)}-got-{FormatType(actualType)}");
            }

            switch (parameter.Type)
            {
                case Ag2ParameterType.Bool:
                {
                    var value = stackalloc byte[1];
                    value[0] = parameter.BoolValue ? (byte)1 : (byte)0;
                    InvokeSetter(_bindings.SetBool, entityPointer, parameterRef, value);
                    break;
                }
                case Ag2ParameterType.Float:
                {
                    var value = stackalloc float[1];
                    value[0] = parameter.FloatValue;
                    InvokeSetter(_bindings.SetFloat, entityPointer, parameterRef, value);
                    break;
                }
                case Ag2ParameterType.Id:
                {
                    if (!_symbols.TryGetOrCreate(parameter.IdValue!, out var valueSymbol))
                    {
                        return new Ag2WriteResult(false, $"{parameter.Name}:id-symbol-missing");
                    }

                    var value = stackalloc nint[1];
                    value[0] = valueSymbol;
                    InvokeSetter(_bindings.SetId, entityPointer, parameterRef, value);
                    break;
                }
                default:
                    return new Ag2WriteResult(false, $"{parameter.Name}:unsupported");
            }

            return new Ag2WriteResult(true, parameter.Name);
        }
        catch (Exception exception)
        {
            return new Ag2WriteResult(
                false,
                $"{parameter.Name}:native-error-{exception.GetType().Name}");
        }
    }

    private bool IsOwnerThread()
        => Environment.CurrentManagedThreadId == _ownerThreadId;

    private static bool TryGetEntityPointer(
        IBaseModelEntity entity,
        out nint entityPointer,
        out string status)
    {
        entityPointer = nint.Zero;
        status = "entity-invalid";
        try
        {
            if (entity.IsDisposed
                || !entity.IsValid()
                || entity.IsMarkedForDeletion())
            {
                return false;
            }

            entityPointer = entity.GetAbsPtr();
            if (entityPointer == nint.Zero)
            {
                status = "entity-pointer-missing";
                return false;
            }

            status = "entity-ok";
            return true;
        }
        catch (Exception exception)
        {
            status = $"entity-guard-error:{exception.GetType().Name}";
            return false;
        }
    }

    private unsafe byte ReadParameterType(
        nint entityPointer,
        string parameterName,
        out string status)
    {
        if (!_symbols!.TryGetOrCreate(parameterName, out var symbol))
        {
            status = "symbol-missing";
            return 0;
        }

        var parameterRef = stackalloc nint[1];
        parameterRef[0] = symbol;
        status = "read";
        return ((delegate* unmanaged<nint, nint, byte>)_bindings.GetParameterType)(
            entityPointer,
            (nint)parameterRef);
    }

    private static byte GetNativeType(Ag2ParameterType type)
        => type switch
        {
            Ag2ParameterType.Bool => BoolType,
            Ag2ParameterType.Float => FloatType,
            Ag2ParameterType.Id => IdType,
            _ => 0,
        };

    private static string FormatType(byte type)
    {
        if (type == BoolType) return "bool";
        if (type == FloatType) return "float";
        if (type == IdType) return "id";
        return type == 0 ? "missing" : type.ToString(CultureInfo.InvariantCulture);
    }

    private unsafe nint MakeGlobalSymbol(string value)
    {
        var byteCount = Encoding.UTF8.GetByteCount(value);
        var requiredBytes = checked(byteCount + 1);
        if (requiredBytes <= StackUtf8Bytes)
        {
            Span<byte> bytes = stackalloc byte[requiredBytes];
            Encoding.UTF8.GetBytes(value.AsSpan(), bytes);
            bytes[byteCount] = 0;
            fixed (byte* pointer = bytes)
            {
                return ((delegate* unmanaged<byte*, nint>)_bindings.MakeGlobalSymbol)(pointer);
            }
        }

        var rented = ArrayPool<byte>.Shared.Rent(requiredBytes);
        try
        {
            var bytes = rented.AsSpan(0, requiredBytes);
            Encoding.UTF8.GetBytes(value.AsSpan(), bytes);
            bytes[byteCount] = 0;
            fixed (byte* pointer = bytes)
            {
                return ((delegate* unmanaged<byte*, nint>)_bindings.MakeGlobalSymbol)(pointer);
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(rented);
        }
    }

    private static unsafe void InvokeSetter<T>(
        nint setter,
        nint entityPointer,
        nint* parameterRef,
        T* value)
        where T : unmanaged
        => ((delegate* unmanaged<nint, nint, nint, int, void>)setter)(
            entityPointer,
            (nint)parameterRef,
            (nint)value,
            0);
}
