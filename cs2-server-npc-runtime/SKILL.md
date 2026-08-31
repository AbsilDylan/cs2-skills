---
name: cs2-server-npc-runtime
description: "Design, audit, and debug server-authoritative CS2 NPC gameplay: lifecycle, AI, navigation, collision movement, combat, scheduling, hot reload, and validation. Excludes asset authoring."
---

# CS2 Server NPC Runtime

Build or review the gameplay runtime for a Counter-Strike 2 server-controlled NPC, independently of whether its presentation uses AnimGraph2, a verified named-sequence input, or no animation yet.

Use this skill for entity ownership, perception, behavior planning, navigation, collision movement, attacks, damage, death, cleanup, performance, and update resilience. Combine it with `cs2-ag2-npc-runtime` only when an existing model's AnimGraph2 controller must be inspected or driven. Use `cs2-player-model-porting` for character geometry/rigging and `cs2-animgraph2-authoring` for weapon or item graph authoring.

This portable contract distills reusable lifecycle/navigation mechanisms and
engine/framework safety invariants. It is not bundled runtime proof: every new
integration begins `unverified` and needs its own reproducible tests plus a
current-build canary.

The bundled C# file is a compilable design scaffold, not an operational ModSharp/CS2 plugin. It deliberately leaves framework entity creation, trace layers/groups, NAV adapters, resource paths, and native calls to the exact version-specific ports.

## Non-Negotiable Rules

1. Keep health, targeting, movement intent, action timing, damage, and death server-authoritative. Animation is a projection of gameplay state.
2. Separate immutable archetype/profile data from per-instance mutable state.
3. Identify an entity by its full handle or index plus serial and a managed world generation. An entity index or cached wrapper alone is not identity.
4. Make spawning transactional. Dispatch exactly once according to the framework contract; if any later setup step fails, clean up the partially created entity and every owned child/effect.
5. Keep engine wrappers and traces on the game thread. Workers receive immutable value snapshots only, and completed work is applied behind world-, entity-, and request-generation guards.
6. Treat world deactivation as a native-safety barrier: cancel managed work and forget wrappers without dereferencing, killing, restoring, or stopping them.
7. Model attacks as `Windup -> Active -> Recovery`, with entry tokens and absolute deadlines. Revalidate target, range, faction, line of sight, and ownership at the impact point.
8. Surface `NoNav`, `NoPath`, `Blocked`, `Stuck`, and `UnsupportedTraversal` to behavior. Keep pathfinding and motor outcomes distinct, then normalize them into behavior facts without erasing the source. Do not silently convert path failure into straight-line pursuit or teleport rescue.
9. Use one collision hull contract for NAV eligibility, traces, local steering, and arrival. Publish at most one authoritative transform per movement tick.
10. Use bounded work queues, cadence separation, per-agent jitter, LOD, and metrics. Never let a spawn/config value create unbounded entity, path, trace, or callback work.
11. Make cleanup idempotent and explicit for bodies, children, timers, sounds, particles, pending paths, planner actions, and extension callbacks. Bound retries and retain an actionable failed state on exhaustion.
12. Isolate extension and event callbacks. One sensor, modifier, or listener exception must not abort the host frame or accidentally let native damage through.
13. Never retain raw native graph/node pointers across frames or write guessed offsets. Resolve build-scoped signatures uniquely and fail closed.
14. `AcceptInput` is generic entity-I/O dispatch, not AG2 control. A verified animation input with an exact baked sequence label is only a separate presentation fallback. Route real AG2 work to `cs2-ag2-npc-runtime`.
15. Do not redistribute extracted Valve or third-party monster models in a public example. Use a user-owned/permitted asset, and keep native CS2 models only as local positive controls.

## Choose The Work Branch

| Need or symptom | Primary reference |
|---|---|
| Design the host, entity identity, state ownership, scheduling, reload, or teardown | [architecture-lifecycle-and-scheduling.md](references/architecture-lifecycle-and-scheduling.md) |
| Select a NAV source, find routes, implement a collision motor, or diagnose stuck/fall/step behavior | [navigation-and-locomotion.md](references/navigation-and-locomotion.md) |
| Implement perception, attacks, damage, death, or animation projection | [perception-combat-and-presentation.md](references/perception-combat-and-presentation.md) |
| Audit another NPC repository or plan layered validation | [review-and-validation.md](references/review-and-validation.md) |
| Need a small framework-neutral C# shape to adapt | [minimal-runtime-blueprint.md](references/minimal-runtime-blueprint.md) and [ServerNpcRuntimeSkeleton.cs](examples/ServerNpcRuntimeSkeleton.cs) |
| Existing model is visible but AG2 is static or its parameters cannot be set | Use `cs2-ag2-npc-runtime` |

