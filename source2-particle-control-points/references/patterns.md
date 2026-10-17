# Native CP authoring and verification patterns

## Two-endpoint beam or tether

For “a beam between the hand and the target”, assign independently driven endpoint poses after inspecting the chosen graph. CP0/CP1 is one possible contract; CP1/CP2 is equally legitimate. Keep the real hand/weapon attachment and target driver separate from any derived distance/tint data channels.

The CS2 compiled corpus contains `C_INIT_CreateAlongPath` in 26 effects. A bounded observed fragment from `particles/impact_fx/chamber_cube_spark.vpcf_c` selects:

```text
_class = "C_INIT_CreateAlongPath"
m_PathParams = {
    m_nStartControlPointNumber = 1
    m_nEndControlPointNumber = 2
}
```

The reflected `CPathParameters` contract additionally declares a midpoint CP, bulge-control selector, bulge/midpoint scalars and start/mid/end offsets. Query these fields and defaults when a curved or slack beam is requested. A rope renderer does not create the ordered particles or enforce endpoint locations; initialization, ordering, emission count, lifetime, constraints and renderer/material setup must describe the same beam.

Inspect and remove or redirect endpoint writers only when they conflict with the intended external drivers. A sibling `C_OP_SetControlPointPositions` in a reference can deliberately supply preview/test positions; blindly copying it can overwrite the game's hand/target poses.

Native checks: coincident endpoints; short/long distance; translated pair; swapped ends; different attachment orientation; animated target after emission; entity disappearance; new instance after stop/restart. Capture endpoint/CP axes alongside pixels. Initializers and continually evaluated operators must not be confused when verifying follow behavior.

## Distance driving width, density or actual brightness

`C_OP_DistanceBetweenCPsToCP` declares **15 own fields** in the pinned CS2 schema:

| Role | Exact properties and types | Recorded own defaults |
| --- | --- | --- |
| Input endpoints | `m_nStartCP:int32`, `m_nEndCP:int32` | `0`, `1` |
| Output | `m_nOutputCP:int32`, `m_nOutputCPField:int32` | `2`, `0` |
| Timing | `m_bSetOnce:bool` | `false` |
| Remap bounds | `m_flInputMin/Max:float32`, `m_flOutputMin/Max:float32` | `0/128`, `0/1` |
| Visibility trace | `m_bLOS:bool`, `m_flMaxTraceLength:float32`, `m_flLOSScale:float32`, `m_CollisionGroupName:char[128]`, `m_nTraceSet:ParticleTraceSet_t` | `false`, `-1`, `0`, `"NONE"`, `PARTICLE_TRACE_SET_ALL` |
| System propagation | `m_nSetParent:ParticleParentSetMode_t` | `PARTICLE_SET_PARENT_NO` |

`m_nStartCP` and `m_nOutputCPField` are valid declared fields even though neither was explicitly serialized in this local class corpus. Do not remove them because examples omit default-valued fields. Conversely, the schema's output-field declaration does **not** establish that the result is written to every component. Verify the selected field and the other channels independently.

Original authoring fragment for CP0→CP1 distance mapped into CP4 field 0:

```text
{
    _class = "C_OP_DistanceBetweenCPsToCP"
    m_nStartCP = 0
    m_nEndCP = 1
    m_nOutputCP = 4
    m_nOutputCPField = 0
    m_bSetOnce = false
    m_flInputMin = 128
    m_flInputMax = 1024
    m_flOutputMin = 0.2
    m_flOutputMax = 0.85
    m_bLOS = false
}
```

Put it in the appropriate pre-emission list and use a scalar provider with `PF_TYPE_CONTROL_POINT_COMPONENT`, `m_nControlPoint=4` and the deliberately selected vector component in the real consumer. Keep CP4 free of endpoint/position writers. Select an operator for changes during life, an initializer for a birth-time sample, or a collection input for emission; the common provider type does not define that consumer's timing.

The friendly metadata describes distance/output bounds, but exact clamping, degenerate ranges, selected component, trace failure and parent propagation need native tests. Establish expected outputs for the intended mapping at below-minimum, midpoint and above-maximum distances, then compare observed values; do not present a guessed linear formula as a measured native oracle. Test `m_bSetOnce` separately from inherited `m_bRunOnce`.

For “brighter”, select the actual appearance control: alpha/transparency, RGB and emissive/HDR material/renderer intensity are different. A correct distance scalar does not prove any of them. Inspect and validate the real consuming property/material; a change in alpha alone must not be reported as emissive brightness. If LOS is requested, add occluded/unoccluded native cases and the intended trace set/collision group.

## Vector data and orientation

For CP-driven tint, declare the input range. A real CS2 `C_OP_RemapCPtoVector` example uses `m_nCPInput=16`, `m_nFieldOutput=6`, `m_vInputMax=[255,255,255]`, `m_vOutputMax=[1,1,1]`. This is an observed scaling pattern, not a rule that all CP colors use bytes. Inspect `m_nSetMethod` and `ParticleSetMethod_t`: replacing, scaling an initial value and scaling the current value can accumulate differently over successive updates.

