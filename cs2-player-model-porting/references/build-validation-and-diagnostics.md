# Build, Validation, And Diagnostics

Use this reference to build deterministically, validate editable and
compiled player resources, record evidence, and diagnose model failures.

Prerequisite: complete the applicable authoring references linked directly from
`../SKILL.md` before running the completion gate.

## Contents

1. Deterministic build pipeline
2. Layered validation
3. Build report schema
4. Diagnostic matrix

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
10. preserve exact Source 2 DMX when that is the selected source branch, or
    export FBX/equivalent without source animations or leaf bones for branches
    that require a generic interchange format;
11. write materials and ModelDoc;
12. compile with `resourcecompiler.exe`;
13. if editable sources cannot reproduce the contract, block completion; an
    exact-build, hash-gated, manifest-driven project-local PHYS experiment may
    run only as a separately reviewed diagnostic and must not modify base-game
    files or enter the release artifact;
14. inspect compiled DATA, MDAT, and PHYS;
15. render QA views and write the final report.

Never convert a preserved Source 2 DMX branch to FBX merely to satisfy a generic
checklist item. Assertions must target the actual declared interchange format.

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

### Static interchange assertions

Run equivalent checks against the declared final DMX, FBX, or other selected
interchange format. Do not convert formats merely to satisfy the validator.

Check:

- canonical bone names and hierarchy;
- zero undeclared vertex groups or bones, except a separately proven and
  recorded current-build extension;
- zero unweighted or non-normalized vertices;
- no more than four non-zero influences after pruning and renormalization;
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

### Workshop and clean-client validation

Build an allowlisted player-model closure containing the compiled VMDL,
project-owned meshes, materials, textures, and required authored dependencies.
Inspect both the staged and downloaded VPK, compare hashes, and verify the model
on a client with no loose addon files. Packaging a player model remains part of
this skill; private item graphs and proxy routing remain in
`$cs2-animgraph2-authoring`.

## Build report schema

Write JSON containing at least:

- source path, hash, source type, creator, and provenance;
- license/permission evidence and redistribution status;
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
- staged/downloaded VPK resource closure and clean-client artifact hash;
- QA image paths and hashes;
- validation status and known limitations.

Use statuses such as `source-inspected`, `dmx-validated`, `fbx-validated`,
`compiled-validated`, `packaged`, `clean-client-validated`, and
`in-game-validated`. Never collapse them into one ambiguous `success` flag.
Unknown or incompatible redistribution rights must set distribution status to
`blocked`, even when local technical validation passes.

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
| Hand effect exists in third person but not first person | compiled FP mesh/bodygroup omits its components | FP export allowlist assumed weights were sufficient | explicitly include effect objects and materials in FP, exclude them from body-only wrist smoothing, and audit the compiled component count |
| Wrist twists only in first person | abrupt lower-arm/hand weights under asymmetric pose | rigid wrist boundary in dedicated FP mesh | audit the active skeleton; smooth the FP lower-arm/hand envelope without inventing absent twist bones |
| Fix removes a finger | whole component deleted | symptom hidden by geometry removal | restore component, shorten/reweight it |
| Bullets pass through | compiled hitbox set missing | physics shapes mistaken for hitboxes | add and audit official hitbox contract |
| Player stays standing after death | masses zero or joints absent | incomplete compiled PHYS | author/recompile a compatible physics contract from a current reference; never redistribute a donor PHYS payload |
| Model is correct at rest but bad in motion | bind or transition defect | validation stopped too early | run isolated stress poses and game animations |

Return to the [completion gate](../SKILL.md#completion-gate). Technical success
and permission to distribute are separate required report fields.
