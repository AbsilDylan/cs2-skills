# Portable AnimGraph2 Tooling

Use the bundled scripts for deterministic, current-build extraction, Blender
authoring, DMX export, VNMClip generation, and ResourceCompiler builds. The
pipeline is manifest-driven: the Five-SeveN paths in the example are only a
replaceable baseline, not code defaults.

## Contents

1. Scope and guarantees
2. Prerequisites
3. Project manifest
4. Discover and extract current stock references
5. Create the Blender authoring scene
6. Author first- and third-person actions
7. Export complete DMX actions
8. Generate VNMClip documents
9. Compile declared resources
10. Inspect and package outputs
11. Change the baseline weapon or item
12. Failure diagnostics
13. Reproducibility and licensing

## 1. Scope And Guarantees

The scripts implement this local pipeline:

```text
current CS2 VPK
  -> local decompiled references and hashes
  -> exact 1P/3P Blender armatures and reference actions
  -> complete sampled DMX channels
  -> current-template VNMClip documents
  -> ResourceCompiler outputs and receipts
```

They do not choose a runtime proxy, create a private graph state machine,
patch a compiled graph, register VData, or publish a Workshop item. Those
steps remain build- and project-specific; use the other references in this
skill after the clips have passed inspection.

The repository ships no Valve resource. Extraction always targets the user's
installed build and writes to `.local/references` or another explicitly chosen
cache.

A historical integration observation recorded on 2026-07-17 used Blender
4.1.1 plus the then-installed CS2 `dmxconvert`, ResourceCompiler, and
Source2Viewer-CLI for three first-person and three third-person clips. It noted
56-bone/112-channel viewmodel and 74-bone/148-channel worldmodel data and six
compiled VNMClips. The repository does not ship that run's raw receipt, so
treat these figures as a documented observation, not reproducible current-build
proof. Produce new versioned, non-overwriting receipts before relying on them.

## 2. Prerequisites

Required tools:

```text
Python 3.10+
Blender 4.1.1 with its bundled bpy/mathutils (recorded/tested version;
  revalidate any other Blender version)
CS2 Workshop Tools and resourcecompiler
dmxconvert from the current CS2 game/bin directory
Source2Viewer-CLI or ValveResourceFormat CLI
Source2Viewer or an equivalent compiled-resource inspector
```

Useful environment variables:

```text
CS2_ROOT or CS2_LOCAL_ROOT = Counter-Strike Global Offensive install root
VRF_CLI or SOURCE2VIEWER_CLI = Source2Viewer-CLI executable
DMXCONVERT = dmxconvert executable
RESOURCECOMPILER = resourcecompiler executable
```

The scripts also accept explicit command-line paths. Explicit arguments take
precedence over environment variables.

Resolve the installed skill and the addon project independently before using
the commands below. Do not copy the bundled scripts into the project or depend
on the shell's current directory:

```powershell
$SkillRoot = (Resolve-Path "<installed-cs2-animgraph2-authoring-skill>").Path
$ProjectRoot = (Resolve-Path "<addon-content-project-root>").Path
$Manifest = Join-Path $ProjectRoot "animgraph2-project.json"
$ReferenceRoot = Join-Path $ProjectRoot ".local\references"
$BlendFile = Join-Path $ProjectRoot ".local\authoring\item-actions.blend"
$ArtifactRoot = Join-Path $ProjectRoot ".local\compiled-handoff"
$Blender = "<absolute-path-to-blender-executable>"
```

The two resolved roots must be different concepts even when a temporary test
checkout happens to place them near each other. Replace the angle-bracket
values and verify `$Blender` exists before running any mutating command.

## 3. Project Manifest

Copy [animgraph2-project.example.json](../examples/animgraph2-project.example.json)
to the root of the addon content project and rename it. Keep generated source
paths relative to this manifest.

The important top-level fields are:

```text
schema_version       portable schema version, currently 1
project.name         project id
project.addon        csgo_addons directory name
project.namespaces   one or more private resource roots
project.artifact_policy  blocked/allowed status plus explicit provenance bases
sets                 independent viewmodel/worldmodel authoring sets
stock_dependencies   local Valve sources required only by ResourceCompiler
stage_sources        extra private transitive sources copied by --stage
compile_resources    exact dependency order for project resources
```