For “eject in the barrel's direction”, position alone is insufficient. Establish the real model attachment basis, transform selection and relative-direction consumer. Compare an asymmetric direction before/after rotating the attachment, with a translated origin to expose accidental position addition. Do not substitute subtraction of two endpoints for an orientation contract unless the requested effect is explicitly aim-derived.

## Native writers and ownership

| Class | Native own-field details that prevent common mistakes |
| --- | --- |
| `C_OP_SetSingleControlPointPosition` | Exactly four own fields in the snapshot: `m_bSetOnce:bool`, `m_nCP1:int32`, `m_vecCP1Pos:CParticleCollectionVecInput`, **lowercase** `m_transformInput:CParticleTransformInput`. The transform's metadata says “transform to offset positions from” and `MParticleInputOptional`. The snapshot does not declare `m_bUseWorldLocation` or `m_nHeadLocation` on this class, although older compiled examples can store them. |
| `C_OP_SetControlPointPositions` | Four target/position pairs plus world/orientation/head-location controls; query its own record rather than borrowing SetSingle's provider type or defaults. |
| `C_OP_SetControlPointOrientation` | `QAngle` rotations, `m_flInterpolation:CParticleCollectionFloatInput`, world/randomize/set-once/target/head controls. The interpolation declaration is not marked `MParticleInputOptional`. Never replace it with a position write or a guessed quaternion property. |
| `C_OP_SetControlPointRotation` | Axis/rate rotation exists in the pinned CS2 schema even though the local CS2 compiled corpus has no instance; Deadlock examples alone do not establish CS2 runtime behavior. |
| `C_OP_SetControlPointToPlayer`, `...ToHand`, `...ToHMD`, `...ToImpactPoint` | Actual engine/player/world inputs are required. Shared CP numbering does not create an entity or supply eye/hand orientation. |

Inspect inherited timing/strength/disable controls as well as own fields. Pre-emission function base `m_bRunOnce` is distinct from a class's `m_bSetOnce`. The native list/stage, execution order and driver update order determine who wins when two writers target a CP. Do not assert a single global writer precedence from class names.

## Children: group, source and destination are different

`m_Children` entries observed in CS2 store `m_ChildRef`, optional `m_flDelay`, `m_bEndCap`, `m_nDetailLevel`. They are not a universal CP mapping table. Inspect native child declarations and explicit binding operators instead of inventing properties on the resource reference.

Three declared operators illustrate why names/types must be checked per class:

| Class | Declared mapping inputs | Metadata distinction |
| --- | --- | --- |
| `C_OP_SetChildControlPoints` | `m_nChildGroupID:int32`, `m_nFirstControlPoint:int32`, `m_nNumControlPoints:int32`, **`m_nFirstSourcePoint:CParticleCollectionFloatInput`**, reverse/orientation controls | First source is labeled “first particle to copy”; count is “# of control points to set”. |
| `C_OP_SetPerChildControlPoint` | Group/destination/count plus **`m_nParticleIncrement:CParticleCollectionFloatInput`**, **`m_nFirstSourcePoint:CParticleCollectionFloatInput`**, set-orientation/vector-attribute/count-from-particles controls | Count is labeled “# of children to set”; orientation can come from a particle vector field. |
| `C_OP_SetParentControlPointsToChildCP` | Group/child CP/count plus **`m_nFirstSourcePoint:int32`** and set-orientation | First source is labeled “first parent control point to set from”; count is “# of children to set”. |

Read the complete records for defaults and enums. Despite its name, `ParticleParentSetMode_t` concerns particle-system propagation: its friendly labels distinguish self/children, immediate parent/self/children and root downward. It must not be repurposed as a declaration that CP1 is geometrically parented to CP0.

A child test needs at least two distinguishable parent particles or CP values, two child instances/groups when applicable, nonzero first-source/destination indices and a non-identity orientation. Verify count, ordering, destination ownership, wrong-group exclusion and behavior after parent death/endcap/restart. One stationary child at origin cannot establish a binding algorithm.

## Animation and attachments

Provide a real time-varying entity/attachment driver when the prompt needs follow, velocity, change-age or a moving endpoint. A static PET pose does not demonstrate those behaviors. Check motion after initial emission, loop boundaries, sequence changes, attachment absence, driver removal and instance restart. Use a path with unequal direction/speed segments to distinguish position, displacement, speed and change-age.

Keep native preview configuration and runtime game binding explicit in the deliverable: model/attachment name, actor/entity selection, coordinate-space/offset convention, update source, lifecycle and per-CP readers/writers. Save the VPCF plus the required native test setup; do not claim that saving preview drivers implements the spawning integration in the game.
