using System;
using System.Collections.Concurrent;
using System.Threading;

namespace ModSharpAg2NpcExample.Animation;

internal sealed class Ag2SymbolRegistry
{
    private readonly ConcurrentDictionary<string, nint> _symbols =
        new(StringComparer.Ordinal);
    private readonly Func<string, nint> _factory;
    private readonly object _missGate = new();
    private readonly int _capacity;
    private readonly int _ownerThreadId;
    private int _cachedCount;

    internal Ag2SymbolRegistry(
        Func<string, nint> factory,
        int capacity,
        int ownerThreadId)
    {
        _factory = factory;
        _capacity = capacity;
        _ownerThreadId = ownerThreadId;
    }

    internal bool TryGetOrCreate(string value, out nint symbol)
    {
        symbol = nint.Zero;
        if (string.IsNullOrEmpty(value)
            || value.Contains('\0', StringComparison.Ordinal))
        {
            return false;
        }

        if (_symbols.TryGetValue(value, out symbol))
        {
            return symbol != nint.Zero;
        }

        if (Environment.CurrentManagedThreadId != _ownerThreadId)
        {
            symbol = nint.Zero;
            return false;
        }

        lock (_missGate)
        {
            if (_symbols.TryGetValue(value, out symbol))
            {
                return symbol != nint.Zero;
            }

            if (Volatile.Read(ref _cachedCount) >= _capacity)
            {
                return false;
            }

            symbol = _factory(value);
            if (symbol == nint.Zero)
            {
                return false;
            }

            if (_symbols.TryAdd(value, symbol))
            {
                Interlocked.Increment(ref _cachedCount);
            }
            else if (_symbols.TryGetValue(value, out var existing))
            {
                symbol = existing;
            }

            return symbol != nint.Zero;
        }
    }
}
