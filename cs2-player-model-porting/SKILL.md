---
name: cs2-player-model-porting
description: Port, repair, compile, and validate custom Counter-Strike 2 player models for the current AnimGraph2 runtime from Source 2 VMDL_C/DMX, Source 1 MDL, FBX, DAE, glTF, or Blender sources. Use for source classification, canonical skeleton extraction, bind-pose retargeting, skin-weight repair, accessories, first-person geometry, ModelDoc authoring, materials, bullet hitboxes, compiled physics/ragdolls, and static or animated QA.
---

# CS2 Player Model Porting

Build a reproducible player-model port that uses the current CS2 player
skeleton and AnimGraph2 contract. Treat geometry, animation, rendering,
first-person visibility, bullet hit detection, and ragdoll physics as separate
contracts. A successful compile proves only that the resource compiler accepted
the files.

Keep this skill model-focused. Distribution and infrastructure are outside its
scope.

## Required tools

Discover installed paths instead of assuming fixed locations:

- CS2 with its authoring toolchain and `resourcecompiler.exe`;
- Blender with a version compatible with the chosen import/export add-ons;
- Source2Viewer or ValveResourceFormat CLI for Source 2 inspection;
- SourceIO or an equivalent importer for Source 1 assets;
- an image tool capable of preserving color space and alpha;
- scripts for deterministic inspection, retargeting, compilation, and QA.

Use the current game installation as the authority for skeletons, graph
references, bodygroups, hitboxes, and physics. Valve may change these resources.

## Non-negotiable rules

1. Preserve every original source file as read-only.
2. Build into a separate deterministic work directory.
3. Record source paths, file hashes, tool versions, commands, and outputs.
4. Extract the current canonical skeleton; never redraw it by eye.
5. Preserve source skinning unless evidence proves that it is unusable.
6. Change one hypothesis at a time and compare measurable A/B outputs.
7. Fail on unknown bones, missing weights, changed topology, or missing files.
8. Inspect the compiled VMDL_C, not only the editable VMDL.
9. Validate real animation states before declaring success.
10. Never hide an anatomical defect by deleting expected visible geometry.

## Definition of success

A finished port must have:

- the exact current canonical worldmodel skeleton and hierarchy;
- only valid target vertex groups;
- zero unweighted vertices;
- normalized finite weights with no more than four influences per vertex;
- a visually correct third-person mesh;
- controlled first-person geometry;
- current AnimGraph2 skeleton and graph references;
- canonical weapon attachments;
- a bullet hitbox set;
- physical shapes, body markup, non-zero masses, and ragdoll joints;
- correct opaque, masked, or translucent materials;
- static, stress-pose, compiled-resource, and in-game validation evidence;
- a machine-readable build report.

Do not hardcode historical bone, hitbox, body, joint, or mass counts as eternal
truth. Record them from the current official reference model and assert that the
port matches that reference. A commonly observed humanoid contract has 74
worldmodel bones, 19 hitboxes, 15 physics bodies, and 14 ragdoll joints, but the
installed game remains authoritative.

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

## Phase 6: retarget bind geometry

### Full-matrix retargeting

For compatible bind bases, transform a source-bound point with:

```text
p_target = M_target * inverse(M_source) * p_source
```

This preserves full orientation, including axial roll. It is appropriate only
when source and target bone bases are genuinely compatible.

### Swing-scale retargeting

Use this for many Source 1 or custom rigs whose joint positions are sound but
whose axial rolls differ from CS2.

For source segment `a -> b` and target segment `A -> B`:

```text
source_vector = b - a
target_vector = B - A
rotation = shortest_rotation(normalize(source_vector), normalize(target_vector))
parallel_scale = length(target_vector) / length(source_vector)
```

Decompose each point offset into parallel and perpendicular components:

```text
offset = p - a
parallel = axis * dot(offset, axis)
perpendicular = offset - parallel
p_target = A + rotation * (
    parallel * parallel_scale + perpendicular * perpendicular_scale
)
```

Use a stable global or profile-specific perpendicular scale to preserve limb
volume. This aligns the limb while avoiding arbitrary source twist transfer.

For a vertex with several influences, accumulate transformed positions and
target weights:

```text
p_final = sum(weight_i * transform_i(p_source)) / sum(valid_weight_i)
```

Normalize remapped target weights afterward.

### Reject pathological segments

Do not use anisotropic segment transforms when a source segment is:

- nearly zero length;
- reversed relative to the anatomical chain;
- almost perpendicular because it is a helper, not a deform segment;
- discontinuous or based on a control rig.

