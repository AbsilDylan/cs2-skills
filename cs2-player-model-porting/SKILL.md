---
name: cs2-player-model-porting
description: "Port, diagnose, repair, and validate CS2 player assets: skeletons, weights, topology, materials, first-person geometry, hitboxes, ragdolls, and Workshop closure. Excludes item graphs and NPC runtime."
---

# CS2 Player Model Porting

Build a reproducible player-character port against the current CS2 player
skeleton and runtime contract. Treat geometry, animation compatibility,
rendering, first-person visibility, bullet hit detection, and ragdoll physics as
separate contracts. A successful compile proves only that ResourceCompiler
accepted the files.

Use the current installed game as the authority. Valve can change skeletons,
bodygroups, attachments, graph references, hitboxes, and physics contracts.

## Scope And Handoff

This skill owns the player-character asset: mesh, canonical player skeleton,
bind pose, weights, character materials, player ModelDoc, bullet hitboxes,
ragdoll physics, player-body geometry visible in first person, and the
player-model/material resource closure required for clean-client delivery.

Selecting current existing world/UI/view graph resources in ModelDoc is model
wiring and remains in scope. Creating or patching VNMClip/VNMGraph resources,
private item graph roots, weapon/item variations, proxy prediction, or item
runtime routing belongs to `$cs2-animgraph2-authoring`. Server-controlled model
entity ownership, AI, navigation, combat, and cleanup belong to
`$cs2-server-npc-runtime`; materializing or driving an existing NPC
`CBaseAnimGraphController` belongs to `$cs2-ag2-npc-runtime`.

When several skills are needed, complete and validate the player-character
asset first. Hand its compiled model and ModelDoc item graph slots to
`$cs2-animgraph2-authoring`, or hand the body to `$cs2-server-npc-runtime` and
add `$cs2-ag2-npc-runtime` only for NPC animation presentation.

## Load The Relevant References

For a complete port, read all four references in order. For a focused repair,
load the applicable reference and the validation reference before claiming
success.

- Read [source-classification-and-target-contract.md](references/source-classification-and-target-contract.md)
  for source classification, inventory, canonical target extraction, semantic
  mapping, orientation, and scale.
- Read [retargeting-skinning-and-geometry.md](references/retargeting-skinning-and-geometry.md)
  for bind transforms, weight repair, seams, accessories, and first-person
  player-body geometry.
- Read [materials-modeldoc-and-physics.md](references/materials-modeldoc-and-physics.md)
  for character materials, player ModelDoc wiring, bullet hitboxes, and ragdoll
  physics.
- Read [build-validation-and-diagnostics.md](references/build-validation-and-diagnostics.md)
  for deterministic builds, static/compiled/in-game QA, reporting, and symptom
  diagnosis.

## Required Tools

Discover installed paths instead of assuming fixed locations:

- CS2 with Workshop Tools and `resourcecompiler.exe`;
- Blender compatible with the selected import/export add-ons;
- Source2Viewer or ValveResourceFormat for Source 2 inspection;
- SourceIO or an equivalent Source 1 importer when applicable;
- an image tool that preserves color space and alpha;
- project-local deterministic inspection, retargeting, compilation, and QA
  scripts selected for the source branch.

This is a contract-driven guidance skill: it intentionally bundles no Blender
add-on, executable, current-build binary profile, or universal retargeter. The
operator must identify and hash the actual project-local tools in the build
report schema from `build-validation-and-diagnostics.md`; do not imply that this
skill supplied or validated them.

## Non-Negotiable Rules

1. Process only assets the user owns or is authorized to modify. Record creator,
   source, license/permission, and redistribution restrictions.
2. Preserve original source files as read-only and hash every input.
3. Build in a separate namespaced addon/work directory. Never overwrite
   base-game files or Valve global resource paths.
4. Extract current Valve references locally from the user's installation. Do
   not commit or publish stock compiled resources, decompiled sources,
   standalone skeletons, textures, or donor PHYS payloads.
5. Treat imported `.blend` files, add-ons, and build scripts as untrusted.
   Disable embedded script auto-execution for untrusted files and review code
   before execution.
6. Extract the current canonical skeleton; never redraw it by eye.
7. Preserve source skinning unless evidence proves it unusable.
8. Change one hypothesis at a time and compare measurable A/B outputs.
9. Fail on undeclared bones, missing weights, unexpected or undeclared topology
   changes, missing files, or unknown modification authority/provenance. Record
   unresolved redistribution rights as `blocked` and refuse public artifact
   handoff. A deliberate custom chain is an explicit current-build extension,
   never an accidental unknown.
10. Inspect the compiled VMDL_C, not only the editable VMDL.
11. Validate real animation states before declaring success.
12. Never hide an anatomical defect by deleting expected visible geometry.

## Workflow

1. Classify the source and inventory untouched files, scene content, geometry,
   rig, weights, materials, axes, and provenance.
2. Extract and hash a current official player model contract locally.
3. Build an explicit semantic rig profile and normalize orientation/scale.
4. Retarget bind geometry with a measured full-matrix or swing-scale method.
5. Repair weights, seams, accessories, and dedicated first-person geometry.
6. Author materials and ModelDoc; add hitboxes and a compatible ragdoll contract.
7. Build deterministically and inspect editable plus compiled resources.
8. Validate source-versus-final geometry, stress poses, first/third person,
   bullet traces, death/ragdoll behavior, and clean-client Workshop delivery;
   write the evidence report.

## Completion Gate

### Asset invariants

A finished port must have all of these outcomes:

- the exact current canonical worldmodel skeleton and hierarchy for required
  bones, plus only separately declared and proven custom extensions;
- only valid target vertex groups;
- zero unweighted vertices;
- normalized finite weights with no more than four influences per vertex;
- visually correct third-person and controlled first-person geometry;
- current existing skeleton and graph references wired in ModelDoc;
- canonical weapon attachments;
- a separately validated bullet hitbox set;
- physical shapes, body markup, non-zero masses, and ragdoll joints;
- correct opaque, masked, or translucent materials;
- static, stress-pose, compiled-resource, and in-game validation evidence;
- a machine-readable build report with provenance and redistribution status.

Do not hardcode historical bone, hitbox, body, joint, or mass counts as eternal
truth. Record them from the current official reference and assert that the port
matches. Previously observed humanoid counts are evidence for that exact build,
not a portable contract.

### Required evidence

Prove the outcomes above before declaring the port complete:

1. the build is reproducible from untouched authorized sources;
2. source provenance and target contracts are recorded;
3. static assertions pass on the actual interchange format used by the selected
   source branch (`DMX` when exact Source 2 data is preserved, otherwise the
   explicitly selected `FBX`/equivalent export);
4. source-versus-final renders show no unexplained regression;
5. stress poses show no tearing, twisting, collapse, or floating components;
6. compiled graph wiring, attachments, hitboxes, and physics pass inspection;
7. first-person and third-person geometry are controlled;
8. firearm traces hit all expected regions;
9. death produces a real articulated ragdoll;
10. a clean client mounts the expected player-model resource closure;
11. the exact tested artifact hash, redistribution status, and limitations are
    recorded.

If only compilation and static QA passed, report `compiled-validated; in-game
validation pending`. Do not call the port finished or distributable.
