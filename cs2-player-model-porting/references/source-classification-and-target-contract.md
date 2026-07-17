# Source Classification And Target Contract

Use this reference to classify inputs, inventory untouched assets, extract
the current canonical CS2 player contract, map the source rig semantically,
and normalize orientation and scale before retargeting.

Record creator, source URL/path, license or permission, and redistribution
restrictions during inventory. Stop when the user cannot establish authority to
modify the input. Unknown or incompatible redistribution rights set distribution
status to `blocked`: local authorized inspection and technical validation may
continue, but packaging, publication, and distributable completion must stop.

## Contents

1. Classify the source
2. Inventory the source
3. Establish the target contract
4. Build a semantic rig profile
5. Normalize source orientation and scale

## Phase 1: classify the source

Choose the pipeline before editing anything.

### Existing Source 2 model

Typical inputs: `.vmdl_c`, `.vmat_c`, `.vtex_c`, compiled Source 2 resources.

1. Decompile with Source2Viewer or ValveResourceFormat.
2. Prefer the decompiled DMX and ModelDoc representation.
3. Preserve original bind transforms, vertex weights, UVs, and material slots.
4. Add or update the current AnimGraph2 and runtime model contract.
5. Recompile and inspect DATA, MDAT, and PHYS blocks.

Avoid a VMDL_C -> glTF -> automatic weights round trip. It can discard exact
bind information and produce a model that looks correct at rest but explodes in
reload, crouch, or defuse animations.

Keep DMX as the final interchange format when it preserves the exact source
bind and skinning contract. Do not force this branch through FBX merely because
the generic-source branch uses it. Record the selected final interchange format
in the build report and run format-specific assertions on that artifact.

### Source 1 model

Typical inputs: `.mdl`, `.vvd`, `.vtx`, optional `.phy`, `.vmt`, and `.vtf`.

1. Verify all MDL sidecars before import.
2. Import through SourceIO or another importer that preserves skeleton and
   weights.
3. Preserve the original weighted mesh and bind pose.
4. Retarget to the current CS2 skeleton with a method that does not blindly
   copy incompatible axial bone roll.
5. Build current hitboxes and physics independently of the Source 1 `.phy`.

An MDL without matching VVD/VTX data is usually incomplete.

### Generic rigged model

Typical inputs: FBX, DAE, glTF, or BLEND with an armature, static pose, or a
sample `Motion` animation.

1. Import without baking source animation into the final player.
2. Identify the actual deform armature when control rigs also exist.
3. Measure source anatomy and bind matrices.
4. Map bones by anatomical role.
5. Retarget geometry and remap weights to canonical groups.
6. Assign every accessory through an explicit policy.

A sample animation proves that skinning exists. CS2 AnimGraph2 still drives the
final model.

### Static or unusably rigged model

Treat this as a new rigging task. Fit the mesh to a compatible canonical body,
transfer or paint weights, and validate every major articulation. Do not present
automatic weights as a simple conversion.

## Phase 2: inventory the source

Generate a source report before modifying the scene. Include:

- files and hashes;
- object, mesh, material, armature, animation, and shape-key inventory;
- candidate deform armatures and modifier links;
- bone names, parent hierarchy, heads, tails, local matrices, and deform flags;
- world-space bounds and forward/up axes;
- vertex and polygon counts per object;
- connected-component counts and bounds;
- material slots, texture paths, UV layers, alpha ranges, and normal maps;
- vertex groups, weighted-vertex counts, total weights, and maximum influences;
- zero-weight vertices and non-normalized vertices;
- source animations used only for diagnosis;
- visible accessories and intentionally absent anatomy.

Render the untouched source from front, side, three-quarter, and rear views.
These images are the geometric reference, not merely presentation renders.

## Phase 3: establish the target contract

Extract from a current official CS2 player model:

- worldmodel skeleton resource;
- viewmodel skeleton resource when required;
- world, UI, and view AnimGraph2 references;
- skeleton hierarchy and model-space bind transforms;
- bodygroup ordering and mesh masks;
- attachment names and parent bones;
- hitbox set;
- physics shapes, body markup, compiled masses, and joints.

Reconstruct the target armature exactly. Preserve bone names, parentage, model
space transforms, and required helper or attachment bones even when the custom
mesh does not use them.

Typical anatomical targets include:

```text
root_motion
pelvis
spine_0 ... spine_3
neck_0
head_0
clavicle_L/R
arm_upper_L/R
arm_lower_L/R
hand_L/R
finger_*_L/R
leg_upper_L/R
leg_lower_L/R
ankle_L/R
ball_L/R
wpnPivot
wpn
```

Use a tiny invisible weighted keeper mesh if the FBX exporter would otherwise
drop required unweighted bones. The keeper does not replace hitboxes or
physics.

## Phase 4: build a semantic rig profile

Represent each source binding independently:

```text
source group -> target weight group, source transform anchor, binding mode
```

Keeping target weight and transform anchor separate is essential. Several
source helper bones may merge into one CS2 group while still requiring distinct
source-space transforms.

Map the major chains first:

- root and pelvis;
- lower, middle, and upper spine;
- neck and head;
- clavicle, upper arm, forearm, hand, and fingers;
- thigh, calf, foot, and toe.

Then classify every remaining weighted source group:

- anatomical mapping;
- twist/helper merged into an anatomical segment;
- rigid accessory anchored to head, torso, pelvis, or limb;
- intentionally removed component;
- invalid/unmapped, which must fail the build.

Do not infer left/right from a single naming convention. Confirm positions and
parent chains.

## Phase 5: normalize source orientation and scale

Correct coordinate conventions before measuring bones:

1. determine the source forward and up axes;
2. apply the orientation correction to the armature and all meshes together;
3. update world matrices;
4. only then measure source joints and segment lengths;
5. store the correction in the rig profile and build report.

Estimate global scale from the median of several reliable anatomical ratios,
not from one total-height measurement. Use symmetric limbs and torso spans.
Reject outliers and degenerate segments.

Continue with
[retargeting-skinning-and-geometry.md](retargeting-skinning-and-geometry.md)
only after source provenance and target-contract hashes are recorded.
