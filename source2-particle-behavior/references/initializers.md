# Native initializers: placement, velocity and captured state

Separate **spawn location**, **render size**, **initial velocity**, **lifetime**, **color/alpha**, **orientation** and **sequence**. Distance from an emitter center is not the radius of a rendered sprite. An initializer establishes a newly created particle's attributes; downstream operators can modify them.

Fields below are typed native contracts and authoring interpretations. Exact distributions, transform order and algorithmic formulas remain unmeasured unless explicitly stated. Valve tool help describes sphere/box functions as random placement; [VRF's sphere implementation](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/Renderer/ParticleRenderer/Initializers/CreateWithinSphere.cs) is an independent reconstruction rather than native execution proof.

## Sphere and shell

`C_INIT_CreateWithinSphereTransform` combines a transform, radial distance and velocity controls:

| Property | Native type/purpose | Decision and probe |
|---|---|---|
| `m_TransformInput` | `CParticleTransformInput`, input position transform | Bind CP/transform explicitly; translate and rotate separately to distinguish origin from basis. |
| `m_fRadiusMin/Max` | Per-particle float inputs, distance limits | Equal positive bounds are a shell probe; zero bounds isolate the center. Measure birth positions before movement. |
| `m_vecDistanceBias` | Per-particle vector, distance bias | Change one axis at a time; do not assume a particular world-coordinate rescaling formula. |
| `m_vecDistanceBiasAbs` | Direct vector, absolute-value bias controls | Test sign/hemisphere/octant restrictions in a known basis; operation order relative to other biases needs measurement. |
| `m_bLocalCoords` | Boolean, bias in local system | Rotate the input basis 90 degrees and observe shaping separately from whole-effect translation. |
| `m_fSpeedMin/Max` | Per-particle float inputs, speed limits | Separate radial motion from spawn distance by sampling birth and later state. |
| `m_fSpeedRandExp` | Direct scalar, speed random exponent | Distribution shaping rather than an assumed speed multiplier; measure a histogram. |
| `m_LocalCoordinateSystemSpeedMin/Max` | Per-particle vector inputs, local-coordinate speeds | Use a rotated CP and zero radial speed to isolate local velocity. |
| `m_nFieldOutput`, `m_nFieldVelocity` | Particle attribute selectors | Confirm which vector attributes receive the result; do not assume a fixed destination in every configuration. |

The embedded `full_sphere_cp1` fixture retained a nondefault minimum-radius provider and CP1 in native readback. This is **Serialized** support, not a proof of volume-uniform/radius-uniform placement, random draw order, invalid-bound behavior or an exact local-space formula.

### Shell fragment

~~~text
{
    _class = "C_INIT_CreateWithinSphereTransform"
    m_TransformInput = { m_nControlPoint = 1 }
    m_fRadiusMin = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 32 }
    m_fRadiusMax = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 32 }
    m_fSpeedMin = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0 }
    m_fSpeedMax = { m_nType = "PF_TYPE_LITERAL" m_flLiteralValue = 0 }
}
~~~

This initializer fragment needs an emitter, known CP1, lifetime and renderer/material. Use distinct nonzero CP0/CP1. Inspect positions immediately after birth. Then test bounds 16..32 with many particles: bounding-region correctness does not establish the probability distribution inside it.

## Box

`C_INIT_CreateWithinBox` has per-particle vector inputs `m_vecMin/Max`, CP index `m_nControlPointNumber` and space flag `m_bLocalSpace`. It also declares `m_randomnessParameters` and `m_bUseNewCode`; retain supplied controls rather than assuming compatibility switches have no effect.

Think of bounds as the region, the CP as its reference, and the space choice as its basis. Do not assume invalid/reversed ranges are clamped. A degenerate box min=max=[8,0,0] isolates placement. Rotate the CP and compare local-space on/off; translation alone cannot verify orientation.

A useful CP-relative anchoring test translates the entire bound CP setup by T and observes the intended region shifted once. Use a distinct nonzero CP0/CP1 and birth-time observations so subsequent following/movement cannot hide the result. Native `box_cp1` readback establishes acceptance of tested selection/bounds, not every transform combination.

## Offset, scalar/vector and velocity composition

| Function | Useful meaning | Composition trap and decisive check |
|---|---|---|
| `C_INIT_PositionOffset` | Modify position with `m_OffsetMin/Max`, transform/local-space controls; `m_bProportional` is labelled proportional to radius. | Set radius before a proportional offset; compare two radii. Offset-after-placement differs from a second replacement placement. |
| `C_INIT_InitFloat` | Apply `m_InputValue` to `m_nOutputField` with `m_nSetMethod` and per-particle strength. | Replacement/addition/scaling differ; test current/initial choices and strength independently. |
| `C_INIT_InitVec` | Initialize a selected vector field using its input/set method, `m_bNormalizedOutput` and `m_bWritePreviousPosition`. | Point, velocity, normal and color differ; normalization and previous-position writes must be intentional, not copied from InitFloat's strength contract. |
| `C_INIT_VelocityRandom` | Establish an initial velocity distribution through its speed/local-coordinate inputs. | Inspect velocity before judging displacement; movement must integrate it. |
| `C_INIT_InitialVelocityNoise` | Initialize velocity from noise/spatial inputs. | A random range is not proof of the correlation or time behavior of a noise field. |
| `C_INIT_RemapTransformOrientationToRotations` | Initialize orientation-related state from a transform, with optional normal output. | Test all axes with asymmetric imagery/geometry; round sprites hide errors. |
| `C_INIT_RandomColor` / `C_INIT_RandomAlpha` / `C_INIT_RandomSequence` | Initialize visual variation. | Verify actual channel range/color space/selection mode; byte alpha convention is not universal across all alpha fields. |

Use schema attribute/method enums. `m_nOutputField` selects an attribute rather than supplying its value. List each destination before/after initialization to expose order-dependent overwrites. A scale is dimensionless; a replacement lifetime or speed is not.

## Defaults and downstream operators

Native compiler controls found a serialization default 5 for `CParticleSystemDefinition.m_flConstantRadius`: explicit 5 was omitted while 7 survived. This is build-scoped **Serialized** evidence, not a design recommendation. Subsequent initialization can replace or scale that value.

An over-life operator scaling initial size needs a defined initial size. A radius-dependent offset needs a defined radius at its evaluation point. Do not repeatedly apply a scale to an already-scaled current value unless that is the intended method.

Snapshots, model surfaces, hitboxes and entity-linked initializers need real resources/bindings. A CP position is not a substitute for snapshot arrays or sampled geometry. Verify resource/binding, sampling and inheritance before judging final appearance.

## Native verification cases

1. **Point/shell/volume:** zero speed and fixed CP; compare zero bounds, equal positive bounds, ordered unequal bounds. Measure birth positions and radial histogram.
2. **Local basis:** rotate nonzero CP1 by 90 degrees; use unequal X/Y bounds or velocity. Vary local options separately.
3. **Position/velocity:** compare birth and later observations with movement enabled/disabled.
4. **Attribute order:** set radius, then proportional offset; reverse those two in a diagnostic copy. Identify each written destination.
5. **Reproducibility:** fix random controls, restart, change one control, then compare an independent instance.

See [providers](providers.md), [composition cases](composition-cases.md) and [embedded evidence](native-compiler-evidence.json). Exact native algorithms beyond recorded observations remain **Unknown**.
