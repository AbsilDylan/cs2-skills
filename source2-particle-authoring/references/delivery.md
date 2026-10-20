# Delivery and validation handoff

## Native assets are the primary output

Deliver the root `.vpcf`, every newly authored child source, and any newly
authored resources requested by the task. Preserve the intended addon-relative
directory structure. Include a concise CP/resource plan when the effect needs
external runtime input. Keep the result usable as ordinary native source files.

Describe dependencies precisely: existing verified game/addon resource,
authored source included, user-provided pending, or unresolved. An unresolved
material/model can prevent the intended appearance even when the VPCF parses.
Do not bundle Valve or third-party assets merely because local tools can read
them. Original examples in this skill contain no extracted game assets.

## Check the level actually available

1. **Source/closure check:** syntax if a suitable parser is available, root and
   child references, stage structures, paths, provider fields and dependency
   inventory. Preserve unfamiliar native content if a local parser is narrower
   than the official format; use the official tools rather than deleting it.
2. **Official compilation:** use the target game's compiler or Workshop Tools
   on a scratch addon or other user-authorized destination. Retain the exact
   inputs and compiler/build identity, actual exit diagnostics and output
   presence. If a compiler is unavailable, leave this check explicitly pending.
3. **Visual/runtime observation:** open the root in the target editor/PET or
   game, set the documented CPs and scene, and observe startup, motion, end and
   restart. Validate the intended attachment/resource delivery in game when
   required. Record what was actually observed.

For a failed compile, use the error to correct the relevant source/resource
contract and recompile after the change. Avoid repeated speculative rewrites
of unrelated fields. Stop the retry loop when additional native evidence or a
missing dependency is required; preserve the useful authored work and explain
the concrete missing input.

The optional sibling `source2-particle-validation` skill supplies native
compilation and readback procedures. It does not bundle a compiler or launch
script. Using the installed target-game tools, copy the addon-relative source tree into an
authorized content addon and use the official editor/compiler for that install.
Tool locations and flags differ by game/toolchain; derive them from the actual
installation.

## Useful acceptance checks

Select checks that match the effect rather than running a universal checklist:

- Root starts all intended children at the requested times.
- The selected scene/time shows the intended scale, silhouette and color.
- CP transforms and attachments produce the documented response.
- Animated materials, trails, models, lighting/depth and collision behave as
  required in the target renderer.
- Emission stops, particles decay, and restart/owner removal behave correctly.
- Resources resolve in the intended delivery environment, and the particle
  population/frame cost is suitable for the use case.

Compiler success must not be reported as visual success. When a tool cannot
interpret a native class, verify the class with native evidence rather than
deleting it from the effect.

## Delivery layout

Use an addon-relative source tree, for example:

```text
particles/my_effect/root.vpcf
particles/my_effect/core.vpcf
particles/my_effect/smoke.vpcf
materials/my_effect/core.vtex
materials/my_effect/core.tga
materials/my_effect/smoke.vtex
materials/my_effect/smoke.tga
```

Include a `.vmat`, model sources, animation sheets or snapshots when the chosen
native renderer and resource pipeline require them. Preserve their own dependent
files. A declared path is not a delivered asset: identify unresolved or existing
external dependencies in the adjacent plan, and verify their target location.

Keep demonstration helpers outside the production dependency closure. A PET
helper may animate a control point, set a numeric parameter, add a reference
actor or repeat playback. The production root should accept the caller's real
inputs without depending on that helper. Document required initial values;
saved PET values do not initialize a game-created instance.

Select the final roots explicitly and traverse both source imports and native
compiled references. Include generated textures and model animation imports
when required, even if their names differ from the root's namespace. A final
effect can legitimately use resources with different revision suffixes; file
names and timestamps cannot select the approved composition. Deduplicate
identical shared resources and report differing same-path payloads.

The final report should name the root to open, list authored files, describe CP
setup and state the checks actually completed. Keep installation paths and
machine-specific temporary directories out of reusable source contracts.
