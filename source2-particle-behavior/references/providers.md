# Native providers: source, mapping and context

## A provider is a computation

`CPerParticleFloatInput`/`CPerParticleVecInput` differ from direct scalars/vectors; `CParticleCollectionFloatInput` is collection-scoped. A property prefixed `m_fl` can still be a provider: native `C_OP_ContinuousEmitter.m_flStartTime` is a collection float input. Check the schema type before choosing its KV3 shape.

Choose **source**, **map**, and **evaluation context** separately. The consuming field determines units: count, speed and lifetime can use the same input structure without having the same dimension. Resolve actual enums/default objects through the schema catalogue (`$source2-particle-schema`); use target-game tool help where available.

## Scalar sources

| Family | Relevant fields/tokens | Authoring meaning and decisive check |
|---|---|---|
| Literal | `PF_TYPE_LITERAL`, `m_flLiteralValue` | Fixed scalar. Compile/read back a nondefault before testing a dynamic source. |
| Random | `PF_TYPE_RANDOM_UNIFORM`, `m_flRandomMin/Max`, `m_nRandomMode`, `m_nRandomSeed`, `m_bHasRandomSignFlip` | Controlled variation. Distinguish a stable per-particle draw from time-varying input; measure when resampling happens. |
| CP component | `PF_TYPE_CONTROL_POINT_COMPONENT`, `m_nControlPoint`, `m_nVectorComponent` | An external scalar channel. Agree whether CP components carry position, intensity, time or another application value. |
| Particle time | `PF_TYPE_PARTICLE_AGE`, `PF_TYPE_PARTICLE_AGE_NORMALIZED` | Time since birth versus lifetime fraction; use lifetime other than one second to distinguish them. |
| Collection time | `PF_TYPE_COLLECTION_AGE` | Collection-associated clock; measure a delayed child's clock independently. |
| Attributes | `m_nScalarAttribute`, `m_nVectorAttribute`, `m_nVectorComponent` and the matching source enum | Select particle data with the correct scalar/vector type. Establish who writes it and whether initial/current data is intended. |
| Noise, LOD, camera, snapshots, named values | Dedicated source enums and companion fields | Require the corresponding state/resources. Populated companion fields do not activate a mode by themselves. |

Do not guess numeric attribute indices. `m_nOutputField` selects a destination; it is not the value written. For set/add/scale methods, distinguish a value in destination units from a dimensionless multiplier.

### Randomness probes

Constant/varying enum names do not establish the native RNG algorithm, independence, cache lifetime or seed scope. Emit several particles in one update, follow one across updates, restart with identical controls, change a seed, compare independent instances/children, and add an unrelated random consumer. Record what changes.

A sample constant over time need not be identical across particles. Identical child definitions do not prove shared or independent streams. Claim reproducibility only for the tested build and full input configuration.

## Mapping an input to a useful output

`m_nMapType` selects a branch; endpoints, input mode, reverse, multiplier, bias, rounding and curves configure selected branches. An expanded provider contains inactive fields for other modes.

- Select input/output ranges with meaningful units. For example, CP.x 0..100 can be designed to control radius 2..20. Probe below, at and above each endpoint to establish clamping/extrapolation.
- Change `m_nInputMode` and `m_bReverseOrder` independently. Swapping endpoints and toggling reverse need not be equivalent in every map.
- Determine `m_flMultFactor` order relative to remap/round/bias using values for which the possible orders produce different outputs.
- A populated `m_nRoundType` does not prove rounding is active in a direct map. Test the selected rounding branch.
- `m_Curve` is `CPiecewiseCurve` with spline, tangent and domain data. Preserve those values; replacing them with straight segments is not an established native equivalence.
- `m_nBiasType`/`m_flBiasParameter`, notched ranges and comparison controls need their own branch probes. A familiar mathematical function named “bias” is not proof of Valve's formula.

Endpoint values alone cannot establish a spline's interpolation. Test between points, tangent changes, domain boundaries and outside-domain behavior. For source/map failures, first hold the source literal and vary the map, then hold a direct map and vary the source.

## Vector sources and transform sources

| Native vector mode | Companion fields | Distinction |
|---|---|---|
| Literal / literal color | `m_vLiteralValue` / `m_LiteralColor` | Coordinate/direction vector versus byte color. |
| Current/initial particle vector | Attribute selector and scale | Current state versus a captured initial value. |
| CP value | `PVEC_TYPE_CP_VALUE`, `m_nControlPoint`, `m_vCPValueScale` | Read CP data; it need not be a spatial point. |
| CP-relative position | `PVEC_TYPE_CP_RELATIVE_POSITION`, `m_vCPRelativePosition` | A point relative to a CP transform; translation matters. |
| CP-relative direction | `PVEC_TYPE_CP_RELATIVE_DIR`, `m_vCPRelativeDir` | A direction/basis relationship; do not confuse it with a translated point. |
| Float components | `PVEC_TYPE_FLOAT_COMPONENTS`, `m_FloatComponentX/Y/Z` | Three scalar sources with independent map settings. |
| Float interpolation | `PVEC_TYPE_FLOAT_INTERP_*`, `m_FloatInterp`, `m_flInterpInput0/1`, `m_vInterpOutput0/1` | One scalar drives vector interpolation/gradient; this is not three component providers. |
| Random, CP delta, named, velocity | Matching enum and fields | Different state and units; do not collapse all CP-related tokens into one position read. |

The point/direction distinction is a coordinate contract. Exact native normalization, scale handling and multiplication order require documentation or observation. Use a translated, rotated, non-unit-scaled CP so these cases produce distinguishable results.

`CParticleTransformInput` has transform source selection, `m_bUseOrientation`, CP index/range, growth and named-value controls. Decide whether the consumer needs origin only or basis as well. Preserve the API's orientation representation rather than assuming an Euler order. See [CPs](control-points-children.md).

Defaults belong to the consuming class's recorded object, not just the shared nested type. For example, the captured sphere transform default uses CP0 with orientation enabled, while the captured attraction transform uses CP0 with orientation disabled. Record the class/build when copying a provider default; do not turn either into a universal transform rule.

## Native fragments

These are alternative field fragments for differently typed consumers, not complete effects:

~~~text
m_flStartTime = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0.75 }

m_InputValue = {
    m_nType = "PF_TYPE_CONTROL_POINT_COMPONENT"
    m_nControlPoint = 1
    m_nVectorComponent = 0
}

m_InputValue = {
    m_nType = "PVEC_TYPE_FLOAT_COMPONENTS"
    m_FloatComponentX = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 10 }
    m_FloatComponentY = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0 }
    m_FloatComponentZ = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0 }
}
~~~

Do not paste both input alternatives onto the same field. The [embedded compiler fixtures](native-compiler-evidence.json) demonstrate particular literal/random provider representations surviving serialization, not every provider branch.

Use seconds where time is documented, dimensionless fractions for documented normalized lifetime, counts for emission count and target-game spatial units for position/radius. `float32` does not establish an angular unit or a metre conversion.

## Evidence boundary

Exact identities/types are **Typed**; tested serialized inputs are **Serialized**. Random-stream identity, complete map order, spline evaluation, relative-transform scale handling and sampling times are **Unknown** until documented/measured. A resource viewer's evaluator supplies an implementation hypothesis, not an engine specification.
