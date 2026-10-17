# Evidence and provenance

## Contents

- [Local examples: high confidence for structure, no rendered-pixel claim](#local-examples-high-confidence-for-structure-no-rendered-pixel-claim)
- [Primary references and what they establish](#primary-references-and-what-they-establish)
- [Standalone authoring checks](#standalone-authoring-checks)
- [Positive native controls on owned artwork](#positive-native-controls-on-owned-artwork)

This skill contains instructions and owned code, not extracted Valve assets.
The local observations below were made on 2026-10-15. They identify inspected
installations rather than claiming to be the latest available builds.

## Local examples: high confidence for structure, no rendered-pixel claim

Archive reads verified entry CRC, then inspected Resource2/KV3 declarations,
material parameters and texture metadata in memory. No game assets were copied
into the skill. Paths below are engine-relative to the named
VPK, so another installation can locate them without these machine drive letters.

| Target | Local install identity | Inspected archive |
| --- | --- | --- |
| CS2 | app 730, Steam build 25640462 | `game/csgo/pak01_dir.vpk` |
| Deadlock | app 1422450, Steam build 25660886 | `game/citadel/pak01_dir.vpk` |

Examples and complete SHA-256 digests:

- **CS2** `particles/explosions_fx/explosion_hegrenade.vpcf_c`:
  behavior version 12; sprite renderers reference a VTEX through
  `m_vecTexturesInput[].m_hTexture`; the effect also has 13 child references.
  SHA-256 `6e91963270ccbf0b45d1660e075ddf43f183bad32164bc64f9f75c8749e703b5`.
- **CS2** `particles/explosions_fx/explosion_hegrenade_smoke_core.vpcf_c`:
  sprite texture groups include a smoke image and an animation-motion-vector
  auxiliary texture. The observed animation mode is fit-lifetime; a numeric
  animation rate of 2 is therefore not automatically a universal 2 fps setting.
  SHA-256 `c524a5ac4dd49ae4f372acd8964d30897280183ba26a067b97b667b06a3d0a5d`.
- **CS2** `materials/particle/explosion_fireballs/smoke/explosion_fireball_01_smoke.vtex_c`:
  BC7, 4096x4096, one mip; sheet version 8, five sequences of 32 frames with
  a recorded sequence-time scalar of 31, clamping and cropped/uncropped UVs. This is an observed
  complex example, not a recommended default texture budget.
  SHA-256 `82db52f28029cb35818e10a311afa080a911cd37855a52af820243cd7f42fb95`.
- **CS2** `materials/particle/smoke_trail_01/smoke_trail_01_loop.vtex_c`:
  BC7, 1024x512, one mip; sheet version 8, one 32-frame sequence with recorded
  sequence total-time scalar 32 and clamping disabled. Sequence total time is
  distinct from frame display time and is not itself a frames-per-second value.
  SHA-256 `f81d72f33f223cd899722436b8ed16cedd0c2525ee313521bb0b5daf434a9015`.
- **CS2** `materials/particle/sparkles.vmat_c`: compiled shader identity
  `generic.vfx`, `F_TRANSLUCENT=1`, `F_UNLIT=1`, with a `g_tColor` texture slot.
  This proves one material's declarations; it is not a universal sprite VMAT.
  SHA-256 `f5d5aba79500440ddd7675ff505e09a1d3393f28f713f35ee6cbe53cc8b36f10`.
- **Deadlock** `particles/impact_armor_ricochet_sparks.vpcf_c`: behavior version
  5, trail renderer, direct `materials/effects/spark.vtex` binding, and output
  blend enum `PARTICLE_OUTPUT_BLEND_MODE_ADD`.
  SHA-256 `a8ca15e5a8252b64d0126368f9003785ffcdd6752a83493e0547288b808ab283`.
- **Deadlock** `materials/effects/spark.vtex_c`: DXT1, 32x64, one mip; no sheet
  metadata observed. Its use in an additive effect does not imply every particle
  texture must carry an alpha channel.
  SHA-256 `4c11f1379cf5d121368bcfd450a5cf794d7b8b27a07b40e434ff44688efeb9f8`.

Large sheets were inspected without allocating their complete pixel data.
Readback retained a warning where the declared non-streaming size differed from
the complete texture resource length. Metadata remained readable; that warning
was not treated as full validation of every section. These checks establish the
stated structures, not native playback timing or rendered appearance.

An installed CS2 source at `content/core/materials/default/default_normal.vtex`
uses a `CDmeVtex` DMX definition with a TGA input, explicit linear channel
declarations and RGBA mapping. It is useful to inspect source structure, not as
a particle color template. An addon-local `.mks` inspected beside a fire VTEX
was explicitly marked as reconstructed by Source 2 Viewer 19.2.0.0; it was not
treated as original Valve source or as a successfully compiled example.

CS2's compiler launcher existed with SHA-256
`00db3daca0e733601bf3fcc1d1bf9df1b2ade805629098c48bd6c51af3d96f51`.
No compiler existed at the two Deadlock paths checked (`game/bin/win64` and
`bin/win64`); no claim about every possible location or future availability
follows. Neither game was launched. A separate native compiler check on owned
test textures is recorded below.

## Primary references and what they establish

- [SchemaExplorer machine-readable manifest](https://s2v.app/SchemaExplorer/llms.txt)
  identifies downloadable per-game snapshots and the schema structure. Obtain
  the appropriate game/revision; don't silently replace the installed build's
  contract with a newer snapshot.
- [CS2 renderer schema](https://s2v.app/SchemaExplorer/cs2/particles/CBaseRendererSource2)
  and [Deadlock renderer schema](https://s2v.app/SchemaExplorer/deadlock/particles/CBaseRendererSource2)
  expose field/type/enum metadata. These are extracted references with Windows
  layouts, not a portable runtime ABI or complete shader specification.
- [VRF texture extraction](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/Extract/TextureExtract.cs)
  establishes its MKS exporter and reconstructed VTEX workflow.
- [VRF texture content model](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/ContentFormats/ValveTexture.cs)
  establishes the named DMX objects and input/output channel structure.
- [VRF material extraction](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/Extract/MaterialExtract.cs)
  establishes its editable `Layer0` serialization, shader-aware texture-input
  mapping and `DynamicParams` container. It is a reconstruction implementation,
  not a generic material template accepted by every native shader.
- [VRF format-support matrix](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/format-support.md#particles-vpcf)
  describes particle round-trip and viewer limitations.
- [CS2 game configuration tracked from the game](https://github.com/SteamTracking/GameTracking-CS2/blob/master/game/csgo/gameinfo.gi)
  documents that snapshot's mount/addon configuration; inspect the local version
  for packaging decisions.

VRF is the primary source for its own implementation, independent from Valve.
Its renderer implementation is useful for preview diagnosis, not proof of native
game rendering. Valve Developer Community pages were unavailable during this
audit, so their unobserved contents are not cited as verification.

## Standalone authoring checks

The procedural helper was exercised for a sprite, a trail and eight flipbook
frames. All ten generated RGBA TGA images were decoded independently of their
writer; dimensions, alpha and neutral RGB agreed. The MKS described eight
looping frames totaling approximately 8/24 seconds. Existing-output refusal and
invalid-argument rejection were checked separately.
The `--resource-path` mode was then checked against the native controls: every
TGA, MKS and VTEX input reproduced the recorded SHA-256 byte-for-byte. Invalid
and nonportable resource paths were rejected before output creation.

## Positive native controls on owned artwork

[Compact machine-readable evidence](../assets/native-texture-evidence.json)
records the first-attempt CS2 compilation on build 25640462, SourceRevision
11064488, using the compiler identified above. The
[supplied VTEX source](../assets/linear-rgba-test.vtex) is an exact byte copy of
the **owned** successful sprite definition, SHA-256
`1f4033d07f02c8b9596c7cfc9c653993ee433878d4c2b76c51928185083d31ff`.
It is not an extracted Valve material or texture.

- Sprite: 64x64 RGBA8888, one mip; compiled readback compared with the generated
  TGA, with zero changed components and maximum difference zero.
- Flipbook: eight 64x64 owned frames packed to a 256x128 RGBA8888 texture, one
  mip; sheet v8 retained one non-clamped sequence and eight display times of
  approximately 0.041666668 seconds. The total-time field was approximately
  0.33333331. Native playback was not recorded.
- Both compiler processes returned zero. The decoder retained a warning about
  the non-streaming size versus complete file length and an informational RED2
  section diagnostic; neither was erased from the evidence.

The [VRF texture reader/writer](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/Resource/ResourceTypes/Texture.cs)
serializes sequence total time as `m_flTotalTime`. In this control it agrees
with the sum of the eight frame display times. Read it as total time, not as a
measured frame rate. No native rendering, VMAT compilation or Deadlock compiler
compatibility was certified by these tests.
