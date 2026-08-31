---
name: cs2-ag2-npc-runtime
description: "Diagnose and drive CS2 AnimGraph2 NPC presentation: graph contracts, controllers, typed parameters, Linux signatures, and Workshop delivery. Excludes gameplay AI/nav/combat and asset authoring."
---

# CS2 AnimGraph2 NPC Runtime

Operate a server-authoritative NPC around an existing AnimGraph2 model, discover the graph's real control contract, drive its supported parameters, and validate it on a clean Counter-Strike 2 client.

Use this skill for NPCs represented by `prop_dynamic_override` or another model entity with a `CBaseAnimGraphController`. It owns animation presentation, not general NPC gameplay. Use `cs2-server-npc-runtime` for entity ownership, targeting, AI, navigation, collision movement, combat, scaling, and cleanup; use `cs2-player-model-porting` for character asset porting; and use `cs2-animgraph2-authoring` for first-person/third-person weapon or item graph authoring. Combine skills only when the request genuinely spans their boundaries.

## Non-Negotiable Rules

1. Inspect the compiled graph before inventing parameter names or animation states.
2. Separate resource visibility from runtime materialization. `Resident` does not prove that a graph definition or graph instance exists.
3. Diagnose `primary`, `definition`, and `instance` in that order.
4. Write parameters through engine functions with the exact discovered type. Never write graph, node, controller, or CModel memory directly, including in staging.
5. Keep behavior state server-authoritative and make animation a deterministic projection of that state.
6. Resolve signatures per build and fail closed after an update. Never patch `libserver.so`.
7. Validate from the downloaded Workshop addon on a clean client. Loose files are only an explicit A/B test.
8. Do not redistribute extracted Valve or third-party compiled assets. Keep decompilation outputs local.
9. Run every native graph getter/setter on the server game thread. Never call entity-native functions from timers, networking callbacks, or worker threads directly.
10. Validate native probes first on an isolated, non-player staging server with a watchdog and an independently reachable restart path.
11. Bind deferred work to an entity identity plus generation/serial. Revalidate lifetime immediately before every native call.
12. Treat addon configuration edits as explicit operations: obtain approval, back up and hash the original, show the diff, and provide a tested restoration path.
13. Never breadth-first/depth-first scan arbitrary process pointers or infer parameters from allocation order, addresses, vtable proximity, or readable pages.
14. `AcceptInput` is generic entity-I/O dispatch, not an animation backend. A verified animation input such as `SetAnimation` with an exact model-published sequence label is a separate fallback; it does not materialize or drive missing AG2 parameters.
15. Reacquire named schema fields, controller, definition, and graph instance at use time. Never retain a raw graph/node pointer across frames or controller rematerialization.
16. Keep reverse-engineering commands outside the distributed production plugin and disabled by default.
17. Do not publish extracted Valve or third-party models as examples. Use placeholders or user-owned/permitted assets and keep native assets as local controls only.

## Choose The Investigation Branch

Classify the current failure before changing code:

| Observation | Meaning | Next reference |
|---|---|---|
| Need parameter names, types, transitions, clips, or event timing | The graph contract is unknown | [graph-inspection.md](references/graph-inspection.md) |
| Model is visible but static; `primary=0`, `definition=0`, `instance=0` | Failure is before AG2 materialization | [entity-and-controller.md](references/entity-and-controller.md) |
| `primary!=0`, `definition=0` | Runtime chose a graph resource but failed to resolve its definition | [packaging-and-validation.md](references/packaging-and-validation.md) |
| `definition!=0`, `instance=0` | Definition exists but no `CNmGraphInstance` was created | [entity-and-controller.md](references/entity-and-controller.md) |
| Instance exists but states are wrong or static | Parameter type/value/state-machine issue | [behavior-and-animation.md](references/behavior-and-animation.md) |
| Managed API cannot set AG2 parameters on Linux | A small native call bridge may be required | [linux-parameter-bridge.md](references/linux-parameter-bridge.md) |
| Works locally but fails for a clean Workshop client | Missing published root or incomplete resource closure | [packaging-and-validation.md](references/packaging-and-validation.md) |
| Need targeting, planning, navmesh, collision movement, combat, damage, lifecycle, or crowd scaling | This is general NPC gameplay | Use `cs2-server-npc-runtime` |

## End-To-End Workflow

### 1. Establish provenance and a control

- Record the source game's build, CS2 client/server build, platform, model path, graph path, skeleton path, clips, particles, materials, and sounds.
- Pick one native CS2 model that already materializes AG2 through the same entity class. A chicken is a useful control when available.
- Preserve an evidence label for every conclusion: `static-observed`, `runtime-proven`, `inferred`, or `unverified`.

### 2. Inspect the compiled graph

- Decompile the `.vnmgraph_c` with a current Source 2 resource viewer.
- Enumerate control parameter names and derive each Bool, Float, ID, Vector, or Target type from its control-node definition.
- Follow state-machine conditions, comparisons, ID values, clip data slots, loop flags, graph events, referenced graphs, and skeleton dependencies.
- Produce a graph contract table before implementing AI.
- Use `scripts/summarize_vnmgraph.py` as a first-pass report generator, then verify important transitions by hand.

