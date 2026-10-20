# Emission and time

## Contents

- [Choose a temporal composition](#choose-a-temporal-composition)
- [Core emitter fields and units](#core-emitter-fields-and-units)
- [Native-accepted emitter fragments](#native-accepted-emitter-fragments)
- [Emission duration, particle lifetime and capacity](#emission-duration-particle-lifetime-and-capacity)
- [CP-driven delay and stopping](#cp-driven-delay-and-stopping)
- [Random scheduling and provider composition](#random-scheduling-and-provider-composition)
- [Birth-time and restart measurements](#birth-time-and-restart-measurements)
- [Minimal native probe set](#minimal-native-probe-set)
- [Evidence ledger and source boundaries](#evidence-ledger-and-source-boundaries)

Use this reference to turn a timing request into native Source 2 particle authoring choices. Keep three questions separate: what a field is intended to control, whether the target build accepts its representation, and what the running engine actually does. See [providers](providers.md) for typed values and [control points and children](control-points-children.md) for CP ownership and coordinate frames.

## Choose a temporal composition

| Visual intent | Useful composition | Decisions to make explicitly |
| --- | --- | --- |
| One impact or flash | An instantaneous emitter, shape initializer, lifetime and renderer | Burst count, onset, size, duration of the visible residue |
| Sparks followed by smoke | Separate burst and continuous components, often separate child effects | Which stage begins first, overlap, distinct lifetimes, shared CP bindings |
| A sustained aura or stream | A continuous emitter with explicit rate and an intentional stop mechanism | Density, maximum population, attachment, shutdown behavior |
| A delayed pulse | An instantaneous emitter with an explicit start input | Delay origin and whether a changing CP is supposed to reschedule it |
| A short stream with a lingering tail | Continuous emission duration plus a longer particle lifetime | Last birth time and disappearance time are different controls |
| A CP-controlled stop | A duration/stop component supported by the target schema | CP component, units, sampling time, and whether stopping affects existing particles |

These are authoring patterns, not complete resources. They still require a valid renderer, usable material/texture or model, initialization, bounds and game integration. Separate layers when they need independent duration, lifetime, orientation or resource state; share CPs deliberately rather than relying on implicit inheritance.

## Core emitter fields and units

The [embedded native help facts](native-help-facts.json) freeze the relevant start/rate/duration/cap/population/lifetime interpretations from a CRC/hash-verified local help payload. They retain exact token identities and passage hashes; their **Documented** level remains distinct from compilation and runtime observation.

Valve's distributed help assigns seconds to start, duration and lifespan, and particles/second to rate. It describes a single burst or an ongoing stream, and specifies unlimited emission for a zero continuous update cap. [Valve-authored CS2 tool help, online mirror](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt). This is descriptive documentation, not a runtime capture or a version match to the compiler evidence below.

| Class / field | Authoring role | Representation / qualification |
| --- | --- | --- |
| Both: `m_flStartTime` | Emission onset, seconds | Literal number-provider objects survived native compilation in the attached evidence |
| Continuous: `m_flEmissionDuration` | Emission interval length, seconds | A positive literal provider was preserved; do not infer zero/negative sentinel behavior from this test |
| Continuous: `m_flEmitRate` | Requested birth rate, particles/second | Literal provider preserved; runtime counting and fractional remainder rules need measurement |
| Continuous: `m_nLimitPerUpdate` | Birth cap per update | Valve help specifies **0 = no limit**; verify availability/type in the target schema |
| Instantaneous: `m_nParticlesToEmit` | Burst population | Despite the `m_n` prefix, a number-provider object was preserved; fractional/negative results require a separate behavioral test |
| Instantaneous: `m_nMaxEmittedPerFrame` | Burst distribution cap | Frame-based documentation exists; measure actual scheduling and sentinel values on the target build |
| System: `m_nMaxParticles` | Population ceiling | Distinct from requested count, rate, and any emitter cap |

The table deliberately gives no guessed numeric defaults. A property omitted after compilation can be default-valued, unsupported, or normalized elsewhere. Establish a default using an explicit default candidate **and a nondefault control**, on the same build. Do not replace provider objects with scalars merely because a field name resembles a float or integer.

The [attached compiler evidence](native-compiler-evidence.json) records CS2 build `25640462`, SourceRevision `11064488`, behavior version 12 in the decoded fixtures. Its `minimal_burst` retained a start provider of 0.125 seconds and a count provider of 24. Its `continuous_cp63` retained start 0.2, duration 2.5, and rate 36. These are tested inputs, **not defaults**. Both compilation and decoded readback succeeded; no native runtime timing or images were captured in that pass.

## Native-accepted emitter fragments

These fragments show the representations retained in those compiled fixtures. Place them in an otherwise valid system's `m_Emitters` array; they are not standalone effects.

```text
{
    _class = "C_OP_InstantaneousEmitter"
    m_flStartTime = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0.125 }
    m_nParticlesToEmit = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 24 }
}
```

```text
{
    _class = "C_OP_ContinuousEmitter"
    m_flStartTime = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0.2 }
    m_flEmissionDuration = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 2.5 }
    m_flEmitRate = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 36 }
}
```

Use a fresh effect instance to evaluate either fragment. With an explicitly finite lifetime and no early kills, compare an observation before onset, just after onset, near the intended end of emission, and after the remaining particles have died. Record birth activity separately from visible intensity: fading, off-screen particles, transparent materials, and occlusion can make continuing emission difficult to see.

## Emission duration, particle lifetime and capacity

Treat these as independent authoring decisions:

- **Emission duration:** how long births should continue.
- **Particle lifetime:** how long an individual particle should remain eligible to exist.
- **Fade interval:** how its appearance changes during that life.
- **Stop/destroy operation:** what the owning effect does when its controller stops or removes it.

For planning, a constant rate of 40 with a one-second lifetime suggests a steady population on the order of 40. This is a dimensional estimate, not an exact engine formula: caps, random lifetimes, initial particles, other emitters, death operators, events and children change the result. Start testing with a capacity comfortably above that estimate, then lower it while watching population and visual continuity.

For a strict visible-duration brief, budget every layer's last birth plus maximum remaining life, including child delays. A root lifespan alone does not set every child's duration. Keep normalized fade time, model-clip timing and PET playback speed distinct; see the [short-event pattern](observed-patterns.md#short-events-and-their-visible-tail).

A cap is not a rate control. Valve's help warns that delayed burst batches may share an end time; the population ceiling can reject births. [Valve-authored CS2 tool help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt). Verify both behaviors before relying on them for precisely timed layers.

Do not guess whether overflow is queued, discarded, retried, or redistributed, or whether the engine's update corresponds to a displayed frame under all conditions. Those choices materially affect sparks, tracer spacing and low-frame-rate bursts. Measure them with the cap probe below.

## CP-driven delay and stopping

A CP is a vector/transform channel, not intrinsically a duration. If a provider uses CP3.x as seconds, write that interface down: index, component, units, initialization value, writer, and when the value may change. Use a CP index distinct from the spawn transform for the first test so moving the emitter cannot accidentally change the requested delay. Consult [control points and children](control-points-children.md) before connecting parents and children.

`C_OP_StopAfterCPDuration` and its `m_flDuration` provider are schema-level authoring candidates. This guide has no matched native runtime observation establishing their sampling schedule or shutdown side effects. In particular, a class name does not establish whether its duration is sampled at creation, evaluated repeatedly, measured from system onset or an event, or applied to a parent, children, existing particles, or only future births.

For CP-driven start inputs, distinguish two desired interfaces before authoring:

- **Initial delay:** a controller supplies the delay before the effect is created; later edits should not retime the scheduled burst.
- **Live deadline:** changes to the CP are intended to affect whether or when the effect fires.

Neither interpretation follows automatically from provider serialization. First replace the CP input with a literal and verify the timing. Then test the CP input at a constant value, change it before onset, change it after onset, and finally move it backward across the threshold. Preserve the provider mode and CP binding in the recorded resource for every variant. Check [providers](providers.md) for the target game's supported input modes and mapping controls.

## Random scheduling and provider composition

Random start, random count and random lifetime answer different artistic questions. To obtain repeatable comparisons, first lock two of them to literals and vary only the third. A random start test should record when a fresh effect first emits, not only its appearance at a later time.

Do not assume that a collection-level provider ignores `m_nRandomMode` or `m_nRandomSeed`, that it resamples every update, or that identical seed numbers guarantee identical effects across games or builds. The intended scope of a random value and the actual engine sampling schedule must be established separately. A useful native experiment compares multiple fresh instances with a fixed seed, changes one provider seed, then repeats with a different root seed and a different frame cadence.

Do not confuse a vector provider's `m_FloatInterp` with its `m_FloatComponentX/Y/Z` inputs. One suggests an interpolation input and the others suggest axis components, but field presence alone does not determine the selected native branch, interpolation domain, endpoints, mapping order or evaluation frequency. Select the vector provider mode using its target schema, then test endpoints and midpoint with all other inputs fixed. See [providers](providers.md) rather than inventing a vector interpolation formula.

## Birth-time and restart measurements

For ordinary uncapped tests, use particle age as elapsed life since creation, while checking whether any pre-age initializer deliberately offsets that age. A start boundary falling between two engine updates is especially useful: it can reveal whether births and first movement are placed at the interval start, interval end, or an internal time. Do not prescribe a fractional-timestep movement formula without measuring it.

Use a small constant velocity, no drag/gravity, a long explicit lifetime and a start offset that does not line up with the capture cadence. Capture the first positions of new particles at several cadences. This separates sub-frame birth handling from decay or frame-dependent force integration. Repeat with no velocity to compare birth/death timing independently of motion.

A fresh effect instance, an editor restart, a timeline scrub, and a stop/start on an existing owning entity are different operations until the target tools establish otherwise. Test whether each operation resets one-shot emission, random choices, children, event state and CP values. Do not use a repeated editor loop as proof that the running game will automatically retrigger an instantaneous emitter.

## Minimal native probe set

These are proposed experiments, not pre-certified results. Use a simple visible particle, fixed lifetime and ample capacity unless the row intentionally varies them.

| Probe | Change only | Record / question answered |
| --- | --- | --- |
| Literal onset | Start 0.125 versus 0.625 | First birth relative to fresh effect creation; timing units and delay origin |
| Literal count | Burst count 8 versus 24 | Accepted births and maximum visible population before deaths |
| Stream duration | Duration 0.5 versus 1.5, fixed rate | Last birth, then last death; emission stop versus life tail |
| Continuous update cap | Positive cap versus zero | Births per observed update; confirm the documented unlimited-zero case |
| Burst frame cap | Small positive cap versus uncapped configuration saved by the editor | Batch timing, accumulated count, and whether late particles share an end time |
| Capacity pressure | High capacity versus capacity below requested population | Rejected versus delayed births; recovery when particles die |
| CP delay | Same initial CP3.x, then one pre-onset edit | Cached scheduling versus live reevaluation |
| CP stop | Literal duration, constant CP input, then a mid-run CP edit | Sampling time, stop scope and effect on existing particles |
| Birth inside an update | Non-aligned start, multiple capture cadences | First displacement and age; sub-frame treatment without assuming a formula |
| Restart/retrigger | Fresh creation, tool restart, owner stop/start | Which operation really starts a new burst and resets state |
| Random schedule | Fixed/changed seed, same inputs and cadence | Repeatability and sampling scope on this exact build |

For every probe, keep resource identity, build, material, CP history, camera, frame/capture timing and any quality settings fixed. Distinguish requested births, accepted births, current live particles, and pixels. If only video is available, report the measured appearance/disappearance intervals instead of claiming an exact internal count.

## Evidence ledger and source boundaries

| Statement | Current evidence | Remaining uncertainty |
| --- | --- | --- |
| Start/duration/lifetime use seconds; continuous rate is per second | Valve-authored particle tool help linked above | Exact boundary placement, precision and game-specific timing adjustments |
| Listed literal emitter-provider representations are accepted | [Native compiler evidence](native-compiler-evidence.json), named burst/continuous fixtures | Evaluation schedule, random behavior and visual result |
| Continuous zero update cap means unlimited | Distributed Valve tool-help documentation | Target-build runtime confirmation under the intended cadence |
| Numeric emitter defaults, count rounding, overflow policy, dynamic CP stop and restart details | No matched native runtime capture attached here | Run the relevant probes; keep these claims unresolved |

The online tool-help URL is a mirror of Valve-authored game resources, not a build-pinned runtime capture. Compare it with the help and schema shipped with the target game. Older Source-engine manuals and another Source 2 game's interfaces can suggest a probe, but do not silently substitute for the selected game's build.

Compiler exit code zero is insufficient: the attached native evidence includes deliberately unknown fields that were removed without an error. Inspect the decoded compiled values and include nondefault controls. Use [evidence and verification](evidence.md) when promoting an authoring hypothesis to a documented native runtime result.
