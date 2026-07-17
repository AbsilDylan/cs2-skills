# Materials, ModelDoc, Hitboxes, And Physics

Use this reference for character materials, wiring the player ModelDoc to
current existing runtime resources, bullet hitboxes, and ragdoll physics.

Prerequisite: validate the final retargeted geometry and weights with
[retargeting-skinning-and-geometry.md](retargeting-skinning-and-geometry.md).

## Contents

1. Build materials correctly
2. Wire the player ModelDoc runtime contract
3. Add bullet hitboxes
4. Build a real ragdoll

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

## Phase 12: wire the player ModelDoc runtime contract

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

This phase wires existing current graph resources into a player model. Creating
or patching VNMClip/VNMGraph resources, private roots, weapon variations, or
runtime `weapon_type` routing belongs to `$cs2-animgraph2-authoring`.

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

First reproduce the current contract in editable project-owned ModelDoc and
physics sources. If ResourceCompiler still cannot emit the required PHYS
payload, completion is blocked. A current official humanoid may still be used
locally as a diagnostic reference only:

1. hash the exact reference build and compare skeleton/body compatibility;
2. compile the custom model normally;
3. run an experimental PHYS transformation only when a separately reviewed,
   project-local tool declares exact input hashes, an exact-build guard, a
   machine-readable operation manifest, output hashes, and rollback; never
   modify the base-game resource;
4. re-audit body count, non-zero masses, total mass, joints, markup, and shapes;
5. test death while observing the player in third person;
6. label the result `experimental-diagnostic`; it cannot satisfy the completion
   gate or enter a release artifact without a separately proven editable or
   reviewed reproducible pipeline and permitted provenance;
7. keep distribution status `blocked` unless the final artifact is generated
   from redistributable inputs and its provenance permits publication.

Do not copy a compiled PHYS block between incompatible skeletons or body
layouts. A recipe does not automatically make donor-derived bytes
redistributable. Keep Valve-derived references local and hash-gated, and never
publish a donor payload or derivative without established rights.

Continue with
[build-validation-and-diagnostics.md](build-validation-and-diagnostics.md) and
do not claim completion from ModelDoc or PHYS compilation alone.
