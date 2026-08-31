using System;
using System.Linq;
using Sharp.Shared;

namespace ModSharpAg2NpcExample.Animation;

internal sealed record Ag2NativeBindings(
    string Status,
    nint MakeGlobalSymbol = 0,
    nint GetParameterType = 0,
    nint SetBool = 0,
    nint SetFloat = 0,
    nint SetId = 0)
{
    internal bool IsResolved
        => Status == "bindings-resolved"
           && MakeGlobalSymbol != nint.Zero
           && GetParameterType != nint.Zero
           && SetBool != nint.Zero
           && SetFloat != nint.Zero
           && SetId != nint.Zero;
}

internal static class Ag2NativeResolver
{
    // These are private gamedata aliases, not Valve C++ symbol names.
    private const string KeyPrefix = "Ag2NpcExample::Parameters::";

    internal static Ag2NativeBindings Resolve(
        IModSharp modSharp,
        IGameData gameData)
    {
        try
        {
            if (!TryGetAddress(gameData, $"{KeyPrefix}GetType", out var getParameterType))
            {
                return new Ag2NativeBindings("gamedata-address-missing:GetType");
            }

            if (!TryGetAddress(gameData, $"{KeyPrefix}SetBool", out var setBool))
            {
                return new Ag2NativeBindings("gamedata-address-missing:SetBool");
            }

            if (!TryGetAddress(gameData, $"{KeyPrefix}SetFloat", out var setFloat))
            {
                return new Ag2NativeBindings("gamedata-address-missing:SetFloat");
            }

            if (!TryGetAddress(gameData, $"{KeyPrefix}SetIdentifier", out var setId))
            {
                return new Ag2NativeBindings("gamedata-address-missing:SetIdentifier");
            }

            var addresses = new[]
            {
                (Name: "GetParameterType", Address: getParameterType),
                (Name: "SetBoolParameter", Address: setBool),
                (Name: "SetFloatParameter", Address: setFloat),
                (Name: "SetIdParameter", Address: setId),
            };
            if (addresses.Select(item => item.Address).Distinct().Count() != addresses.Length)
            {
                return new Ag2NativeBindings("gamedata-address-alias");
            }

            var server = modSharp.GetLibraryModule("server");
            if (server is null)
            {
                return new Ag2NativeBindings("server-module-missing");
            }

            foreach (var item in addresses)
            {
                if (!server.GetFunctionRange(item.Address, out var start, out var end)
                    || start != item.Address
                    || end.ToInt64() <= start.ToInt64())
                {
                    return new Ag2NativeBindings(
                        $"gamedata-function-entry-invalid:{item.Name}");
                }
            }

            var tier0 = modSharp.GetLibraryModule("tier0");
            if (tier0 is null)
            {
                return new Ag2NativeBindings("tier0-module-missing");
            }

            var makeGlobalSymbol = tier0.GetFunctionByName("MakeGlobalSymbol");
            if (makeGlobalSymbol == nint.Zero)
            {
                makeGlobalSymbol = tier0.GetFunctionByName("_MakeGlobalSymbol");
            }

            if (makeGlobalSymbol == nint.Zero)
            {
                return new Ag2NativeBindings("make-global-symbol-missing");
            }

            return new Ag2NativeBindings(
                "bindings-resolved",
                makeGlobalSymbol,
                getParameterType,
                setBool,
                setFloat,
                setId);
        }
        catch (Exception exception)
        {
            return new Ag2NativeBindings($"resolve-error:{exception.GetType().Name}");
        }
    }

    private static bool TryGetAddress(
        IGameData gameData,
        string key,
        out nint address)
    {
        address = nint.Zero;
        return gameData.GetAddress(key, out address) && address != nint.Zero;
    }
}
