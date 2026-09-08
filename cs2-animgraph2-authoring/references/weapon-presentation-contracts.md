# Weapon Presentation Contracts

Use this reference when a custom weapon is visible but its hands, world
attachment, charge, rotor, muzzle, or sounds disagree with gameplay. It records
lessons from a native M249 proxy carrying a custom M134. It does not prescribe
that proxy, its coordinates, or its timings for other weapons.

## Contents

1. Separate presentation surfaces and identity
2. Keep the private agent selected
3. Separate scene, export, and runtime attachments
4. Diagnose held versus holstered placement
5. Fit hands and frame the weapon
6. Drive charge and continuous rotation
7. Place muzzle effects and own sound playback
8. Evidence and limits

## 1. Separate presentation surfaces and identity

| Surface | Contract to inspect |
| --- | --- |
| World weapon entity | Entity model plus unified-model metadata, skeleton, physics and attachment compatibility |
| Owner's weapon object | Client-resolved VData model and weapon skeleton; a server `SetModel` alone does not establish this route |
| First-person hands | Active player model's named `hudmodel` private root, observed weapon variation and final IK |
| Third-person player pose | Active player model's default/named `worldmodel` roots, action and locomotion branches |
| Moving weapon parts | Secondary weapon tracks in the character clips and matching model/VData skeleton |

For a native proxy, retain its observed client identity. The M249 case needed
matching presentation values under both native VData keys, `14` and
`weapon_m249`: `m_szWorldModel`, `m_szWorldModelAg2Override`, and
`m_szAnimSkeleton`. This is evidence of a native-record presentation override,
not proof that an invented subclass key registers on a clean client.

`scripts/weapons.vdata` is a global resource path. Preserve current stock
records and gameplay fields when an intentional addon-wide presentation
override is authorized; compare the allowed field changes in both lookup forms.
A private player graph or server entity marker does not scope global VData
changes to one player. Document proxy exclusivity or prove another discriminator.
Never fix this by writing loose client base-game files implicitly.

## 2. Keep the private agent selected

A graph-only agent variant can reuse the approved model while changing only
its default/named graph references. Preserve mesh, bind pose, weights,
materials, hitboxes and physics. This operation does not require a character
port; use `$cs2-player-model-porting` only when its asset contracts need work.

Find the final appearance resolver, including role assignment and later
inventory/cosmetic application. An early fallback model can be overwritten by
the chosen cosmetic agent. Map the exact supported role and original model to
its private graph variant in the shared resolver used by both paths. Preserve
persisted cosmetic identity, tint, accessories and unrelated roles. Do not
fight another subsystem with repeated `SetModel` calls.

Inspect the pawn model after the final appearance assignment and after a
cosmetic change or respawn. Restore the appropriate model when the private
roots are no longer needed, with the native-proxy exclusivity rules from
[graph-routing-and-patching.md](graph-routing-and-patching.md).

## 3. Separate scene, export, and runtime attachments

These are different transforms:

- Blender scene parent: where the weapon is held while posing the hands.
- Source DMX parent: the hierarchy ResourceCompiler uses to extract secondary
  animation tracks.
- Runtime attachment: where the engine composes the secondary skeleton.

In the measured M134 case, the Blender weapon remained under `wpn`. Exporting
its parent-relative channels under DMX `wpn` accumulated the grip transform in
the compiled secondary root. The stock M249 secondary root was neutral. An A/B
export under the measured neutral `root_motion` joint, preserving the same
channels, produced a neutral secondary root without changing primary character
curves. Runtime attachment remained `wpn`.

The bundled manifest exposes this distinction:

```json
{
  "secondary_attach_bone": "wpn",
  "secondary_export_attach_bone": "root_motion"
}
```

This is an opt-in example, not a universal repair. The export parent defaults
to the scene parent for compatibility. Compare the stock and custom compiled
secondary root, bind transforms, channel frame and skeleton names before
selecting a different parent. Verify both 1P and 3P; do not move the character
or erase its grip transform to compensate for a doubled secondary transform.
See [portable-tooling.md](portable-tooling.md) for export receipts.

