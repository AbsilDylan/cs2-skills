# Native contracts that affect authoring

## Contents

- [Separate the evidence](#separate-the-evidence)
- [Providers are typed behavior](#providers-are-typed-behavior)
- [Components run in a context](#components-run-in-a-context)
- [CP and coordinate-space contract](#cp-and-coordinate-space-contract)
- [Renderer, material and geometry are separate](#renderer-material-and-geometry-are-separate)
- [Bounds and lifecycle](#bounds-and-lifecycle)
- [Interpolation and defaults](#interpolation-and-defaults)

Read the relevant sections when selecting unfamiliar fields or diagnosing an
effect that parses but behaves unexpectedly. These are authoring invariants,
not an exhaustive catalog of engine classes.

## Separate the evidence

| Evidence | Establishes | Does not establish by itself |
| --- | --- | --- |
| Target-game schema/reflection, DWARF, field layout | Class/member identity, types, inheritance and sometimes defaults/enums | Sampling scope, equations, update order, particle-space semantics or visual parity |
| Existing legal target-game source | Authored combinations and concrete resource references | That a copied combination is appropriate or distributable for this task |
| Official resourcecompiler success | This input was accepted by that compiler/toolchain | Intended motion, good visuals, correct CP ownership or deployment to another install |
| PET or in-game observation | Observed behavior in a recorded scene/build | A universal class contract outside that exercised case |

Prefer target-game evidence. A s&box symbol can be a lead for investigating CS2;
it is not an automatic CS2 contract or a reason to rename fields without proof.
Record unresolved assumptions at the field/behavior that depends on them.

## Providers are typed behavior

A reflected numeric field may be a provider structure, not a plain number.
Check the exact target type and a suitable source example before choosing
literal, random, curve, noise, attribute, collection-age, CP-derived or other
provider inputs. Preserve the discriminator and authored nested fields.

For random inputs, distinguish sampling per particle, per collection, at
initialization or continuously. Use observed enum values rather than inventing
a plausible spelling. For time-driven inputs, establish whether time is system
age, particle age, normalized lifetime or another domain. “Constant” in a native
enum does not establish the full random sampling contract from its name alone.

Attribute indices and names are engine contracts too. The included CS2 example
authors scalar fields `1` and `3` as a concrete observed starting point; it does
not define attribute layouts for every game or permit inventing new indices.
Prefer the target schema/source and named native enum where the tool exposes it.

## Components run in a context

Keep emitters, initializers, operators, forces, constraints, renderers and
pre-emission controls in the correct native stage. Initialization and update
are not interchangeable. Check interactions: an operator replacing alpha or
radius later in the update may override another operator's intended result.
Do not implement a guessed force equation merely because its vector layout is
visible in reflection.

Engine-driven providers can require owner/entity state, world traces, model
geometry, snapshots, lighting or render-pass context. Keep the native component
and specify those inputs. A test without the required context cannot establish
the component's in-game behavior.

## CP and coordinate-space contract

For each consumed control point, record:

- Meaning: origin, target, direction/orientation, owner bone, scalar/vector
  parameters, or another purpose evidenced for that component.
- Who provides it and whether it is set once, updated continuously, inherited
  by children, or changed by pre-emission logic.
- Coordinate space and whether movement/orientation of the owner is inherited.
- A reproducible initial/test value, and behavior when its owner or target ends.

Do not treat a CP position as an orientation or a CP component as an arbitrary
spare channel without checking every consumer. Moving CP0 in an editor does not
prove every child or already-emitted particle follows it. For a directed effect,
define both orientation and endpoint contracts as needed by the chosen classes.

## Renderer, material and geometry are separate

A screen-facing sprite, a world-oriented sprite, a ribbon/trail and rendered
model geometry have different spatial/readability contracts. A normal-aligned
quad is still a quad. Use a real verified model path when the effect requires
mesh fragments. Investigate the target engine's actual volumetric/projected/
refractive capability when those features matter; do not silently approximate
the request through a single generic sprite.

Resource paths should refer to assets actually authored or present in the
target addon/game. Declare whether the dependency is source or compiled and
how it is delivered. Texture frames/sequences, blend mode, color space, alpha,
depth tests and soft-particle behavior can dominate the appearance even when
particle motion is correct. A material-free compiling source may rely on native
defaults; compilation does not prove that it has the intended silhouette.

## Bounds and lifecycle

Choose bounds from the effect's full motion and rendered extent, including
growing radius, trails, model scale, CP movement and child layers. A bound
estimated only from initial radius can cause culling after the particles grow.
Check whether the target branch treats bounds in local or world space.

Define stop and cleanup behavior for both root and children. Sustained emission,
particle lifetime and effect-system duration are distinct. Check repeat,
restart, end-cap and owner-removal behavior when they matter to the use case.

## Interpolation and defaults

Obtain the bias domain, time domain and default from the exact native field and
its target-game behavior. A familiar interpolation formula or a value that looks
neutral in another renderer does not establish the CS2 equation. Distinguish an
authored value, a reflected default, a compiler-elided default and a value
actually observed at runtime. Preserve existing values when making unrelated
artistic edits; change the specific curve intentionally when the request needs it.
