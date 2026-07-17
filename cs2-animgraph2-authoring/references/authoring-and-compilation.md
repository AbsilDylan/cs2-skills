# Authoring And Compilation

Use this reference while creating weapon models, animation sources, VNMClip
documents, and deterministic build scripts. Keep graph routing and Workshop
deployment concerns in their dedicated references.

For an executable current-build workflow, use the manifest and scripts in
[portable-tooling.md](portable-tooling.md). This file explains the contracts;
the tooling reference defines the exact extraction/export/build commands.

## Contents

1. Build inventory
2. Canonical addon layout
3. Model contracts
4. Animation source contract
5. VNMClip documents
6. Compilation
7. Compiler registration recovery
8. Compiled-resource inspection
9. Build manifest

## 1. Build Inventory

Before editing, record the current environment. CS2 updates can change asset
formats, skeletons, graphs, compiler registrations, and runtime parameters.

Record at least:

```text
CS2 build/revision
Workshop Tools build/revision
content root
game/addon output root
resourcecompiler.exe path and hash
assettypes_common.txt path and hash
Blender version and exporter versions
compiled-resource inspector version
stock reference paths and hashes
```

Select a current stock item with a similar hold style and action timing. Inspect
the actual installed resources; do not rely only on an old decompile or guide.
The reference should establish:

```text
native entity classname
client-visible weapon_type
graph variation suffix
weapon skeleton
first-person character skeleton
third-person character skeleton
owner and world model conventions
action names, frame rates, durations, and events
```

Treat the native classname, VData name, anim class, `weapon_type`, and graph
variation suffix as distinct until runtime evidence proves otherwise.

## 2. Canonical Addon Layout

Keep authored sources under the Workshop addon content tree:

```text
<CS2>/content/csgo_addons/<addon>/
  animation/<namespace>/<item>/
    viewmodel.vnmgraph
    worldmodel.vnmgraph
    ...private graph children...
  models/<namespace>/<item>/
    <item>_owner.vmdl
    <item>_world.vmdl
    clips/
      idle_<item>.vnmclip
      draw_<item>.vnmclip
      primary_<item>.vnmclip
    source/
      idle_<item>.dmx
      draw_<item>.dmx
      primary_<item>.dmx
  materials/<namespace>/<item>/
  scripts/weapons.vdata                 # optional
  panorama/images/icons/equipment/      # optional
```

Expect compiled resources under the matching game addon tree:

```text
<CS2>/game/csgo_addons/<addon>/
```

Use one canonical action name. Avoid retaining `idle_stock`, `idle_probe`,
`idle_custom`, and `idle_final` in the shipping route. Store experiments outside
the packaged namespace or list them explicitly as non-shipping artifacts.

Do not copy loose test resources into the base `game/csgo` tree. A clean
Workshop-only test is required before calling distribution successful.

## 3. Model Contracts

### Owner object model

The owner object is the item seen by the local player. Its origin, orientation,
attachments, and skeleton must match the animation and proxy conventions used
by the selected graph. A custom mesh does not by itself provide arms or select a
custom player animation.

Do not set `m_sToolsOnlyOwnerModelName` to an object-only VMDL when the selected
runtime path expects that field to provide a complete composed owner viewmodel.
That mismatch can produce a floating weapon with no arms. In architectures
where the player model's `hudmodel` graph owns the arms, preserving the stock
empty value can be correct. Verify against the current proxy VData.

### World object model

The world model is the separate object attached to a third-person hand, dropped
on the ground, or shown to observers. It can need a different origin, skeleton,
scale, attachments, or collision contract from the owner object.

### Player model

The player ModelDoc owns the graph roots that animate first-person arms and the
third-person character. Preserve current stock bodygroups, helper bones,
attachments, constraints, and IK topology until a measured replacement proves
safe.

A common private setup is:

```text
named AnimGraph2 ref `hudmodel`   -> private first-person root
default AnimGraph2 graph          -> private third-person root
named AnimGraph2 ref `worldmodel` -> the same private third-person root
```

The exact ModelDoc node names and serialization can change. Compare with a
current stock model and inspect the compiled VMDL_C.

Full player-model porting, hitboxes, and ragdolls are separate work. Pair this
skill with a dedicated current CS2 player-model porting workflow when replacing
the complete character.

## 4. Animation Source Contract

### Start from exact skeleton data

Import or reconstruct the exact current target skeleton, hierarchy, rest
transforms, and axes. Do not redraw a humanoid or viewmodel rig by eye. A clip
that looks plausible in Blender can place the arms far outside the camera when
its basis, rest pose, parenting, or units differ from Source 2.

