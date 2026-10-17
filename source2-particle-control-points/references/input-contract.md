# Native CP input contracts

## Contents

- [Roles, indices and evidence](#roles-indices-and-evidence)
- [Scalar, vector, transform and model inputs](#scalar-vector-transform-and-model-inputs)
- [Native rotations and external quaternion APIs](#native-rotations-and-external-quaternion-apis)
- [Real PET control-point configuration](#real-pet-control-point-configuration)

## Roles, indices and evidence

Assign a contract per effect. An example is CP0 = origin pose, CP1 = target pose, CP4.X = derived intensity and CP16 = tint data. These are deliberate choices, not engine reservations. The compiled `chamber_cube_spark` example instead selects CP1 and CP2 for its path. Inspect the whole root/child graph before choosing an unused index.

CP slots are 0–63. Distinguish a slot identifier from a selector sentinel: the reflected `CPathParameters.m_nMidControlPointNumber` default is `-1`, while the same record's start/end defaults are `0`. Do not clamp every negative property value to CP0 or treat `63` as an always valid range endpoint independent of its containing class.

The bundled typed catalogue is CS2 SchemaExplorer revision **11131657**, 14 October 2026 16:57:53; the exact source hashes are in its provenance. Full property records are queried with `scripts/cp_contracts.py`. `partial` defaults status means some inherited layers were unreadable; a requested own field can still have a recorded default and declaring source. Omitted values are not fabricated zeroes.

## Scalar, vector, transform and model inputs

| Family | Native declarations and CP modes | Properties to inspect |
| --- | --- | --- |
| Scalar | `CParticleFloatInput`; collection/per-particle subclasses inherit its fields. `ParticleFloatType_t`: `PF_TYPE_CONTROL_POINT_COMPONENT`, `CHANGE_AGE`, `SPEED`, `DISTANCE`, `IS_SET` | `m_nControlPoint:int32`, `m_nVectorComponent:int32`; mapping/input mode enums, `m_flInput0/1`, `m_flOutput0/1`, `m_flMultFactor`, curve, round/bias and randomness fields |
| Vector | `CParticleVecInput`; collection/per-particle subclasses. `ParticleVecType_t`: `PVEC_TYPE_CP_VALUE`, `CP_RELATIVE_POSITION`, `CP_RELATIVE_DIR`, `CP_RELATIVE_RANDOM_DIR`, `CP_DELTA` | `m_nControlPoint:int32`, `m_nDeltaControlPoint:int32`, `m_vCPValueScale:Vector`, `m_vCPRelativePosition:Vector`, `m_vCPRelativeDir:Vector`, component/interpolation inputs |
| Transform | `CParticleTransformInput`; `ParticleTransformType_t`: `PT_TYPE_CONTROL_POINT`, `PT_TYPE_CONTROL_POINT_RANGE`, named-value and invalid modes | `m_nControlPoint:int32`, `m_nControlPointRangeMax:int32`, `m_bUseOrientation:bool`, `m_bSupportsDisabled:bool`, `m_flEndCPGrowthTime:float32`, named-value/follow flags |
| Model | `CParticleModelInput`; `ParticleModelType_t` includes `PM_TYPE_CONTROL_POINT` | `m_nControlPoint:int32`, `m_NamedValue:CParticleNamedValueRef`; not interchangeable with a vector value |

Use the actual containing field's declared type. A property whose friendly name says “rate” can require `CParticleCollectionFloatInput` rather than a raw number. Collection and per-particle input wrappers are not a license to assume the same evaluation timing in every consumer.

The schema establishes mode names, numeric enum values, types and recorded defaults; it does not establish the subtraction order of CP_DELTA, speed units, which points DISTANCE uses, temporal history lifetime, normalization, out-of-range behavior or exact spline interpolation. Test those modes with asymmetric data rather than inferring them from names.

Observed CS2 scalar provider fragment from `particles/ambient_fx/env_sparks_directional_e.vpcf_c`:

```text
m_nType = "PF_TYPE_CONTROL_POINT_COMPONENT"
m_nControlPoint = 1
m_nVectorComponent = 1
m_nMapType = "PF_MAP_TYPE_REMAP"
m_flInput0 = 0
m_flInput1 = 3
m_flOutput0 = 0.5
m_flOutput1 = 1.5
```

This is serialized vocabulary, not a complete asset or a verified numerical oracle. Use channel-isolation values such as `[2,11,37]` to verify which selected component reaches the actual consumer in the target engine. For CP vectors, test a non-unit asymmetric value such as `[2,3,5]`, non-unit `m_vCPValueScale`, a translated/rotated CP and a different delta CP; a zero vector cannot reveal an ignored mode.

For a scalar data channel exposed as a percentage,
`PF_TYPE_CONTROL_POINT_COMPONENT` can select CP.X and explicitly use
`m_nMapType = "PF_MAP_TYPE_MULT"`, `m_flMultFactor = 0.01`. This is a useful
option if the actual PET numeric control fails to commit fractional values;
check the committed value rather than assuming a universal UI limitation.
For uniform `C_OP_RenderModels.m_vecComponentScale`, use
`PVEC_TYPE_FLOAT_COMPONENTS` and wire all three float components to that
same scalar provider. Define units/defaults and initialize the channel from
the runtime caller before emission; a saved PET preset supplies no such
runtime guarantee. A scale of zero can collapse the model.

## Native rotations and external quaternion APIs

`C_OP_SetControlPointOrientation.m_vecRotation` and `m_vecRotationB` are **QAngle**, not quaternion arrays. The schema metadata for `m_vecRotation` labels the tuple **pitch yaw roll**. Its own fields additionally include `m_bUseWorldLocation`, `m_bRandomize`, `m_bSetOnce`, `m_nCP`, `m_nHeadLocation`, and `m_flInterpolation:CParticleCollectionFloatInput`. Recorded own rotation defaults are `[0,0,0]`; own defaults do not prove local/world composition, head transform, random selection or interpolation order.

A CP position value does not change that CP's orientation basis, and `m_bUseOrientation` is not itself a rotation value. A consumer can deliberately interpret a numeric CP vector as rotation: `C_OP_RenderModels.m_vecLocalRotation` driven by `PVEC_TYPE_CP_VALUE` used CP position components as Euler inputs in a native pitch-90 test. Document this data-channel contract separately from transform orientation. If the actual game integration accepts quaternions, document that API's component order, handedness, basis, units and normalization. Convert to/from native angle or basis inputs using the API's verified convention; do not presume an XYZW JSON field exists in VPCF. Test an asymmetric rotation and separate pitch/yaw/roll changes with a visible directional marker or attachment axes.

## Real PET control-point configuration

The native top-level array is `CParticleSystemDefinition.m_controlPointConfigurations`, whose element type is `particles::ParticleControlPointConfiguration_t`. It declares:

| Field | Native type |
| --- | --- |
| `m_name` | `CUtlString` |
| `m_drivers` | `CUtlVector<ParticleControlPointDriver_t>` |
| `m_previewState` | `ParticlePreviewState_t` |

Each `ParticleControlPointDriver_t` declares:

| Field | Native type | Recorded schema default |
| --- | --- | --- |
| `m_iControlPoint` | opaque atomic `ParticleParamID_t` | serialized value `0` |
| `m_iAttachType` | `animationsystem::ParticleAttachment_t` | `PATTACH_ABSORIGIN_FOLLOW` |
| `m_attachmentName` | `CUtlString` | empty |
| `m_vecOffset` | `Vector` | `[0,0,0]` |
| `m_angOffset` | `QAngle` | `[0,0,0]` |
| `m_entityName` | `CUtlString` | empty |

The atomic `ParticleParamID_t` declaration remains opaque despite the numeric default and numeric compiled examples; do not reconstruct its internal memory layout. The attach enum also declares point/follow, eye/follow, custom/world/origin variants. Query the full enum rather than restricting authoring to the three strings observed in one package.

Native configuration shape, with task-specific values filled deliberately:

```text
m_controlPointConfigurations = [
    {
        m_name = "endpoint_check"
        m_drivers = [
            {
                m_iControlPoint = 0
                m_iAttachType = "PATTACH_WORLDORIGIN"
                m_entityName = "self"
                m_vecOffset = [0, 0, 0]
            },
            {
                m_iControlPoint = 1
                m_iAttachType = "PATTACH_POINT_FOLLOW"
                m_entityName = "self"
                m_attachmentName = "REPLACE_WITH_ATTACHMENT_PRESENT_ON_THE_SELECTED_MODEL"
                m_vecOffset = [0, 0, 0]
                m_angOffset = [0, 0, 0]
            }
        ]
    }
]
```

This is an original structural example, not a guaranteed runnable attachment. Replace the attachment name with an inspected model attachment and configure the preview model/sequence through PET. `m_entityName="self"` is observed in native examples; it is not a universal way to bind an arbitrary target entity. Native preview state can name a model, sequence, playback/simulation rate and attachment/axis display flags; none automatically creates the corresponding in-game spawning code.

Static world offsets, point attachment, point-follow attachment and runtime game drivers have distinct update/lifetime contracts. Verify whether each driver follows while the model animates, what happens when the entity disappears, and whether offsets are applied in the intended basis. A missing attachment must be diagnosed explicitly, not reported as successful because a fallback origin still renders a particle.
