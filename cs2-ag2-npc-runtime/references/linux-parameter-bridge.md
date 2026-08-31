# Linux AG2 Typed Parameter Bridge

## Contents

- [Choose The Framework Path](#choose-the-framework-path)
- [Engine Call Contract](#engine-call-contract)
- [Bundled ModSharp Example](#bundled-modsharp-example)
- [ModSharp Gamedata And Factory](#modsharp-gamedata-and-factory)
- [Runtime Lifecycle And Safety](#runtime-lifecycle-and-safety)
- [Adapt Another Framework](#adapt-another-framework)
- [Recover After A CS2 Update](#recover-after-a-cs2-update)
- [Failure Policy](#failure-policy)

## Choose The Framework Path

Use a native bridge only when the selected server framework has no verified
public API for setting AG2 control parameters. Call existing engine functions;
never patch `libserver.so` or write guessed graph/controller memory.

- For ModSharp, use the bundled concrete project. Do not create a second JSON
  schema, identity-profile loader, manual executable scanner, or fictional EKV
  abstraction.
- For another framework, reuse only the engine-level call contract and safety
  invariants. Translate integration through that framework's documented APIs.
- When the framework/version is unknown, stop at the engine contract instead
  of presenting pseudocode as callable code.

## Engine Call Contract

The verified Linux x86-64 shapes used by the example are equivalent to:

```csharp
delegate* unmanaged<nint, nint, byte> getParameterType;
delegate* unmanaged<nint, nint, nint, int, void> setParameter;
```

Conceptual arguments:

```text
getParameterType(entityPointer, addressOfParameterSymbol)
setParameter(entityPointer, addressOfParameterSymbol, addressOfTypedValue, 0)
```

Observed scalar type codes:

```text
1 -> Bool
2 -> ID
3 -> Float
```

Vector and Target may appear in graph contracts, but this bridge does not
claim writable setters for them. Never coerce either through a scalar setter.

Convert parameter names and ID values through the engine global-symbol
facility used by these functions. In the ModSharp example that export is
`MakeGlobalSymbol` from `tier0`. A managed string pointer, unrelated hash, or
enum ordinal is not a substitute.

## Bundled ModSharp Example

Use [examples/modsharp-ag2-npc-example](../examples/modsharp-ag2-npc-example/)
as the maintained ModSharp implementation. Important files are:

| File | Role |
| --- | --- |
| `src/Ag2NpcExampleModule.cs` | module lifecycle, gamedata registration, command, hooks |
| `src/Animation/Ag2NativeResolver.cs` | resolved-address and function-entry checks |
| `src/Animation/Ag2ParameterWriter.cs` | symbol conversion, type probe, typed calls |
| `gamedata/modsharp-ag2-npc-example.games.jsonc` | four strict Linux signatures |
| `src/Npc/DirectChaseNpcRuntime.cs` | deliberately limited spawn/materialization demonstration |

It uses real ModSharp APIs for `IGameData`, synchronous entity spawning, EKV,
resource precache, frame hooks, entity guards, and cleanup. Its flat direct
chase is only enough to demonstrate locomotion parameters; it is not NAV,
collision movement, or reusable NPC gameplay. Route those concerns to
`cs2-server-npc-runtime`.

No model, graph, skeleton, clip, material, texture, particle, or sound asset is
bundled. The path-only Deadlock controls require a separately lawful and
complete client/server resource closure. Replace them when publishing a module
that does not have that asset basis.

Install the example's gamedata separately from the module DLL:

```text
{CS2}/game/sharp/gamedata/modsharp-ag2-npc-example.games.jsonc
```

## ModSharp Gamedata And Factory

ModSharp loads the file through:

```csharp
gameData.Register("modsharp-ag2-npc-example.games.jsonc");
gameData.GetAddress("Ag2NpcExample::Parameters::GetType", out var address);
```

The `Addresses` keys are private registry aliases. They are deliberately
readable and collision-resistant, but they are not recovered Valve C++ names.
Renaming one is safe only when the C# lookup changes with it.

ModSharp resolves each signature with strict matching: zero matches and more
than one match both fail registration. The shared setter prologue is therefore
not usable directly because it matches multiple functions.

The example instead signs a type-specific instruction sequence inside each
setter. On the observed 2026-08-31 Linux binary, that sequence begins 303
decimal bytes after the function entry. ModSharp's post-resolution operation:

```json
"factory": "-303"
```

subtracts that distance from the signature match and returns the callable
function entry. `factory` is an address-transformation pipeline, not an object
factory. ModSharp also supports relative resolution and dereference operations,
but this example needs only subtraction.

Because an update could move the internal sequence while preserving some
bytes, the resolver additionally calls `GetFunctionRange` and requires the
factory result to equal the function start. It also requires all four resolved
addresses to be distinct.

The gamedata intentionally contains no RVA, module hash, ELF Build ID, Steam
Build ID, or multi-profile selector. This keeps it native to ModSharp and easy
to maintain. The tradeoff is explicit: it proves strict uniqueness on the
loaded module, not cryptographic identity with an earlier build. Revalidate
after every CS2 update.

## Runtime Lifecycle And Safety

The example follows this activation ladder:

1. Register gamedata during module initialization.
2. Read all four addresses and reject zero, aliases, or non-function entries.
3. Resolve `MakeGlobalSymbol` by its exported `tier0` name.
4. Spawn the model entity exactly once through ModSharp.
5. Remain on the server game thread and revalidate entity lifetime.
6. Probe graph-proven Bool, Float, and ID parameters with the type getter.
7. Enable writes only when all three returned types match.
8. Unregister gamedata during shutdown.

Before every getter or setter call, validate game-thread ownership, managed
wrapper validity, deletion state, native entity pointer, parameter symbol, and
runtime parameter type. A managed `try/catch` is not a native crash boundary.

## Adapt Another Framework

Do not copy ModSharp class names into another library. Map these operations to
the exact framework version instead:

| Required operation | ModSharp example | Other framework requirement |
| --- | --- | --- |
| Load signatures | `IGameData.Register` | documented gamedata/module scanner |
| Require uniqueness | ModSharp strict address resolution | explicit zero-or-one check |
| Transform inner match | gamedata `factory` | supported offset transform or verified function-start signature |
| Validate function entry | `ILibraryModule.GetFunctionRange` | executable/function-boundary equivalent |
| Spawn body | `SpawnEntitySync<IBaseAnimGraph>` | one create/precache/dispatch owner |
| Schedule writes | game-frame hook | verified server game-thread dispatcher |
| Validate entity | ModSharp entity wrapper and native pointer | full handle/serial plus lifetime guard |

If the framework cannot transform an inner-function signature, either recover
a unique function-entry pattern or perform a bounded, validated adjustment in
code. Never call the inner match itself.

## Recover After A CS2 Update

Work offline against a copied `libserver.so` from the exact target build. Do
not probe production entity pointers while recovering signatures.

1. Disassemble the four previously identified functions and confirm their
   controller lookup, parameter type check, and typed store behavior.
2. Rebuild each signature using invariant opcodes and wildcard only branch,
   call, or relocation displacements.
3. Require exactly one match for the getter and every typed setter tail.
4. Recalculate the distance from each setter match to its function entry; do
   not assume `303` survived the update.
5. Update the gamedata and record the observation date and resolved relative
   addresses in a validation note, not as runtime RVAs.
6. Test a deliberately invalid signature and require clean module degradation.
7. On an isolated non-player server, probe one graph-proven Bool, Float, and ID
   before permitting a harmless write of each type.
8. Confirm a remote clean client observes the expected animation and that map
   teardown/hot reload do not retain stale wrappers.

Use semantic strings and xrefs only as discovery anchors. Classification still
comes from the function's controller path, type comparison, and typed store.

## Failure Policy

Disable native animation writes when:

- gamedata is missing or registration fails;
- any signature has zero or multiple matches;
- a factory result is not a function entry;
- resolved addresses alias one another;
- `MakeGlobalSymbol` is unavailable;
- execution is not on the server game thread;
- entity lifetime or native pointer cannot be proven;
- the getter disagrees with the decompiled graph contract;
- a caller requests an unsupported parameter type.

Keep gameplay running with a static or separately verified named-sequence
fallback where possible. Expose one actionable health status and never fall
back to an old RVA, scan order, guessed pointer, or direct graph-memory write.
