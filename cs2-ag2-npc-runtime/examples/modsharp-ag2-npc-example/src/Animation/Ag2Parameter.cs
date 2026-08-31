using System;

namespace ModSharpAg2NpcExample.Animation;

internal enum Ag2ParameterType
{
    Bool,
    Float,
    Id,
}

internal readonly record struct Ag2Parameter
{
    private Ag2Parameter(
        string name,
        Ag2ParameterType type,
        bool boolValue,
        float floatValue,
        string? idValue)
    {
        Name = ValidateSymbol(name, nameof(name));
        Type = type;
        BoolValue = boolValue;
        FloatValue = floatValue;
        IdValue = idValue;
    }

    internal string Name { get; }
    internal Ag2ParameterType Type { get; }
    internal bool BoolValue { get; }
    internal float FloatValue { get; }
    internal string? IdValue { get; }

    internal static Ag2Parameter Bool(string name, bool value)
        => new(name, Ag2ParameterType.Bool, value, 0.0f, null);

    internal static Ag2Parameter Float(string name, float value)
    {
        if (!float.IsFinite(value))
        {
            throw new ArgumentOutOfRangeException(nameof(value));
        }

        return new Ag2Parameter(name, Ag2ParameterType.Float, false, value, null);
    }

    internal static Ag2Parameter Id(string name, string value)
        => new(
            name,
            Ag2ParameterType.Id,
            false,
            0.0f,
            ValidateSymbol(value, nameof(value)));

    private static string ValidateSymbol(string? value, string parameterName)
    {
        if (string.IsNullOrEmpty(value)
            || value.Contains('\0', StringComparison.Ordinal))
        {
            throw new ArgumentException(
                "AG2 symbols must be non-empty and cannot contain NUL.",
                parameterName);
        }

        return value;
    }
}

internal readonly record struct Ag2WriteResult(bool Applied, string Status);