Use a uniform transform inherited from the nearest healthy anatomical anchor,
or create a model-specific corrective mapping. Adding an epsilon to a bad
segment does not repair its direction.

### Preserve joint continuity

Transforms for adjacent bones must agree at shared joints. Test elbow, knee,
wrist, ankle, neck, and finger boundaries. A model can have correct bone names
and weights yet tear because neighboring bind transforms disagree.

## Phase 7: repair skin weights

After retargeting, require:

- zero unweighted vertices;
- finite non-negative weights;
- sum approximately equal to one;
- no more than four dominant influences;
- no target group absent from the canonical skeleton;
- smooth transitions at deforming joints;
- rigid weights only for genuinely rigid accessories.

Prefer source weights over automatic weights. Repaint only when the source rig
is missing, corrupt, or anatomically incompatible.

### Twist bones

Do not delete every `TWIST`, `ROLL`, or helper group by name.

1. count vertices and total weights for the group;
2. inspect its parent chain and bind axis;
3. prove that the visual defect follows that group;
4. compare an A/B build;
5. merge into the nearest anatomical segment only when justified.

An unchanged defect after removing twist groups usually means the real problem
is bind roll or transform selection.

### Abrupt rigid boundaries

Connected faces can stretch when adjacent vertices are rigidly assigned to
different target anchors. Common examples are collar-to-spine and neck-to-head
boundaries.

Detect them by comparing source and final edge lengths. For each matching edge:

```text
ratio = final_length / source_aligned_length
distortion = max(ratio, 1 / ratio)
```

Investigate high distortion together with absolute length change. Repair the
semantic mapping first. If the boundary is genuinely deformable, blend a small
seam ring across the two anatomical groups and validate it under animation.

Do not use a broad weight-paint brush before identifying the exact groups and
vertices responsible.

## Phase 8: preserve topology and seams

Inventory connected components before deleting or reassigning anything. One
source object may contain several unrelated pieces, while one visible feature
may span several objects.

### Coincident component boundaries

Visually joined components may contain duplicate boundary vertices. Capture
coincident clusters before retargeting using a scale-aware tolerance. After
retargeting, enforce both invariants:

1. matching boundary vertices share the same position;
2. matching boundary vertices share the same normalized target weights.

Welding only positions can close the rest pose while allowing the seam to open
during animation.

### Wrong accessory binding

If a connected collar or armor component alternates between torso and shoulder
groups, mapping one helper group to a distant clavicle can create long black
triangles. Inspect both endpoints of the stretched edge and remap the incorrect
source group to the transform used by the rest of that connected component.

### Proportional neck corrections

Treat a long or forward neck as a rig and weight problem first:

1. compare source and final head, neck, and upper-spine joint locations;
2. inspect head/neck crossing edges and their weights;
3. verify collars, hair, jewelry, and shoulders use compatible anchors;
4. correct group mapping or seam blending;
5. validate with animated head and upper-body motion.

A world-space height warp is a last resort for genuine proportion mismatch. It
must affect all relevant visible components continuously and can still produce
bad animation pivots. A better-looking rest pose is not proof that the rig is
fixed.

## Phase 9: handle accessories and unusual anatomy

Create an explicit policy for every non-canonical feature. Typical fallbacks:

- hair, horns, earrings, and rigid face ornaments -> `head_0`;
- upper cape, wings, or rigid back arms -> upper spine;
- tail -> pelvis or a deliberate retained chain;
- skirt panels -> pelvis or thighs according to desired motion;
- rigid wrist or ankle armor -> corresponding limb segment;
- intentionally invisible anatomy -> keep canonical bones, hitboxes, and
  physics even when no visible mesh uses them.

Delete by connected component with assertions, not merely by object name. A
single object can mix a removable rope or weapon with valid hair or armor.

Record expected vertex and polygon counts for every removal. Fail if source
topology changes instead of silently deleting a different component.

## Phase 10: author first-person geometry

Do not assume the third-person mesh is safe near the camera. Build a dedicated
first-person mesh when the full body can expose claws, wings, ropes, torso,
shoulder panels, or long nails.

1. duplicate from the final retargeted world geometry;
2. preselect allowed source objects;
3. filter by arm, hand, and finger weights;
4. split and inspect connected components;
5. remove non-anatomical islands only from the first-person duplicate;
6. preserve the exact target skeleton with a keeper if necessary;
7. validate knife, pistol, rifle, reload, and inspect poses.

A weight threshold alone is insufficient. Shoulder or torso panels can be
fully weighted to clavicles and still appear in front of the camera.

