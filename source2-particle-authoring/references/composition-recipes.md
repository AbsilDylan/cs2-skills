# Native composition recipes

## Contents

- [Smoke: readable volume and controlled overdraw](#smoke-readable-volume-and-controlled-overdraw)
- [Fire: separate flame, embers and residual smoke](#fire-separate-flame-embers-and-residual-smoke)
- [Beam or tether: endpoints before decoration](#beam-or-tether-endpoints-before-decoration)
- [Real model fragments: geometry and scale contract](#real-model-fragments-geometry-and-scale-contract)
- [Animated mesh swarms: choreography and playback](#animated-mesh-swarms-choreography-and-playback)
- [Attraction or orbiting detail: explicit force target](#attraction-or-orbiting-detail-explicit-force-target)
- [Requests outside these examples](#requests-outside-these-examples)

Use these as concrete authoring starting points, then select the native classes
and resources the brief needs. Counts and times below are artistic estimates,
not engine defaults, support limits or a guarantee of final appearance.

For an unfamiliar member, use the schema skill's `scripts/schema_catalog.py query`
on its exact class and field when that skill is available. Otherwise inspect the
native editor, target schema dump or lawful CS2 source directly. Class names here
are discoverable candidates, not a substitute for their inherited fields,
provider types, resource inputs or native behavior. Compile and observe the
authored combination on the intended CS2 build.

## Smoke: readable volume and controlled overdraw

Start with one sustained smoke child. A useful small-scale starting point is
12 particles/s, lifetime 1.5–2.5 s, low initial speed and slowly increasing size.
Its maximum-lifetime population estimate is 30; choose capacity with headroom
and account for simultaneous emitters. Add a short impact puff or larger slow
wisps as independent children only when their timing or material differs.

Candidate sequence:

1. `C_OP_ContinuousEmitter` for sustained emission, or
   `C_OP_InstantaneousEmitter` for a single puff.
2. `C_INIT_CreateWithinSphereTransform` or `C_INIT_CreateWithinBox` for source
   volume; `C_INIT_InitFloat` for lifetime/radius and `C_INIT_RandomColor` for
   controlled variation. Add sequence or rotation initialization when the chosen
   animated texture needs it.
3. `C_OP_BasicMovement` for authored motion inputs. Inspect
   `C_INIT_InitialVelocityNoise` or `C_OP_CurlNoiseForce` for suitable variation
   rather than applying unstructured jitter to every parameter.
4. `C_OP_InterpolateRadius`, color/alpha operators and decay for the intended
   expansion and disappearance. Inspect each native curve/time contract before
   choosing its exact values.
5. `C_OP_RenderSprites` with an explicitly chosen smoke texture/binding and
   suitable blending/depth behavior. Use a verified animation sheet when the
   silhouette needs evolving detail.

Tune the texture's opacity and occupied area before multiplying particle count.
Large overlapping quads can become opaque cards or dominate fill cost. Observe
against light and dark backgrounds and through nearby geometry. If the brief
requires actual volume or another renderer, investigate that native path;
stacked sprites are a conscious visual method, not equivalent geometry.

## Fire: separate flame, embers and residual smoke

A starting composition for a small sustained source:

| Layer | Emission/lifetime starting point | Main control |
| --- | --- | --- |
| Flame | 32/s, 0.35–0.7 s | Coherent upward motion, animated silhouette, brightness/color evolution |
| Embers | 10/s, 0.6–1.2 s | Smaller radius, outward/upward velocity, independent fade and rotation |
| Smoke | 12/s, 1.5–2.5 s | Slower expanding particles, lower opacity, separate resource |

The upper population estimates are approximately 23 + 12 + 30 = 65 particles
before headroom, repeated systems and additional layers. A point light or heat
distortion is a separate native/resource decision with its own cost and scene
dependencies; it is not enabled by increasing sprite brightness.

Use independent child systems so a faster flame does not shorten the smoke and
a brighter ember material does not turn all smoke additive. Inspect sprite
sequence inputs, radius and color progression, fade/kill behavior and movement
providers. For trails, select `C_OP_RenderTrails` only when the intended streak
geometry and lifetime/length fields are appropriate. Define source stop behavior
so the flame can stop while existing smoke decays.

## Beam or tether: endpoints before decoration

Define CP0 as the origin and CP1 as the target, with their external owner,
coordinate space and update cadence. Begin with a baseline endpoint separation
and fixed CPs. A straight beam can use a native path populated by ordered
particles and a rope renderer; other beam requests may need
`C_OP_RenderLightBeam`, trails or another native renderer.

For the path/rope approach, inspect `CPathParameters`,
`C_INIT_CreateSequentialPath`, `C_OP_MaintainSequentialPath` and
`C_OP_RenderRopes`. The [cyan tether sources](../assets/cyan-tether/README.md)
provide a compiling example with 24 path particles, an owned line texture and
CP0/CP1 inputs. They demonstrate source wiring and selected serialized fields;
they do not establish live endpoint tracking or topology in every scene.

Select segment count from the intended path curvature, length and renderer
behavior. A long straight connection and a curved moving cable need different
sampling. Test coincident endpoints, swapped endpoints, a long diagonal,
translated origins and a moving target. Confirm texture direction, UV stretch,
width, endpoint inclusion and occlusion. Add a flash or end impact as a child
with its own timing rather than overwriting the beam's path data.

## Real model fragments: geometry and scale contract

Use an actual `.vmdl` resource with `C_OP_RenderModels` or another appropriate
native model renderer. A normal-aligned textured quad is not a mesh fragment.
Resolve the model and its material/texture dependencies before describing the
effect as a delivered mesh effect.

A compact impact starting point is 8–16 fragments, lifetime 0.5–1.2 s and a
small spawn volume around CP0. Derive the scale from the real model bounds;
do not assume a sprite-radius value is a universal model scale. Inspect model
selection, transforms, angular initialization/update, tint/alpha behavior and
whether animation is needed. Add collisions only when the brief requires them
and the target scene/trace contract is defined.

Keep a short luminous core or dust layer separate from geometry. First inspect
one fragment at a reproducible pose/time so incorrect axes, giant geometry or
unintended materials are visible before increasing population.

## Animated mesh swarms: choreography and playback

For a choreographed flock, rotating shell or coordinated debris, a skinned
model can contain multiple independently animated elements. A model particle
then instances that whole model: count visible elements, model instances,
bones, triangles and material cost as well as the VPCF particle population.
A small particle count alone does not establish a cheap effect. Baked flight
paths implement choreography; they do not add live flocking or world collision.

The exercised ModelDoc route imports a skinned mesh and uses `AnimFile`
children in `AnimationList` for named clips. Set the source clip range,
framerate and looping deliberately. With `C_OP_RenderModels`, inspect
`m_bAnimated`, `m_SequenceName`, forced looping, manual-frame mode,
`m_bScaleAnimationRate` and the typed `m_flAnimationRate` input. Source
framerate, renderer animation rate and PET simulation/playback speed are
different controls; verify elapsed playback and fades instead of assuming
a rate value is a universal multiplier or copying a clip's FPS blindly.

Author mesh bind poses and animation tracks around the intended emission
anchor, such as a throat, rather than retaining an unrelated floor-height
offset. Keep clips and bind poses consistent if rebasing. Model component
scale also scales baked relative travel; it does not automatically scale
separate sprite children. Confirm wings/rotation and silhouette at multiple
times and views; a CP-driven rotation test changes the effect orientation,
not the camera. Choose counts and budgets for the actual use case rather
than treating one tested rig's bone count as an engine limit.

## Attraction or orbiting detail: explicit force target

For particles emitted near CP0 and drawn toward CP1, inspect
`C_OP_AttractToControlPoint`, its transform input, force provider, falloff,
minimum-distance and component-scale fields, together with the movement
operator that consumes the force. The cyan tether's shard child is a compiling
CP1 attraction example with a separately authored texture.

Choose a small initial population, lifetime and target distance. Then vary one
force-related input at a time. Do not infer the native equation, units or the
meaning of zero falloff solely from member names. Test the target near the
origin, behind it, coincident with particles and moving across the effect.
Observe overshoot, capture, instability and cleanup.

Attraction alone is not an orbit. An orbit requires a deliberate tangential
motion/rotation/path contract and appropriate damping/constraints. Investigate
native rotation/path/force components for the requested trajectory rather than
renaming an attracted cloud “spiral.” `C_OP_RandomForce` and noise forces are
separate motion choices; preserving their native inputs does not prove their
sampling or integration behavior.

## Requests outside these examples

Search the full target catalogue for the requested mechanism: ring/path/model
surface/snapshot spawn; scalar/vector remapping and curves; world constraints;
entity-driven CPs; projected particles, lights, blobs, GPU or other native
renderers. Query the matching records and their declared dependencies, choose
the necessary engine context/resources, and build an isolated native test.

Do not treat this list as a list of implemented features or a claim that every
reflected class works in every context. The selection process is open to all
target-native classes and providers; the final effect is established by its
actual sources, native compilation and the observations relevant to the brief.
