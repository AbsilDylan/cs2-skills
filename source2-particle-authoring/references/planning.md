# From a prompt to an effect plan

Use this reference when a brief contains several layers, attachment rules or
visual ambiguities. A short effect does not need a formal planning document.

## Resolve the decisions that change the result

| Intent in the brief | Concrete authoring decision |
| --- | --- |
| Impact, detonation, pulse | Emission trigger, burst count, delayed children, restart and cleanup conditions |
| Flame, aura, ambient field | Sustained rate, system duration, stop behavior, warm-up and particle lifetime |
| Ring, spiral, ribbon, beam | Native spawn/path/control geometry, orientation, attachment and renderer; not just a sphere with a themed color |
| Smoke, mist, volumetric appearance | Required silhouette and depth cues, material/texture or model resources, lighting/depth behavior and actual engine support |
| Fragments, debris, 3D pieces | Real model resource, transform/orientation inputs, movement, collision requirements and lifetime |
| Follows a player, weapon or projectile | Runtime owner, CP transform/update contract, local versus world space and behavior when the owner disappears |
| More powerful, slower, cleaner | Named changes in radius, duration, motion, density, contrast, layers or timing; retain unrelated authored choices |

If the user gives dimensions or time, preserve them. State the unit conversion
used for the target game rather than assuming that every Source 2 branch uses
an identical authoring convention. For unspecified scale, pick a coherent
initial size and make it easy to tune.

## Choose systems by independent behavior

A system can contain several native components. Split into children when it
helps maintain different populations, independent emission timing, lifetimes,
forces, collision, materials or renderer behavior. Typical visual roles include
a readable core, directional details and a slower residual layer; they are
options, not mandatory components or a fixed number of layers.

Write a compact table before complex authoring:

| System | Visual role | Emission/lifetime | Motion | Renderer/resources | CPs |
| --- | --- | --- | --- | --- | --- |
| Root | Composition and shared placement | Starts children, owns effect end | None if it emits no particles | Child references | Placement/orientation contract |
| Child A | Main silhouette | Explicit timing and population | Named spatial behavior | Actual intended renderer/resource | Inputs consumed |
| Child B | Detail or residual layer | Independent timing and cleanup | Independent behavior if needed | Actual intended renderer/resource | Inputs consumed |

Bound the work by the effect's use case. For a sustained layer, estimate live
population as `rate * mean lifetime`; use `rate * maximum lifetime` for a
conservative capacity starting point. For bursts, account for repeated impacts
whose lifetimes overlap. Sum simultaneous children, not merely the root's
particle capacity. A zero-emission root can still own expensive children.

For example, a 40/s flame with a 0.6 s maximum life, 12/s embers with a 1.2 s
life and 16/s smoke with a 2.5 s life have upper population estimates of 24,
15 and 40 before headroom and overlaps: approximately 79 live particles in one
running effect. Six simultaneous effects can reach approximately 474 particles.
These are authored starting estimates, not measured engine limits.

Choose quality tiers by the visual role, not by scaling every parameter blindly:

| Tier decision | Preserve | Reduce or simplify first |
| --- | --- | --- |
| Distant/local impact | Event timing and primary silhouette | Small secondary motes and redundant overlapping layers |
| Sustained smoke/fire | Coherent emission and readable motion | Texture area/overdraw, unnecessary lights, simultaneous expensive layers |
| Beam | Endpoint contract and continuous connection | Excess segments beyond the needed silhouette; material pass complexity |
| Model debris | Perceived scale and movement direction | Fragment count, model complexity, costly collision where unnecessary |

Particle count alone is insufficient. Large translucent quads can dominate
overdraw; trails can expand geometry; model renderers and scene traces add
different costs. Measure the target scene with its expected concurrency and
camera distance, then adjust the layers causing the cost.

## A useful durable plan

For effects requiring later iteration, keep a small adjacent plan containing:

- Target game, relevant build/toolchain and intended in-game use.
- The root resource and each layer's purpose/timing.
- CP roles, required initial values and ownership/update rules.
- Assets with origin and status: authored here, existing verified game/addon
  resource, user-supplied pending, or unresolved.
- The user's visual acceptance criteria and checks actually completed.

Use the optional [example plan](../assets/layered-impact/effect-plan.json) as a
shape, not as a schema that restricts which native fields can be authored.

## Editing an existing effect

Read the root and reachable children before changing the visible symptom.
Keep unknown classes, provider objects, metadata and unrelated properties.
If the available writer cannot round-trip a native construct, make a narrow
text edit or use the official editor rather than serializing a reduced tree.

When the request is an artistic revision, identify the minimum systems and
parameters that control it. Compare a consistent seed/time/camera when the tools
allow it. Preserve attachment, timing and resource contracts unless the request
calls for changing them.
