---
name: source2-particle-materials
description: "Create and diagnose native Source 2 particle textures, flipbooks, VTEX/MKS and material bindings in CS2 or Deadlock, with compilation and resource closure."
---

# Source 2 particle textures and materials

Turn the requested appearance into owned source images, the target renderer's
actual resource bindings, and compiled dependencies that can be verified in the
chosen game. This is a standalone knowledge and authoring folder. Its optional
Python helper uses only the standard library; choose any suitable image editor,
generation model, format-aware resource inspector and target-game tools.

Establish the target game, installed build, renderer class and existing source
asset before choosing shader names or property keys. Reuse an already supplied
target; inspect local manifests and a small relevant asset when it is missing.
CS2 and Deadlock share resource families but do not share a guaranteed shader,
operator, serialization default or material contract. s&box's C# ParticleEffect
is a separate authoring target.

Read only the relevant references:

- [Texture and flipbook authoring](references/textures.md): sprite, trail, image
  generation, alpha, MKS, VTEX and sampling choices.
- [Renderer and material bindings](references/materials.md): native spritecard
  versus VMAT, blend/depth/feathering controls and shader-specific properties.
- [Compilation and resource closure](references/compile-and-closure.md): native
  tools, source/compiled trees, verification and delivery.
- [Evidence and provenance](references/evidence.md): inspected game builds,
  exact resource identities, primary sources and owned native controls.

## Work from the visual intent

Resolve the few choices that change the assets: soft smoke versus luminous
glow, single sprite versus moving trail versus animated flipbook, looping versus
one shot, particle tint, ground intersection and required view distance. Infer
routine choices from the prompt. Create or modify the smallest asset set that
achieves it, then test how that set is used by the target renderer.

Native sprite/trail renderers can reference VTEX resources directly. Do not
invent a VMAT for every sprite. Use VMAT when the selected renderer/model or
verified material path needs one. Do not transplant Source 1 `UnlitGeneric`,
`$basetexture`, `$additive` or `$translucent` text into a `.vmat` file.

For image assets, preserve a true alpha channel when required and record the
RGB/alpha convention. A transparent background image alone does not define
blend mode, depth behavior or soft particle intersections. Inspect the alpha
channel and the image over both dark and light backgrounds before changing
engine properties to compensate for image defects.

The helper can create a deterministic owned test sprite/trail or expanding-ring
frame sequence to isolate bindings and UVs:

```text
python scripts/make_test_texture.py --output <new-directory> --kind sprite
python scripts/make_test_texture.py --output <new-directory> --kind trail
python scripts/make_test_texture.py --output <new-directory> --kind flipbook --frames 8 --fps 24
python scripts/make_test_texture.py --output <new-directory> --kind flipbook --size 64 --frames 8 --fps 24 --resource-path materials/owned_test/flipbook.vtex
```

These paths are relative to this skill folder. The helper creates RGBA TGA files,
an MKS for flipbooks, and a manifest. `--resource-path` also emits a source VTEX
from the [owned native-tested template](assets/linear-rgba-test.vtex). Place the
output files in the content directory matching that engine-relative path before
compiling. The template uses linear RGBA8888 without mipmaps to isolate the
pipeline; adapt production sampling/compression deliberately. No universal VMAT
is supplied. The [control evidence](assets/native-texture-evidence.json) proves
CS2 compilation/readback of a sprite and an eight-frame sheet, without native
rendering or Deadlock certification. New outputs still need their own check.

## Verify the actual binding

Inspect the selected renderer and a same-game example. For new properties, read
the target schema's class, parents, enums and default metadata; for shader
parameters, inspect the target material/editor/shader declarations. An exact
field spelling in a newer public schema does not certify an older local build.

Compile the authored definitions with that game's tools, read back the compiled
resource, then preview the effect in the target game/tools when available.
Unknown fields can be silently discarded by the compiler. Distinguish default
stripping from unsupported input with a known nondefault control.

Deliver source images and definitions, compiled resources when requested, a
dependency list with game-provided versus authored entries, and the evidence
actually obtained. State separately: source checks, native compilation/readback,
preview approximation, and observed native rendering. Keep inspection of local
Valve examples separate from redistribution of their payloads.
