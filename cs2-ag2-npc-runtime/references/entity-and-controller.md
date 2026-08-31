# Entity, CModel, And Controller Materialization

## Contents

- [Runtime Pipeline](#runtime-pipeline)
- [Choose The Animated Entity](#choose-the-animated-entity)
- [Resolve The Named Schema Ladder](#resolve-the-named-schema-ladder)
- [Understand The CModel Lookup](#understand-the-cmodel-lookup)
- [Use The Materialization Ladder](#use-the-materialization-ladder)
- [Build Safe Diagnostics](#build-safe-diagnostics)
- [Compare A Positive Control](#compare-a-positive-control)
- [Use A Minimal Framework-Agnostic Shape](#use-a-minimal-framework-agnostic-shape)
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
animgraph2_identifier=<exact ModelDoc-authored identifier, when required>
```

Set graph-related keyvalues before spawn. Omit `animgraph2_identifier` only
when the model contract and a positive control prove that its empty/default
identifier resolves correctly; never invent `worldmodel` or another key. Read
back the controller's actual identifier during the materialization diagnostic.

Dispatch exactly once. In particular, verify whether the framework's
synchronous spawn helper already dispatches before calling a separate
`DispatchSpawn` function.

Do not add the legacy Source 1 `animate_every_frame` key: current CS2 FGD
metadata does not define it, so treating it as a required Source 2 control can
hide the real controller/materialization failure.

Then set collision, solidity, scale, origin, angles, health, team, ownership, and networking through supported entity/schema APIs.

Do not use `info_target` as the visual animated body. It can be a helper for destinations, camera targets, effects, or aim points, but it does not replace a model entity with a skeleton instance and animation controller.

Do not conclude that an entity class is wrong merely because a custom model is static. Prove the same class works with a known native AG2 model first.

## Resolve The Named Schema Ladder

Resolve every materialization hop from the exact current-build schema first.
Record the declaring class, field name, field type, schema/build provenance,
and observed value. Current evidence exposes two alternative controller access
paths; do not splice them into one chain:

```text
model-body path:
CBaseEntity::m_CBodyComponent
  -> CBodyComponentBaseAnimGraph::m_animationController
     (inline CBaseAnimGraphController)

CBaseAnimGraph entity path:
CBaseAnimGraph::m_pMainGraphController
  -> CAnimGraphControllerPtr::m_pController
     (CAnimGraphControllerBase*; require a runtime-proven dynamic type/downcast)

either verified controller ->
  CBaseAnimGraphController::m_sAnimGraph2Identifier
  -> CBaseAnimGraphController::m_primaryGraphId
  -> CBaseAnimGraphController::m_hGraphDefinitionAG2
  -> CBaseAnimGraphController::m_pGraphInstanceAG2
```

Class names and ownership can evolve. Resolve the exact owner plus field name
and verify the runtime type instead of copying numeric offsets from this or any
other build. If a required named field is unavailable, report
`schema-unavailable` and stop. Never substitute a historical offset or a
pointer scan.

## Understand The CModel Lookup

The controller does not need to parse the raw VMDL's `m_animGraph2Refs` on every update. It reads its graph identifier and asks the runtime `CModel` for the corresponding graph resource ID.

Conceptually:

```text
key = controller.m_sAnimGraph2Identifier
primary = CModel.LookupAnimGraph2(key)
if primary == 0:
    stop before graph definition creation
```

Recover the exact CModel pointer through the model entity's normal body/skeleton/model-state path when the framework exposes it. If reverse engineering is necessary, prove every hop against a native positive control and executable/schema evidence:

```text
entity
  -> BodyComponentSkeletonInstance
  -> SkeletonInstance / CModelState
  -> model handle or runtime CModel
  -> AG2 lookup table
```

Do not scan arbitrary pointer candidates until one looks nonzero. Never perform
a breadth-first or depth-first scan from a controller, definition, graph
instance, or model. Readable memory and a plausible vtable do not establish
ownership, type, lifetime, or semantics.

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
entity full identity, class, and schema class
model resource path
named-schema body/controller chain obtained through verified accessors
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
11. Never write graph-instance, node, controller, or CModel memory. A value
    reading back proves only that memory changed, not that a parameter, state,
    clip, or pose was selected.

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

## Use A Minimal Framework-Agnostic Shape

Keep public examples schematic and require a user-owned presentation contract:

```csharp
var spec = LoadPresentationContract("<user-owned config>");
var body = CreateModelEntity("prop_dynamic_override");

SetModel(body, spec.ModelPath);
SetKeyValue(body, "use_animgraph", spec.Mode == Ag2 ? "1" : "0");
SetKeyValue(body, "AnimateOnServer", "1");

if (spec.Mode == Ag2 && spec.Identifier is not null)
    SetKeyValue(body, "animgraph2_identifier", spec.Identifier);

SpawnExactlyOnce(body);
var identity = CaptureFullEntityIdentity(body);

DeferOnGameThread(identity, TimeSpan.FromMilliseconds(250), current =>
{
    var ladder = ReadNamedSchemaMaterialization(current);
    presentation = SelectValidatedAg2AseqOrDisabled(spec, ladder);
});
```

Then keep one adapter active:

```text
AG2      -> typed writes from the authoritative gameplay snapshot
sequence -> verified animation input with exact baked label, only on legal state entry/change
Disabled -> no native-memory fallback
```

These names describe responsibilities, not a guaranteed ModSharp API. Verify
the exact framework version before implementing creation, keyvalue, dispatch,
and deferred game-thread calls. Do not attach a real model path, extracted
asset, RVA, or signature profile to this public example.

## Avoid Crash-Prone Probes

Past failures in this class of work came from deep unmanaged pointer walking, especially formatting internal definition handles and resolver state from chat commands. Avoid:

- dereferencing an internal graph-definition object without a verified layout;
- interpreting random adjacent controller offsets as alternate controllers;
- exposing heavy lifecycle probes through commonly used chat commands;
- running deep diagnostics for every NPC every tick;
- preserving obsolete offsets after a game update;
- breadth-first/depth-first walking of readable process memory;
- deriving parameter names/types/indexes from address or allocation order;
- writing directly into graph nodes, instances, controllers, or CModel tables;
- queuing raw entity/controller pointers into timers or worker jobs;
- assuming `try/catch` can recover from an invalid native dereference.

The production runtime should only retain the smallest validated operations it needs: normal entity APIs, bounded status data, signature-resolved game-thread engine calls, generation-aware lifetime checks, and a fail-closed health check.

Every conclusion must include its evidence label plus build, platform, entity
class, model/resource hash, and lifecycle snapshot. A memory read-back is not
animation proof. A visual or bone delta proves a pose changed, not which graph
state or clip produced it, unless independently correlated.