Every authored output, `stage_sources` entry, and `compile_resources` entry
must live below one declared `project.namespaces` root. This permits a single
manifest to own private `animation/...`, `models/...`, and `materials/...`
families without widening access to Valve-global roots. The legacy singular
`project.namespace` remains accepted and is canonicalized to a one-item list.
Validation rejects Valve-global
namespaces, case-insensitive path/name collisions, non-finite numbers,
unordered preroll samples, and Windows-ambiguous names before any tool writes.

`project.artifact_policy.status` defaults to `blocked` when absent. Set it to
`allowed` only after recording a concrete `basis` that covers every generated
and transitive input. Outputs generated by preserving a locally decompiled
stock template are derivative evidence and remain blocked unless the owner has
established the right to redistribute the resulting artifact. An `allowed`
policy therefore also requires a separate non-empty
`template_derivative_basis` covering the preserved VNMClip template fields.
A manifest assertion records that decision; it does not create permission.

Each set declares:

```text
id                                viewmodel, worldmodel, or another unique id
armature                          exact Blender armature object name
fps                               authoring sample rate
blender_units_per_source_unit     explicit DMX-to-Blender scale
translation_mode                  absolute or bind-pose-delta
max_abs_source_position           corruption guard in Source units
primary_skeleton                  character skeleton used by VNMClip
secondary_skeletons               optional weapon/object skeletons
preroll_seconds                   negative DMX samples required by the format
reference_dmx_frame               source-axes (VRF <= 19.1 references, default,
                                  converted on export) or compiler (VRF >= 19.2)
secondary_skeleton_dmx            optional weapon skeleton DMX (stock decompiled
                                  skeleton under the reference root, or a
                                  project-relative custom skeleton DMX)
secondary_attach_bone             Blender scene parent (default wpn)
secondary_export_attach_bone      DMX insertion parent (defaults to the scene parent)
actions                           canonical action definitions
continuity                        optional endpoint assertions
```

`reference_dmx_frame` is the second data contract that decides whether the
clip renders at all: ResourceCompiler expects the frame Source 2 Viewer
>= 19.2 writes, and the pinned 19.1 CLI writes raw Source axes. Leave the
default when the references come from that CLI; set `compiler` only for a
cache produced by a >= 19.2 release. `secondary_skeleton_dmx` adds the
weapon skeleton's joints under `secondary_attach_bone` in the authoring
scene and exports them as the clip's secondary animation (what moves a
slide, a pin or an object inside a held model); list the matching
`.vnmskel` in `secondary_skeletons` so the document declares it.

`secondary_export_attach_bone` controls only the DMX insertion hierarchy. It
leaves Blender parenting and pose sampling unchanged, and defaults to
`secondary_attach_bone` for existing manifests. In a measured M134 case,
`wpn` in Blender plus `root_motion` in DMX yielded the required neutral compiled
secondary root. Do not use that override without comparing the current stock
and custom compiled-root contract; see
[weapon-presentation-contracts.md](weapon-presentation-contracts.md).
The export report records both scene and export parents. Portable unit tests
cover defaults, validation and hierarchy/channel preservation; they do not
constitute a Blender/ResourceCompiler or in-game run for a new project.

`translation_mode` is a data contract, not an aesthetic choice. In the
current tested build, viewmodel position channels were local absolute values,
while the tested worldmodel channels were bind-pose deltas. Inspect a current
reference before using those conventions for another skeleton.

Each action declares a current compiled stock reference, a Blender action
name, one output DMX, one output VNMClip, and an event policy. Set
`minimum_frames` when a static or looping action needs a finite duration. A
31-frame idle at 30 FPS is a useful current-build baseline. One-frame static
actions are valid: duration is zero and finite DMX `frameRate` remains the
declared FPS.

Event policies:

```text
clear                remove every inherited event
preserve-reference   retain the current stock template events
replace              load m_eventTracks from event_tracks_file
```

For `replace`, the event file must contain exactly one KV3 array literal. Do
not inherit stock fire, ammo, reload, or sound events accidentally.

## 4. Discover And Extract Current Stock References

List candidate clips without extracting them:

```powershell
python -B (Join-Path $SkillRoot "scripts\extract_stock_references.py") list `
  --cs2-root $env:CS2_ROOT `
  --vrf-cli $env:VRF_CLI `
  --prefix animation/anims/viewmodel/ `
  --regex "(draw|idle|shoot|plant).*\.vnmclip_c$"
```

Repeat with `animation/anims/world/` for third-person references. Put the exact
current paths in each action's `reference_resource`.

Extract all references and declared local compiler dependencies:

```powershell
python -B (Join-Path $SkillRoot "scripts\extract_stock_references.py") extract `
  --manifest $Manifest `
  --cs2-root $env:CS2_ROOT `
  --vrf-cli $env:VRF_CLI
```

The default output is `.local/references`. The extractor requires every
expected DMX, VNMClip document, skeleton source, and companion DMX to exist.
It writes `reference-extraction-report.json` with VPK receipts and SHA-256
hashes.

A cache hit requires the same VPK hash, VRF executable hash, exact per-resource
VPK/CRC receipt, and unchanged hashes for every extracted output. Merely
finding old files under `.local/references` is not a cache hit. Use `--force`
to extract again even when all provenance checks pass.
Each extraction also writes a versioned
`reference-extraction-report-<run-id>.json`; the unversioned report is the
cache/latest pointer.

`stock_dependencies` is for build-only source material. A typical current
configuration declares the primary character skeleton and the selected weapon
skeleton. These sources are compiled locally before the clips and have
`package: false`; they are not copied to the artifact handoff.

## 5. Create The Blender Authoring Scene

Run Blender's Python, not system Python:

```powershell
& $Blender --background --factory-startup `
  --python (Join-Path $SkillRoot "scripts\blender_create_scene.py") -- `
  --manifest $Manifest `
  --reference-root $ReferenceRoot `
  --cs2-root $env:CS2_ROOT `
  --output $BlendFile
```

The creator refuses to replace an existing `.blend`. Pass
`--force-overwrite` only after preserving or reviewing that file.
It also refuses to clear a loaded, saved, dirty, or non-factory scene. Keep
`--background --factory-startup` in automation; `--allow-clear-scene` is an
explicit destructive-memory opt-in after saving and reviewing the open scene.

The script:

- derives the bone set and hierarchy from each current DMX reference;
- creates one exact armature per selected set;
- imports every stock clip as `REF_<set>_<action>`;
- duplicates it to the manifest's editable action name;
- appends the set's `secondary_skeleton_dmx` joints under the attach bone
  (with `cs2_source_rest_position` set for bind-delta sets) and records them
  in the armature (`cs2_secondary_bones`);
- keys the complete rig, including hands and fingers;
- preserves quaternion sign continuity;
- stores manifest, skeleton, scale, source hashes, and a canonical
  name/parent/rest-matrix signature in the scene.

Use `--set viewmodel` or `--set worldmodel` to create separate files. Keeping
both sets in one file is also supported when their armature and action names
are globally unique.

The generated scene intentionally contains no redistributed Valve mesh. For
accurate hand clearance, locally import a current stock preview or a
user-owned FBX/GLB, then parent or skin that preview without changing the
authoring armature object transform. Preview geometry is ignored by export.
For complex player meshes, use the separate player-model porting skill.

## 6. Author First- And Third-Person Actions

Open the `.blend` interactively and edit only the action names declared in the
manifest. `REF_*` actions are comparison references.

Rules that prevent the common broken-arm result:

1. Keep the armature object's location and rotation at zero and scale at one.
2. Animate pose bones; do not move or mirror the armature object.
3. Preserve names, hierarchy, rest axes, and stored source unit scale.
4. Pose hands, fingers, helpers, and weapon targets deliberately.
5. Inspect the actual first-person camera and a third-person observer view.
6. Keep item geometry outside fingers and palms on every sampled frame.
7. Use separate 1P and 3P actions; one is not a retarget of the other.
8. Make draw/action endpoints intentionally compatible with idle before adding
   strict continuity rules.

The exporter samples every expected bone at every integer frame, so manually
keying every child is not required after posing. Missing or scaled bones still
fail validation.

## 7. Export Complete DMX Actions

Save the edited `.blend`, then export through Blender:

```powershell
& $Blender $BlendFile --background `
  --python (Join-Path $SkillRoot "scripts\blender_export_dmx.py") -- `
  --manifest $Manifest `
  --reference-root $ReferenceRoot `
  --cs2-root $env:CS2_ROOT
```

Select a subset with repeated `--set` or `--action` options. The exporter:

- rejects mirrored/non-identity armature transforms and bone scaling;
- rejects changed bone names, parenting, or edit-bone rest matrices;
- samples all pose channels with quaternion sign continuity;
- converts the root-level bones from raw Source axes to the compiler frame
  unless the set declares `reference_dmx_frame: compiler` (see section 3);
- inserts the weapon joints and channels of `secondary_skeleton_dmx` under
  `secondary_export_attach_bone` in the stock template before filling it, so the
  compiled clip carries a secondary animation for that skeleton;