Use the skeleton required by the destination graph:

```text
first-person character motion:
  animation/skeletons/characters/viewmodel.vnmskel

third-person full-character motion:
  animation/skeletons/characters/worldmodel.vnmskel

secondary object/weapon motion:
  the exact current proxy weapon skeleton
```

Names are current conventions, not a substitute for inspecting the installed
build.

### Blender authoring rules

1. Preserve bone names, hierarchy, rest matrices, and scale.
2. Animate in Pose Mode; never solve a Source 2 skeleton by moving mesh objects.
3. Key every required deforming and control bone, including fingers and hands.
4. Export finite position and orientation channels for the full expected set.
5. Avoid helper-only clips: visible hands can remain in stock poses if only
   shoulders or weapon helpers are keyed.
6. Keep the item attached to the intended weapon/hand helper rather than baking
   accidental object transforms into the character.
7. Inspect first and last frames for discontinuities before making an idle loop.
8. Remove accidental actions, NLA strips, constraints, and unkeyed defaults from
   the export copy.
9. Test finger curls for self-intersection and item penetration from the actual
   game camera, not only an orbiting Blender view.
10. Export one deterministic action at a time and record frame range and FPS.

Keying a parent does not automatically key every child. Select the complete
required pose-bone set before inserting transforms, or use a deterministic
export script that samples every expected channel per frame.

Do not hardcode a historical bone or channel count. Some observed viewmodel
builds used 56 bones and 112 position/orientation channels, but the current
installed skeleton is the authority. Derive the expected set and fail the build
when exported names or counts differ.

### DMX validation

Treat DMX as an intermediate artifact. Validate:

```text
skeleton name and hierarchy
time base and frame count
all expected transform channels
finite values
consistent units and basis
first/last frame behavior
secondary object skeleton, when used
```

Keep the Blender file, exporter script/settings, DMX, and generated report. A
binary DMX can be edited programmatically, but direct opaque byte edits are not
a maintainable authoring workflow.

## 5. VNMClip Documents

Create an editable `.vnmclip` source for each canonical action. Current
documents reference the DMX and target skeletons, but the accepted fields can
change. Generate from a current locally decompiled template whenever possible.
A representative historical structure is:

```text
<!-- kv3 encoding:text:version{...} format:generic:version{...} -->
{
    _class = "CNmClipDocument"
    m_nVersion = 1
    m_sourceFilename = "models/<namespace>/<item>/source/idle_<item>.dmx"
    m_animationSkeletonName = "animation/skeletons/characters/viewmodel.vnmskel"
    m_bonesToSampleInModelSpace = [ ]
    m_secondaryAnimationSkeletonNames =
    [
        "animation/skeletons/weapons/<proxy>.vnmskel"
    ]
    m_eventTracks = [ ]
    m_nStartFrame = 0
    m_nEndFrame = -1
    m_flDurationOverrideSeconds = -1.0
    m_additiveType = "None"
}
```

The header UUIDs, class fields, and accepted enum spelling are build-dependent.
Generate from a current Workshop Tools document or a locally inspected,
hash-gated current resource, then preserve every field not intentionally
changed. Do not distribute Valve-derived source material.

Use the primary character skeleton for the graph's character pose. Add the
weapon/object skeleton as a secondary skeleton only when the clip contains and
needs those channels. Do not point a first-person clip at the worldmodel
skeleton or vice versa.

Events are part of behavior. Preserve or author required events deliberately;
do not copy stock muzzle, ammo, reload, or fire-complete events into a non-gun
action without understanding their runtime effect.

### Loop ownership

In current inspected documents, the referencing graph clip node owns looping
(for example, a build-specific `CNmGraphDocClipNode.m_bAllowLooping`), not the
`CNmClipDocument` shown above. Set it deliberately and recheck the current
schema:

```text
idle / optional hold loop       true
draw / attack / reload          false
finish / cancel / sentinels     false
```

A completion transition must not wait on a looping node. Split a held action
into a non-looping start, optional looping hold, and non-looping finish/cancel.
Inspect loop ownership in the compiled graph and confirm it at runtime.

## 6. Compilation

Prefer Workshop Tools and its current `resourcecompiler.exe`. Compile from the
content addon into the matching game addon. Use explicit source and output roots
in scripts; do not depend on the shell's current directory.

`-game` identifies the game/mod directory that contains `gameinfo.gi`; it is not
the addon output directory. With an input under
`content/csgo_addons/<addon>`, ResourceCompiler derives the matching output under
`game/csgo_addons/<addon>` from the configured content paths.

