---
name: source2-particle-authoring
description: "Create and revise native CS2 particle effects from prompts: layered VPCF, providers, control points, resources and native validation."
---

# Source 2 particle authoring

Turn the user's intent into editable native CS2 assets: a root `.vpcf`, its
children, required resources and a concise CP/validation contract. Use CS2 by
default. If the user names another Source 2 game, retain that target and verify
its own schema/toolchain before reusing CS2-specific fields.

## Decide the effect, then author it

Establish the intended in-game use and installed CS2 toolchain from available
context. Keep the user's chosen renderer, visual intent and attachment rules.
A newer s&box layout or a matching class name does not establish that CS2
implements the same behavior.

Translate the brief into a short plan: emission trigger/duration, scale,
silhouette, motion, color/alpha over time, independent layers, attachments/CPs,
resource choices and performance budget. Use reasonable stated defaults for
minor artistic choices. Ask only when a missing fact changes the deliverable.
For composition, quality tiers and population estimates, read
[the planning workflow](references/planning.md). For actionable smoke, fire,
beam, model-fragment, animated-mesh swarm and attraction starting points, read
[the composition recipes](references/composition-recipes.md).

Author native text `.vpcf` documents directly. Use child systems when layers
need independent timing, population, motion, resources or renderer behavior.
There is no class whitelist: emitters, initializers, operators, forces,
constraints, pre-emission controls, providers and renderers come from the target
engine's actual capabilities. Preserve unknown fields when editing an existing
effect. Choose the actual native component or resource pipeline needed by the
request; the starting examples do not define the available feature set.

Before introducing unfamiliar native fields, enums or providers, inspect local
target-game schema and suitable legally available sources. Read
[native authoring contracts](references/native-contracts.md) for the distinctions
that prevent plausible-looking but incorrect VPCF. If available, use the sibling
`source2-particle-schema` skill for targeted evidence lookup, or inspect the
same evidence manually. For efficient discovery, run the following from the
installed schema skill directory, then query the fields actually being authored:

```sh
python scripts/schema_catalog.py search --module particles --kind class --contains Render --limit 20
python scripts/schema_discover.py --module particles --class C_OP_RenderSprites --contains texture --limit 20
python scripts/schema_catalog.py query --module particles --class C_OP_RenderSprites --field m_vecTexturesInput
```

Follow declared class/enum dependencies returned by exact field queries.
Class search and field discovery are pages: continue with `--offset` when
`next_offset` is present. Discovery defaults to 20 fields (maximum 100), showing
compact type labels and declaring/inherited identities. This explicitly partial
view omits full type trees, metadata and defaults; obtain exact field contracts
before authoring. Reserve the full `catalogue.md` and whole-class `--summary`
for reviews that need them and set a deliberate context/output budget with
`--max-output-bytes`. Full queries remain available when necessary.
Without the optional schema skill, inspect the corresponding native editor,
schema dump or lawful CS2 source directly. Reflection proves layout/type
information, not runtime equations or visual fidelity.

## Keep the effect connected

Describe CP ownership, initial values, coordinate space, update cadence and
which systems consume each CP. Model orientation, sprite facing and volumetric
appearance are separate choices; do not silently substitute a billboard for
requested mesh geometry. Use `source2-particle-control-points` or
`source2-particle-behavior` when available for deeper work; the essential
contracts are also covered in the reference above.

Deliver every newly authored child and declare material, texture, model,
snapshot and other dependencies with their origin/status. Verify existing
paths rather than inventing a plausible game asset name. If new materials or
textures are needed, author them or retain an explicit unresolved dependency
and explain its effect. The sibling `source2-particle-materials` skill is useful
when installed, but is not a prerequisite to writing VPCF.

## Iterate against the actual target

Build IDs date evidence; they are not a supported-version allowlist. Reuse
established contracts after updates, investigating relevant changes or
regressions rather than refreshing every reference or repeating every probe.

Check source structure and resource closure, then compile with the target game's
official tools when available and authorized. Recompile after source changes.
Treat compiler acceptance and PET/in-game observation as different evidence.
Use `source2-particle-validation` when available, or follow the manual handoff in
[delivery and validation](references/delivery.md). Preserve native functionality
throughout iteration, including unfamiliar classes and nested provider fields.

Report the root asset, editable sources, CP/resource requirements, completed
checks and the specific remaining uncertainty. Do not claim that every visual
request is guaranteed by generated syntax, reflected fields or compilation.
If the target genuinely lacks a requested feature, explain the evidenced gap
and propose an implementation that preserves the intent as closely as possible.

## Starting asset

For a small structural starting point, copy the original
[layered impact sources](assets/layered-impact/particles/skill_examples/layered_impact/root.vpcf)
and both sibling child files. The example is a seed for editing, not a feature
ceiling. Read [its evidence and limitations](references/example-evidence.md)
before describing its native validation or appearance.

For an example with owned textures and a two-point CP contract, read
[cyan tether](assets/cyan-tether/README.md). It includes four native particle
sources, three original RGBA images and three VTEX definitions, compiled and
read back without source repairs. Native motion and pixels
remain unverified; use its source tree as an editable example, not a visual oracle.