- applies the set's absolute or bind-delta translation contract;
- patches the exact current stock DMX structure;
- fixes duration and finite `frameRate`, including zero-duration stock idles;
- rejects non-finite or implausibly large Source-space positions;
- converts KV2 to binary DMX and back;
- verifies every channel has equal time/value counts;
- optionally enforces declared action endpoint continuity.

It also verifies that the scene was created from the current manifest and that
every stock DMX template still has the scene-recorded hash. Regenerate the
scene after a game/reference change. `--allow-manifest-drift` and
`--allow-reference-drift` are explicit forensic escape hatches, not normal
workflow flags.

No destination DMX is touched until the whole selected batch passes validation.
Each final file uses an atomic same-filesystem replacement, and catchable
mid-batch errors roll earlier replacements back. This is not a filesystem-wide
atomic transaction: a power loss or forced process termination can interrupt a
batch. A versioned `dmx-export-transaction-<run-id>.json` journal is written
before commit to detect an unresolved `prepared` or `committed` transaction on
a later run when the operating system has persisted that write. This is a
detection-only process journal, not a power-loss-durable write-ahead log: the
tool does not fsync file and directory metadata on every transition. Only
`failed` (rollback completed) and `reported` are treated as terminal; an
unknown, malformed, or `rollback-failed` journal also blocks the next run.
Inspect/restore the listed outputs and any preserved `.pending`, `.rollback`,
`.rollback-current`, or `.rollback-corrupt` recovery files, then archive the
journal deliberately.
Rollback quarantines the exact current destination and republishes recovery
files with no-replace semantics; if another writer wins either race, its bytes
are restored/preserved and the transaction remains unresolved for manual review.

Before exporting, the tool probes atomic non-overwriting versioned-report
creation so an unsupported report filesystem fails before any destination DMX
changes. Normal NTFS/ext4 volumes use hard-link publication; Windows can use a
no-replace rename fallback. A POSIX filesystem without hard-link support is
refused rather than silently weakening immutable-receipt semantics.

Audit KV2 files and a versioned `dmx-export-report-<run-id>.json` are written
under `.local`; `dmx-export-report.json` is only the latest pointer. Open the
binary DMX or later compiled VNMClip in an inspector before graph work.

## 8. Generate VNMClip Documents

Generate one document per canonical action:

```powershell
python -B (Join-Path $SkillRoot "scripts\generate_vnmclips.py") `
  --manifest $Manifest `
  --reference-root $ReferenceRoot
```

The generator preserves unknown fields from the current decompiled template.
It changes only the source DMX, primary/secondary skeleton contract, and chosen
event policy. This is more update-resistant than inventing a fixed historical
`CNmClipDocument` schema.

Use `--allow-missing-dmx` only to inspect planned documents. A normal build
requires each generated DMX and records its hash.
The generator prepares the entire selected set before touching a destination,
then uses per-file atomic replacement, quarantined rollback, backup hash
revalidation, and no-replace recovery publication. A
`vnmclip-transaction-<run-id>.json` journal records `prepared`, `committed`, and
`reported`; unresolved, malformed, unknown, or `rollback-failed` journals block
the next run. As with the DMX journal, this detects persisted interrupted state
but is not an fsync-backed write-ahead log. Inspect the journal and any
`.pending`, `.rollback`, `.rollback-current`, or `.rollback-corrupt` files before
archiving an unresolved transaction.

Before output mutation, the generator probes immutable versioned-receipt
publication. Each attempted batch then writes a best-effort versioned
`vnmclip-report-<run-id>.json` on success or caught preparation/commit failure;
`vnmclip-report.json` is only the latest pointer. Argument, manifest, selector,
forced-termination, storage, or report-write failures can still produce stderr
without a receipt. If reporting fails after commit, the journal remains
`committed` and blocks a silent retry.

## 9. Compile Declared Resources

When the manifest directory is already the installed addon content root:

```powershell
python -B (Join-Path $SkillRoot "scripts\compile_animgraph2.py") `
  --manifest $Manifest `
  --cs2-root $env:CS2_ROOT
```

For a portable project elsewhere, stage only declared/generated sources:

```powershell
python -B (Join-Path $SkillRoot "scripts\compile_animgraph2.py") `
  --manifest $Manifest `
  --cs2-root $env:CS2_ROOT `
  --reference-root $ReferenceRoot `
  --stage
```

After replacing the example's blocked policy with a reviewed `allowed` policy
plus both evidence bases, create an isolated handoff with:

```powershell
python -B (Join-Path $SkillRoot "scripts\compile_animgraph2.py") `
  --manifest $Manifest `
  --cs2-root $env:CS2_ROOT `
  --reference-root $ReferenceRoot `
  --stage `
  --artifact-root $ArtifactRoot
```

`--stage` copies generated sources, `stage_sources`, and compile inputs. It
does not silently replace a different installed file: review the conflict or
pass `--force-overwrite`, which retains its exact preimage under
`.local/backups/<run-id>`. Staging and artifact destinations are contained under
their declared roots; symlink/junction write-through is refused. Publication
quarantines the observed preimage, rechecks ownership, and uses no-replace
semantics so a concurrent external writer is preserved rather than overwritten.

Stock sources always come from the hash-validated reference cache, including
when the manifest already lives at the installed addon root. They are staged
temporarily, compiled first, then removed or restored to their exact pre-build
state. Compiled stock dependencies with `package: false` are likewise removed
or restored after project compilation, so they cannot linger for accidental
Workshop inclusion. Dependencies explicitly marked `package: true` also
require their own `redistribution_basis` and enter the artifact handoff only
when the project artifact policy is allowed.

For a pre-existing compiled destination, a successful ResourceCompiler exit is
accepted only when the output bytes changed. Merely touching the old file is
treated as a potentially stale result and fails closed; archive the old output
first when an intentionally byte-identical deterministic rebuild must be
distinguished from stale reuse.

The artifact copier uses the same hash-aware overwrite policy. The compile
receipt records manifest, gameinfo, ResourceCompiler, all source/output
preimages and results, staging actions, backups, cleanup, commands, and hashes.
Those provenance states are captured before mutation and checked again during
the run; source/tool/manifest drift fails the build rather than relabeling an
output with later bytes.
It refuses an artifact request when policy is blocked, a subset build is
selected, a declared destination conflicts, or undeclared files already exist
in `--artifact-root`; then it verifies the exact resource set, byte lengths, and
SHA-256 hashes. Use a new/empty handoff when resources are renamed.
Versioned `compile-report-<run-id>.json` files are created atomically and the
tool refuses to replace an existing run receipt; `compile-report.json` is only
the latest pointer. Receipts are not cryptographically signed, so archive or
sign them externally when tamper evidence matters. This is a best-effort
post-initialization guarantee: after manifest/policy validation and CS2 plus
ResourceCompiler resolution, the tool probes every report root before staging;
a non-dry-run attempted build records caught
preflight-or-later failures. Argument, manifest, policy, environment-resolution,
forced-termination, storage, or receipt-write failures may produce stderr only;
dry-runs intentionally write no compile receipt.

Each mutating compile run also creates
`compile-transaction-<run-id>.json`. Its states cover preparation, staging,
compilation, optional artifact handoff, commit, and reporting. Only `failed`
(rollback completed) and `reported` are terminal; malformed, unknown,
partially completed, `committed`, or `rollback-failed` journals block the next
run. A `committed` journal normally means the outputs were verified but the
immutable report could not be published. Inspect the journal, output guards,
backups, and preserved recovery files, restore or archive them deliberately,
then archive the journal before retrying. Like the DMX and VNMClip journals,
this detects persisted interrupted state but is not an fsync-backed
write-ahead log.

The bundled mutating tools take non-blocking operating-system locks keyed by
their canonical project, installed-addon, and artifact roots. This serializes
cooperating DMX, VNMClip, and compile runs without stale lock ownership after a
process exits. Non-cooperating programs are not locked; ownership, hash, and
file-identity checks still fail closed and preserve their bytes during
rollback.

Project sources staged into the installed addon intentionally persist. A
versioned managed-stage index refuses formerly managed paths that were renamed
but still exist. This catches stale files from earlier tool runs, but it does
not prove the entire installed addon is clean: unrelated pre-existing files
remain outside the tool's authority. Package from the verified artifact
handoff or independently inventory the final Workshop VPK.

`compile_resources` is an ordered build list. Start with VNMClips, then private
variation/child graphs, roots, models, and other resources according to their
dependencies. List non-compiled transitive inputs (for example model source,
texture, or event files needed after portable staging) in `stage_sources`.
Use `--resource` for an explicitly declared subset and `--dry-run` to inspect
exact commands and source provenance without invoking ResourceCompiler.

ResourceCompiler receives the base game root:

```text
-game <CS2>/game/csgo
```

The expected output remains:

```text
<CS2>/game/csgo_addons/<addon>/<resource>_c
```

The script never writes loose files into the base `game/csgo` tree.

## 10. Inspect And Package Outputs

Before graph integration or Workshop publication:

```text
open every VNMClip_C in Source2Viewer
verify skeleton, duration, frame range, fingers, helpers, and object clearance
inspect 1P from the real camera
inspect 3P from front, rear, and both sides
compare artifact hashes with compile-report.json
confirm stock build dependencies are absent from the handoff unless intentional
```

After graph/model compilation, inspect the actual Workshop VPK and compare its
resource list and hashes with the declared project outputs. A file in the local
addon output tree does not prove it was included in the Workshop item.

## 11. Change The Baseline Weapon Or Item

No bundled Python script contains a Five-SeveN path. To use a grenade, C4,
rifle, sniper, healthshot, or another current item:

1. Discover its current viewmodel and worldmodel VNMClip paths.
2. Replace each action's `reference_resource`.
3. Set the exact primary and optional secondary skeletons.
4. Declare the skeleton compiled resources and decompiled outputs under
   `stock_dependencies` when ResourceCompiler needs local sources.
5. Confirm `translation_mode` from the extracted DMX contract.
6. Regenerate the `.blend`; do not reuse an old rig across skeleton changes.
7. Export, generate, compile, and inspect again.

The 1P and 3P baselines may come from different stock items when that better
matches the intended handling, but document that choice and test transitions.

## 12. Failure Diagnostics

`Invalid skeleton file` during VNMClip compile:

```text
Add the current compiled skeleton to stock_dependencies, list every decompiled
source output, extract again, and compile it before the VNMClip.
```

`No animation defined, frame count is -2147483647`:

```text
The stock template may have duration 0 and frameRate inf. Regenerate with the
bundled exporter. It emits the declared finite FPS even for a one-frame,
zero-duration action; increase minimum_frames only when the graph needs time.
```

Arms explode, disappear, or move far outside the camera:

```text
Check translation_mode, unit scale, armature object identity, parent updates,
quaternion sign continuity, complete finger channels, and source-position
guard metrics. Regenerate the scene after changing skeletons.
```

Weapon floats while arms are correct:

```text
Check secondary skeleton choice, weapon helper channels, object model origin,
attachments, and graph/model ownership. A VNMClip cannot repair a mismatched
owner model by itself.
```

Compiled clip is correct but runtime remains stock:

```text
The remaining problem is graph routing, player private roots, client-visible
weapon_type, Workshop mounting, prediction, or server proxy behavior. Continue
with graph-routing-and-patching.md and workshop-runtime-and-debugging.md.
```

Arms and weapon absent in game although the clip compiled cleanly:

```text
The DMX is in raw Source axes. Check the set's reference_dmx_frame against
the Source 2 Viewer release that produced the reference cache (<= 19.1 CLI:
source-axes, >= 19.2: compiler) and re-export.
```

The weapon's own parts stay still while the arms animate:

```text
The clip has no secondary animation for the weapon skeleton. Declare
secondary_skeleton_dmx (and the matching secondary_skeletons entry), recreate
the scene so the joints exist under the attach bone, and re-export.
```

## 13. Reproducibility And Licensing

Keep these original project files:

```text
manifest JSON
edited Blender file
generated DMX and VNMClip sources
private editable graph/model sources
reports and hashes
commands and tool versions
```

Keep `.local/references`, audit dumps, and Valve-derived skeleton sources out of
version control and public skill packages. Never commit compiled game assets,
VPKs, native binaries, or third-party Workshop content without permission.

Use the canonical evidence vocabulary from `SKILL.md`. This tooling reference
normally proves only the following prefix or intermediate stages:

```text
generated                 script produced the source
roundtrip-valid           dmxconvert accepted binary -> KV2 -> binary -> KV2
compiled                  ResourceCompiler produced the expected _c file
inspected                  a resource viewer showed the expected semantics
packaged                   the publisher VPK contains the expected hash
downloaded-vpk-inspected   a clean download contains that same hash
mounted                    the client resolved the downloaded addon
route-proven               the intended private branch was observed
first-person-validated / third-person-validated / gameplay-validated
in-game-validated          every applicable runtime branch above passed
```

Do not replace `inspected` with `roundtrip-valid`, or call a locally built VPK
`downloaded-vpk-inspected`. Later runtime labels require the separate clean-
client workflow in `workshop-runtime-and-debugging.md`.
