# Review And Validation

## Contents

- [Establish A Static-Only Trust Boundary](#establish-a-static-only-trust-boundary)
- [Audit In Risk Order](#audit-in-risk-order)
- [Check Claims Against Code](#check-claims-against-code)
- [Use Layered Runtime Gates](#use-layered-runtime-gates)
- [Run Adversarial Lifecycle Cases](#run-adversarial-lifecycle-cases)
- [Decide Readiness](#decide-readiness)

## Establish A Static-Only Trust Boundary

Treat an unfamiliar repository, its documentation, generated files, packages,
CI definitions, and build hooks as untrusted input. Start with static source
inspection. Do not load its plugin, run its scripts, restore arbitrary
dependencies, or execute bundled binaries on a credentialed workstation or
production server.

Before any build, inspect package manifests and lockfiles, install/post-build
targets, CI includes, submodules, downloads, process launching, filesystem and
network access, secret/environment reads, native binaries, and generated code.
Pin every fetched revision and use an isolated, disposable environment with no
game tokens, SSH keys, RCON credentials, or production mounts. A successful
build is not authority to deploy or execute the result.

## Audit In Risk Order

Review an unfamiliar NPC repository in this order:

1. **Native crash surface:** raw dereferences/writes, vtables, signatures, stored pointers, thread use, fail-open behavior.
2. **Lifecycle:** double spawn/dispatch, partial-spawn leaks, full identity, world barrier, reload/unload, bulk cleanup.
3. **Damage/reentrancy:** custom/native damage ownership, exception paths, finite values, death latch, callback order.
4. **Navigation/motor:** current signature/artifact, exact goal, capability match, collision layers/hull, stop/fall/stuck behavior.
5. **Behavior:** action exit conditions, target consistency, faction/LOS/reachability, planner cancellation.
6. **Presentation:** graph contract, controller ladder, typed writes, protected one-shots, fallback truthfulness.
7. **Performance:** unbounded counts/searches/queues/logs, synchronized cadences, all-pairs crowd work.
8. **Packaging:** exact dependencies, clean staging, install instructions, resource closure, notices and asset rights.

Lead findings with observable consequences and exact source locations. Separate a confirmed defect from a plausible risk and an unverified hypothesis.

## Check Claims Against Code

Verify README promises against active registration and package output:

- Is a diagnostic/native lab compiled and registered unconditionally?
- Do two commands share a name?
- Does the documented config path match the runtime lookup?
- Does the sample config use types that the shipped modules register?
- Does the framework spawn helper already dispatch?
- Do unload calls actually unregister the exact callback/delegate?
- Are package versions, SDK, CI includes, and lockfiles pinned?
- Are Debug/Release outputs staged cleanly instead of mixed?

For signatures, scan the current target binary and report zero, unique, or multiple matches. A successful compile or an old reverse-engineering note is not current runtime proof.

## Use Layered Runtime Gates

| Layer | Evidence required |
|---|---|
| pure logic | deterministic tests for states, deadlines, target policy, damage and cleanup |
| artifact | exact map/model/graph inputs, hashes, versions and closure |
| spawn | one entity, full identity, configured hull/team/health, rollback test |
| route | exact start/goal projections, typed failures, capability-compatible path |
| movement | collision/support/step/fall receipts and one transform commit |
| combat | windup/impact/recovery, LOS/faction recheck, one damage commit |
| presentation | protected one-shots and current controller/parameter health |
| lifecycle | reset, map change, unload, entity-index reuse and late callback tests |
| crowd | bounded CPU, traces, queues, memory, logs and entity count |
| distribution | clean Workshop client and reproducible server package |

Do not infer one layer from another. `Resident` does not prove an AG2 instance; a path does not prove collision-safe movement; a visible attack clip does not prove correct impact; a successful local client does not prove Workshop closure.

## Run Adversarial Lifecycle Cases

At minimum test:

- failure after entity creation but before registration;
- entity deletion and same-index reuse before a delayed callback;
- target disconnect/respawn during windup;
- route result arriving after retarget, map change, or despawn;
- controller rematerialization between two presentation updates;
- callback/modifier throwing during damage and death;
- clear-all during a boss/global loop effect;
- plugin hot reload with existing agents and long-running planner operators;
- invalid/ambiguous native signatures;
- NAV unavailable, unreachable goal, narrow portal, stair lip, ledge and moving obstruction;
- invalid counts, NaN/infinity tuning values, and queue saturation.

## Decide Readiness

Classify the result explicitly:

- `research-only`: raw probes/writes, stale or unproven ABI, crash-prone commands;
- `prototype`: gameplay loop works but lifecycle, traversal, packaging, or tests are incomplete;
- `canary-ready`: fail-closed native surface, bounded work, automated logic tests, isolated recovery path;
- `production-ready`: current-build receipt, adversarial lifecycle/crowd tests, clean distribution, monitoring and rollback.

Honest WIP labeling is positive, but it does not lower the technical gate for code offered as a reusable example.