## End-To-End Workflow

### 1. Freeze The Runtime Contract

Record the CS2 build, server platform, framework version/commit, map and NAV provenance, tick rate, entity class, model rights, collision hull, teams/factions, health rules, capabilities, animation strategy, resource closure, and expected NPC count.

Label conclusions as `static-observed`, `runtime-proven`, `inferred`, or `unverified`. Do not turn reverse-engineering evidence into a permanent API claim.

### 2. Define Ownership Before Spawning

Specify:

- one immutable profile per archetype;
- one state object per spawned instance;
- a full entity identity plus world generation;
- owners for timers, path requests, particles, sounds, and child entities;
- active cleanup versus world-teardown forget behavior;
- maximum counts and per-frame budgets.

Then implement a spawn transaction with one dispatch owner and a rollback path for every step.

### 3. Separate Decision, Route, Motor, Combat, And Presentation

Use an explicit pipeline:

```text
game-thread observations
  -> perception/threat snapshot
  -> behavior decision and action state
  -> path request/result
  -> collision-checked motor
  -> combat impact transaction
  -> animation/effects projection
```

Do not let an animation clip decide whether damage occurred, let a pathfinder move an entity, or let a movement fallback hide a planner failure.

### 4. Implement State And Failure Results

Include lifecycle states such as:

```text
Materializing -> Spawning -> Idle <-> Moving
Moving/Idle -> AttackWindup -> AttackActive -> AttackRecovery
Any live state -> Falling or Stunned
Any live state -> Dead -> Removed
```

Return typed route/motor/action results instead of booleans. Behavior must be able to react to an invalid target, missing NAV, unreachable goal, obstruction, unsupported ledge, expired async result, lost controller, or failed presentation without conflating them.

### 5. Schedule Bounded Work

- Observe and move on the game thread.
- Stagger perception, replanning, and route refreshes.
- Run immutable graph search on bounded workers when it is material.
- Cap pending requests and coalesce superseded work per NPC.
- Apply results only when world generation, entity identity, request serial, age, and target drift still pass.
- Use measured seconds or the actual tick interval; do not bake `64` into gameplay deadlines.

### 6. Project Presentation

Choose one adapter:

- typed AG2 parameters from a discovered graph contract;
- verified named-sequence input fallback;
- static body plus effects during early gameplay tests.

The adapter may fail without corrupting gameplay. Protect spawn, attack, reaction, and death one-shots from an idle/locomotion writer. Route AG2 controller materialization, signatures, parameter types, and Workshop closure to `cs2-ag2-npc-runtime`.

### 7. Validate In Layers

1. Pure state-machine, path-policy, damage, and cleanup tests.
2. Spawn/rollback/unload tests with fake ports.
3. Isolated server test for entity, collision, traces, and native adapters.
4. Two-NPC and crowd tests with route and trace budgets.
5. Round reset, map change, hot reload, disconnect/slot reuse, and entity-index reuse tests.
6. Clean Workshop client presentation test when the NPC publishes custom client resources; otherwise record this layer as `not-applicable`.
7. Current-build canary where invalid signatures disable only the affected native feature.

Read [review-and-validation.md](references/review-and-validation.md) for the audit matrix and evidence gates.

## Expected Deliverables

- runtime/profile/state contract and explicit ownership table;
- lifecycle and action state diagrams;
- NAV/hull provenance and route/motor capability matrix;
- bounded scheduling and performance budget;
- behavior-to-combat and behavior-to-presentation mappings;
- spawn rollback, active cleanup, and world-forget procedures;
- build/version/signature receipt for every native bridge;
- automated smoke tests plus an isolated-server and clean-client report;
- known limitations, especially unsupported traversal and presentation fallbacks.

## Reference Map

- [architecture-lifecycle-and-scheduling.md](references/architecture-lifecycle-and-scheduling.md): layer boundaries, entity identity, spawn transactions, generations, scheduling, extensions, and teardown.
- [navigation-and-locomotion.md](references/navigation-and-locomotion.md): NAV provenance, path result semantics, hull-compatible movement, steps, falls, sliding, and worker application.
- [perception-combat-and-presentation.md](references/perception-combat-and-presentation.md): atomic perception, action FSMs, safe damage, death, AG2/sequence projection, and bones.
- [review-and-validation.md](references/review-and-validation.md): severity-led review checklist, runtime gates, failure matrix, and production readiness.
- [minimal-runtime-blueprint.md](references/minimal-runtime-blueprint.md): how to adapt the bundled framework-neutral code without inventing framework APIs.
