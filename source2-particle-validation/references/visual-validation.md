# Runtime, control-point, and visual validation

## Contents

- [Choose and identify the validation surface](#choose-and-identify-the-validation-surface)
- [Manual official-editor procedure](#manual-official-editor-procedure)
- [Establish a reproducible observation](#establish-a-reproducible-observation)
- [Write the CP contract before testing it](#write-the-cp-contract-before-testing-it)
- [Exercise CP 0 and CP 1 independently](#exercise-cp-0-and-cp-1-independently)
- [Test lifetime and child propagation](#test-lifetime-and-child-propagation)
- [Verify artwork, blend, depth, and scene interaction](#verify-artwork-blend-depth-and-scene-interaction)
- [Verify delivery in the intended game environment](#verify-delivery-in-the-intended-game-environment)
- [Deliver independent evidence and limits](#deliver-independent-evidence-and-limits)

Use this procedure when the claim concerns native motion, control points
(CPs), child behavior, artwork, or delivery in the intended game. Keep native
compiler acceptance and [compiled retention](compiled-readback.md) as separate
results. Neither establishes the behavior below.

## Choose and identify the validation surface

| Surface | What an observation can establish |
| --- | --- |
| Official CS2 Particle Editor / PET preview | Behavior and appearance in that installed tools preview, with the CP inputs actually supplied there |
| Intended CS2 game/addon scene | Spawn/precache path, entity and attachment mapping, live updates, scene interaction, and resources visible in that test environment |
| Third-party resource viewer | What that viewer decodes or renders; it is not CS2 runtime evidence |
| Custom renderer or simulation | Behavior of that implementation under its supplied inputs |

Record the exact surface, game/build, addon, selected asset path, source/binary
digests, and observation date. CS2 and Deadlock require separate runs and
reports. Matching class names, a successful Deadlock preview, or another
Source 2 game's editor cannot certify CS2 behavior.

Use a native graphical surface already available or open the official tools
when native visual testing is within the requested task. A compile-only task
does not require launching the game, editing launch options, or changing an
existing addon. Do not assume a headless particle-image command or a working
direct-asset launch recipe. If the native tools or game scene are unavailable,
finish the independent checks and mark the corresponding visual/runtime
checks **not run**, with the specific reason.

## Manual official-editor procedure

1. Identify the installed CS2 Workshop Tools and the intended addon through
   their available launcher/interface. Confirm the addon content and compiled
   resource paths. Do not infer that an arbitrary file outside mounted content
   is openable by the tools.
2. Inspect the interface actually present. Use its asset browser or file-open
   action to select the intended `.vpcf` and open the available particle editor.
   Confirm the displayed resource path. If an asset-opening error appears,
   resolve mounting/path/compilation before making appearance claims.
3. Locate the visible preview, playback/restart controls, component properties,
   and any CP/test-input controls. Record which are available and how values
   were entered. Labels and layouts can differ between builds. Do not invent
   a menu, hotkey, console command, scripting API, or automation capability.
4. Replay the effect from a known start using the available control. If only
   continuous playback is exposed, record that limitation and use a timed
   screen recording or repeated restarts; do not claim exact frame stepping.
5. Verify the resource shown after edits/recompilation. Restart or reopen it
   when required by the observed UI, then record that action. Stale preview
   state must not be mistaken for the compiled revision under test.
   Recheck committed CP values after reload; preview inputs can survive it.
6. Enter the CP/test inputs needed for the contract if the UI exposes them.
   If a transform, attachment, collision surface, or lifecycle operation cannot
   be supplied there, move that test to an authorized game test scene or mark
   it untested. A preview default is not evidence of a live entity attachment.

Use manual interaction when that is the capability available. Optional UI
automation must be based on controls and capture facilities verified in the
current environment; it is not a prerequisite for completing this procedure.

## Establish a reproducible observation

Preserve a baseline capture with the asset identity visible, then capture the
effect unobscured. Record:

- Camera position/view, field of view or zoom, resolution, background, exposure
  and lighting, playback speed, elapsed effect time, and the effect's scale.
- Emission type/rate or burst count, maximum particle budget, lifetime range,
  parent/child start offsets, and seed/deterministic options if actually exposed.
- CP positions, orientations, parents/remaps, and any driven scalar/vector
  values; include scene/entity motion when those supply the CPs.
- Relevant quality, LOD, culling, and rendering settings when comparing images.
  Do not change them between comparison captures without noting the change.

Capture startup, peak, sustained phase where applicable, fade, last parent
particle death, child completion, and post-completion. Choose times from the
authored duration; for a short burst, several fractions of its lifetime plus
one sample after the final child dies are more useful than one arbitrary shot.
For looping effects, capture at least two cycles and a stop/restart transition.

Use a short video or ordered frame sequence for trails, rotating sprites,
animated textures, flicker, emission cadence, or rapidly changing CPs. Label
timestamps from the tool timeline where available. Wall-clock estimates are
approximate and must be labeled as such. If randomness cannot be fixed, repeat
the same setup and distinguish expected variation from a systematic defect.

A nonblank image, particle count, or viewport grid does not certify appearance.
Check that the capture contains the intended effect rather than an asset
browser, error material, missing-resource message, overlay, or unrelated system.

## Write the CP contract before testing it

CP numbers have meanings assigned by the authored system and its caller.
Do not assume CP 1 is always an endpoint or that a CP vector always represents
a position. Record each use explicitly:

| CP | Authored consumers | Supplied by caller | Space and updates |
| --- | --- | --- | --- |
| 0 | List spawn/transform/orientation consumers actually present | Origin, entity, or named attachment actually bound | World/local basis, parent/remap, startup and live updates |
| 1 | List endpoint, direction, attraction, scalar/vector, or other consumers | Independently assigned input or explicit alias/remap | Units, component packing, orientation, update timing |
| Other claimed CPs | Exact consuming classes/properties | Actual binding mechanism | Index range verified for the target, inheritance and timing |

Record entity identifiers and attachment names for a game test, and the
preview controls used for an editor test. If the contract consumes only CP 0,
use a disposable diagnostic variant with a verified CP-consuming component to
test CP 1 mapping; do not claim the unmodified effect already uses it. Include
the highest CP index the deliverable claims to support when relevant, using
the target's verified range rather than an assumed universal maximum.

## Exercise CP 0 and CP 1 independently

Keep input changes separate and compare against a baseline. Example probe
positions in authored units are CP 0 = `(0, 0, 0)` and CP 1 = `(128, 32, 64)`;
adapt their magnitude to keep the effect in view. The unequal coordinates make
swapped axes and aliasing easier to notice. Do not infer the axis convention
from those numbers alone.

| Probe | Action and required observation |
| --- | --- |
| Mapping | Separate CP 0 and CP 1 spatially. Move CP 1 alone, then CP 0 alone. Identify which spawn region, endpoint, child, or target follows each input. |
| Position | Translate one CP along each known axis. Compare measured origin/endpoint displacement with the supplied displacement; check unexpected offsets and scale. |
| Orientation | Keep position fixed; apply identity and a quarter turn around one verified axis, then a second axis. Record units/convention used by the actual UI or runtime binding. Use an asymmetric direction/shape to reveal the rotation. |
| Live sampling | Start playback, let a visible cohort survive, then move/rotate the CP at a recorded time. Observe already-alive particles and later emissions separately. |
| Parenting | Where authored, move/rotate the parent CP, then alter the child CP's local transform. Check local-versus-world interpretation and any explicit remapping. |
| Invalid or absent input | Only when part of the requested contract, omit a required binding in a disposable test and record the actual failure/default behavior. Do not rely on an untested fallback. |

Check consumers independently: spawn position, initial velocity/direction,
sprite normal or orientation mode, attraction target, trail endpoint, and
child propagation. Screen-facing sprites may intentionally ignore CP rotation;
a rotated spawn region does not prove sprite orientation support. A position
test does not prove basis vectors were supplied correctly.

Repeat after a restart to distinguish startup sampling from live sampling.
Record whether a change affects initializers, update operators, new particles,
existing particles, children, or only the renderer. Retained CP indices and
correct preview transforms do not establish that the intended game's caller
updates those same inputs.

## Test lifetime and child propagation

Run the actual spawn/start, emission-stop, natural completion, restart, and
destruction operations exposed by the chosen surface. Distinguish stopping
emission from immediately destroying the system. If the surface cannot
perform an operation, leave that result untested.

- Observe particle age, fade-in/out, size/color over life, and death against
  the authored lifetime range. Check for residual particles after the expected
  tail, then replay to catch state retained across restarts.
- Inspect every child: path, enabled state, start delay, inherited or remapped
  CPs, spawn location, orientation, and live movement. Test the child alone
  when possible, then within its parent; standalone success does not prove
  parent propagation.
- Stop or destroy the parent and observe whether children finish, stop, or
  continue according to the authored contract. Capture endcap/death effects
  and their completion when present. Check repeated spawn/stop cycles for
  duplicate child instances or growing residual counts.
- For continuous effects, observe long enough to reach steady state and test
  the longest claimed parent/child tail. A startup screenshot cannot establish
  bounded lifetime, stable counts, or correct shutdown.

Do not estimate native lifetime equations from compiled values alone. If exact
timing is required, use timestamped playback/recording and define a tolerance
before comparing observations.

For a one-shot PET test, disable Auto-Restart if available, wait beyond
the last child lifetime, and capture the completed empty state. Re-enable
it for convenient preview only after recording the shutdown result.
Keep playback at the recorded normal rate for a duration claim. A finite
emitter test, pressing PET Stop, and invoking the game's emission-stop API are
different tests: an empty viewport after an intervention does not prove a
natural tail duration or the caller's shutdown behavior. If a preview actor
shares the capture, distinguish the whole visible composition's duration from
the production effect's own last-particle time.

## Verify artwork, blend, depth, and scene interaction

Use the intended material and texture in the final render. Verify the bound
resource paths and inspect texture artwork/alpha separately when needed.
Compare the actual silhouette, edge softness, color, opacity, aspect ratio,
UVs, sequence/frame ordering, animation rate, and trail continuity against the
requested look. A placeholder disk cannot certify a textured sprite effect.

For blending, capture on dark, midtone, and light backgrounds and with several
overlapping particles. Check edge halos, additive saturation, unexpected dark
fringes, alpha cutout, and opacity over life against the material's intended
blend mode. Do not assume every shader uses the same straight/premultiplied
alpha contract or that a decoded alpha channel proves the material uses it.

For depth, place an opaque surface in front of, through, and behind the effect
in a suitable scene. Move the camera and emitter to expose sorting, depth
testing, intersection fading/soft-particle behavior, and clipping where those
features are claimed. Record material/settings and viewing angle. A flat
background provides no occlusion evidence.

Test collision, gravity, lighting response, fog, water, shadows, attachment
motion, bounds/culling, distance/LOD, and camera-dependent orientation only in
surfaces that supply those inputs. Use a representative gameplay scene when
the claim depends on them. Treat performance separately: record measurement
method, particle counts, scene, and hardware for any performance claim;
screenshots alone do not establish cost or acceptable overdraw.

For refraction, isolate the layer over a fixed structured background such
as the viewport grid. Look for localized background distortion rather than
a bright sprite or blur alone, then check the final root composition again.

## Verify delivery in the intended game environment

Use the actual supported spawn/precache mechanism for the target setup; inspect
its available interface or API before constructing commands. Do not borrow
Source 1, Dota, or Deadlock commands as CS2 instructions. Record the resource
string requested, resolved system, entity/attachment bindings, client-visible
result, and relevant console/log diagnostics.

Reconcile the authored child graph and transitive external dependencies with
the files shipped by the intended addon/package. Distinguish target-game base
resources from owned packaged resources. A local editor may resolve loose
files or other mounted content that the recipient will not have. Verify the
intended mounted/package environment without relying on those loose copies
when delivery is in scope; this does not require publishing a Workshop item.

If an effect is invisible, preserve the failure and test one layer at a time:
correct asset/revision, successful spawn/precache, emission/lifetime, CP
placement, camera/bounds/culling, material/texture resolution, depth/blending,
children, and package closure. A simplified diagnostic copy can isolate a
cause; rerun the final authored effect after the fix before declaring success.

## Deliver independent evidence and limits

Use **pass**, **fail**, **inconclusive**, or **not run** for each category,
with artifact paths and the exact claim tested:

| Category | Evidence required for a positive claim |
| --- | --- |
| Native compilation | Target compiler identity, native exit, logs, fresh output digests |
| Property retention | Decoder identity/diagnostics and controlled owning-node readback |
| CP/runtime behavior | Input/binding contract and observed position, orientation, live-update, lifetime and child tests relevant to the claim |
| Visual appearance | Timed native captures using intended artwork, material, camera, and relevant blend/depth conditions |
| In-game delivery | Spawn/precache/attachment observations in the intended mounted environment plus dependency/package audit |

Retain the baseline and failed captures as well as successful ones. A compact
manifest should map each capture to asset digest, surface/build, time, camera,
CP inputs, action, expected result, and observed result. Use relative paths in
portable reports; retain machine-specific paths only in local run details.

Name the precise missing evidence: tools unavailable, asset cannot be mounted,
no CP input UI, no required scene surface, no exact timing control, no live
spawn access, or decoder/compilation failure. “Compiled; appearance unverified”
is valid when no native visual test ran. A successful PET preview with no live
spawn test leaves in-game precache, attachment, and delivery unverified. A
visible live effect with untested shutdown or CP 1 behavior proves only the
observed cases; do not promote it to universal support.
