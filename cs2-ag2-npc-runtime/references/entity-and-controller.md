# Entity, CModel, And Controller Materialization

## Contents

- [Runtime Pipeline](#runtime-pipeline)
- [Choose The Animated Entity](#choose-the-animated-entity)
- [Understand The CModel Lookup](#understand-the-cmodel-lookup)
- [Use The Materialization Ladder](#use-the-materialization-ladder)
- [Build Safe Diagnostics](#build-safe-diagnostics)
- [Compare A Positive Control](#compare-a-positive-control)
- [Avoid Crash-Prone Probes](#avoid-crash-prone-probes)

## Runtime Pipeline

Use this model of the server path:

```text
compiled VMDL references an AG2 graph/identifier
    -> ResourceSystem loads the model resource
    -> runtime CModel publishes an AG2 identifier-to-resource entry
    -> model entity creates CBaseAnimGraphController
    -> controller looks up its graph identifier in CModel
    -> primary graph ResourceId_t is selected
    -> graph definition is resolved
    -> CNmGraphInstance is created
    -> typed parameters can affect evaluation
```

Each arrow can fail independently. A visible model proves only the earlier model/material path. A `Resident` graph proves only that the ResourceSystem can resolve a path; it does not prove the CModel publishes that graph to the controller.

## Choose The Animated Entity

`prop_dynamic_override` is a practical server-networked body for many custom NPCs. It is not inherently incompatible with AG2. A native model such as a chicken can materialize AG2 on the same class.

Create the body with the framework's normal entity manager and set the equivalent keyvalues before or during spawn as required by that API:

```text
classname=prop_dynamic_override
model=<compiled model resource>
use_animgraph=1
AnimateOnServer=1
```

Do not add the legacy Source 1 `animate_every_frame` key: current CS2 FGD
metadata does not define it, so treating it as a required Source 2 control can
hide the real controller/materialization failure.

Then set collision, solidity, scale, origin, angles, health, team, ownership, and networking through supported entity/schema APIs.

Do not use `info_target` as the visual animated body. It can be a helper for destinations, camera targets, effects, or aim points, but it does not replace a model entity with a skeleton instance and animation controller.

Do not conclude that an entity class is wrong merely because a custom model is static. Prove the same class works with a known native AG2 model first.

## Understand The CModel Lookup

The controller does not need to parse the raw VMDL's `m_animGraph2Refs` on every update. It reads its graph identifier and asks the runtime `CModel` for the corresponding graph resource ID.

Conceptually:

```text
key = controller.m_sAnimGraph2Identifier
primary = CModel.LookupAnimGraph2(key)
if primary == 0:
    stop before graph definition creation
```

In one investigated Linux build, the relevant CModel table appeared as a count near `CModel + 0x418`, an entries pointer near `CModel + 0x420`, and approximately 16-byte key/value records. Treat those offsets as **historical reverse-engineering evidence**, not an API. Reconfirm the live build before using them in a diagnostic, and never use them for production writes.

Recover the exact CModel pointer through the model entity's normal body/skeleton/model-state path when the framework exposes it. If reverse engineering is necessary, prove every hop against a native positive control and executable/schema evidence:

```text
entity
  -> BodyComponentSkeletonInstance
  -> SkeletonInstance / CModelState
  -> model handle or runtime CModel
  -> AG2 lookup table
```

Do not scan arbitrary pointer candidates until one looks nonzero. That produces persuasive-looking garbage and is unsafe in a live server process.

Classify a table probe as one of:

- `table-empty`
- `table-unreadable`
- `no-key-match`
- `key-match-value-zero`
- `key-match-value-nonzero`

Log the controller key and selected primary ID beside that classification.

## Use The Materialization Ladder

Capture these three values after model assignment and after a short deferred interval:

| Primary | Definition | Instance | Interpretation |
|---:|---:|---:|---|
| 0 | 0 | 0 | Failure before graph selection; investigate CModel entry, model metadata, paths, provenance, and packaging |
| nonzero | 0 | 0 | Graph resource selected but definition failed to resolve or load |
| nonzero | nonzero | 0 | Definition exists; graph instance creation failed |
| nonzero | nonzero | nonzero | Materialization succeeded; move to parameter and behavior diagnostics |

Do not investigate parameter names, graph evaluation cadence, or client replication while all three are zero. Those stages have not been reached.

Do not report success from controller flags alone. Values such as `useAnimGraph`, `graphUpdate`, `updateScheduled`, or `animatedEveryTick` can be true while the primary graph is still zero.

## Build Safe Diagnostics

Prefer a server-console diagnostic with bounded, defensive reads. First run deep diagnostics on an isolated non-player staging server with a watchdog and an independently reachable restart path. Log:

```text
build identifier and module hash
entity index, class, schema class, pointer
model resource path
body/skeleton/controller pointers obtained through verified accessors
controller graph identifier key
primary graph ResourceId_t
definition handle/pointer
graph instance pointer
CModel table classification, when independently verified
```

Apply these safety rules:

1. Marshal the command onto the server game thread before touching entity-native state.
2. Resolve the entity through framework APIs and capture its index plus generation/serial; never retain a raw pointer as identity.
3. Revalidate entity identity, generation/serial, lifetime, body, controller, and graph instance immediately before each native hop.
4. Read one verified field at a time.
5. Check pointer range/alignment/readability before the next hop.
6. Bound counts before iterating a table.
7. Never recurse through unknown handles.
8. Run deep probes from an explicit server-console command, not ordinary chat or per-tick code.
9. Rate-limit probes and keep a watchdog/restart path outside the game process; managed exceptions do not reliably contain native access violations.
10. Remove or disable reverse-engineering probes after the contract is proven.

Use lifecycle snapshots such as:

```text
after-create
after-model-set
after-spawn
after-0.25s
after-1.00s
```

This separates a delayed initialization from a permanently missing graph.

## Compare A Positive Control

Use the same creation path for both models:

| Variable | Positive control | Custom model |
|---|---|---|
| Entity class | same | same |
| Keyvalues | same | same |
| Spawn timing | same | same |
| CModel AG2 table | measure | measure |
| Primary/definition/instance | measure | measure |

If the positive control materializes AG2, the general entity path is valid. Focus on model runtime metadata and resource closure.

## Avoid Crash-Prone Probes

Past failures in this class of work came from deep unmanaged pointer walking, especially formatting internal definition handles and resolver state from chat commands. Avoid:

- dereferencing an internal graph-definition object without a verified layout;
- interpreting random adjacent controller offsets as alternate controllers;
- exposing heavy lifecycle probes through commonly used chat commands;
- running deep diagnostics for every NPC every tick;
- preserving obsolete offsets after a game update;
- writing directly into CModel/controller tables.
- queuing raw entity/controller pointers into timers or worker jobs;
- assuming `try/catch` can recover from an invalid native dereference.

The production runtime should only retain the smallest validated operations it needs: normal entity APIs, bounded status data, signature-resolved game-thread engine calls, generation-aware lifetime checks, and a fail-closed health check.
