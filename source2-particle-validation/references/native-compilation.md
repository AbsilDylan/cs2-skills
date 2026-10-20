# Compile authored assets with the CS2 tools

## Contents

- [Requirements and target identity](#requirements-and-target-identity)
- [Work across CS2 updates](#work-across-cs2-updates)
- [Prepare a source package](#prepare-a-source-package)
- [Run the standalone helper](#run-the-standalone-helper)
- [Operational budgets and failure reporting](#operational-budgets-and-failure-reporting)
- [Optional readback text capture](#optional-readback-text-capture)
- [Direct native procedure and limitations](#direct-native-procedure-and-limitations)
- [Verify the helper itself](#verify-the-helper-itself)

## Requirements and target identity

Use Python **3.10 or newer**, its standard library, Windows, and an installed
CS2 Workshop Tools compiler. Compilation does not require opening the game.
Use the actual installation supplied by the operator; do not guess a Steam
library or reuse another Source 2 game's tools.

Expected paths below are relative to that CS2 installation:

- `game/bin/win64/resourcecompiler.exe`
- `game/csgo/gameinfo.gi` and `game/csgo/steam.inf`
- `content/csgo_addons` and `game/csgo_addons`

The helper checks `steam.inf` for `appID=730` and `ProductName=cs2`, a
`GameInfo` root, the fixed compiler path and its Windows `MZ` header. It records
the compiler SHA-256, available `resourcecompiler.dll`, `particles.dll`, and
`resourcesystem.dll` fingerprints, patch/date/SourceRevision fields and the
Steam build ID when the adjacent `appmanifest_730.acf` is available.

These checks identify the selected installation; they are not a publisher
signature verification. `--expect-compiler-sha256` can pin a fingerprint
already obtained from a trusted installed compiler. The report explicitly
leaves Authenticode **not checked**. Never take a known hash from a different
build as a universal expected hash.

Inspect the installed compiler's help for unfamiliar options, a changed
interface, or an invocation failure. The tested
flags are `-i`, `-game`, `-nop4`, and `-fshallow`. Preserve the exact version and
flags in the run evidence. This helper targets **CS2**, not Deadlock: another
game requires its own gameinfo, addon layout, compiler and validation run.

## Work across CS2 updates

Build/revision numbers and binary hashes identify an observation. A changed
build ID alone neither invalidates editable particle sources nor proves
their continued compatibility. Keep established authoring contracts and
use the installed target tools. Recompile modified sources; investigate
only relevant field/provider, shader, dependency, tool-interface or observed
behavior changes. An existing effect that still loads and behaves correctly
does not need all probes repeated solely because Steam updated.

If a relevant regression appears, compare the affected source/resource and
run a focused compiler, readback or PET/game check. Refresh only the needed
reference evidence. An unsupported inspector format is a decoder limitation,
not by itself an engine incompatibility. Keep editable sources available
when compiled resources need regeneration. Do not pin the compiler hash
unless the task explicitly needs exact historical reproduction.

## Prepare a source package

Keep resource-relative paths under one directory, for example:

```text
source/
  materials/fx/example/soft.tga
  materials/fx/example/soft.vtex
  particles/fx/example/root.vpcf
  particles/fx/example/core.vpcf
```

Pass `source/` as `--source-root`. For a package with a dedicated `source/`
subdirectory, do not pass its parent containing unrelated files. The helper
also tolerates `.md`, `.json`, and `.txt` sidecars, reports them as ignored,
and does not stage them. Asset filenames must use relative resource-safe paths.
The supported staged extensions include VPCF, VTEX, VMAT, VMDL, MKS, common
image formats, and common model-source formats; see `STAGED_EXTENSIONS` in the
helper for the exact list. An unsupported extension fails before staging.

Include all newly authored child `.vpcf` files and owned texture/model inputs.
Do not rely on a base-game resource with the same path to supply a missing
child. The helper conservatively scans literal VPCF resource/child references
and refuses missing particle sources unless `--allow-external-particles` was
explicitly requested. That exception permits installed-game resolution; it
does not validate the external child or prevent dependent rebuilds.

The literal scan is a precheck, not a full KV3 parser, dependency resolver or
native-class whitelist. It can be conservative about comments or unusual
string syntax. Keep valid authored features; if a legitimate source cannot
pass that precheck, inspect it and use the direct native procedure below with
the same path/staging safeguards. Do not remove a feature merely to satisfy
the precheck.

## Run the standalone helper

In PowerShell, replace the four values with explicit absolute directories:

```powershell
$skill = '<absolute source2-particle-validation directory>'
$cs2 = '<absolute CS2 installation root>'
$sources = '<absolute source asset directory>'
$work = '<absolute separate native-work directory>'

python -I "$skill/scripts/compile_native.py" `
  --cs2-root "$cs2" --source-root "$sources" --work-root "$work" `
  --effect-root 'particles/fx/example/root.vpcf' --plan

python -I "$skill/scripts/compile_native.py" `
  --cs2-root "$cs2" --source-root "$sources" --work-root "$work" `
  --effect-root 'particles/fx/example/root.vpcf'
```

`--plan` inventories and fingerprints files without creating a run directory
or launching a process. The execution command creates:

- A new UUID addon named `s2_particle_validation_<uuid>` under the installation's
  `content/csgo_addons` and `game/csgo_addons` parents.
- A new `<work>/<uuid>/` with bounded process logs and `report.json`.

Existing addon or report destinations are refused. Source files are copied
with exclusive creation; original hashes are checked again after compilation.
All existing path ancestors are checked for symbolic links, junctions,
reparse points and redirected realpaths. Work logs must be outside the CS2
installation and separate from the source tree. No automatic cleanup runs.

Default compilation selects every `.vtex`, `.vmat`, `.vmdl`, then `.vpcf` in
that order. This produces texture inputs before dependent materials/particles.
MKS/TGA/mesh inputs are staged but compiled through their owning native
resource. Every selected top-level input is forced individually with
`-fshallow`, including helper particle systems not reachable from the root.

Use repeatable `--input <relative/path>` only when intentionally checking a
subset. Such a report certifies the listed `selectedInputs`, not every asset
in the folder. A supplied `--effect-root` must be among the selected inputs.
Omit `--effect-root` for a texture-only pass.

## Operational budgets and failure reporting

Defaults are 128 staged asset files, 64 MiB total source bytes, 128 MiB
aggregate compiled output, 64 KiB retained combined output per process,
45 seconds per process and 180 seconds for compilation plus optional readback.
These are operational limits, not CS2 format limits. Adjust the explicit
`--max-*`, `--timeout`, and `--total-timeout` options for the actual package.
The compiled-byte budget audits the entire fresh game-addon tree after each
compiler call, including unselected dependency outputs there. It does not
measure or confine writes elsewhere in the installation. A bounded file-count
audit also rejects unexpectedly large output trees.

The helper launches a fixed installed executable with an argument array,
`shell=False`, no interactive stdin and a hidden Windows process window. It
drains stdout/stderr while bounding retained bytes and terminates the compiler
process on timeout. It does not claim process-tree or operating-system
isolation. Truncation and incomplete capture are recorded.

Exit status **0** means all selected native compilations produced fresh
regular outputs within their budgets. Exit **1** means the attempted native
pass failed; inspect its report and logs. Exit **2** means preflight/configuration
failed. A failure after staging retains its new addon and partial report so
the cause can be diagnosed. A preflight failure does not stage files.

The report contains resource-relative inventory paths, original/compiled
SHA-256, game/compiler identity, actual logical argv, process statuses, output
sizes and freshness, ignored sidecars, and independent validation states.
The stdout summary provides the local report location. Raw log files can
contain absolute local paths from the native tool; review/redact those before
sharing them. The portable report replaces configured roots in errors with
markers. A hash identifies one binary from one run; native metadata can make
binary hashes differ across new addon paths even with identical source bytes.

## Optional readback text capture

When an installed Source 2 Viewer CLI is available and its `--help` confirms
the flags, append `--viewer-cli '<absolute CLI executable>'`. After native
compilation, the helper invokes `-i <compiled> --block DATA`, captures text
under `logs/readback-*.txt`, and records the viewer fingerprint and status.
It does not download a viewer or assume a JSON-output option.

`text-captured` means text was obtained, not that a property comparison passed.
An exit-zero viewer with no non-whitespace output is reported as `empty`;
check its invocation and the available resource blocks before interpreting it.
Property retention remains unverified until the owning nodes and controlled
values are inspected. Truncated text cannot establish that a field is absent.
See [compiled-readback.md](compiled-readback.md) for complete steps and the GUI
alternative. Keep native compile status separate when the viewer fails.

## Direct native procedure and limitations

The helper deliberately creates fresh audit addons. For iteration in an
existing user-authorized addon, use its own namespace and direct compiler
invocation; a new addon is not required for each artistic adjustment.
Identify the edited inputs/dependencies, preserve unrelated files, and
verify fresh outputs for the changed resources.

With verified absolute paths, a direct PowerShell invocation is:

```powershell
$compilerArgs = @(
  '-i', $authoredResource,
  '-game', $gameCsgoDirectory,
  '-nop4',
  '-fshallow'
)
$nativeOutput = @(& $resourceCompiler @compilerArgs 2>&1)
$nativeExitCode = $LASTEXITCODE
$nativeOutput | Set-Content -LiteralPath $runLog -Encoding utf8
```

Apply containment, reparse checks, bounded execution and freshness/hash
verification. Use exclusive creation for new audit destinations; deliberate
replacement of owned iteration files does not require an empty addon. Keep paths compact:
long Steam addon paths can cause misleading texture/resource errors. If a
resource must be renamed, update its references and manifest deliberately.

`-nop4` disables automatic Perforce activity. The installed help describes
`-fshallow` as forcing top-level resources while compiling children/associates
as needed. A fresh addon is therefore **not a filesystem sandbox**. The helper
does not pass `-skiptype`: textures are intentionally compiled in a full pass.
That optional native filter is not a proven write-isolation boundary either;
see [observed-evidence.md](observed-evidence.md). If strict filesystem isolation
is required, use an appropriately isolated installation/environment.

No game/PET launch, launch-option edit or Workshop publication is performed.
Native exit 0 plus fresh binaries establishes compiler acceptance. It does
not establish resource closure, field retention, CP equations, live updates,
appearance or in-game delivery. Continue with readback and native observation.

## Verify the helper itself

Its tests use an injected fake runner and temporary test-owned files; they
need neither a game installation nor third-party Python packages:

```powershell
python -B -I -m unittest discover `
  -s "$skill/scripts" -p 'test_*.py' -v
```

The tests cover staging order, hashes/logs, refusal to overwrite, invalid paths
and child references, CS2 identity/pinning, budgets, failure/timeout/stale
outputs, optional readback capture including empty output, and process-output bounds. An OS account
that cannot create directory symlinks may skip the real-link test; the Windows
reparse-attribute guard is still tested separately. Synthetic outputs are not
native-fidelity evidence.
