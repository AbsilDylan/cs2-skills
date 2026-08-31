# Navigation And Locomotion

## Contents

- [Choose A Navigation Authority](#choose-a-navigation-authority)
- [Preserve Provenance And Capabilities](#preserve-provenance-and-capabilities)
- [Return Exact Route Results](#return-exact-route-results)
- [Apply Worker Results Safely](#apply-worker-results-safely)
- [Build A Collision Motor](#build-a-collision-motor)
- [Handle Stops, Stuck State, And Crowds](#handle-stops-stuck-state-and-crowds)

## Choose A Navigation Authority

Prefer, in order:

1. a current framework/engine navigation API with a documented ABI;
2. an offline-extracted, immutable managed NAV artifact with exact source/build provenance;
3. a small build-scoped native read bridge when neither option exists.

A live `CNavMesh*` signature is not automatically the best runtime design. Native pointers add update and crash risk. If used, require a unique signature, module-range/structure checks, current build/hash receipt, isolated canary, and fail-closed behavior. A canonical-looking address is not proof that the object is alive or has the expected layout.

## Preserve Provenance And Capabilities

Record map identity, NAV SHA-256, format/generator version, CS2 compatibility build, selected hull, radius, height, short/crouch height, climb, and slope. Reject incompatible or incomplete artifacts.

Serialize only traversal the motor can execute. A walk-only NPC must exclude ladders, jumps, drops, and off-mesh connections. Do not label edge types and then ignore them at movement time. Filter paths by the same hull/capabilities used by traces.

## Return Exact Route Results

Use typed outcomes:

```text
Success(exact projected start, corridor, waypoints, exact projected goal)
NoNav | StartOutside | GoalOutside | NoPath | UnsupportedTraversal
Cancelled | Expired | Superseded | BudgetExceeded
```

The final waypoint is the exact projected goal, not merely the center of its NAV area. A same-area route must still preserve that goal. String-pull/funnel through real directed portals; do not guess portal left/right from area-center deltas or assign Z from arbitrary centers.

Keep path failure visible to behavior. A deliberate straight-line mode is a separate capability with collision/visibility proof, not a silent `NoPath` fallback.

## Apply Worker Results Safely

Snapshot plain positions, target identity, blocker state, agent profile, world generation, and request serial on the game thread. Bound worker concurrency and coalesce older requests per NPC.

Apply on the game thread only if:

- world generation and entity full identity still match;
- request serial is still current;
- result age is within policy;
- target identity and drift remain acceptable;
- dynamic blockers have not invalidated the corridor.

Never send an engine wrapper or live native pointer to a worker.

## Build A Collision Motor

Use one radius/height contract for navigation and movement. A robust walk motor normally performs:

1. derive desired horizontal velocity from the next route contact;
2. apply bounded acceleration/deceleration using real `dt`;
3. sweep the actual capsule through the requested displacement on a movement collision layer/group;
4. clip/slide the remaining displacement against each new contact normal;
5. if blocked, prove a raise/cross/descend step within the hull climb limit;
6. prove ground support and walkable slope;
7. commit one final transform and publish actual velocity/facing.

Update the remaining velocity after each impact. Do not reuse the original vector for every slide plane. Distinguish a blocked wall from a missing floor: a horizontal obstruction must not manufacture a fall.

For falling, cancel the invalid upper route, apply gravity/terminal velocity, sweep continuously, and require a walkable non-sky landing before returning to ground movement. Unsupported traversal should fail or despawn according to policy, not teleport to a guessed surface.

## Handle Stops, Stuck State, And Crowds

`Stop` must clear internal desired/actual velocity and publish a zero engine velocity when the world is active. Arrival, progress, and stuck checks should use the route geometry and relevant 3D/support state, not XY distance alone.

Do not reset all stuck/progress timers every time a moving target is retargeted. Detect route progress separately from Euclidean distance to the final goal; a valid detour can temporarily increase that distance.

Use deterministic, bounded local avoidance. Avoid all-pairs separation for large crowds; use spatial bins/neighborhood caps and a global optional-probe budget. A teleport rescue may exist as an explicit admin/recovery policy, but it must be logged and must not make normal navigation appear successful.

