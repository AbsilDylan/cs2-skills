# Native composition cases

These are reproducible **test designs**, not claims that all cases have already been measured. They require a target game's particle tools, valid native source/material dependencies and a defined CP-binding setup. The [embedded observations](native-compiler-evidence.json) cover compilation/readback only.

## 1. A shell carried by CP1

Author a burst and `C_INIT_CreateWithinSphereTransform` with CP1, equal positive radial bounds, zero radial/local speed and a fixed visible particle radius. Give the effect enough lifetime to inspect birth positions. Put CP0 and CP1 at distinct nonzero coordinates.

Measure distance from CP1 at birth; translate the full CP setup; then rotate CP1 with an anisotropic bias. Separate center/radius correctness from distribution and local-basis behavior. A filled range needs a histogram, not just min/max. See [initializers](initializers.md) for the exact fragment.

## 2. Delayed short emission with a visible tail

Use `C_OP_ContinuousEmitter` with literal-provider start 0.75 seconds, positive duration 0.5 seconds, rate 20 particles/second and particle lifetime 2 seconds. Choose capacity large enough to avoid clipping and no active birth cap.

Before 0.75, inspect births; inside the window, inspect rate/count; after the window, distinguish no new births from existing particles still living. Roughly rate × active time is a planning estimate, not an exact subframe-count oracle. Repeat with a per-update cap and frame-rate/timestep variations to measure scheduling. Preserve the native provider shape even if a different consumer expects a direct scalar.

## 3. Radial launch plus local drift plus gravity

Use a shell around CP1, radial speed with equal min/max, local drift on one axis, `C_OP_BasicMovement` and gravity. First disable drift/gravity and measure velocity; then add each separately. Rotate CP1 to distinguish radial direction from local drift. Finally add drag and compare trajectories under two timesteps.

This determines whether the desired composition occurs without assuming an integrator or drag exponent. Document units from target help and measurements rather than treating `float32` as a unit declaration.

For “drift, **then** fall”, choose the clock explicitly. Constant gravity is not a delayed transition. A single burst can use a collection-timed force activation while basic movement remains active; confirm the force's inherited timing/strength controls in the target build. A continuous stream usually needs particle-age-dependent force/velocity input, since a collection-wide switch affects young and old particles together. Select a native consumer whose declared input supports that context, then measure onset at two birth times. Do not gate all movement if the intended pre-fall phase must still drift.

## 4. Four-second lifetime with simple fade and decay

Use a known visible material, fixed initial alpha, lifetime 4 seconds, `C_OP_FadeOutSimple.m_flFadeOutTime=0.25` and lifespan decay. Valve help describes this Simple field as a lifetime fraction: the final quarter corresponds to one second in this setup. Inspect alpha and existence separately at early time, fade start, mid-fade, end and just after end.

This checks documentation against the actual build. It does not assume a particular interpolation curve or that fading itself destroys particles. Add fade-in in a separate variant; inspect writer interactions rather than assuming all alpha modifiers multiply. A zero-alpha particle can still exist and consume capacity.

## 5. CP-driven beam or rope

Use a native sequential-path initializer, rope/trail renderer appropriate to the design, known texture/material and two endpoint CPs. Query exact path parameter fields and any endpoint-pair mode from the schema/help.

Test endpoints, point order, segment count, texture tiling and motion after emission. Then add a third CP to distinguish a two-point path from sequential CP pairs. A rope renderer alone does not establish a path, a beam or inheritance from endpoints.

## 6. Child burst followed by an end-cap layer

Start with each child effect working alone. Bind their CP contracts explicitly and add ordinary, delayed and end-cap child entries one at a time. Record child resource, own limits/lifetime, CP readers/writers, trigger, delay origin, inherited attributes and random controls.

Observe start, stop, restart, parent removal and detail-level changes. Test two references to the same child definition. Do not infer shared state, blanket attribute inheritance or a trigger per parent particle merely from a child resource reference.

## 7. Animated sprite changed to a model

Establish sprite sequence selection and lifetime first. Use a visibly asymmetric texture with identifiable frames; distinguish sequence number from frame/time. Test changed animation rate and lifetime-fit mode where declared.

For a model variant, use a valid model/material dependency and known lighting. Test full/half/zero alpha, zero size and recovery; overlap differently colored opaque instances in both viewing/draw orders, then include translucent instances. Assess the native material's alpha and depth behavior rather than assuming particle alpha alone determines final visibility. Renderer-family-specific units and attribute consumers must be checked independently.

## Record each result

For every case keep the authored fragment, fresh compiled readback, game/build, dependencies, CP poses/drivers, random controls, observation times, camera/exposure and numerical/pixel result. Label it **Typed**, **Documented**, **Serialized** or **Measured** using [the evidence ledger](evidence.md); leave the exact unobserved behavior **Unknown**.
