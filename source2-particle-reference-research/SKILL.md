---
name: source2-particle-reference-research
description: "Research native particle, material and texture examples in local CS2 or Deadlock VPKs using bounded extraction, provenance and offline observations."
---

# Research Source 2 references

Turn local resources into verifiable facts useful for writing new particles. A resource observed in Deadlock is a lead for CS2; its presence proves neither that the class exists in CS2 nor that it has the same properties or default values there.

## Consult the bundled observations

Read [the coverage and limits of the CS2/Deadlock observations](references/native-vpk-observations.md), then query only the relevant class with the portable helper. It requires no installed game, Node, or network connection:

```text
python scripts/query_observations.py --game cs2 --search Render --limit 20
python scripts/query_observations.py --game cs2 --class C_OP_RenderSprites --stage m_Renderers
python scripts/query_observations.py --game cs2 --class C_OP_RenderSprites --field "m_vecTexturesInput[].m_hTexture"
python scripts/query_observations.py --game deadlock --class C_OP_RenderLightBeam --stage m_Renderers
```

`--search` searches the class/stage names in the index, without reading every record or searching their fields. By default, `--class` returns a summary and at most `--limit` field names, rather than their thousands of values. `--field` selects an exact path, with `[]` for arrays, and returns its supporting example with the payload hash. Every record read is checked against its size and SHA-256 declared in the index. A local snapshot can be selected explicitly with `--references`. Reads are limited to 4 MiB per file and JSON output to 128 KiB; if the output is too large, request a specific field or reduce `--limit`.

The historical numeric minima and maxima were withdrawn after a review found that the exporter excluded integer scalar representations. Query output records this correction and also suppresses those statistics when reading an older snapshot from that exporter. Retained examples and frequencies describe stored observations; they do not define allowed values, defaults or recommended settings.

The bundled records contain observations, not every property declared by the engine. Use the local VPK search below to fill in a missing case, then cross-check the result against the target game's schema.

## Find and select

Start with the target game, its build, and the VPK path supplied or discovered in a local installation. Read the archives in place; write extractions to an explicit new working directory. Do not assume that an already decompiled corpus is up to date.

The included helper requires Python 3.10+ with no dependencies. From this skill directory:

```text
python scripts/vpk_reference.py inventory --vpk "PATH/pak01_dir.vpk" --extension vpcf_c --limit 20
python scripts/vpk_reference.py inventory --vpk "PATH/pak01_dir.vpk" --extension vpcf_c --prefix particles/ --limit 100
python scripts/vpk_reference.py inventory --vpk "PATH/pak01_dir.vpk" --extension vpcf_c --contains smoke --limit 20
python scripts/vpk_reference.py inventory --vpk "PATH/pak01_dir.vpk" --extension vmat_c --extension vtex_c --prefix materials/particle/ --limit 20
```

The inventory counts all extensions in the VPK, then applies the filters to the list. `--contains` searches for a literal path fragment without regex. `--limit 0` produces only counts and provenance. At this stage, CRC32 values are declared by the index, without payload verification; a filename identifies a candidate, not its actual appearance. Do not routinely restrict particles to the `particles/` directory: both games studied also have `.vpcf_c` files elsewhere.

Choose a few effects that match the visual need, then follow their children, textures, materials, models, and other referenced resources. For an exhaustive search, retain aggregates and errors per file instead of loading every resource into context.

## Extract and inspect

```text
python scripts/vpk_reference.py extract --vpk "PATH/pak01_dir.vpk" --entry particles/example.vpcf_c --output "WORK/new-extraction"
```

Repeat `--entry` to select multiple exact paths from the inventory. The parent directory must exist; the output directory must be new. Extraction combines preload and data, verifies CRC32, and produces `vpk-reference-manifest.json` with a SHA-256 for each resource. Limits: 64 MiB index, one million entries, 4096-byte strings; extraction of 64 files, 64 MiB per file, 256 MiB total. This script does not execute, download, or decompile any VPK content. It does not verify VPK signatures or MD5 sections.

The `*_c` files are compiled. Use an **already installed Source2Viewer-CLI/ValveResourceFormat**, compatible with their version. Check its help and version first; interfaces change:

```text
Source2Viewer-CLI --help
Source2Viewer-CLI --version
Source2Viewer-CLI --input "WORK/new-extraction/particles/example.vpcf_c" --block DATA
```

The last command was verified with VRF 19.2.0. Its result also contains the summary and external references: do not treat all of its output as raw KV3. To produce a source file or resolve dependencies, follow the help for **the installed version** and keep all outputs in the working directory. A copy extracted outside the game may lose dependency resolution; do not interpret this as absence from the VPK. See the [official VRF guide](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md).

For reproducible research, the standalone helper `scripts/inspect_vpk_with_vrf.py` performs these checks, reads payloads with CRC32 verification, and produces a local snapshot of DATA transcriptions, hashes, formats, and coverage. It requires only this skill's scripts, the Python standard library, and an already installed VRF:

```text
python scripts/inspect_vpk_with_vrf.py --vpk "PATH/pak01_dir.vpk" --vrf "TOOLS/Source2Viewer-CLI.exe" --game cs2 --entry particles/example.vpcf_c --output "WORK/new-inspection"
```

To select all particles in an index, use `--all-particles --max-files 20000` in place of `--entry`. Cumulative limits and errors remain explicit; only `coverage.complete = true` confirms that the entire requested selection has been inspected. Exit code 2 indicates incomplete coverage. Read [the standalone procedure and its limits](references/native-vpk-observations.md#independent-reproduction-with-the-bundled-tools) before a full scan. This independent VRF method provides new textual evidence; it does not exactly recreate the historical aggregates obtained through binary decoding.

## Turn observations into knowledge

For a candidate found only in the index, retain the game/build, path, index hash, and declared but unverified CRC. For a resource actually read, add the payload SHA-256 and CRC check; for an inspected property, also record the decoder/version, class and stage, exact property path, observed type, context, and limits. Distinguish between:

- **observed in a resource**: the name, type, and value present in that file;
- **declared by the schema**: the type, enum, and default from that version's schema;
- **accepted by the target compiler**: freshly generated output that has been read back;
- **visually verified in the target engine**: protocol, capture, and result.

An absent property may have been removed by the compiler. An observed value does not become a global default. Exit code 0 may accompany an unknown property that was silently removed. A name shared by two games does not prove identical semantics. Keep unknown facts unknown.

To reproduce the principle behind an effect, describe its layers, timeline, CPs, providers, renderers, and dependencies; then write your own sources and assets. Keep the original resources locally. The skill repository contains the method, metadata, and original examples, without copying the game's assets.

Read [the verified ingestion observations](references/vpk-ingestion-2026-10-15.md) for the builds and evidence used while creating this skill. These observations are not an exhaustive property catalog.

## Verify the helper

```text
python scripts/audit_observations.py
python -m unittest discover -s scripts -p "test_*.py" -v
```

The audit reads every indexed class record and checks hashes, identities, aggregate counts, witnesses and correction provenance. It requires no game installation. Passing it establishes metadata consistency only; original payload and runtime validation are separate checks.
