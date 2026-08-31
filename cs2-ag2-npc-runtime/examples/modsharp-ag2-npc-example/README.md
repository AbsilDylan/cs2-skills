# ModSharp AnimGraph2 NPC Example

A small, framework-native ModSharp example that spawns a Deadlock Shambler or
Trooper, materializes its AnimGraph2 controller, drives typed graph parameters,
and moves it directly toward the nearest living CS2 player.

This repository is intentionally an animation and entity-lifecycle example.
It is not an AI, navigation, combat, or asset-distribution framework.

## What the example proves

- `SpawnEntitySync<IBaseAnimGraph>` uses the real ModSharp EKV API and performs
  create, precache, and `DispatchSpawn` exactly once.
- The model owns its graph. No speculative `animgraph2_identifier` key is used.
- `use_animgraph=1` and `animateonserver=1` request a server-updated graph.
- Linux native AG2 functions are resolved through ModSharp's `IGameData`
  registry. Every signature must have exactly one match.
- Setter signatures match a unique type-specific instruction sequence, then a
  ModSharp `factory` offset resolves the function entry; raw RVAs are not used.
- A materialized entity must expose the expected Bool, Float, and ID parameter
  types before the first write.
- Movement updates `in_air`, `forward_speed`, `move_speed`, `look_heading`, and
  `time_scale` through typed native setters.
- A named animation hint is sent only when idle/moving state changes. It helps
  graphs whose protected spawn one-shot otherwise remains visually latched;
  typed parameters remain the locomotion control plane.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/Ag2NpcExampleModule.cs` | ModSharp entry point, listener, command, lifecycle |
| `src/Npc/` | model catalogue and deliberately simple chase runtime |
| `src/Animation/Ag2ParameterWriter.cs` | guarded typed Bool/Float/ID calls |
| `src/Animation/Ag2NativeResolver.cs` | reads resolved addresses from ModSharp gamedata |
| `gamedata/modsharp-ag2-npc-example.games.jsonc` | four Linux AG2 signatures |

Only `Ag2NpcExampleModule` implements `IModSharpModule`.

## Commands

Use the client console command or its ModSharp chat trigger:

```text
!ag2npc shambler [1-8]
!ag2npc amber [1-8]
!ag2npc sapphire [1-8]
!ag2npc status
!ag2npc clear
```

The example limits the process to 24 active NPCs. It does not include an admin
permission check; add one before exposing the command on a public server.

## Required assets

The repository does **not** redistribute Valve or Deadlock assets. A legally
supplied addon or Workshop package must mount the complete dependency closure
on both the server and every client:

- selected `.vmdl_c` model;
- referenced `.vnmgraph_c` graph and subgraphs;
- `.vnmskel_c` skeletons;
- referenced `.vnmclip_c` clips;
- materials, textures, and any other ModelDoc dependencies.

The example model paths are:

```text
models/heroes_wip/necro/necro_shambler.vmdl
models/npc_units/troopers/amber_trooper_01/amber_trooper_01.vmdl
models/npc_units/troopers/sapphire_trooper_01/sapphire_trooper_01.vmdl
```

`PrecacheResource(model)` cannot repair an incomplete package. If a dependency
is absent, the model may be invisible, use a stock pose, or never materialize
the expected graph controller.

## Build and install

Requirements:

- .NET SDK 10.x;
- ModSharp `2.1.79`;
- Linux x64 CS2 dedicated server for the native AG2 bridge.

Build with the published SDK package:

```bash
dotnet publish -c Release
```

For local ModSharp source development, point the optional property at
`Sharp.Shared.csproj`:

```bash
dotnet build -c Release \
  -p:ModSharpProject=/path/to/ModSharp-public/Sharp.Shared/Sharp.Shared.csproj
```

Install the publish output so these paths match:

```text
{CS2}/game/sharp/modules/ModSharpAg2NpcExample/ModSharpAg2NpcExample.dll
{CS2}/game/sharp/modules/ModSharpAg2NpcExample/ModSharpAg2NpcExample.deps.json
{CS2}/game/sharp/gamedata/modsharp-ag2-npc-example.games.jsonc
```

Copy the published `gamedata/modsharp-ag2-npc-example.games.jsonc` file to the
global ModSharp `sharp/gamedata` directory shown above. Do not ship a private
copy of `Sharp.Shared.dll` beside the module.

## Native safety contract

`gamedata/modsharp-ag2-npc-example.games.jsonc` deliberately uses ModSharp's
native gamedata format. It contains only the four required Linux addresses:
the parameter type getter and the Bool, Float, and ID setters. There are no
build profiles, hashes, Build IDs, offsets tied to a module base, or custom
signature parser.

Names such as `Ag2NpcExample::Parameters::SetBool` are private, readable
gamedata aliases. They are not recovered or claimed Valve C++ symbol names.

The resolution ladder is:

1. register the file through `IGameData.Register`;
2. let ModSharp resolve each signature strictly: zero or multiple hits fail;
3. apply `factory: "-303"` to each type-specific setter tail to recover its
   function entry;
4. read the four resolved addresses through `IGameData.GetAddress`;
5. require ModSharp's function-range lookup to confirm that all four addresses
   are distinct function entries;
6. resolve the exported `MakeGlobalSymbol` function from `tier0`;
7. probe `in_air` (Bool), `time_scale` (Float), and `base_action` (ID) on a
   live materialized graph instance;
8. enable writes only after every gate passes.

After a CS2 update, revalidate all four patterns against the new Linux
`libserver.so`. If one no longer resolves uniquely, update that signature from
newly verified disassembly; do not add a fallback RVA or bypass ModSharp's
strict matching. The module still loads with spawning disabled when gamedata
registration fails, and `!ag2npc status` exposes the failure.

## Deliberate movement limitations

The chase motor is flat XY interpolation through `Teleport`. It has no NAV,
pathfinding, traces, step solver, gravity, avoidance, or collision response.
Consequently NPCs can pass through walls, cannot change floor, and may overlap.
That simplicity is the point of this example: it keeps presentation/AG2 work
separate from a real movement system.

For production, replace `DirectChaseNpcRuntime.UpdateChase` with a validated
NAV or steering motor while keeping the spawn and AG2 safety contracts.

## License

The example module source is MIT-licensed; see `LICENSE`. ModSharp remains
covered by its own license and module exception.
