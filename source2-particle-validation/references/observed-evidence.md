# Observed CS2 evidence — 2026-10-15

## Contents

- [Installation identity](#installation-identity)
- [Compiler acceptance and retention](#compiler-acceptance-and-retention)
- [Compound effect and recompilation-filter probes](#compound-effect-and-recompilation-filter-probes)
- [Positive texture compilation controls](#positive-texture-compilation-controls)
- [Standalone helper check](#standalone-helper-check)

These are historical local measurements, not defaults guaranteed for every
future installation. No native binary or Valve source asset is included here.

## Installation identity

- Steam app 730, installed build **25640462**, patch **1.41.8.8**.
- `steam.inf` SourceRevision **11064488**, version date **2026-09-30**.
- Compiler executable SHA-256:
  `00db3daca0e733601bf3fcc1d1bf9df1b2ade805629098c48bd6c51af3d96f51`.
- Installed `resourcecompiler.dll` SHA-256:
  `3b4fa1887be100551160188f7f2cf70ae9fbe51598a07e5d33302b53a40382a6`.
- Installed `particles.dll` SHA-256:
  `2cf870d86cddc8326534f37fce39735b5f2937755bf538e50d9b1932c79ddd2b`.
- Installed `resourcesystem.dll` SHA-256:
  `91fefb1a36111c34e380a8ec2c74c584f29ef66332a0ddba01123dd0adec778d`.

A public schema with SourceRevision **11131657** was newer than this installed
build and was not used to certify its runtime semantics.

## Compiler acceptance and retention

Thirteen authored fixtures compiled into fresh addons using `-i`, `-game`,
`-nop4`, and `-fshallow`. All produced `.vpcf_c` with native exit 0; all decoded
without diagnostics. Cases covered burst/continuous emission, point/sphere/box
spawn, CP 1/63, gravity/drag, random force, attraction, four sprite orientations,
trails, rotation/sequence and an explicit base-game model reference.

`C_INIT_CreateWithinSphereTransform.m_fRadiusMin` retained a literal provider
with value **2**, while `m_fRadiusMax` retained **18**. Spawn CP **1** and an
attraction target CP **63** also survived. This proves accepted serialization
shapes, not native sampling or CP attachment behavior.

Controlled value comparisons showed:

| Authored default-valued input | Binary observation | Nondefault control |
| --- | --- | --- |
| Root `m_flConstantRadius = 5` | Omitted | 7 retained |
| Root `m_bInfiniteBounds = false` | Omitted | true retained |
| InitFloat `m_nOutputField = 3` | Omitted | 1, 4, 5 and 10 retained |
| FadeOutSimple `m_flFadeOutTime = 0.25` | Omitted | 0.30/0.37 retained |
| InterpolateRadius start 0/end 1 | Omitted | 0.2/0.8 retained |
| Attraction `m_fFalloffPower = 2` | Omitted | 1.25 retained |
| Transform CP 0 | Omitted | CP 1/63 retained |
| Sprite screen-aligned enum | Omitted | Three other enum values retained |
| Sequence minimum 0/linear false | Omitted | Minimum 1/linear true retained |

A deliberately unknown root sentinel with value `123.456` and renderer
sentinel with value `789.25` were silently discarded while the compiler returned 0.
Neither a permissive text parser accepting a key nor native exit 0 proves property support.

## Compound effect and recompilation-filter probes

A subsequent native compiler run built a root and two child
systems in a new addon. All three outputs decoded without diagnostics; the
root readback retained both child references. The sprite child and a model
child referencing installed `models/particle/flecks3.vmdl` compiled with
`-skiptype vmat,vmdl,vtex`. No game/PET process was launched.

Filter calibration was deliberately inconclusive about dependency isolation:

- A particle referencing an intentionally invalid `.vtex` source compiled
  with **and without** `-skiptype`, producing no `.vtex_c` in either case.
  Thus compiler acceptance also failed to prove texture closure.
- Compiling that invalid `.vtex` as the explicit top-level input failed with
  exit **1**, with **and without** `-skiptype`. The filter did not rescue or
  skip this explicitly requested input in that experiment.

The help documents a recompilation filter, and the flag was accepted. These
experiments do not establish that it prevents every dependent rebuild or
confines filesystem writes. Do not promote the flag into a sandbox guarantee.

No native pixels, temporal equations, material fidelity, collisions, live CP
updates, or in-game resource closure were certified by these runs.

## Positive texture compilation controls

Two additional owned procedural source controls compiled successfully on the
first attempt with the same installation and ordinary `-fshallow` flags:

- A 64×64 neutral-white RGBA TGA and authored `CDmeVtex` DMX source produced
  a 64×64 `RGBA8888` texture with one mip. The decoded base mip matched every
  original TGA RGBA component exactly, including transparent texels.
- An MKS containing eight owned 64×64 TGA frames produced a 256×128
  `RGBA8888` atlas with one mip and SHEET version 8, one sequence and eight
  frames. Each retained display time was approximately 1/24 second; the
  sequence time field was approximately 1/3 second.

An important readback naming trap: inspected VTEX decoding code
exposed that sequence time field as `framesPerSecond`, but its textual dump
labels it `m_flTotalTime`. Do not interpret the observed 0.333333 value as an
observed playback rate. Actual native playback still requires a visual test.

These textures used linear input/output channel settings, `RGBA8888`, and
`m_bNoLod = true`. They establish two controlled source/compiler/byte-decoding
paths, not universal texture settings or material correctness. The decoder
retained its non-streaming-size-versus-trailing-payload warning and preserved
an unrecognized `RED2` section; those diagnostics were not suppressed to claim
a clean readback.

## Standalone helper check

The shipped Python standard-library helper was exercised with eleven synthetic
behavior tests: all eleven passed, including a real directory symlink and the
Windows reparse-attribute guard. The aggregate-output test also counts an
unselected dependency output. Accounts lacking permission to create a link may
skip that particular real-link test. An earlier ten-test revision also ran
from an isolated copy with Python isolated mode; it passed nine and skipped
only the account-restricted real-link test.

A direct native invocation of the final helper compiled an original root and
two authored child VPCFs on the installation identified above. Three selected
inputs returned 0 and produced fresh outputs. No source repair was needed.
No optional viewer was invoked in that check, and no property-retention,
runtime or visual pass was inferred.

The [portable helper evidence](helper-evidence.json) records the tested script
fingerprint, compiler/game identity, exact source fingerprints, process
outcomes and compiled-output hashes. It contains no compiled binary or absolute
user path. The optional viewer protocol was tested with an injected runner;
use the actual viewer's help and inspect its diagnostics before real readback.