To identify a floating first-person fragment, move the camera through another
instance of the world model. If the same fragment remains visible, repair the
world geometry or proximity behavior rather than only the first-person mesh.

## Phase 11: build materials correctly

Map every source slot explicitly to a Source 2 material.

Use:

- opaque rendering for ordinary skin, cloth, and armor;
- alpha test or masked rendering for hair cards, holes, and hard cutouts;
- translucency only for genuinely transparent surfaces;
- a shader that actually compiles the required self-illumination inputs for
  emissive regions.

Avoid global blend/translucency for cutout textures. It can make the entire
character appear ghostlike and introduce sorting artifacts.

Validate:

- albedo color space;
- normal-map interpretation and channel convention;
- alpha range and intended cutoff;
- roughness/metalness inputs;
- emissive mask in the compiled material data;
- backface policy;
- all material remaps in the compiled model.

A local transparent-looking hole may be separated topology, inverted normals,
or divergent seam weights even when the material is fully opaque.

## Phase 12: author the ModelDoc runtime contract

Derive the exact structure from a current official player model. The editable
VMDL normally needs equivalents of:

- `RenderMeshList`;
- ordered bodygroups for third- and first-person choices;
- `MaterialGroupList` and remaps;
- `AttachmentList`;
- `HitboxSetList`;
- `PhysicsShapeList`;
- `GameDataList` with physics body markup;
- `NmSkeletonList`;
- `AnimGraph2List`.

Reference the current worldmodel and viewmodel skeleton resources and the
current world, UI, and view AnimGraph2 graphs. Do not rely only on legacy
animation includes or historical graph-name fields.

Preserve canonical weapon attachments such as the weapon pivot, weapon bone,
and left/right hand attachments. Verify their compiled parent hierarchy.

## Phase 13: add bullet hitboxes

Physics shapes are not bullet hitboxes. Add the current official player hitbox
set separately and bind each shape to a valid canonical bone.

Cover head, neck, torso, pelvis, arms, hands, thighs, lower legs, and feet as
defined by the current official reference. Audit the compiled VMDL_C to confirm
that the hitbox set survived compilation.

Typical symptom of missing hitboxes: the character renders and animates, and
melee may still interact, but firearm traces pass through it.

## Phase 14: build a real ragdoll

Treat these as four independent layers:

1. bullet hitbox set;
2. editable physics shapes;
3. shape-to-bone gameplay markup;
4. compiled PHYS bodies with non-zero masses and joints.

ModelDoc can compile visible physics shapes while producing zero masses or no
joints. The resulting player may remain standing after death and then vanish.

If the compiler cannot reproduce the required PHYS payload:

1. extract a current official humanoid player as donor;
2. verify identical canonical bone identities and compatible body layout;
3. compile the custom model normally;
4. copy or patch only the required compiled physics contract;
5. re-audit body count, non-zero masses, total mass, joints, markup, and shapes;
6. test death while observing the player in third person.

Do not copy a compiled PHYS block between incompatible skeletons or body
layouts.

## Phase 15: use a deterministic build pipeline

Automate this order:

1. validate tools and source files;
2. hash and inventory the source;
3. prepare textures atomically;
4. run Blender in background/factory mode;
5. import and normalize source orientation;
6. reconstruct the canonical target armature;
7. retarget world geometry and weights;
8. repair asserted seams/components;
9. produce first-person geometry when needed;
10. export FBX without source animations or leaf bones;
11. write materials and ModelDoc;
12. compile with `resourcecompiler.exe`;
13. patch compiled physics only when required;
14. inspect compiled DATA, MDAT, and PHYS;
15. render QA views and write the final report.

Use temporary files plus atomic replacement for generated textures and reports.
External tools may temporarily lock files.

## Phase 16: validate in layers

### Source-versus-final geometry

Align source and final models by pelvis, recorded yaw, and measured scale. Render
matching front, side, three-quarter, and rear views. Compare:

- silhouette and proportions;
- head/neck/shoulder relation;
- limb volume;
- feet and ground contact;
- accessory placement;
- connected-component bounds;
- matching edge-length distortion;
- source and final weight groups at suspicious vertices.

Do not inspect only the final model. The source is required to distinguish a
source design choice from a retargeting regression.

### Static FBX assertions

Check:

- canonical bone names and hierarchy;
- zero unknown groups;
- zero unweighted or non-normalized vertices;
- four influences maximum;
- expected world and first-person components;
- expected material slots and UVs;
- no unintended source animation;
- no NaN/Inf coordinates or extreme bounds.

### Stress poses

Exercise each chain independently:

- spine bend and twist;
- head yaw, pitch, and roll;
- shoulders raised and crossed;
- elbows near full flexion;
- wrists rotated;
- fingers curled;
- hips flexed and abducted;
- knees deeply bent;
- ankles and toes flexed.

Render front, side, three-quarter, and rear views. A correct rest pose does not
validate bind transforms.

### Compiled-resource audit

Inspect the final VMDL_C for:

- target skeleton and parent hierarchy;
- AnimGraph2 graph references;
- world and first-person mesh choices/masks;
- material remaps;
- weapon attachments;
- bullet hitboxes;
- physics shapes and markup;
- non-zero masses and ragdoll joints.

### In-game model validation

Test at minimum:

- idle and movement in several directions;
- crouch;
- jump and landing;
- weapon aim and reload;
- defuse or another upper-body interaction;
- knife, pistol, and primary weapon;
- first-person visibility;
- third-person observation;
- dynamic shadow;
- firearm hits on head, torso, arms, and legs;
- death and ragdoll fall.

Record the exact artifact hash used for the test.

## Build report schema

Write JSON containing at least:

- source path, hash, and source type;
- tool versions;
- target reference path/hash/version;
- orientation and unit scale;
- source-to-target mapping and fallback policy;
- transform method per source group;
- objects, components, vertices, polygons, and materials;
- removed or repaired component evidence;
- zero-weight, normalization, and influence statistics;
- source/final edge-distortion summary;
- first-person component statistics;
- compiled skeleton, graph, attachment, hitbox, and physics audit;
- QA image paths and hashes;
- validation status and known limitations.

Use statuses such as `source-inspected`, `fbx-validated`, `compiled-validated`,
and `in-game-validated`. Never collapse them into one ambiguous `success` flag.

## Diagnostic matrix

| Symptom | Primary evidence | Likely cause | Corrective action |
| --- | --- | --- | --- |
| Model explodes in defuse/reload | source DMX differs from rebuilt FBX | bind/weights reconstructed unnecessarily | preserve Source 2 DMX and original skinning |
| One limb twists about 180 degrees | joints align but axial bases differ | source roll copied by full matrix | use swing-scale and source weights |
| Removing twist groups changes nothing | groups have zero/negligible weights | wrong diagnosis | inspect bind transforms and weighted groups |
| Thin thigh, wrist, or ankle | segment dimensions collapse | wrong perpendicular scale | separate longitudinal and volume scale |
| Head or torso flips | tiny/reversed source segment | invalid anisotropic transform | inherit uniform transform from healthy anchor |
| Long black triangles at collar | endpoints use distant anchors | wrong accessory group mapping | remap the whole connected piece to compatible anchor |
| Gap at head/neck seam | rigid 100/0 boundary stretches | incompatible head/neck transforms | blend seam ring and validate head motion |
| Neck looks improved only at rest | arbitrary spatial warp | pivots/weights still wrong | compare source joints and fix rig semantics |
| Waist opens during animation | coincident boundaries have different weights | position-only seam repair | unify both positions and weights |
| Local area appears transparent | opaque material but visible hole | seam, normals, or topology | inspect components and face orientation |
| Entire model looks ghostlike | global translucent/blend material | wrong alpha mode | use opaque or alpha test as appropriate |
| Emissive color is missing | source VMAT text looks correct | shader/compiler dropped emissive input | inspect compiled material and use compatible shader |
| Floating piece in first person | component follows arm/clavicle | incomplete first-person filtering | inspect connected components, not weights alone |
| Fix removes a finger | whole component deleted | symptom hidden by geometry removal | restore component, shorten/reweight it |
| Bullets pass through | compiled hitbox set missing | physics shapes mistaken for hitboxes | add and audit official hitbox contract |
| Player stays standing after death | masses zero or joints absent | incomplete compiled PHYS | patch from compatible current official donor |
| Model is correct at rest but bad in motion | bind or transition defect | validation stopped too early | run isolated stress poses and game animations |

## Completion gate

Declare the port complete only when all are true:

1. the build is reproducible from untouched sources;
2. source and target contracts are recorded;
3. static FBX assertions pass;
4. source-versus-final renders show no unexplained regression;
5. stress poses show no tearing, twisting, collapse, or floating components;
6. compiled AnimGraph2, attachments, hitboxes, and physics pass inspection;
7. first-person and third-person geometry are both controlled;
8. firearm traces hit all expected regions;
9. death produces a real articulated ragdoll;
10. the exact tested artifact hash and remaining limitations are recorded.

If only compilation and static QA have passed, report `compiled-validated,
in-game validation pending`. Do not call it finished.