Read [graph-inspection.md](references/graph-inspection.md) for the exact fields and an explicitly unverified table-shape example.

### 3. Build and package the complete resource closure

- Prefer recompilation from editable source when possible.
- Include the model, graph, skeleton, every reachable clip, secondary skeleton, material, texture, particle child, soundevent manifest, and sound dependency.
- Preserve valid normalized resource paths and references. Treat path relocation as a compiled-resource rewrite, not a file move.
- Preserve the model and graph's intended resource paths. If they use `animation/...`, inspect the addon's search paths. Do not edit `gameinfo.gi` without explicit approval, a timestamped backup plus hash, a reviewed diff, and a verified restore procedure.
- Inspect the downloaded VPK, not only the authoring tree.

### 4. Spawn a real model entity

Use `prop_dynamic_override` when it satisfies collision and networking
requirements. Follow [entity-and-controller.md](references/entity-and-controller.md)
for the exact model, graph identifier, server-animation, and spawn configuration.
Set scale, collision, transform, team, health, and ownership through normal
entity APIs. Do not use `info_target` as the animated body; it can remain a
helper target.

### 5. Prove controller materialization

After creation and again after a short deferred interval, log:

```text
entity class and pointer
model path and graph identifier key
named-schema body/controller path
primary graph resource ID
graph definition handle/pointer
graph instance pointer
```

Use defensive accessors and stop at the first invalid layer. Never dereference a guessed definition internals chain from a chat command. Run deep probes first on isolated staging, from a server-console-only command, while a watchdog and out-of-process restart path are available.

### 6. Add the typed parameter bridge only if needed

- Reuse a framework-provided typed AnimGraph setter when one exists and is verified for AG2.
- Otherwise resolve the engine type getter plus Bool, Float, and ID setters by
  signatures, but enable them only when the exact local binary profile and a
  runtime validation receipt match. This repository deliberately ships no
  callable signature/RVA profile as proof for the current server.
- Detect Vector and Target controls in the graph contract and runtime type getter, but report them as `diagnostic-only` until a setter and calling convention are independently proven for the exact build. Never coerce them through the three scalar setters.
- Convert parameter names and ID values through the engine symbol/string-token facility expected by those functions.
- Cache resolved functions only after structural and runtime validation.
- Disable native animation writes when any signature is missing or ambiguous.
- Marshal all calls onto the game thread and revalidate entity identity, generation/serial, native pointer, controller, and graph instance at call time.

Read [linux-parameter-bridge.md](references/linux-parameter-bridge.md) before implementing unmanaged calls.

### 7. Map behavior to graph parameters

Keep gameplay states explicit, for example:

```text
Spawning -> Idle -> Moving -> Windup -> Attacking -> Recovery -> Dead
```

On each animation update:

- derive local forward and strafe speed from world velocity;
- set Bool/Float/ID air, health, speed, and time-scale controls at their required cadence;
- set Vector/Target controls only through a separately verified framework/native API; otherwise leave them unsupported and expose that limitation in diagnostics;
- set ID selectors only to values proven in the graph;
- pulse action booleans on state entry, then clear them;
- keep one-shot duration and recovery in server state rather than restarting the action every tick.

Read [behavior-and-animation.md](references/behavior-and-animation.md) for formulas, transition rules, and lifecycle design.

### 8. Validate in layers

1. **Static resource:** model, graph, skeleton, and clips resolve without errors.
2. **Runtime model:** the model publishes a matching AG2 entry.
3. **Controller:** `primary`, `definition`, and `instance` become nonzero.
4. **Parameters:** type getter reports expected Bool/Float/ID/Vector/Target types; only setters proven for that exact type and build are exercised.
5. **Animation:** idle, locomotion, turns, attacks, reactions, and death are visually correct.
6. **Networking:** remote clean clients see the same state.
7. **Workshop:** the downloaded addon alone reproduces the result.
8. **Update resilience:** an intentionally invalid signature disables the bridge without crashing.

## Expected Deliverables

Produce these artifacts for a complete NPC integration:

- a provenance and dependency manifest;
- a graph contract table with parameter names, types, valid IDs, semantics, and update cadence;
- a behavior-to-parameter mapping;
- a resource closure and Workshop verification report;
- a runtime diagnostic showing the `primary -> definition -> instance` ladder;
- build-scoped native signature metadata with recovery notes when a bridge is necessary;
- a clean-client validation log and known limitations.

## Reference Map

- [graph-inspection.md](references/graph-inspection.md): decompile and read VNMGraph parameters, conditions, clips, and events; its historical parameter table is an unverified shape example only.
- [entity-and-controller.md](references/entity-and-controller.md): entity choice, CModel lookup, controller materialization, and safe diagnostics.
- [behavior-and-animation.md](references/behavior-and-animation.md): convert AI state, velocity, targeting, and one-shots into graph inputs.
- [linux-parameter-bridge.md](references/linux-parameter-bridge.md): local build-profile schema, partial call contract, signature recovery, validation, and fail-closed update policy.
- [packaging-and-validation.md](references/packaging-and-validation.md): compile closure, addon roots, Workshop delivery, clean-client tests, and failure matrix.