A decompiler's primary-character DMX may omit secondary weapon tracks. Missing
rotor joints in that output alone do not prove the compiled clip lacks motion.
Inspect `m_secondaryAnimations` and use a decoder that actually exposes those
tracks, or label source-curve measurements separately from compiled checks.

## 4. Diagnose held versus holstered placement

A rifle visible on the body while a pistol is active can be normal holstering.
The defect is an active weapon that remains at the same body anchor rather than
following the hands. Compare stock, defective and corrected unified models.

On the inspected M249 path, parenting the entity at `weapon_center` was normal;
a later held-bone placement override depended on the weapon model contract.
The observed path required one physical part containing exactly one convex
hull, compatible `weapon`/`weapon_offset` bones, unified weapon metadata and the
expected holster attachments, including `weapon_holster_center` on a compatible
physics bone. A shape named "hull" that was actually a capsule had zero convex
hulls and did not pass that gate. Authoring a real hull from the custom geometry
corrected this model contract.

This is a build-scoped unified-weapon observation, not a rule for player
ragdolls or NPC collision. Inspect compiled PHYS shape types/counts and the
current native placement path before applying it elsewhere. Do not reparent
the weapon entity or offset tracers to conceal a failed model contract. Check
active/holstered states, weapon switching, observer view and shadow separately.

## 5. Fit hands and frame the weapon

Define grip markers from the actual handle surfaces and solve arm reach with
measured upper/lower arm lengths. Pose the fingers within their anatomical
reach; preserve bone lengths, scales and finger translation channels. Solve
against the final layered pose: an extra wrist/helper transform applied after
the grip solve can invalidate a correct intermediate pose.

For a long thumb or twisted wrist, compare original skinning under stock and
custom poses, helper targets, local phalanx transforms and bind frames before
changing weights. Do not stretch the skeleton or delete fingers to reach a
handle. A diagnostic remap with zero unmapped weights can still use the wrong
bind frames and deform the mesh severely.

Render the actual agent/gloves as well as any stock hand reference. A correct
reference hand does not prove the custom glove fits. Check grip penetration,
thumb proportions, wrist silhouette and reachable elbow positions across the
requested actions. Hand fitting is a pose problem unless mesh/bind evidence
shows otherwise; route actual geometry defects to `$cs2-player-model-porting`.

Adjust framing as a consistent transform of weapon, hands and grip helpers.
Use a measured camera view to keep the barrel rotation visible and aim the
presentation toward the screen center. Preserve gameplay bullet direction.
Keep approved non-target curves unchanged when repairing only the rotor or
muzzle; curve comparisons catch accidental hand or framing regressions.

## 6. Drive charge and continuous rotation

Separate the server attack gate from the client animation request. In the
inspected client, `m_bInReload` plus an attack delay did not request the private
reload branch. `ReflectWeaponState` consumed `m_iWeaponGameplayAnimState` and
its timestamp. The corrected proxy used the framework's named `Reload` token
with a fixed phase-start timestamp to select the private spin-up action.
`InReload` stayed false for this animation-only use. Do not copy raw enum values
or assume an ammo reload on other proxies behaves identically.

Publish the start time once per phase; reasserting state with a new timestamp
every command restarts the clock. At speed, release the gate and allow the
native firing path. Make early release, weapon switch, death and role cleanup
explicit; resolve serial-bearing entity handles afresh and avoid native calls
after world teardown. Validate prediction and observer playback in game.

For a rotor, inspect unwrapped angles, angular velocity and quaternion signs:

- Match the spin-up endpoint speed to the loop and make the loop close modulo
  a revolution.
- End slowdown at an orientation equivalent to idle with velocity tending to
  zero. A 228-degree endpoint blended into zero has a real discontinuity.
