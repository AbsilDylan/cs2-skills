# Renderer, material and blend contracts

## Contents

- [Start at the binding that the effect uses](#start-at-the-binding-that-the-effect-uses)
- [Decide the behavior before the spelling](#decide-the-behavior-before-the-spelling)
- [Author VMAT only when required](#author-vmat-only-when-required)
- [Model cutouts and compiled alpha](#model-cutouts-and-compiled-alpha)
- [Refraction textures carry displacement data](#refraction-textures-carry-displacement-data)
- [Separate rotation, flipbook and material animation](#separate-rotation-flipbook-and-material-animation)
- [Diagnose appearance in a useful order](#diagnose-appearance-in-a-useful-order)

## Start at the binding that the effect uses

There are distinct paths:

1. A native sprite/trail renderer chooses a spritecard-related shader and texture
   groups from its VPcf renderer configuration.
2. A model/mesh particle uses a model's material or a supported explicit material
   override. That path can require VMAT definitions and their textures.
3. A custom shader uses the target game's own available program and feature
   declarations. It is a separate compatibility decision.

Inspect the actual class and resource before deciding which path applies.
`spritecard.vfx` is a shader-family name observed in native shader packages; it
does not mean that every sprite has a `.vmat` with `shader = spritecard.vfx`.
The shape of a `C_OP_RenderSprites` renderer is not the same as a generic
material definition.

In the CS2 schema, `CBaseRendererSource2` declares shader selection and texture
group inputs, plus output blend, depth and feathering controls. Current names
include `m_nShaderType`, `m_strShaderOverride`, `m_vecTexturesInput`,
`m_nOutputBlendMode`, `m_bDisableZBuffering`, `m_nFeatheringMode`,
`m_flFeatheringMinDist` and `m_flFeatheringMaxDist`.
[Source schema](https://s2v.app/SchemaExplorer/cs2/particles/CBaseRendererSource2).
Inherited layouts and deprecated texture shapes change between builds; inspect
the selected snapshot rather than inserting all these keys into every file.

## Decide the behavior before the spelling

| Desired behavior | Decision | Native verification |
| --- | --- | --- |
| Luminous glow/spark | Additive-like output may suit it | Read target output-blend enum; inspect RGB and alpha contribution |
| Opaque-looking smoke/dust | Alpha compositing often suits it | Check sorting, opacity accumulation and light/dark background |
| Crisp cutout | Alpha testing can avoid translucent edges | Confirm the shader supports it; test threshold and minification |
| World occlusion | Keep the intended depth test | Check behind geometry; do not disable depth to hide an intersection problem |
| Soft intersection with a wall | Depth feathering/soft particles | Confirm depth texture/pass support and test contact from multiple views |
| Deliberate through-wall effect | Explicit depth-test change | Verify it separately from depth writing and blending |

Blend, depth testing, depth writing, sorting and depth feathering are separate
choices. Disabling Z-buffering does not implement soft particles. A transparent
pixel need not have zero RGB; the shader's blend equation determines whether
that hidden RGB matters. Refraction, lighting, fog and auxiliary textures add
further dependencies and should be introduced once the basic binding works.

Do not infer a native flag from a familiar name. An independent preview may
normalize a material declaration into its own generic blend settings; that is
not proof the original flag exists on the selected native shader. Likewise a
`F_DEPTH_*` feature in one VCS package does not establish the VPcf field or VMAT
parameter that drives it.

## Author VMAT only when required

Create an owned material with the target Material Editor, or start from an
owned target-game source material that already compiles. Record its exact shader
identity and preserve the supported parameter spelling and resource types.
Change the color/opacity inputs and only the features needed by the effect.
Keep generated material paths under an authored namespace.

Source VMAT can use a KeyValues-style `Layer0` and shader-specific keys; compiled
VMAT stores normalized parameter containers. The two representations are not
interchangeable by file extension. Decompile through a format-aware tool before
editing a compiled resource. References in compiled materials can point to
compiled textures while source materials can name source image ingredients;
follow the accepted compiler's actual conversion rather than rewriting suffixes
indiscriminately.

A concrete reconstruction path is:

1. Inspect one material from the **target game/build**, including its exact
   shader, integer/float/vector parameters and texture references. The observed
   CS2 `materials/particle/sparkles.vmat_c` uses `generic.vfx`, `F_UNLIT=1`,
   `F_TRANSLUCENT=1` and `g_tColor`; these identify a real case to inspect rather
   than an assumed shader family.
2. Open it in a format-aware inspector with the relevant game archives mounted,
   or use the target Material Editor to save an editable source. VRF's
   `MaterialExtract.ToValveMaterial()` emits a KeyValues1 `Layer0` document,
   writes `shader` and the recorded scalar/vector parameters, and resolves
   texture source-input names through shader data. A compiled `g_tColor` binding
   therefore does not justify inventing a source key with the same spelling.
3. Keep that verified source structure and replace its inputs with owned artwork
   under a new engine-relative namespace. Preserve any required masks or packed
   channels until their meaning is understood; a missing default texture is
   different from an optional unused input.
4. Compile the new VMAT with the selected game's tools. Read back the new shader
   identity, nondefault feature values and exact texture references, then test
   it on the intended model/renderer. Retain generated texture products in the
   closure inventory instead of guessing their hashed filenames.

[Primary material-export implementation](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/Extract/MaterialExtract.cs).
This explains a real editable-source route; it does not claim that the
inspected compiled example's complete original authoring source was recovered.
No source VMAT generated during the recorded texture controls was compiled.

For time-driven material expressions, preserve the target's expression syntax
and parameter names. VRF emits a `DynamicParams` section for recorded dynamic
expressions. That is a source container, not a JavaScript/Lua execution hook;
do not paste another engine's material-proxy language into it. Use the target
editor to author an expression or start from an inspected compatible expression,
and distinguish shared material time from per-particle age before tuning it.

For an unlit appearance, select the actual target shader or renderer option.
Names differ across game families and updates. `csgo_unlitgeneric.vfx` and
Source 1 `UnlitGeneric` are not the same authoring syntax. A same-named shader
in Deadlock and CS2 also does not imply identical features or defaults.

Avoid a bundled universal VMAT template: the skill's local VPK observations prove
specific compiled material identities, not a portable authoring contract for all
shader keys. Use [the evidence ledger](evidence.md) to find a relevant local
example, then prove the resulting authored material with the selected compiler.

## Model cutouts and compiled alpha

For the inspected CS2 `csgo_complex.vfx` alpha-test path, an RGBA
`TextureColor` source alone did not preserve the intended cutout: the generated
color texture's alpha was effectively opaque. The working authored material
supplied a separate `TextureTranslucency` image and enabled `F_ALPHA_TEST`.
The opacity image copied the desired coverage into RGB with image alpha 255.
The compiler packed the result into the generated `g_tColor` texture; there
was no separate native translucency texture parameter to copy.

This is a shader-specific starting point, not a rule for all VMATs or direct
sprite VTEX bindings. Confirm the installed shader's input declarations.
For an opaque rectangle despite a transparent source image, inspect the
generated texture actually bound by the material before retuning particle
alpha. Check its alpha range and transparent corners, then preview the
cutout and its threshold on the intended geometry.

The owned control retained `F_RENDER_BACKFACES` for open surfaces and
`g_flAlphaTestReference` for its threshold. Neither is a substitute for opacity
data. Alpha testing cuts out pixels; it does not certify smooth per-particle
model fading. The observed control and its exact limits are recorded in
[the material evidence](evidence.md#owned-model-material-and-refraction-checks).

## Refraction textures carry displacement data

The observed CS2 sprite/rope refraction examples use a texture containing packed
normal directions in RGB and coverage in alpha, supplied through the verified
renderer texture input. A painted white band is not the same input. The owned
control used linear channels and mapped unit XYZ normals to RGB with
`0.5 * normal + 0.5`; a flat normal is approximately `(128, 128, 255)` in
8-bit storage. Preserve the coverage mask when generating the texture.

Inspect the selected renderer's native shape for `m_bRefract`,
`m_flRefractAmount` and related options. Do not infer that an extra arbitrary
texture slot supplies normals, or promote one tested refraction amount into a
default for every scale. Compare enabled and disabled refraction over a fixed
grid or detailed surface, then test the intended scene. Localized background
displacement is the useful evidence. A luminous or blurred strip alone is not.
The recorded rope control distorted the PET grid but remained too bright on
the white Plane background, so it did not certify appearance on a game map.

## Separate rotation, flipbook and material animation

These are different mechanisms even if the prompt simply says "animate":

| Request | Mechanism to author | Independent check |
| --- | --- | --- |
| A spark starts at a different angle | Rotation initializer | Inspect one particle at birth; use an asymmetric sprite |
| A mote keeps spinning | Angular speed plus its update, or the selected spin operator | Compare birth and later orientation without changing the flipbook |
| An explosion evolves through images | VTEX sheet sequence and renderer timing | Verify frame display times, sequence selection and lifetime mapping |
| A beam pattern scrolls | Tileable image plus supported UV/time controls | Check continuity and which UV axis follows the beam |
| A model fades or changes an emissive material parameter | Supported model/material variable path | Confirm the exact shader variable and material binding, then its time source |

In the CS2 schema, `C_INIT_RandomRotation` and
`C_INIT_RandomRotationSpeed` inherit the initial value, min/max offsets and
random-direction controls from `CGeneralRandomRotation`.
`C_OP_SpinUpdate` inherits `CSpinUpdateBase`; `C_OP_Spin` instead inherits
`CGeneralSpin`. Read the corresponding target-game declarations rather than
copying a random rotation initializer into a speed field. Avoid stacking two
independent spin mechanisms unintentionally. A circular glow cannot reveal its
rotation; test with a streak or marked sprite.
[Rotation schema](https://s2v.app/SchemaExplorer/cs2/particles/CGeneralRandomRotation),
[spin update](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_SpinUpdate),
[spin operator](https://s2v.app/SchemaExplorer/cs2/particles/CGeneralSpin).

For a material-variable route, the schema exposes
`C_OP_RenderMaterialProxy` with a material control point, proxy type, material
variables and an override material. `MaterialVariable_t` identifies the named
material variable, particle field and scale. This is a concrete path to inspect
for a supported model/material effect; it is not an invitation to invent a
shader uniform or attach it to every sprite. Select a valid shader variable and
proxy enum from the actual target, then verify which object/material instance
receives the value. A global time expression and particle age are not equivalent.
[Material proxy schema](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_RenderMaterialProxy),
[material variable schema](https://s2v.app/SchemaExplorer/cs2/particles/MaterialVariable_t).

Three useful deliverable shapes are: a neutral static sprite tinted cyan by the
particle; a short one-shot sheet whose sequence fits particle lifetime; and a
tileable trail strip whose length and UV motion are controlled by the target
trail renderer. Each can be authored without a custom VMAT when the renderer
binds VTEX directly. Add a model material only when the effect needs that route.

## Diagnose appearance in a useful order

First verify the exact selected resource path and texture slot. Then inspect
decoded pixels and alpha, source/output color-space declarations, UV/sequence
metadata and particle tint/alpha. Only then change blend/depth/lighting settings.
For a checker/error material, inspect logs and closure before artistic tuning.
For a solid rectangle, inspect alpha preservation and output blend. For black
fringes, inspect edge RGB, alpha convention and mip behavior. For popping,
inspect sorting/culling/sequence boundaries rather than assuming one cause.

An independent preview can help isolate defects. It cannot certify native
shader selection, depth integration or pixel equivalence unless those specific
edges were verified for the target build.
