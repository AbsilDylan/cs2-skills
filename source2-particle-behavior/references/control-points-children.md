# Native control points, transforms and children

## Define the effect's CP contract

For each CP, state index, role, value kind, coordinate space, driver, internal writer, readers and update timing. CP0/CP1 have no universal endpoint/intensity convention. A CP used for scalar data is not also a geometric endpoint unless the effect explicitly intends it.

A CP can carry positional data and orientation, but field representation is consumer-specific. A vector provider, `QAngle` field, basis vectors and quaternion are different contracts. Do not insert four quaternion numbers into an angle field or infer Euler order from an unlabelled vector.

The target schema and control-point skill (`$source2-particle-control-points`) provide exact indices/sentinels, attachment drivers and typed configurations. Tested native resources used CP1 and CP63; that serialization fact does not establish every selector's sentinel semantics.

## Position, direction, data and transform

| Consumer/input | Required meaning | Discriminating experiment |
|---|---|---|
| `PF_TYPE_CONTROL_POINT_COMPONENT` | A scalar from a selected CP component | Put different values in all three components and select each separately. |
| `PVEC_TYPE_CP_VALUE` | CP vector data, with its declared scale controls | Distinguish a parameter vector from a world-space location. |
| `PVEC_TYPE_CP_RELATIVE_POSITION` | A point relative to a CP transform | Translate and rotate the CP independently. |
| `PVEC_TYPE_CP_RELATIVE_DIR` | A direction relative to a basis | Translation should not be mistaken for a direction; test rotation and non-unit scale separately. |
| `CParticleTransformInput` | A transform source, optionally using orientation | Confirm which origin/basis the actual function consumes. |
| `C_INIT_NormalAlignToCP` | A selected CP axis becomes particle-normal input | `m_nControlPointAxis` is selectable; do not hard-code world +Z as a universal rule. |
| `C_INIT_RemapTransformOrientationToRotations` | Orientation remap with offset rotation, internal quaternion option and normal/rotation output choice | Compare `m_bUseQuat` and `m_bWriteNormal` using an asymmetric image/model and three-axis changes. |
| `C_OP_SetSingleControlPointPosition` | Write a chosen CP from collection vector input and optional transform offset | Check `m_bSetOnce`, target `m_nCP1` and exact lowercase `m_transformInput`. Detect overwrites of external input. |

Exact transform multiplication, normalization, parent-scale effects and source precedence require native documentation/measurement. Use a CP with nonzero translation, nonidentity rotation and unequal scale; an origin/identity test cannot distinguish these semantics.

## Bindings and ongoing motion

A particle created at a CP need not remain attached to it. Separate initial position from an operator intended to follow/lock to a transform. Move the CP after particles have been emitted and record whether old particles, new particles, or both respond.

Similarly, a saved particle-editor control configuration is not proof of an in-game entity/attachment binding. Establish who supplies that CP at runtime and when it becomes available. A pre-emission writer can overwrite a game-provided value; check writer order and allocate derived CP outputs deliberately.

Valve's public particle-manager API distinguishes CP data, entity binding and orientation operations. Its [Half-Life: Alyx API documentation](https://developer.valvesoftware.com/wiki/Half-Life:_Alyx_Workshop_Tools/Scripting_API) also distinguishes orientation basis conventions. That documents the named game's API; it does not make those exact symbols a CS2 integration API. Use the actual target integration and test its handedness/basis.

A snapshot is a structured source of particle attributes/subsets. An entity surface requires geometry and an attachment requires the actual entity/attachment. CP position alone cannot substitute for those resources.

## Child collections and inheritance

`ParticleChildrenInfo_t` declares a particle resource reference, `m_flDelay`, `m_bEndCap`, disable state and detail level. Choose whether the child supplies an ordinary layered part or an end-cap part; do not infer the complete trigger schedule merely from a resource reference.

Children can have their own emitters, limits, lifetimes, renderers and CP readers. A layered effect should make these contracts explicit:

- Which CPs are shared, remapped, internally written or externally driven?
- Is the child's position tied to the collection, an entity attachment, an individual parent particle or another source?
- Which initial/current attributes are inherited, if any, and through which native function?
- When does delay begin, and when does the child's clock start?
- What happens on stop, end cap, restart, parent destruction, culling or detail-level changes?
- Are repeated instances' random streams reproducible and sufficiently independent for the design?

Do not assume every child inherits position, velocity, color, orientation, age or seed merely because it is listed in `m_Children`. Read actual inheritance functions such as the relevant `C_OP_InheritFromParentParticles*` class and their field selections. The thirteen embedded compiler observations do not measure child trigger/inheritance semantics.

## Native composition tests

1. **Distinct input:** CP0=[100,200,300], CP1=[-40,70,20], separate parameter CP with three unequal components. Verify every reader without conflating origin and data.
2. **Spawn/follow:** emit a burst, move its CP after emission, then restart while it moves. Compare existing and newborn particles.
3. **Basis:** rotate around each axis, then add unequal scale. Use an asymmetric model or arrow texture and inspect normal/rotation attributes.
4. **Writers:** change an externally driven CP while toggling the internal pre-emission writer and `m_bSetOnce`. Record precedence and update time.
5. **Children:** run one child alone, then two references, then delayed/end-cap variants. Measure CP state, counts, clocks, bounds and RNG separately for each.
6. **Unavailable binding:** deliberately remove an attachment/snapshot/model in a diagnostic copy. Record native diagnostics and failure behavior; do not silently substitute origin data.

The declarations are **Typed**. Particular tested CP selectors in [compiler evidence](native-compiler-evidence.json) are **Serialized**. Runtime source precedence, inheritance, trigger details, random isolation and exact transforms remain **Unknown** until documented or measured in the target build.