- Keep adjacent quaternion keys in the same hemisphere and choose interpolation
  deliberately. Sample subframes, not just keys, to detect an unintended long
  rotation or overshoot.
- Check actual graph looping and exit ownership. Arbitrary loop-phase release
  and rapid re-press require runtime testing even when authored endpoints match.

The accepted M134 example used 25/15/49 intervals at 30 FPS for spin-up/loop/
slowdown. Nine actions passed 2,145 Blender subframe samples; non-rotor curves
were unchanged. These are source-motion checks, not decoded compiled-secondary
motion or proof of every possible crossfade. Adapt curves to gameplay timings.

## 7. Place muzzle effects and own sound playback

On the inspected owner-view path, HUD lookup for `muzzle_flash` and
`muzzle_flash2` reads VData `m_vecMuzzlePos0/1`, transforms them in the viewmodel
frame and mirrors the lateral component for the left-handed view. A corrected
ModelDoc attachment alone can leave the first-person flash at stock VData
coordinates. Compute the vectors from the final approved pose and firing
station; update both relevant native VData lookup forms. Do not copy another
weapon's coordinates or adjust bullet trajectories to match a visual effect.

World muzzle attachments and VIP/world tracers have a separate projection from
the owner viewmodel. Diagnose each origin independently. Keep verified native
fire events and their attachment contract; AG2 event support does not imply a
generic arbitrary-particle API. Persistent cosmetic effects also need an owner,
valid attachment and stop/removal behavior when their state ends.

A projectile message naming a missing attachment is a model-contract failure,
even if its model and particle are precached. Add the exact required attachment
to the custom model at a measured parent/position and recompile/package it.
Examples from this case were `incgrenade_particle` for the incendiary effect
and `decoy_particle` for the decoy ground effect.

Give each sound one playback owner. In this case, the server owned the three
motor phases and the native weapon path owned per-shot audio. A VData fire
sound plus a native-name alias in the private bank covered native shot lookup;
neither AG2 nor the module emitted an additional shot. Such aliases can affect
every proxy weapon using that bank and must be scoped intentionally.

Preserve supplied WAV provenance and metadata, including loop cues. Start a
validated engine loop once and stop it on phase/lifecycle changes; retry a
failed start, not an already-running loop. Package and precache the sound bank
and raw sounds explicitly when their string paths are not RERL dependencies.
For inspected VSND v5 files, streaming PCM followed the declared resource size;
a zero-sized DATA block was not evidence of empty audio. Compare decoded PCM
and loop metadata with an appropriate reader rather than that size alone.

## 8. Evidence and limits

This is a sanitized engineering summary of a private M134 integration accepted
by its owner on September 8, 2026. Local asset receipts, controlled exports and
read-only native inspection informed it; proprietary assets, decompiled Valve
sources and binaries are intentionally not bundled. The original 28-bone
sample in this skill remains compile-proven only; later M134 acceptance does
not upgrade that separate sample.

| Evidence | Recorded scope |
| --- | --- |
| Linux client 2000899 | Unified M249 placement gate inspection and stock/custom compiled-model comparison |
| Linux client 2000905, Steam build 25175329 | Weapon animation-state reader and HUD muzzle lookup inspection |
| M134 source and compiled artifacts | Neutral secondary-root A/B; graph/model/skeleton checks; source subframe and non-rotor invariants; audio PCM/loop checks |
| Owner feedback after release | Overall positive acceptance of the final presentation; no exhaustive per-action or clean-Workshop-only test matrix was reported |

Inspected `libclient.so` SHA-256 values:

```text
2000899  2a48c33e38efc0ea5a67b85914546d3a8a41631decda7ad732926fc92d442a16
2000905  0d418018466ed4b76690c17f2dffdc86dcdf226319970cbd0d429d53fe7cecb7
```

Revalidate native readers and stock controls after a game update. This record
contains no portable ABI offsets or signature profile. Report the evidence
layer actually obtained; static inspection, source animation, owner acceptance
and clean-client delivery are separate results.
