# Architecture, Lifecycle, And Scheduling

## Contents

- [Keep Ports Narrow](#keep-ports-narrow)
- [Own Identity And State](#own-identity-and-state)
- [Spawn Transactionally](#spawn-transactionally)
- [Guard Deferred Work](#guard-deferred-work)
- [Schedule By Cost](#schedule-by-cost)
- [Make Extensions Composable](#make-extensions-composable)
- [Tear Down Safely](#tear-down-safely)

## Keep Ports Narrow

Keep the decision model independent of ModSharp or another host. Put engine work behind game-thread ports:

```text
entity/body port    create, validate, trace, move, remove
navigation port     project and route immutable values
combat port         validate and apply one impact transaction
presentation port   apply AG2/sequence/effect state
lifetime port       generation, cancellation, active cleanup, forget
```

The brain consumes typed observations and emits intent. It must not retain engine wrappers, call traces, or mutate entities.

## Own Identity And State

Use immutable `NpcProfile` data for archetype tuning and one mutable `NpcState` per entity. The state normally holds:

```text
full entity handle or index+serial
world generation and spawn serial
lifecycle/action state plus entered-at deadline
target identity and observation revision
desired and actual velocity
path request/result serial and waypoint cursor
health, cooldowns, damage/death latch
owned children, sounds, particles, timers
presentation revision and one-shot token
```

Never use an entity index, a managed wrapper, or a raw pointer as durable identity. Re-resolve the current wrapper and compare the full identity immediately before native access.

## Spawn Transactionally

Treat spawn as a transaction:

1. Validate profile, model permission/path, count limits, transform, and hull.
2. Create the entity and set required pre-spawn keyvalues.
3. Let exactly one owner dispatch it. Verify whether the framework's synchronous spawn helper already dispatched.
4. Capture its full identity and register ownership.
5. Configure collision, health, team, presentation, and children.
6. Publish it to AI/update loops only after every required step succeeds.
7. On failure, cancel requests and destroy every entity/effect created by the transaction.

Do not catch a post-spawn exception and merely return `null`; that leaks a live unowned entity.

## Guard Deferred Work

A delayed callback carries value data only:

```text
world generation
entity full identity
operation/request serial
target/session identity when relevant
absolute expiry
```

On completion, first test pure managed lifetime state, then marshal to the game thread, re-resolve wrappers, and revalidate every identity. Superseded work is discarded, not applied optimistically.

## Schedule By Cost

Suggested starting classes, to tune with metrics:

| Work | Typical cadence |
|---|---|
| identity/critical lifecycle | every server tick |
| collision motor | every tick or stable high rate |
| presentation locomotion | 15-30 Hz |
| nearby perception | 5-10 Hz |
| behavior replan | on dirty facts plus bounded fallback |
| route refresh | on target drift, obstruction, or a staggered deadline |
| distant/inactive NPC | explicit lower LOD |

Derive cadence from elapsed seconds or the actual tick interval. Add stable per-agent jitter so a cohort does not replan on the same frame. Bound paths, traces, candidate targets, callbacks, logs, and spawned count. Expose queue depth, dropped/superseded requests, route latency, traces per tick, and per-system time.

Long-running planner operators need an executing condition or an explicit `Success/Failure` exit when their gate clears. Do not assume a planner automatically rechecks a parent condition while an operator returns `Continue`. Cancel the current operator on death, despawn, reload, or domain replacement.

## Make Extensions Composable

- Give each extension a namespaced typed state slot; do not share raw byte indices or one global `Scratch` object.
- Build perception results atomically so later sensors cannot replace only the target while leaving stale hostility facts.
- Use deterministic priority plus registration IDs for ties.
- Catch and attribute extension exceptions, continue the host frame, and quarantine a repeatedly failing contributor.
- Require sensors/listeners/operators to detach or dispose.
- Version domains per archetype and explicitly migrate, respawn, or retire existing agents on reload.

## Tear Down Safely

Normal reset/shutdown while the world is active may cancel planners, stop timers/sounds/particles, kill children and bodies, and clear registries. Make every operation idempotent. Retry an incomplete active cleanup on a configured cadence with a strict attempt bound; on exhaustion retain ownership in an explicit failed state for remediation rather than silently forgetting live children/effects or retrying every frame forever.

On world deactivation, Source 2 owns native destruction. Increment the managed generation, cancel worker work, and forget wrappers/handles without dereferencing them. Late callbacks must fail the managed generation check before touching the framework.
