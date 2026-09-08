# Retargeting, Skinning, And Geometry

Use this reference after the source and target contracts are recorded. It
covers bind-geometry retargeting, skin-weight repair, topology and seams,
accessories, and first-person player-body geometry.

Prerequisite: complete
[source-classification-and-target-contract.md](source-classification-and-target-contract.md)
for the current input and game build.

## Contents

1. Retarget bind geometry
2. Repair skin weights
3. Preserve topology and seams
4. Handle accessories and unusual anatomy
5. Author first-person player geometry

## Diagnose a custom grip before retargeting

If the approved agent is correct with stock items and deforms only with a new
weapon pose, first compare final IK/helper transforms and local hand/finger
channels using `$cs2-animgraph2-authoring`. Solve after applicable motion layers
and preserve bone lengths, scales and phalanx translations. A long thumb can
come from a misplaced target or changed local translation, not defective mesh
proportions. Do not stretch or delete anatomy to make a grip reach.

Render the actual agent/gloves beside the reference-hand diagnostic. A stock
hand that fits does not prove a bulky custom glove fits. Conversely, a failed
preview reconstructed with different twist/bind frames does not prove the
original compiled agent is defective. Zero unmapped weights measures mapping
coverage, not skinning fidelity. Preserve original skinning until a stock/custom
pose comparison isolates a mesh or bind defect.

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
- no more than four non-zero influences after pruning and renormalization;
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
- tail -> pelvis by default; retain a custom chain only after proving that the
  current ModelDoc/compiler/runtime graph accepts it, recording it as an
  explicit extension to the canonical contract, and updating the undeclared-bone
  assertions accordingly;
- skirt panels -> pelvis or thighs according to desired motion;
- rigid wrist or ankle armor -> corresponding limb segment;
- intentionally invisible anatomy -> keep canonical bones, hitboxes, and
  physics even when no visible mesh uses them.

Delete by connected component with assertions, not merely by object name. A
single object can mix a removable rope or weapon with valid hair or armor.

Record expected vertex and polygon deltas for every declared removal. Preserve
the untouched source and fail if its topology changes, or if working/final
topology differs from the declared operation instead of silently deleting a
different component.

## Phase 10: author first-person player geometry

Do not assume the third-person mesh is safe near the camera. Build a dedicated
first-person mesh when the full body can expose claws, wings, ropes, torso,
shoulder panels, or long nails.

1. duplicate from the final retargeted world geometry;
2. preselect allowed source objects;
3. filter by arm, hand, and finger weights;
4. split and inspect connected components;
5. remove non-anatomical islands only from the first-person duplicate;
6. preserve every required canonical target bone with a keeper if necessary;
7. validate knife, pistol, rifle, reload, and inspect poses.

A weight threshold alone is insufficient. Shoulder or torso panels can be
fully weighted to clavicles and still appear in front of the camera.

Treat hand-bound accessories and effects as explicit first-person components.
A world-model sphere, aura, rope end, weapon-adjacent prop, or rigid claw does
not automatically enter the dedicated first-person mesh merely because it is
weighted to a hand or finger. Add every intended source object and material
slot to the first-person export/bodygroup allowlist, then assert the expected
component count in the editable and compiled model. Preserve its validated
hand/finger binding, but exclude the accessory objects from anatomical wrist
weight envelopes or other body-only smoothing passes. Otherwise an effect can
be absent in first person, or become distorted while the arm repair itself is
correct. Validate attachment position and translucency separately because an
opaque DCC viewport does not prove the compiled in-game material result.

To identify a floating first-person fragment, move the camera through another
instance of the world model. If the same fragment remains visible, repair the
world geometry or proximity behavior rather than only the first-person mesh.

### Repair wrist twist in a compact first-person skeleton

A wrist can look correct in third person but collapse in knife or pistol view
when the first-person duplicate has an abrupt `arm_lower_*` to `hand_*` weight
boundary. Audit the skeleton before blaming missing twist bones. Some valid AG2
player contracts use a compact skeleton that intentionally has no
`arm_lower_*_TWIST` bones. Do not invent those bones unless the active skeleton
and animation clips both contain them.

For a compact skeleton:

1. measure weights along the segment from the lower-arm pivot to the hand pivot;
2. count rigid lower-arm, rigid hand, and blended vertices near the wrist;
3. duplicate the already validated world mesh for first person;
4. preserve finger-weighted vertices and unrelated influences;
5. redistribute only the combined lower-arm/hand weight through a smoothstep
   envelope around the wrist;
6. normalize, enforce the influence cap, and record changed vertex counts;
7. validate both sides under asymmetric knife, pistol, reload, and inspect poses.

A useful normalized coordinate is `t = dot(vertex - lower_arm_head, axis) /
segment_length`, where `t=1` is the hand pivot. Start the blend before the
visible wrist and finish slightly beyond the pivot. Keep the correction on the
first-person duplicate when the world model is already validated. The exact
interval is model-specific and must be derived from weight histograms and pose
renders rather than copied blindly.

Continue with
[materials-modeldoc-and-physics.md](materials-modeldoc-and-physics.md) after
world and first-person geometry pass static and stress-pose checks.
