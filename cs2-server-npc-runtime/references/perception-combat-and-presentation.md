# Perception, Combat, And Presentation

## Contents

- [Publish Atomic Perception](#publish-atomic-perception)
- [Use An Action State Machine](#use-an-action-state-machine)
- [Apply Damage Transactionally](#apply-damage-transactionally)
- [Own Death And Cleanup](#own-death-and-cleanup)
- [Project Animation](#project-animation)
- [Treat Bones As Evaluated Output](#treat-bones-as-evaluated-output)

## Publish Atomic Perception

Produce one immutable observation containing target full identity, faction relation, sampled locomotion/NAV point, separate aim/bone point, velocity, visibility/LOS, range, NAV reachability, threat score, observed-at time, and revision. Update the record atomically. Compare route drift against the sampled NAV point, not an animated aim attachment.

Use FOV/LOS/PVS and reachability according to the NPC design. Add memory and hysteresis so nearly equal targets do not oscillate. Make tie-breaking deterministic. A follow target is not automatically an attack target; every ability must check goal kind and faction again.

## Use An Action State Machine

Use explicit action phases:

```text
Ready -> Windup -> Active -> Recovery -> Ready
                  \-> Cancelled
Any phase -> Dead
```

Store a monotonically increasing action token, target identity, entered-at time, impact deadline, recovery deadline, damage-applied latch, and presentation pulse latch. Use absolute time so cadence changes do not change attack duration.

At impact, revalidate:

- attacker and target full identities/current generations;
- attacker alive and still in the same action token;
- target alive, hostile, in range and inside the required cone;
- line of sight when the ability requires it;
- finite damage/knockback values and cooldown ownership.

An animation event may refine impact timing, but server state remains authoritative and needs a bounded fallback deadline.

## Apply Damage Transactionally

Use one damage owner. If native damage is intercepted for custom health, validate and compute the custom transaction before marking native damage consumed. Do not let an exception in a modifier/event both skip custom HP and allow unintended native damage.

Reject non-finite inputs, clamp configured ranges, and set original/final damage consistently for hooks and telemetry. Prevent reentrant damage to the same target/action from recursively applying before the first transaction latches.

Publish immutable before/after damage events through exception-isolated callbacks. Decide whether modifiers run before commit and notifications after commit; document it. An observer exception must not roll back committed health or interrupt required cleanup.

## Own Death And Cleanup

Latch death exactly once before external callbacks. Immediately stop decisions, routes, movement, attacks, and looped effects. Then project a death animation/effect for a bounded lifetime and remove the entity once.

Cleanup includes body, collision proxy, hit regions, child props, particles, looped sounds, timers, path requests, planner operator, target leases, boss/global effects, and registry entries. Clearing a collection is not cleanup. A bulk wipe must invoke the same owned cleanup path as one death.

## Project Animation

Presentation consumes an immutable gameplay snapshot:

```text
state/action token + desired/actual local velocity + aim + health
  -> model-specific adapter
  -> typed AG2 parameters OR verified named-sequence input
```

For AG2, inspect the compiled graph and use exact types/ID values through a proven typed setter. `AcceptInput` is only generic entity-I/O dispatch; invoking a verified model/entity animation input such as `SetAnimation` with an exact baked sequence label is a separate named-sequence path. It does not materialize a missing AG2 graph instance or substitute for typed controls.

Protect spawn, attack, reaction, and death one-shots from the locomotion writer. Pulse entry booleans once, set selectors before their consuming pulse, and never restart a one-shot every frame. Drive facing from actual collision-resolved velocity unless the graph contract intentionally separates aim and movement.

Presentation returns a typed `Applied`, `Retry`, or `Degraded` receipt. A retry
does not acknowledge state-entry or action edges; an explicit degraded receipt
may consume them while advertising reduced presentation. Because an exception
can happen after a native side effect, adapters must deduplicate by full entity
identity, presentation revision, and action token. Presentation failure should
produce an actionable health state and a safe fallback, not change damage/nav
decisions. Use `cs2-ag2-npc-runtime` for controller materialization, Linux
setter signatures, graph contracts, and clean Workshop closure.

## Treat Bones As Evaluated Output

Bones are normally evaluated results of the model/controller, useful for attachments, hit-region sampling, muzzle origins, and effects. They are not a generic way to drive AG2.

Resolve a named bone/attachment after the controller is valid, cache only stable indices where the framework contract permits, and read transforms on the game thread. Revalidate entity/controller lifetime and fail closed when the bone is missing. Do not retain a raw bone/node pointer across controller rematerialization.
