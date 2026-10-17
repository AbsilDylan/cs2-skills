---
name: source2-particle-validation
description: "Validate CS2 particles with the native compiler, compiled-property readback, resource closure and PET/game observations; keep runtime and visual evidence separate."
---

# Validate CS2 particle effects

Tie observations to the authored sources and installed game build. A build
number dates a check; it does not restrict the skill to that version. Keep
four independent results: **compilation**, **property retention**, **runtime
behavior**, and **visual appearance**. Passing one does not pass the others.
Use Python 3.10+ standard library and an installed CS2 Workshop Tools compiler.
An optional Source 2 Viewer CLI can capture binary readback text.

## Choose the necessary evidence

- For compiler acceptance or build failures, read
  [native-compilation.md](references/native-compilation.md), including its
  guidance for CS2 updates and existing authorized addons.
- For ignored properties, compiled imports, or suspected defaults, read
  [compiled-readback.md](references/compiled-readback.md).
- For motion, editable CPs, material appearance, or game-versus-editor
  discrepancies, read [visual-validation.md](references/visual-validation.md).
- For reproducible historical findings and their version limits, read
  [observed-evidence.md](references/observed-evidence.md). Historical observations
  guide probes; they do not establish the currently installed build's behavior.

## Compile a concrete source package

Run [scripts/compile_native.py](scripts/compile_native.py) with explicit
absolute `--cs2-root`, `--source-root`, and `--work-root` paths. Use `--plan`
first to inspect its inventory without writing or launching tools, then run
the same command without `--plan`. Supply `--effect-root` when checking a
complete effect. The source folder must preserve resource-relative paths.
The helper stages a fresh addon, compiles textures before dependent assets,
and records logs, identity, hashes, failures and fresh outputs. It never
reuses an existing addon or deletes assets.

Read the compiler reference for a complete command, budgets, external
dependency limitations and optional `--viewer-cli` capture. A successful run
still leaves property retention and native visual/runtime behavior unverified.

## Establish the target

Identify the user's target game/addon, original source root, effect root, child
systems, and requested verification. Inspect the installed game identity and
compiler before choosing flags. Preserve the authored sources separately from
compiled output and record their digests. A public schema or DWARF snapshot
from another revision is type/layout evidence, not a native behavior oracle.

Use a fresh isolated addon for compilation when that fits the requested task.
Resolve destination paths, reject links/redirected paths, and fail if an audit
destination already exists. Do not change another addon, game configuration,
launch option, or published Workshop item to complete an isolated test.
Compilation inside a new addon is not an operating-system sandbox.

Close the authored child graph before compiling. Inventory external
materials, textures, models and other resources separately. Compiler acceptance
does not establish that those dependencies exist, ship, render, or belong to
the target game's Workshop closure.

## Verify the claim being made

For a property, choose a controlled nondefault input and inspect the compiled
readback before interpreting an absent field. Check exact field spelling,
provider shape, enum and component stage. Preserve valid native features when
an inspection tool lacks support; obtain a compatible decoder or mark the
property check unresolved.

For CP behavior, verify the relevant index, position, orientation, and timing.
Test a nonzero CP as well as CP 0, moving or rotating it in the intended
environment. Record whether changing it affects newly spawned particles,
existing particles, children, or an attraction target. A serialized CP index
proves an accepted reference, not a working attachment or live-update rule.

Keep failures and raw logs. Fix a diagnosed source or dependency issue before
repeating the same run. If the required compiler, decoder, or official visual
surface is unavailable, finish the independent checks and report the exact
missing evidence. Artwork images and decoder text do not substitute for a
native visual test.

## Deliver evidence

Report the source/build identity, native command and exit status, fresh output
digests, warnings, readback result, and any observed CP/visual behavior. Mark
unexecuted checks explicitly. Keep portable reports free of absolute user
paths; retain detailed local log locations separately when useful.

Never conclude “all properties work” from exit code 0. Unknown fields can be
silently dropped; defaults can disappear; valid compiled particles can remain
invisible in the intended game scene.
