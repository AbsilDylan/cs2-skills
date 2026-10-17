# Native particle rendering

## Contents

- [Evidence ledger](#evidence-ledger)
- [Choose geometry for the effect](#choose-geometry-for-the-effect)
- [Sprite orientation](#sprite-orientation)
- [Size, alpha and visibility](#size-alpha-and-visibility)
- [Texture layers, materials and sequences](#texture-layers-materials-and-sequences)
- [Model particles](#model-particles)
- [Sprite trails and ropes](#sprite-trails-and-ropes)
- [Native import and verification](#native-import-and-verification)

Use this guide to choose a Source 2 renderer, connect its inputs and design a native test. Preserve requested engine features. An unmeasured field is a research question, not a reason to remove it from an effect.

## Evidence ledger

| Label | Established fact | Boundary |
| --- | --- | --- |
| `Typed` | Native class, inherited field, type, enum or editor metadata in the bundled catalogue. | An authoring label does not establish its mathematical implementation. |
| `Typed default` | A value recorded in defaults metadata for that class/build. | Unavailable defaults are not zero; partial defaults are not complete. |
| `Serialized` | The identified native compiler preserved the intended input on readback, or controlled default/nondefault cases explain its omission. | No rendered result, shader equation or complete resource closure follows from acceptance alone. |
| `Measured` | A native capture measures stated inputs, resources, CP poses, camera and time on the stated game build. | Generalize only to measured branches. |
| `Unknown` | Exact native behavior is unresolved by available evidence. | The property can still be valid and useful to author. |

The bundled typed catalogue (`$source2-particle-schema`) describes CS2 SourceRevision **11131657**, snapshot **14 October 2026**. Its evidence notes (`$source2-particle-schema`) explain inherited fields, partial defaults and game separation. Live SchemaExplorer pages can expose another class snapshot; use the bundled record's provenance when reproducing a fact.

The [native compiler checkpoint](native-compiler-evidence.json) records 13 compilation/readback fixtures for installed CS2 SourceRevision **11064488**, from **30 September 2026**. Sprite orientation tokens, a trail renderer and a model reference were exercised. It records **no native rendered pixels**. Unknown sentinel fields were silently discarded despite successful compilation; inspect the intended field, not just the exit code. A compiled default's omission does not mean the property is ignored.

[Valve-authored particle tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt) is mirrored publicly. Match its keys to the installed build; historical class names and changing upstream content require care.

## Choose geometry for the effect

[Embedded native help facts](native-help-facts.json) retain selected sprite/trail/rope, radius-unit and normal-alignment interpretations with exact token/passage hashes and verified source-payload identity. This allows those concise facts to travel with the guide; full native evaluation and pixels still require target-build measurements.

Valve describes sprites as cards, trails as speed-stretched sprites, and ropes as connected points. Use sprites for puffs, trails for tracers, and ordered rope points for curved beams. [Valve tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt)

Choose `C_OP_RenderModels` when a mesh silhouette, model parts or animation matter. Keep geometry selection separate from movement, lifetime, collision and resource/CP bindings when designing the effect.

## Sprite orientation

`C_OP_RenderSprites.m_nOrientationType` uses `ParticleOrientationChoiceList_t`. These are exact enum members and editor labels in the bundled catalogue:

| Member | Value | Editor label |
| --- | ---: | --- |
| `PARTICLE_ORIENTATION_SCREEN_ALIGNED` | 0 | Screen Align |
| `PARTICLE_ORIENTATION_SCREEN_Z_ALIGNED` | 1 | Screen-Z Align |
| `PARTICLE_ORIENTATION_WORLD_Z_ALIGNED` | 2 | World-Z Align |
| `PARTICLE_ORIENTATION_ALIGN_TO_PARTICLE_NORMAL` | 3 | Particle Normal Align |
| `PARTICLE_ORIENTATION_SCREENALIGN_TO_PARTICLE_NORMAL` | 4 | Screen & Particle Normal Align |
| `PARTICLE_ORIENTATION_FULL_3AXIS_ROTATION` | 5 | Full 3-Axis Rotation |

The recorded default is screen alignment. The renderer exposes `m_nOrientationControlPoint` and `m_bUseYawWithNormalAligned`; editor suppression expressions associate them with the normal-aligned modes. Screen-Z and World-Z are distinct choices. Exact basis construction, degenerate viewing angles, rotation order and normal/CP precedence need a target-build observation rather than a guessed coordinate formula. [Native sprite metadata](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_RenderSprites)

For full three-axis attachment, Valve's help combines CP-to-particle orientation remapping with movement locking that includes rotation. Keep CP position and orientation separate. [Valve tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt)

**Test:** use an asymmetric arrow texture and one stationary particle. Orbit the camera, rotate only the selected CP, then change only particle roll. Compare modes at identical poses, including a normal parallel and perpendicular to the viewing direction. Record the result; accepted tokens alone do not establish it. See [control points](control-points-children.md) for bindings.

## Size, alpha and visibility

Valve documents base radius in world units. Renderer scale and screen-size controls serve different purposes. [Valve tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt)

| Family | Fields to inspect | Authoring purpose / boundary |
| --- | --- | --- |
| Size | Particle radius; `m_flRadiusScale` | Separate particle size from renderer scale. No universal diameter or model-scale formula is established here. |
| Screen visibility | `m_flMinSize`, `m_flMaxSize`, `m_flStartFadeSize`, `m_flEndFadeSize` | Metadata identifies visual screen size and screen-size fading; projection units and clamp order need verification. |
| Opacity | Particle alpha; `m_flAlphaScale`; `m_nAlpha2Field` | Keep particle opacity, renderer scaling and the additional alpha attribute distinct. |
| Color/brightness | `m_vecColorScale`, `m_nColorBlendType`, `m_flOverbrightFactor`, `m_flAddSelfAmount` | Tint and extra light contribution are separate from opacity. |
| Intersection | `m_nFeatheringMode`, `m_flFeatheringMinDist`, `m_flFeatheringMaxDist` | Depth feathering has its own mode and distances; it is not lifetime fading. |
| Depth/sorting | `m_bDisableZBuffering`, `m_bReverseZBuffering`, `m_flDepthBias`, `m_nSortMethod` | Test occlusion and overlap with the intended material. |

Many sprite controls are renderer float/vector inputs, while `CBaseRendererSource2.m_flAnimationRate` is a plain `float32`. Similarly named model/trail fields can have different types. Retrieve the selected class with inherited fields before constructing values. [Native renderer base metadata](https://s2v.app/SchemaExplorer/cs2/particles/CBaseRendererSource2)

The historical `C_OP_RenderSpritesWithRenderSystem` screen-fraction example does not define another class's units. Check installed help and camera distances.

**Test:** hold texture, emission and camera fixed. Vary radius zero/small/large, then alpha zero/half/full independently. Repeat with alpha blend and additive output against light/dark backgrounds and intersecting scene geometry. Identify whether the change affects opacity, brightness, size, culling or soft intersection before changing another input.

## Texture layers, materials and sequences

`m_vecTexturesInput` contains `TextureGroup_t` entries. Each distinguishes enabled state, texture resource or authored gradient, texture role, channel mix, layer blend, blend amount and `TextureControls_t`. Bundled defaults record enabled=true, diffuse role, RGBA channel mix and multiply layer blending. These are `Typed default` facts, not a complete compositing equation. Normal, motion-vector and depth roles have different editor conditions from ordinary color inputs. [Native texture-entry metadata](https://s2v.app/SchemaExplorer/cs2/particles/TextureGroup_t)

Layer blending (`m_nTextureBlendMode`) differs from output blending (`m_nOutputBlendMode`). The output enum offers ALPHA, ADD, BLEND_ADD, HALF_BLEND_ADD, NEG_HALF_BLEND_ADD, MOD2X and LIGHTEN. Choose the actual enum; its label alone does not specify all blend factors, alpha tests or shader operation order.

Texture controls expose U/V scale/offset, rotation/animation-rate scale, zoom, distortion, clamping and per-particle scalar selections. Recorded defaults include scale/zoom=1 and offsets/rotation=0. Exact pivot, transform order and `m_flFinalTextureUVRotation` units are `Unknown` here. Do not introduce a degrees/radians conversion from the field name alone.

Keep sequence identity, frame number and playback rate separate:

- `AnimationType_t` offers `ANIMATION_TYPE_FIXED_RATE`, `ANIMATION_TYPE_FIT_LIFETIME` and `ANIMATION_TYPE_MANUAL_FRAMES`. Choose the timing intention before tuning rate.
- `m_nSequenceOverride` is labeled as a sprite sequence-ID override. `m_bSequenceNumbersAreRawSequenceIndices` is marked as a tools-particle option. Sequence IDs must not silently become packed-image ordinals.
- `m_bAnimateInFPS` changes the declared rate interpretation. `m_bBlendFramesSeq0` and max-luminance frame blending are separate controls; sprite defaults record frame blending enabled.
- Manual frames need an actual input in the selected renderer/version. Verify that field and type rather than inventing a serializer key.

**Test:** import a sheet with numbered frames and two different-length sequences. Compare fixed rate, fit-lifetime and manual control independently at birth, a sequence boundary, last frame, looping and death. Repeat with frame blending off/on. A static texture cannot reveal these errors.

Import resources as resources. VRF documents distinct VPCF extraction, material reconstruction and sprite-sheet reconstruction. Exported images may reflect decoded compile-time transforms and lossy compression; they do not preserve every source choice. Verify shader, channel roles, color interpretation, sheet metadata and dependencies in native tools. [VRF format/export fidelity](https://s2v.app/ValveResourceFormat/guides/format-support.html)

## Model particles

`C_OP_RenderModels.m_ModelList` contains `ModelReference_t`: a typed model handle and relative spawn probability. `m_flManualModelSelection` and optional `m_modelInput` also exist. Start with one model, then test selection deliberately; do not assume that only the first entry can be used.

Metadata separates local offset/rotation, component scale, radius influence (`m_bIgnoreRadius`), CP scaling, local-space scaling, normal influence and alignment of model Z to normal (`m_bOrientZ`). Model animation has its own sequence/rate/manual-frame controls; it is distinct from texture-sheet animation. Exact transform order, angle units and scale combination need a measured native case. [Native model metadata](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_RenderModels)

`m_hOverrideMaterial` is a typed material handle, with separate `m_bOverrideTranslucentMaterials`. Test opaque and translucent model materials independently. The presence of the field is neither a failed feature nor proof of its visual result.

For `m_nSubModelFieldType`, help distinguishes bodygroup submodels, one mesh-group index, a group mask and the model default. Select the mode before wiring its attributes; masks and indices differ. [Valve tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt)

**Test:** use visibly different bodygroups, an asymmetric axis marker and two material types. Vary one scale, orientation/normal input, selection mode or material override at a time. Include zero/half/full particle alpha and overlapping models in both spawn orders. Measure depth behavior instead of prescribing a universal transparency implementation.

## Sprite trails and ropes

For `C_OP_RenderTrails`, inspect `m_nPrevPntSource`, length scale/minimum/maximum, `m_bIgnoreDT`, length growth time, radius-to-length constraint and separate head/tail taper, color and alpha. The native labels describe stretching and an anchor; they do not establish a multipoint history implementation. Test zero speed, constant speed, acceleration and stopping. Compare frame rates before choosing delta-time handling. [Native trail metadata](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_RenderTrails)

For `C_OP_RenderRopes`, plan point order and segment identity. The catalogue exposes reverse order, closed loop, split attribute and segment-ID sorting. Tessellation is described in quads per segment. Texture V has world size, scroll, offset and CP-related controls, distinct from generic U/V transforms. Rendering, maintaining point positions and constraining rope motion are separate tasks. [Native rope metadata](https://s2v.app/SchemaExplorer/cs2/particles/C_OP_RenderRopes)

**Composition/test:** initialize a small fixed set of ordered points along a CP-defined path, assign radius/color and render their connection. Add endpoint following or spring constraints if required. Verify a straight static rope first; then bend the path, move one endpoint, reverse order and close the loop. Tune tessellation and repetition after connectivity works. Record CP poses, point count and segment attributes.

## Native import and verification

1. Select the game/build and retrieve exact classes, inherited fields, enums and defaults. Keep version mismatches visible.
2. Resolve referenced textures, materials, models, sheets and children in the target addon's search paths. A retained resource name alone does not prove dependency closure.
3. Define the CP contract: index, position/orientation, entity/attachment binding and inputs that change after creation. Use distinct poses so a wrong CP cannot look accidentally correct.
4. Compile with that game's toolchain and read back intended fields/resources. Keep source/compiled hashes, diagnostics and default/nondefault controls.
5. Observe in the native editor or game at fixed camera/material/time. Record measured results as `Measured`; keep untested formulas and branches `Unknown` without declaring them impossible.
