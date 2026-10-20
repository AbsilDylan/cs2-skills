# Compiled property readback

## Contents

- [Preserve the input and identify the decoder](#preserve-the-input-and-identify-the-decoder)
- [Optional Source 2 Viewer / ValveResourceFormat path](#optional-source-2-viewer-valveresourceformat-path)
- [Read the owning node, not a matching word](#read-the-owning-node-not-a-matching-word)
- [Distinguish retention, normalization, and omission](#distinguish-retention-normalization-and-omission)
- [Check references and report the boundary](#check-references-and-report-the-boundary)

Use readback to answer a narrow question: **what did this compiler serialize
into these exact bytes?** It does not establish how particles move, when a
provider is sampled, or how a renderer looks. Pair it with
[visual/runtime validation](visual-validation.md) for those claims.

## Preserve the input and identify the decoder

1. Complete [native compilation](native-compilation.md), or identify the
   already compiled resource being inspected. Preserve the original authored
   sources and the unmodified `.vpcf_c`; do not overwrite either with an export.
2. Record the target game, installed build/revision, source digest, compiled
   SHA-256, compiled byte count, and the command/log that produced the binary.
   An extracted shipped binary has no authored-source provenance unless it was
   separately established; label it as an extracted reference.
3. Use a decoder supporting the resource container and binary KV3 version in
   that file. Record its version or commit and diagnostics. A decoder failure
   is a decoder result, separate from compiler acceptance.

CS2 and Deadlock are separate targets. Keep their compiled resources, compiler
identities, schemas, and reports separate. A Deadlock decoder success or field
name is a useful investigation lead; it does not certify CS2 support or a
compatible source shape. Do not relabel one game's output as the other's.

## Optional Source 2 Viewer / ValveResourceFormat path

Source 2 Viewer is a third-party resource inspector; its command-line utility
is named `Source2Viewer-CLI`. It is optional. Another decoder is acceptable if
it exposes the needed values and preserves diagnostics.

First inspect the executable actually available:

```powershell
$viewer = 'C:\Tools\Source2Viewer-CLI.exe'  # replace with the actual executable
& $viewer --help
$helpExit = $LASTEXITCODE
```

Save that help output with the evidence. The upstream
[CLI guide](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md)
documents `--input`, `--block`, `--all`, `--output`, `--vpk_decompile`,
`--version`, and `--help`, but explicitly does not guarantee argument stability.
Use only flags confirmed by the installed release's help. Older executable
names or arguments must be discovered, not guessed. If help cannot be obtained,
use the GUI or another verified decoder and record the limitation.

The optional [native helper](../scripts/compile_native.py) accepts an explicit
`--viewer-cli` path. Confirm that executable's `-i` alias and `--block` syntax
before opting in. It captures bounded `DATA` text in `logs/readback-NNN.txt`;
`text-captured` and `propertyRetention: manual-inspection-required` mean that
the text still needs the controlled inspection below. They are not a property
retention pass. `empty` means the viewer returned zero but captured no usable
text; it does not establish an absent field or empty resource.
Check truncation, timeout, and decoder diagnostics before
interpreting missing fields; an incomplete dump cannot prove omission.

After confirming `--input` and `--block`, use a fresh evidence directory. The
following PowerShell example prints text; it does not request JSON:

```powershell
$compiled = 'C:\Validation\input\particles\example.vpcf_c'
$evidence = 'C:\Validation\evidence\readback-001'
if (Test-Path -LiteralPath $evidence) { throw 'Use a fresh evidence directory.' }
New-Item -ItemType Directory -Path $evidence -ErrorAction Stop | Out-Null
Get-FileHash -LiteralPath $compiled -Algorithm SHA256 |
    Format-List | Out-File -LiteralPath (Join-Path $evidence 'input-sha256.txt')

& $viewer --input $compiled `
    1> (Join-Path $evidence 'resource-summary.txt') `
    2> (Join-Path $evidence 'resource-summary.stderr.txt')
$summaryExit = $LASTEXITCODE

& $viewer --input $compiled --block DATA `
    1> (Join-Path $evidence 'DATA.txt') `
    2> (Join-Path $evidence 'DATA.stderr.txt')
$dataExit = $LASTEXITCODE

"summary=$summaryExit`ndata=$dataExit" |
    Set-Content -LiteralPath (Join-Path $evidence 'exit-codes.txt')
```

Inspect both exit codes, both error files, and the data output. Nonempty output
alone is not success: a summary, exception, partial tree, or unsupported-block
message is not the requested property readback. Bound long runs and retain any
partial output and timeout diagnostic.

If the resource summary shows dependency/edit-info blocks, inspect those
blocks using `--block` with their actual names. `RERL`, `REDI`, and `RED2` are
possible block names, not a promise that every resource contains all three.
If `--all` is confirmed, it can print every block for diagnosis; retain the
full result locally and extract only relevant paths into the report. Do not
assume the text is JSON, invent a JSON-export switch, or parse it as JSON
without an explicitly supported format.

If editable export is needed, first confirm `--output` and `--vpk_decompile`
in that release's help and write to a fresh destination. Keep the export apart
from block dumps and the original binary. Decompiled editable text is a
conversion, not a byte-for-byte copy of the compiled file.

For a GUI-only workflow, open the `.vpcf_c` in Source 2 Viewer using its actual
file-open interface. Inspect the available resource/block views and save or
copy the relevant text with decoder/version details. If reading from a VPK,
use **Export as is** to preserve the original compiled bytes before readback;
**Decompile & export** is the separate editable conversion. These workflows
are described in the upstream
[getting-started guide](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/getting-started.md).
Do not infer a feature from a screenshot of another release's UI.

## Read the owning node, not a matching word

Build a small assertion table before comparing source and readback:

| Assertion | Record explicitly |
| --- | --- |
| Identity | Source resource path, owning class, stage, and stable distinguishing values |
| Property | Exact source key and decoded path, type, enum token or numeric representation |
| Provider | Literal or provider object, provider class, endpoints and units where known |
| CP reference | Authored CP index, owning initializer/operator/renderer, and any parent/remap |
| Resource reference | Typed reference and resource path, including child systems |

Inspect emitters, initializers, operators, pre-emission operators, renderers,
and children at their owning nodes. A similarly named root field does not
prove a component property. A scalar literal and a typed provider are not
interchangeable merely because a text parser accepts both. Preserve the
difference between an absent key, zero, false, an empty array, a null reference,
and an empty provider.

Compare components by class, stage, and controlled identity. Array positions
can change during compilation; an array-index-only comparison can pair the
wrong components. Record generated or normalized values without silently
replacing the authored source.

For texture or material investigations, inspect the corresponding compiled
resource as well. Record image dimensions, format, alpha, sheet/sequence
metadata, material shader and bound texture references as exposed by that
decoder. Verify the meaning and units of each label before interpreting it:
a field named like a rate may represent a duration in another view. Image
readback still cannot prove native playback or blending.

## Distinguish retention, normalization, and omission

Use an isolated diagnostic copy and change one relevant input at a time:

1. Compile a valid baseline and retain its source, logs, binary, and readback.
2. Set one controlled nondefault value. Choose values that are easy to locate
   and valid for the native type; for a min/max provider, keep the interval
   ordered. Compile to fresh output and inspect the owning node.
3. Repeat with a second distinct valid value. Compare the relevant tree and
   source digests, not only the binary digest. Binary differences can arise
   from unrelated metadata; unchanged binaries can expose a stale-output error.
4. For an absent field, test explicit default and nondefault values, then an
   omitted-field baseline where meaningful. Inspect the current target's
   editor/schema evidence before assigning default semantics.
5. Check interaction controls when relevant: stage placement, enabled/disabled
   component, provider type, enum selection, CP index and renderer mode.
   Recompile after each change instead of combining unrelated hypotheses.

Use these result terms narrowly:

| Result | Required observation |
| --- | --- |
| Retained | Controlled value and type are found at the correct decoded node. |
| Normalized | A repeatable compiler transformation maps controlled source values to a documented decoded representation. |
| Default-elided | Nondefault controls are retained; explicit default and omission produce equivalent relevant readback, supported by current-build default evidence. |
| Not observed / unresolved | The field is absent, the decoder is incomplete, the output may be stale, or probes do not distinguish competing explanations. |
| Silently dropped in this probe | Valid fresh runs accept distinct controlled inputs but omit the field, and owning-node/default/normalization checks rule out the alternatives being claimed. |

Do not call every absent key unsupported. If a deliberate unknown sentinel is
used to calibrate compiler strictness, put it only in a disposable diagnostic
fixture. Acceptance plus disappearance proves that fixture's field was
discarded; it does not prove all unknown fields or all native features behave
the same way. Remove the sentinel from deliverable effects.

## Check references and report the boundary

Compare the authored child graph with retained child references, including
enabled state and timing fields where present. Inventory external materials,
textures, models, and their transitive dependencies separately. A reference
present in `DATA` or a dependency block proves serialization, not that the
resource exists, resolves to the intended file, or is included in a distributable
addon. A package listing likewise does not prove successful runtime loading.

Deliver a short readback report with relative asset/evidence paths:

- Game/build, source and binary digests, decoder identity, commands and exits.
- Assertion table with source value, decoded value/path, result term, and
  relevant warning or ambiguity.
- Child/reference inventory and unresolved dependency checks.
- Links to raw block dumps and diagnostics; keep large trees in the evidence
  directory rather than copying them into the report.

If the decoder is missing, incompatible, crashes, or cannot expose the needed
block, mark **readback unavailable** or **inconclusive** and preserve the error.
Complete independent compilation checks. State “compiled; property retention
unverified” when that is the available evidence. Neither successful decoding
nor retained CP indices certify equations, attachment mapping, coordinate
conventions, update order, or visual appearance.
