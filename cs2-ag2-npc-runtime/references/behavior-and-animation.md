# Driving AnimGraph2 From Server Behavior

## Contents

- [Separate Gameplay From Presentation](#separate-gameplay-from-presentation)
- [Define Explicit States](#define-explicit-states)
- [Derive Locomotion Parameters](#derive-locomotion-parameters)
- [Drive Aim And Turns](#drive-aim-and-turns)
- [Pulse Actions Correctly](#pulse-actions-correctly)
- [Synchronize Gameplay And Clips](#synchronize-gameplay-and-clips)
- [Handle Spawn, Death, And Removal](#handle-spawn-death-and-removal)
- [Choose Update Rates](#choose-update-rates)
- [Diagnose Visual Symptoms](#diagnose-visual-symptoms)

## Separate Gameplay From Presentation

Keep one server-authoritative behavior model and derive graph inputs from it. The graph should not decide damage, target validity, cooldowns, navigation, or death ownership.

```text
AI/navigation/combat state
    -> animation adapter
    -> typed AG2 parameters
    -> graph state and clip
```

Maintain these layers separately:

- **Gameplay:** targets, pathing, velocity, attacks, damage, health, cooldowns.
- **Animation adapter:** parameter values, action pulses, ID selectors, one-shot timing.
- **Effects/audio:** attachments, graph event timing, particles, sounds.

This avoids using a clip name as the NPC's actual state and prevents animation corrections from changing gameplay rules.

## Define Explicit States

Use a finite state machine appropriate to the NPC, for example:

```text
Spawning
  -> Idle
  -> Moving
  -> AttackWindup
  -> AttackActive
  -> AttackRecovery
  -> Moving or Idle
Any live state -> Reacting -> previous legal state
Any live state -> Dead -> Removed
```

Store at least:

```text
current state
state entered time
current target
desired world velocity
actual world velocity
pending one-shot action
action pulse sent flag
expected active/recovery deadlines
death/removal deadline
```

Define legal transitions. Do not let the normal idle/movement writer overwrite an attack, wake, spawn, or death state before its minimum duration.

## Derive Locomotion Parameters

Treat Source 2 `Z` as vertical and project locomotion onto the horizontal `XY` plane. Flatten and renormalize the entity basis before taking dot products:

```text
v_xy = (v.x, v.y)
f_xy = normalize((forward.x, forward.y))
r_xy = normalize((right.x, right.y))
forward_speed = dot(v_xy, f_xy)
strafe_speed  = dot(v_xy, r_xy)
move_speed    = length(v_xy)
vertical_speed = v.z
```

Obtain `right` from a verified engine transform/basis API when possible. Do not invent it from `forward` without proving the handedness and sign expected by the graph: Source-family coordinate labels, helper APIs, imported skeletons, and individual graphs can expose different conventions. Calibrate the sign with a known positive-control sidestep and record that evidence with the model/build contract.

Use the units and normalization expected by the inspected graph. Some graphs compare raw world speed; others expect a normalized range. Derive that from Float comparison thresholds and the native behavior if available.

Write continuous locomotion parameters at a stable cadence. If transform updates occur at 20 Hz but animation speed updates at 2 Hz, the model will appear to slide or teleport even when network positions are correct.

If the graph has directional locomotion, rotate the NPC toward its travel direction or supply correct local forward/strafe values. Facing the player while pathing sideways around an obstacle can intentionally select strafe clips; it looks wrong when the desired design is forward running.

Avoid snapping orientation. Apply a bounded angular speed, then use graph-proven pivot-turn IDs when the heading error crosses their thresholds.

## Drive Aim And Turns

Compute target direction from a verified attachment or body-space aim origin:

```text
target_dir = normalize(target_point - aim_origin)
local_yaw  = signed angle between entity forward and target_dir on XY
local_pitch = vertical angle to target_dir
```

Clamp to graph or model limits. Feed `look_heading` and `look_pitch` continuously only when those parameters exist and have the expected Float type.

For an ID turn selector:

1. Read exact IDs from `CNmIDComparisonNode` data.
2. Choose an ID from current heading error.
3. Set it on state entry or when the turn band changes.
4. Clear or return to the graph's neutral ID after the turn contract says to do so.

Do not assume `left`, `turn_left`, and `e_Turn_left_90` are interchangeable.

## Pulse Actions Correctly

Many attack/reaction controls are Bool pulses, not persistent modes. Use an edge:

```text
on action entry:
    set prerequisite target/variant parameters
    set action Bool = true
on next animation update or proven acknowledgement:
    set action Bool = false
```

Do not set `action_shoot=true` every tick. Repeated writes can restart a transition, cut the intro, skip recovery, or make the graph alternate with idle.

For ID-based actions, write the selector before the Bool pulse that consumes it. Keep both a state-entry token and entity generation/serial so delayed timers from an old action or a reused entity index cannot clear a newer action.

Use one owner for animation state. A global idle writer and an attack timer must not both set the same controls independently.

## Synchronize Gameplay And Clips

Prefer this order of evidence:

1. Graph event exposed through a supported runtime callback.
2. Clip event time/percentage recovered from the graph resource.
3. Measured animation offset tied to state-entry time.
4. Visual guess only as a temporary probe.

For a projectile attack:

```text
t0: enter windup and pulse action
t0 + muzzle_offset: resolve attachment, spawn projectile, play launch sound
t0 + active_duration: enter recovery
t0 + total_duration: return to movement/idle
```

Resolve the muzzle attachment at launch time, not at windup start. The attachment moves with the animation.

Do not schedule gameplay from a client-observed animation alone. Server and client can differ by interpolation and latency. Keep damage authoritative and use the clip evidence to choose the server delay.

## Handle Spawn, Death, And Removal

For an emerge/spawn animation:

- place the model where the clip expects it, including intentional initial ground penetration;
- keep the spawn state active for the full one-shot;
- transition directly to locomotion/idle without a one-frame fallback;
- anchor spawn particles independently when their origin contract differs from the model origin.

For death:

- stop navigation and attacks immediately;
- enter the graph's death/explosion state once;
- keep the entity valid through the required visual interval;
- stop owned particles and looped sounds;
- remove the entity exactly once after the clip/effect contract;
- cancel all delayed callbacks by entity generation or validity checks.
- marshal callbacks back onto the server game thread and revalidate identity immediately before graph/entity access.

Never return to idle between lethal damage and removal.

## Choose Update Rates

Use separate cadences instead of one monolithic Think:

| Work | Typical cadence | Notes |
|---|---|---|
| target/path decision | 5-10 Hz | lower for distant or inactive NPCs |
| movement integration | server tick or stable high rate | preserve collision and smooth transforms |
| animation locomotion adapter | 15-30 Hz or movement cadence | avoid visible sliding/stutter |
| attack state transitions | deadline/event driven | do not poll expensively |
| health/target graph values | on change plus periodic refresh | exact graph needs decide |
| diagnostics | explicit command | never per NPC per tick |

LOD expensive AI decisions, not the animation continuity needed for visible NPCs. Measure server frame time before and after changing cadence.

## Diagnose Visual Symptoms

| Symptom | Likely cause |
|---|---|
| Model moves in idle pose | locomotion parameters missing, wrong type, wrong scale, or overwritten state |
| Model runs sideways around obstacles | facing follows target while velocity follows path, or local velocity axes are wrong |
| Intro cuts to idle before loop | idle writer wins during protected action, pulse repeats, or transition deadline is wrong |
| Loop plays once | graph branch is not held, clip is not looping, or controlling condition is cleared |
| Wake briefly returns to sleep | fallback state is written between one-shot completion and idle entry |
| Attack fires before muzzle motion | gameplay is tied to action start instead of graph/clip event |
| Attachment effect jumps to head | attachment lookup failed and fallback origin was used |
| Remote client sees static model | server graph instance/parameters not network-relevant, resources missing client-side, or client graph differs |
| Animation stutters only at scale | update cadence or repeated state writes, not necessarily model LOD |

Log state transitions and parameter diffs temporarily. Remove high-volume logs after validation, but retain a low-cost health summary for future game updates.
