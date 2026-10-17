# Texture, trail and flipbook authoring

## Contents

- [Choose the image representation](#choose-the-image-representation)
- [MKS is a source sequence description](#mks-is-a-source-sequence-description)
- [VTEX connects sources to a compiled texture](#vtex-connects-sources-to-a-compiled-texture)
- [RGBA, sRGB and premultiplication](#rgba-srgb-and-premultiplication)
- [Connect animation to the particle renderer](#connect-animation-to-the-particle-renderer)

## Choose the image representation

| Appearance | Useful source | What to inspect |
| --- | --- | --- |
| Glow, spark, magic mote | Soft sprite; usually neutral RGB so particles can tint it | Center intensity, transparent border, RGB outside alpha, additive versus alpha blend |
| Smoke, dust, mist | Soft opacity image or evolving frames | Density in alpha, contrast over light/dark surfaces, sorting and overdraw |
| Beam, ribbon, speed trail | Narrow strip with soft cross-section | Which UV axis runs along length, stretching versus tiling, seam at repeated ends |
| Explosion, splash, animated flame | Separate frames plus an MKS sequence | Frame order, duration, loop/end behavior, crop, pivot, interpolation |

These are authoring choices, not fixed native shader rules. Determine the actual
UV orientation from the renderer or a test texture with an asymmetric mark.
Do not compensate for a reversed axis by guessing another shader.

For AI-created artwork, request the image's job explicitly: an isolated sprite,
a tileable strip or a coherent sequence with consistent camera, center and scale.
Request real transparency when needed. Inspect generated sequences for duplicate
frames, camera motion, drifting pivots, discontinuities and baked checkerboards.
Create each frame separately when a large contact sheet cannot preserve detail;
a painted grid is not yet native animation metadata.

Use enough padding for the intended minification and filtering. Preserve useful
edge color beyond the visible alpha rather than allowing a black or white matte
to contaminate filtered borders. Straight and premultiplied alpha require
different shader/blend expectations; record the convention and test it. Do not
premultiply twice. Keep normal, distortion, masks and motion vectors separate
from a color image when the renderer declares separate slots.

Select resolution, compression and mipmaps for the viewing distance and alpha
detail. A small effect rarely needs a huge sheet. Preserve alpha through the
chosen output format; an RGB-only result cannot retain a smoke opacity channel.
Keep a lossless original and use a simple uncompressed/known-supported target
format while diagnosing the pipeline before choosing delivery compression.

## MKS is a source sequence description

For a new two-frame sequence in a folder containing the frame files:

```text
sequence 0
LOOP
frame frame_000.tga 0.041666667
frame frame_001.tga 0.041666667
```

This uses the basic sequence/loop/frame form emitted by the independent
[VRF texture exporter](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/Extract/TextureExtract.cs).
Its exporter writes the compiled sheet's `DisplayTime` after each frame path.
The example requests equal 1/24-second frame display times. Omit `LOOP` for the
intended non-looping source, then verify final-frame/end behavior in the target.
Native acceptance and exact timing remain build-specific checks.

Use paths relative to the MKS location for the frame list. Preserve authored
sequence IDs and names. Advanced files can contain RGB/alpha sequence packing,
crop directives and clamp behaviors; do not flatten them into an assumed square
grid or discard an auxiliary alpha sequence. For an imported resource, export
and retain its actual sheet metadata before editing it.

The supplied helper creates this simple MKS form only. It does not create packed
RGB/alpha sequences, flow maps or cropped frame metadata. Its manifest labels
native compilation as unverified.

## VTEX connects sources to a compiled texture

A source `.vtex` is a texture definition, commonly DMX with a `CDmeVtex` root.
Its input can be an image or an MKS. A compiled `.vtex_c` stores texture data and
can include sheet metadata. Renaming an image to `.vtex_c` does not compile it.

For a CS2 pipeline control, the optional helper `--resource-path` emits the
skill's [native-tested owned VTEX](../assets/linear-rgba-test.vtex), changing only
the source input path. It compiled on the recorded CS2 build for both a TGA and
an MKS. It intentionally uses linear RGBA8888, explicit RGBA mapping, and no
mipmaps. This tests texture plumbing and alpha; it is not a universal production
color/compression recipe or a Deadlock compatibility claim.

Use the target Texture Editor or a source definition already accepted by the
target compiler, then edit the input path, channel mapping, output format,
clamp/mipmap choices and color-space declarations. The relevant structural
objects are:

- `CDmeInputTexture`: input name/path, input color space and image processors.
- `CDmeTextureOutputChannel`: input binding, source/destination channels, mip
  algorithm and output color space.
- `CDmeVtex`: texture dimensionality, output format and output channel array.

[VRF's texture content model](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/ValveResourceFormat/IO/ContentFormats/ValveTexture.cs)
documents these structures. Its exporter can reconstruct a 2D source definition
and point it at an exported MKS. That implementation is an independent format
reference, not a promise that every native build accepts every reconstructed
configuration. Avoid writing a complete DMX template from guessed Hungarian
property prefixes. A parser fixture containing intentionally unknown types is
not a native authoring template.

For color textures, distinguish the source interpretation, output channel
declaration and shader sampling transfer. A filename, storage format, input
`m_colorSpace` alone, or an unset compiled flag does not prove the selected
shader's sRGB/linear sampling. Use the exact target declarations and verify the
appearance. Data maps normally need a data interpretation, not automatic color
conversion inferred from a `.png` extension.

## RGBA, sRGB and premultiplication

Record three separate properties: what RGB represents, what alpha represents,
and how the renderer combines the sample with the background. A color image can
store sRGB-encoded RGB while alpha stores linear opacity/coverage. Normal maps,
distortion vectors and lookup data need the target shader's data convention;
the same file container can carry either color or data.

For ordinary straight-alpha compositing, a simplified linear-light color model
is `result = sourceRGB * alpha + backgroundRGB * (1 - alpha)`. For a
premultiplied source, `premultipliedRGB` already contains that multiplication:
the corresponding model is `result = premultipliedRGB + backgroundRGB *
(1 - alpha)`. These equations explain image preparation; they do not select a
native blend enum or establish the exact shader's operations. Decode sRGB color
to linear before doing color arithmetic, and do not apply a display gamma
transform to alpha as if alpha were RGB.

If a premultiplied image is treated as straight, its edges can be multiplied
twice and darken. A straight image treated as premultiplied can reveal its
transparent-border RGB. Preview over black, gray and white, with low particle
alpha and at distant mip levels. Change either the image convention or the
shader expectation deliberately, not both at once.

The supplied test images are straight-alpha, neutral white RGB even where
alpha is zero. Their VTEX control is explicitly linear RGBA8888 without mips.
That combination makes alpha preservation easy to inspect. It does not imply
that painted color artwork, compressed shipping textures or another shader
should use the same settings.

## Connect animation to the particle renderer

Native spritecard-related schema controls include sequence selection, animation
rate/type, `m_bAnimateInFPS` and frame blending. Read them from the target game
and class inheritance; do not assume `m_flAnimationRate` always means frames per
second. Particle-age animation and elapsed system time can produce different
results for particles emitted at different times.

Check at time zero, a frame boundary, mid-life and the end. Compare two particles
born at different times, one-frame and multi-frame inputs, loop and one-shot
sequences. For a trail, additionally check turning, changing speed, short
segments and distant views. Native sheet frames can have crop/pivot rectangles;
the image dimensions alone do not establish their UV coordinates.
