# Motion, forces, and lifetime

## Contents

- [Evidence and defaults](#evidence-and-defaults)
- [Movement Basic](#movement-basic)
- [Force generators](#force-generators)
- [Radius changes](#radius-changes)
- [Alpha fades and death](#alpha-fades-and-death)
- [Native editor test compositions](#native-editor-test-compositions)

Use this when composing native movement, force generators, size changes, fades, and particle death. An initial velocity, an ongoing force, a radius multiplier, and a death condition are separate controls. Choose each property's actual type and clock before combining operators.

## Evidence and defaults

- **Documented:** Valve's shipped [particle editor help](https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt), mirrored from game data, documents authoring intent. Some tokens predate current field layouts. The current mirror is not confirmed to match the September build below.
- **Typed:** The bundled schema catalogue (`$source2-particle-schema`) records types, labels, and reflected defaults for CS2 revision `11131657`, dated 14 October 2026. A label does not establish an algorithm.
- **Serialized:** The [native compiler evidence](native-compiler-evidence.json) records compilation and decoded values for CS2 revision `11064488`, dated 30 September 2026. These are different builds.
- **U-behavior:** Exact integration, random sampling, easing, boundaries, and interactions need controlled native observations. A type or successful compilation proves narrower facts.

Defaults below belong to the recorded schema snapshot. Set critical values explicitly; inspect affected compiled values for a different game, an unfamiliar contract, or a relevant change/regression. A new CS2 build ID alone does not require repeating every probe. A compiler may omit defaults or silently discard an unknown property.

## Movement Basic

The [embedded help facts](native-help-facts.json) preserve selected movement, attraction-sign, shared-random-force, Simple-fade and decay interpretations with exact native token/hash provenance. They are descriptive documentation rather than an integrator or opacity measurement.

Valve documents `C_OP_BasicMovement` as enabling fundamental particle movement. Its typed fields (`$source2-particle-schema`) include:

| Field | Native type | Authoring role / reflected default |
|---|---|---|
| `m_Gravity` | `CParticleCollectionVecInput` | Gravity input; literal `[0,0,0]`. Choose the provider and coordinate space deliberately. |
| `m_fDrag` | `CParticleCollectionFloatInput` | Drag control; literal `0`. Editor metadata advertises `-1..1`. |
| `m_massControls` | `CParticleMassCalculationParameters` | Mass settings; inspect its members for mass-dependent compositions. |
| `m_nMaxConstraintPasses` | `int32` | Constraint pass limit; `3`. |
| `m_bUseNewCode` | `bool` | Implementation-selection switch; `false`. Hold it fixed during comparisons. |

Start with explicit initial velocity, Movement Basic, gravity/drag zero, a fixed lifetime, and a visible renderer. Add gravity, then test drag with the same initial velocity. Test each force separately before combining them. This isolates absent motion from a disabled operator, a missing velocity input, or rendering that obscures movement.

The schema does not establish drag as a percentage removed per frame or per second. Its typed range includes negative values: neither clipping negatives nor assigning a universal amplification formula is justified. Exact force composition order, mass division, integration method, and timestep compensation remain unknown here. Do not substitute an assumed Euler, Verlet, or exponential-damping equation for a measured native result.

Use engine spatial units. Record provider space and transforms alongside coordinates; CP position, CP orientation, and camera axes are different inputs. See [providers](providers.md) and [control points and children](control-points-children.md).

## Force generators

### Pull towards a control point

Valve documents attraction to the selected CP and repulsion with negative force amount. The AttractToControlPoint schema (`$source2-particle-schema`) distinguishes:

| Field | Native type | Editor role / reflected default |
|---|---|---|
| `m_TransformInput` | `CParticleTransformInput` | Target position transform; `PT_TYPE_CONTROL_POINT`, CP0, orientation disabled. Select the intended CP explicitly. |
| `m_fForceAmount` | `CPerParticleFloatInput` | Force amount / maximum force; literal `100`. |
| `m_fMinimumDistance` | `CPerParticleFloatInput` | Threshold distance for maximum force; literal `0`. |
| `m_fFalloffPower` | `float32` | Distance falloff control; `2`. |
| `m_vecComponentScale` | `Vector` | Component scaling; `[1,1,1]`. |
| `m_fForceAmountMin` | `CPerParticleFloatInput` | Minimum pull-force input; literal `0`. |
| `m_bApplyMinForce` | `bool` | Minimum-force option; `false`. |

Those labels do not prove an inverse-square equation, a singularity rule, minimum/maximum clamp order, or component scaling's coordinate basis. Compare particles at two known distances to measure falloff. Test immediately inside/outside the threshold separately. Rotate the selected CP without translating it to investigate orientation options instead of inferring their behavior from a boolean name.

### Curl noise

The CurlNoiseForce schema (`$source2-particle-schema`) declares:

| Field | Native type | Editor role / reflected default |
|---|---|---|
| `m_nNoiseType` | `ParticleDirectionNoiseType_t` | Noise selection; `PARTICLE_DIR_NOISE_PERLIN`. |
| `m_vecNoiseFreq` | `CPerParticleVecInput` | Noise frequency; literal `[0.02,0.02,0.02]`. |
| `m_vecNoiseScale` | `CPerParticleVecInput` | Amplitude; literal `[1000,1000,1000]`. |
| `m_vecOffset` | `CPerParticleVecInput` | Offset; literal `[0,0,0]`. |
| `m_vecOffsetRate` | `CPerParticleVecInput` | Offset progression; literal `[0,0,0]`. |
| `m_flWorleySeed`, `m_flWorleyJitter` | `CPerParticleFloatInput` | Worley controls; literal `0` and `0.875`. |

Frequency, amplitude, offset, and offset rate are distinct controls. Change one at a time, then isolate individual axes. The noise algorithm, curl construction, offset units, seed distribution, and continuity across frames are not established by the field catalogue. Do not describe arbitrary trigonometric motion as this native algorithm or copy an obsolete help token when the current schema declares another field.

### Random force

Valve describes a random force shared uniformly across an effect. The RandomForce fields (`$source2-particle-schema`) are `m_MinForce` and `m_MaxForce`: plain `Vector`, both defaulting to `[0,0,0]`. They are not per-particle vector providers.

Use several particles to distinguish a common influence from independent jitter. Equal min/max vectors remove range variation for a diagnostic. Neither the distribution nor resampling interval is certified here; record seed/restart behavior rather than assuming exact reproducibility.

## Radius changes

Valve describes `C_OP_InterpolateRadius` as scaling across an interval and advises nonoverlapping intervals for multiple instances. Its typed fields (`$source2-particle-schema`) are:

| Field | Native type | Reflected default |
|---|---|---|
| `m_flStartTime`, `m_flEndTime` | `float32` | `0`, `1` |
| `m_flStartScale`, `m_flEndScale` | `float32` | `1`, `1` |
| `m_bEaseInAndOut` | `bool` | `false` |
| `m_flBias` | `float32` | `0.5` |

Initialize a visible radius, then vary the scale endpoints. These are direct scalar fields, not number-provider objects. Bias and easing are transition controls; their exact curves and composition order need measurement. The reference radius during overlapping operators, boundary inclusivity, and writes outside an interval are also unmeasured. Do not publish a rational bias or smoothstep formula as Valve's implementation.

The captured labels alone do not certify the radius time fields' units. Compare two- and four-second lifetimes at matched seconds and matched lifetime fractions. Record which timing aligns on the target build before using the transition for synchronization.

## Alpha fades and death

Valve documents Simple fade times as lifespan fractions. Ranged fades can use seconds with `m_bProportional=false`. A duration fraction `0.2` corresponds to `0.8` seconds for a four-second lifetime; an absolute duration `0.2` remains `0.2` seconds. This conversion specifies the time domain, not an opacity curve.

| Native class | Fields, types, and reflected defaults |
|---|---|
| C_OP_FadeInSimple (`$source2-particle-schema`) | `m_flFadeInTime: float32 = 0.25`; `m_nFieldOutput: ParticleAttributeIndex_t = 7`, labeled alpha field. |
| C_OP_FadeOutSimple (`$source2-particle-schema`) | `m_flFadeOutTime: float32 = 0.25`; `m_nFieldOutput: ParticleAttributeIndex_t = 7`. |
| C_OP_FadeIn (`$source2-particle-schema`) | `m_flFadeInTimeMin/Max: float32 = 0.25`; `m_flFadeInTimeExp: float32 = 1`; `m_bProportional: bool = true`. |
| C_OP_FadeOut (`$source2-particle-schema`) | `m_flFadeOutTimeMin/Max: float32 = 0.25`; `m_flFadeOutTimeExp: float32 = 1`; `m_flFadeBias: float32 = 0.5`; `m_bProportional = true`; `m_bEaseInAndOut = true`. |

Do not copy the Simple class's direct time field onto the ranged class. For a fixed ranged duration, set min=max. Investigate the exponent separately with a larger population; its field identity does not prove an exact probability distribution. Changing fade duration and changing particle lifespan are separate authoring decisions.

**Observed omission default:** In the native compiler evidence, FadeOutSimple time `0.25` is omitted from decoded compiled output while `0.37` survives. This supports the serialization default for the identified build. It does not prove linear alpha interpolation, endpoint inclusivity, composition with other alpha writers, or rendered opacity.

### Decay and combined fades

Valve identifies C_OP_Decay (`$source2-particle-schema`) as lifespan-based removal. Include an explicit death mechanism. Invisibility alone does not demonstrate removal. Its schema includes `m_bRopeDecay` and `m_bForcePreserveParticleOrder`, both reflected false; hold them fixed when testing ordinary lifespan behavior.

Valve describes C_OP_FadeAndKill (`$source2-particle-schema`) as combining fades with decay. These are direct `float32` fields:

| Field | Reflected default |
|---|---|
| `m_flStartFadeInTime`, `m_flEndFadeInTime` | `0`, `0.5` |
| `m_flStartFadeOutTime`, `m_flEndFadeOutTime` | `0.5`, `1` |
| `m_flStartAlpha`, `m_flEndAlpha` | `1`, `0` |

It also declares `m_bForcePreserveParticleOrder: bool = false`. Do not replace these recorded values with guessed zero-alpha endpoints or different fade windows. Observe boundaries before combining it with another alpha/death writer.

### Operator clocks and end caps

Inherited operator fades are separate from particle alpha fades. Valve help places their clock relative to emitter lifespan, with period-relative timing for oscillating operator fades. Consequently, `m_flOpStartFadeInTime` and `m_flFadeInTime` are not interchangeable.

Inspect inherited strength, disable, tools/game selection, normalization-to-stop, fade/offset/timescale controls, and ParticleEndcapMode_t (`$source2-particle-schema`) when a property appears inactive. Preserve unknown enum tokens and identify them as unresolved instead of coercing them to a familiar mode.

C_OP_EndCapTimedDecay (`$source2-particle-schema`) declares `m_flDecayTime` as a collection float provider. C_OP_LerpEndCapScalar (`$source2-particle-schema`) declares a typed output attribute plus scalar output/lerp time. Activation, repeated-stop behavior, and exact clock/reset rules require controlled stop events; names alone do not prove them.

## Native editor test compositions

These are proposed experiments, not completed observations. Use a clearly visible material, disable collisions/unrelated operators, fix count/lifetime, and record the build. Reset the entire effect between comparisons. Hold seed settings constant where exposed; if reset changes the random realization, record repeated trials.

1. **Gravity and drag:** Emit a small burst with one known initial velocity, four-second lifetime, Movement Basic, and Decay. Capture positions at `0.5`, `1`, and `2` seconds with gravity/drag zero. Change gravity only; reset and repeat. Restore gravity and change drag only. Use a side camera and a perpendicular camera to expose depth/axis mistakes.
2. **Two-CP attraction:** Spawn at CP0 and place CP1 at `[128,0,64]`. Select CP1 explicitly. Compare positive, zero, and negative force amounts with gravity/drag zero. Move CP1 and reset; then move it while particles are alive. Rotate CP1 without translation in a separate pass. Hold the camera still during each comparison.
3. **Forces together:** Capture attraction, RandomForce, and CurlNoiseForce separately before combining two. Test RandomForce min=max. For curl, change amplitude with frequency/offset fixed, then restore amplitude and change frequency. Inspect multiple particles for correlated motion. Repeat in a child system to investigate force ownership and inherited CP inputs.
4. **Radius timing:** Use no movement and a fixed starting radius. Compare scale endpoints with easing disabled, enable easing, then vary bias alone. Repeat with two- and four-second lifetimes. Compare matched seconds and matched life fractions from the same camera.
5. **Fade clocks:** Use a material with visible alpha response, a fixed radius, and no movement. Test Simple fades separately. Test ranged fades with min=max `0.2`, proportional true then false, for both lifetimes. Record alpha or calibrated images around the intended boundaries; combine fades only after isolating each.
6. **Death and stop:** Compare live count against visible count with Decay enabled/disabled and then with FadeAndKill. Start a continuous effect, stop emission at a recorded time, observe survivors, and restart it. Inspect children independently; a parent's disappearance does not establish a child's death policy.

Scope resulting claims to the measured class, properties, lifetime, material, CP poses, and build. See [evidence](evidence.md) for separating documented intent, typed metadata, serialization, and observed behavior.
