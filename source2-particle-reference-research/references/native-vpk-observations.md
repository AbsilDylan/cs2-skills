# Compiled particle observations: CS2 and Deadlock

This is a factual inventory of installed VPK contents observed on **2026-10-15**. Use it to find real class/property spellings and short witnesses. It does **not** establish property meaning, runtime behavior, defaults, supported ranges, native appearance, or compatibility between games.

Start with [the inventory index](native-vpk-observations.json), then load the single class file named in `games[].classFiles`. Avoid reading all class files into the model context. For example, sprite renderer observations are [CS2](observations/cs2/m_renderers-c_op_rendersprites.json) and [Deadlock](observations/deadlock/m_renderers-c_op_rendersprites.json).

## Contents

- [Coverage](#coverage)
- [Interpret the files correctly](#interpret-the-files-correctly)
- [Binary decoding and runtime projection are separate stages](#binary-decoding-and-runtime-projection-are-separate-stages)
- [Provenance](#provenance)
- [October 20 review and metadata correction](#october-20-review-and-metadata-correction)
- [Independent reproduction with the bundled tools](#independent-reproduction-with-the-bundled-tools)

## Coverage

| Local installation | Steam app/build metadata | Indexed VPCF_C | Resource2 + binary KV3 decoded | Distinct classes, including system root | Class-local property paths |
|---|---|---:|---:|---:|---:|
| CS2 | 730 / 25640462 | 2,622 | 2,622 | 199 | 26,306 |
| Deadlock | 1422450 / 25660886 | 16,310 | 16,310 | 228 | 31,807 |

All VPCF_C entries in each index were examined, including files outside `particles/`. This is an exhaustive inventory of these two indexes, not an inventory of every mounted game package. The scan read **8,634,396 bytes** of CS2 particle payloads and **57,888,127 bytes** of Deadlock particle payloads. Each reconstructed entry passed its VPK CRC32. No Resource2 or binary KV3 DATA decoding error occurred. Each VPK index retained one `trailing-data` warning for an opaque suffix; this was not treated as a payload decoding error.

The union contains **254 distinct class names**. There are **55 names observed only in the Deadlock corpus** and **26 observed only in the CS2 corpus**. These are observations of assets shipped in the selected packages. They do not prove that an unobserved class is absent from either engine. Exact lists are in `summary.observedOnlyDeadlockClasses` and `summary.observedOnlyCs2Classes`.

## Interpret the files correctly

- Every class JSON contains `classObservation.class`, `stage`, instance count, bounded witness paths, and `fields`.
- Field paths are local to the nearest object with `_class`; array indexes collapse to `[]`. The root system is recorded as `system:CParticleSystemDefinition`. Nested provider structures remain under their owning class.
- `occurrences` counts explicitly stored field occurrences. `kinds` records the binary KV3 IR kinds encountered. It is not the complete declared type contract.
- `examples` contains at most **one short observed value**. The field's `witness` identifies the resource containing that example, or a field-presence witness when there is no scalar example. The index's `games[].witnesses` supplies its payload byte size, SHA-256 and VPK CRC32.
- Numeric extrema are unavailable. The historical exporter omitted integer scalar representations from `observedMin` and `observedMax`; these incomplete statistics were removed in the [October 20 metadata correction](observation-correction-2026-10-20.json). Short examples cannot reconstruct the missing extrema. Examples and frequencies are **not valid-input limits**, defaults, recommended values, or runtime clamps.
- A field absent from an asset can be defaulted, stripped, conditionally unused, or unsupported. Presence alone does not show that the runtime uses it.
- `resourceReferences` combines direct binary KV3 resource values and RERL reference names. Counts can include the same reference through both representations. The recorded top paths are bounded examples, not a complete dependency graph.

The corpus shows direct `m_vecTexturesInput[].m_hTexture` references on `C_OP_RenderSprites` and `C_OP_RenderTrails`. Therefore a new sprite effect does not automatically require a VMAT. Choose the dependency format required by the target renderer and build, and validate the resulting texture or material natively.

Deadlock assets additionally demonstrate names such as `C_OP_RenderBlobs`, `C_OP_RenderLightBeam`, `C_OP_RenderStatusEffectCitadel`, `C_INIT_StatusEffectCitadel`, and `C_OP_SetControlPointFieldToScalarExpression`. Treat these as research leads for that game. Do not copy them into a CS2 effect and claim support without inspecting the CS2 schema and performing native validation.

## Binary decoding and runtime projection are separate stages

One Deadlock resource, `particles/npc/neutrals/neutral_mushroom/neutral_attack_spore_warmup.vpcf_c`, stores **four NaN scalars** under `m_controlPointConfigurations[].m_drivers[].m_vecOffset[]`. Binary KV3 IR decoding preserves these values. They appear in `coverage.nonFiniteExamples`; non-finite scalar examples use a `$nonFinite` tag so JSON never silently converts them into `null`.

A separate typed CP inspection rejected these four values, recording **16,309 accepted definitions plus one projection failure**. This is consistent with this inventory's **16,310 decoded binary documents**. Neither count proves that the original asset works correctly in-game. Do not normalize NaN to zero or reuse this asset as a known-good CP template.

## Provenance

The index labels the SHA-256 domains separately:

| Package | Entire `_dir.vpk` SHA-256 | Header + tree SHA-256 |
|---|---|---|
| CS2 `csgo/pak01_dir.vpk` | `fac8ff988ab9a20c3175c33fd4c5196da3798a0ddcea9fe0a5565ab33cffb5a9` | `0211aadcf8875d4fb9d548aaf2556a30590687a9dcda76e7c0a75292c9d3c0d7` |
| Deadlock `citadel/pak01_dir.vpk` | `cc77bd7b65752d6d206e623be0db0b31508613b1752f3d2dd1e345077737b48c` | `a205cd25bd124bf810a501d2bc5663a7246a7547f1a445bc07d6e6d3b5769d2d` |

Archive chunks were read by bounded ranges, not fully hashed. The report also records an aggregate SHA-256 of the ordered `(resource path, payload bytes, payload SHA-256)` tuples. Steam app/build IDs come from local `appmanifest_*.acf` files; the report hashes those files but does not cryptographically bind their metadata to Valve's VPK content. These are installed builds, not a claim about the latest available releases.

No Valve asset payload, decompiled complete particle source, absolute installation path, texture pixels, or game binary is included here. Reference names, class/property names, short values and hashes are factual evidence metadata.

## October 20 review and metadata correction

The review verified the size and SHA-256 of all **427** indexed class files and their identity, stage, field counts and witness links. It found a real aggregation error: the historical exporter accumulated extrema only from JavaScript `number` values while binary KV3 integer encodings could produce `bigint` values. **400** field examples lay outside their reported extrema. For example, `C_OP_ContinuousEmitter.m_flEmitRate.m_nControlPoint` showed a stored `0` but reported a minimum of `2`; an independent VRF inspection of the hash-matching original confirmed `0`.

[The review evidence](observation-review-2026-10-20.json) records the checks, hashes, changed witness identities and limits. The independent witness inspection used VRF **20.0.6980** and passed the bundled helper's help/version checks. The corrected portable helpers pass **48 tests** in an isolated skill copy with Python `-E -S -B`.

The correction removes `observedMin` and `observedMax` from **30,592** field records across **408** class files. Every other byte of each class record is preserved. The index retains its original observation date, historical generator identity and game/payload identities, and adds a separately dated correction with the prior index hash and all prior class-file hashes. This does not claim that the original generator produced the corrected bytes. The full historical Deadlock payload set is no longer available locally, so replacement extrema were not guessed from the surviving examples.

A fresh native-payload check verified **57,962 of 58,113** field witnesses against CRC-checked, SHA-identical original resources: all **26,306 CS2** fields and **31,656 Deadlock** fields. Their exact field paths, decoded kinds and short examples match. Five Deadlock witness resources changed after the historical scan; **151** field witnesses depend on four of those resources and remain unverified by the new check. This establishes stored-field evidence, not property semantics.

CS2's installed build had changed to **25966348**, but all **2,622** particle payloads still produced the historical ordered payload-manifest hash. Reaggregating them reproduced all **199** historical class records exactly, including the flawed numeric statistics subsequently withdrawn. The VPK index itself had changed. Build IDs therefore identify evidence snapshots rather than impose a runtime compatibility gate.

Run `python scripts/audit_observations.py` for the standalone metadata check. The query helper also suppresses the known incomplete extrema when an older `--references` snapshot identifies the same historical exporter.

## Independent reproduction with the bundled tools

This skill is self-contained. Reading its catalog requires only Python 3.10+ standard library. Inspecting installed compiled particles additionally uses an explicitly selected, already installed [Source2Viewer-CLI/ValveResourceFormat](https://github.com/ValveResourceFormat/ValveResourceFormat). The scripts and observation files needed by these workflows ship with the skill.

The checked-in index and 427 class files are a historical binary-IR observation snapshot. `method.scriptSha256` identifies that historical generating method; the original script is not a runtime dependency of this skill. The independently implemented tools below verify archive identities, retrieve exact witnesses and inspect DATA through VRF. Their text output and evidence schema differ from the historical binary-IR aggregate. Do not claim that this method reproduces the old report hashes, occurrence counts or KV3 IR kind distinctions byte for byte.

From this skill's directory, first inventory without extraction:

```text
python scripts/vpk_reference.py inventory --vpk "CS2/game/csgo/pak01_dir.vpk" --extension vpcf_c --limit 0
python scripts/vpk_reference.py inventory --vpk "Deadlock/game/citadel/pak01_dir.vpk" --extension vpcf_c --limit 0
```

Compare `directoryIndexSha256` with the header/tree hashes above. The inventory's entry CRC is declared, not verified. Inspect selected witnesses with the bundled orchestrator; replace tool and installation placeholders with explicit local paths:

```text
python scripts/inspect_vpk_with_vrf.py --vpk "CS2/game/csgo/pak01_dir.vpk" --vrf "TOOLS/Source2Viewer-CLI.exe" --game cs2 --manifest "steamapps/appmanifest_730.acf" --entry particles/ambient/ambient_water_stream.vpcf_c --output "WORK/new-cs2-inspection"
python scripts/inspect_vpk_with_vrf.py --vpk "Deadlock/game/citadel/pak01_dir.vpk" --vrf "TOOLS/Source2Viewer-CLI.exe" --game deadlock --manifest "steamapps/appmanifest_1422450.acf" --entry materials/dev/steam_test.vpcf_c --output "WORK/new-deadlock-inspection"
```

The output directory must be new, its parent must exist, and it must be outside the archive directory. The helper probes the selected CLI's `--help` and `--version`, checks that its help advertises `--input` and `--block`, and records tool hashes and version. It then invokes the tool with an argument array, without a shell:

```text
Source2Viewer-CLI --input LOCAL_TEMPORARY_PARTICLE.vpcf_c --block DATA
```

These flags were checked and executed with VRF `19.2.0+f86ea981fc37b9f8f23c4eb84e058de2083b6761`. Another version must pass the same help/format checks. A `.dll` CLI distribution is accepted via the installed `dotnet` host. The helper does not install or download either tool. Manual inspection remains possible with the [official CLI guide](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md).

Each selected VPK payload passes CRC32, then is temporarily staged and deleted after inspection. `inspection.json` records the original path, byte size, payload SHA-256, CRC, detected `vpcfNN` format, process outcome and DATA transcript path/hash. `data/*.vrf-data.txt` preserves the CLI's exact output, including its summary; this is **not a standalone KV3 file**. Inspect the KV3 document after its header, and do not infer field meaning from its name. Failed/unsupported formats and tool errors remain explicit records. Original payloads are not retained. Transcripts are local research material and must not be added to a distributable skill as replacement game assets.

For an exhaustive scan of one specified VPK index, replace the selected entries with:

```text
python scripts/inspect_vpk_with_vrf.py --vpk "GAME/pak01_dir.vpk" --vrf "TOOLS/Source2Viewer-CLI.exe" --game GAME_LABEL --all-particles --max-files 20000 --output "WORK/new-full-inspection"
```

Default selection is capped at 64 files; a full scan explicitly raises it. Hard limits are 20,000 particle entries, 16 MiB per payload, 512 MiB cumulative payload budget including failed reads, 16 MiB stdout and 1 MiB stderr per invocation, and 30 seconds per invocation by default (adjustable 1..60). Cumulative transcripts and diagnostics default to 512 MiB and can be raised to at most 2 GiB with `--max-total-text-bytes`. The JSON report is capped at 32 MiB. The directory reader itself retains its bounded VPK v1/v2 index checks.

Read `coverage.matching`, `selected`, `attempted`, `decoded`, `failed`, `selectionTruncated` and `complete`. Exit 0 means the requested selection was completely inspected; exit 2 means a cap, failure or incomplete scan. Exit 1 is a configuration/process setup error. A scan capped below the index's particle count is never exhaustive, even if every selected file decoded. The new helper was verified on the two single-particle examples above, not rerun across all 18,932 resources. The historical coverage table continues to describe the historical complete binary-IR scan.

The subprocess deadline includes output-pipe drainage. Windows subprocesses enter a kill-on-close Job Object before they start; Unix subprocesses use a dedicated session and require `waitid/WNOWAIT` for safe group cleanup. Cleanup is limited to one additional second. Windows execution, inherited-pipe cleanup and output/timeout bounds were tested; the Unix branch was reviewed statically and has not been executed here.

[The standalone validation evidence](standalone-vrf-validation-2026-10-15.json) records final helper hashes, VRF identity, the two witness hashes and the 39-test result. Checks ran from an isolated copy of this skill with Python `-E -S`, disabling environment-based Python paths and site packages. Raw DATA transcripts and game payloads are excluded from that evidence file.

To compare a new snapshot with this catalog, use `query_observations.py` to select the exact class and field, retrieve its witness, verify the same payload hash, then compare the observed field/type/value in that witness's VRF DATA text. Record a changed build or changed hash as a new observation. Do not overwrite old evidence or promote Deadlock observations to CS2 support.