A representative command shape is:

```powershell
& "<CS2>\game\bin\win64\resourcecompiler.exe" `
  -i "<CS2>\content\csgo_addons\<addon>\models\<namespace>\<item>\clips\idle_<item>.vnmclip" `
  -game "<CS2>\game\csgo"
```

Flags can change. Capture the actual command and compiler output used by the
current installation.

Compile in dependency order:

```text
1. optional private skeletons
2. VNMClip documents
3. weapon-specific variation graphs
4. category/action child graphs
5. private root graphs
6. textures and materials
7. owner and world object models
8. player model
9. optional icons, particles, and scripts
```

Fail the build on missing outputs and inspect warnings. A zero exit code does
not prove that the source skeleton, graph route, or clip semantics are correct.

Use a build script that:

```text
validates inputs
removes only declared generated outputs
compiles in dependency order
captures stdout/stderr
checks every expected output
hashes outputs
writes a manifest
```

Never recursively clean an addon that contains unrelated work.

## 7. Compiler Registration Recovery

After a Steam verification or tools repair, ResourceCompiler may report that no
compiler exists for Nm resources. In affected builds, the installed
`game/bin/assettypes_common.txt` omitted registrations equivalent to:

```text
vnmgraph -> CompileNmGraph
vnmskel  -> CompileNmSkeleton
vnmclip  -> CompileNmClip
```

This is a version-sensitive local toolchain repair, not an addon asset. Do not
perform it merely because a guide mentions it: first reproduce the missing
compiler error and obtain the user's explicit approval to edit the installed
toolchain. Work from an offline backup and never redistribute the modified
Valve file. Before changing anything:

1. close CS2 and Workshop Tools;
2. hash and back up the current file;
3. compare it with a matching known-good file from the same tools build;
4. restore only the missing mappings with the exact surrounding syntax;
5. restart Workshop Tools and compile a tiny probe;
6. record the before/after hashes and expect Steam verification to restore it.

Do not blindly paste an old entire `assettypes_common.txt` over a new build.
Other editor features, such as Particle Editor registrations, may be controlled
by nearby asset-type blocks but are separate from Nm compilation.

Require an exact preimage hash, a narrow managed diff, and a guarded restore.
Refuse an updated or unknown preimage. Never package this base-file repair or
apply it automatically to production clients or servers.

## 8. Compiled-Resource Inspection

Open every generated `.vnmclip_c`, `.vnmgraph_c`, and `.vmdl_c` in
Source2Viewer, ValveResourceFormat, or another parser that understands the
current format.

For a clip, verify:

```text
source and primary skeleton
secondary skeletons
duration and frame range
first/last-frame continuity and loop suitability
event tracks
bone/channel names and counts
first, middle, and final poses
hands, fingers, object orientation, and camera framing
```

Inspect the corresponding VNMGraph clip/state node for its looping and reset
policy (for example, a build-specific field such as `m_bAllowLooping`). Confirm
the actual loop at runtime. Do not infer graph looping from the VNMClip source
alone.

For a model, verify:

```text
mesh and material references
skeleton and attachments
owner/world scale and origin
bodygroups
AnimGraph2 named references and default graph
transitive resource paths
```

Create screenshots or machine-readable inspection reports. Comparing only file
timestamps or sizes is insufficient.

## 9. Build Manifest

Keep a machine-readable build manifest and versioned, non-overwriting run
receipts beside the project evidence. These receipts are not cryptographically
signed; archive or sign them externally when tamper evidence matters. Do not
assume the evidence manifest itself belongs inside a Workshop VPK. At minimum
record:

```json
{
  "project_namespaces": [],
  "artifact_policy": {
    "status": "blocked",
    "basis": "redistribution basis not established",
    "template_derivative_basis": "VNMClip template rights not established"
  },
  "game_revision": "recorded-current-build",
  "tool_versions": {},
  "tool_hashes": {},
  "source_hashes": {},
  "stock_reference_hashes": {},
  "sources": [],
  "commands": [],
  "expected_outputs": [],
  "output_hashes": {},
  "workshop_destinations": [],
  "validation": {
    "compiled_resource_inspection": "pending",
    "workshop_vpk": "pending",
    "first_person": "pending",
    "third_person": "pending"
  },
  "known_limitations": []
}
```

Mark generated versus hand-authored files and connect every output to its exact
template and transitive inputs. `compiled` proves tool acceptance; it does not
prove redistribution rights. Keep artifact production blocked until a concrete
basis covers every byte copied into the handoff. Do not include private keys,
server tokens, passwords, or redistributed Valve assets.
