# Local ingestion verified on October 15, 2026

The counts come from the indexes actually installed, not an old decompiled repository. The associated JSON contains the index identifiers and hashes of the two verification extractions: [vpk-ingestion-2026-10-15.json](vpk-ingestion-2026-10-15.json).

| Game | Observed installed Steam build | Total entries in `pak01_dir.vpk` | `.vpcf_c` | `.vmat_c` | `.vtex_c` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Counter-Strike 2 | 25640462 | 137440 | 2622 | 22008 | 71714 |
| Deadlock | 25660886 | 137966 | 16310 | 4412 | 14191 |

A VPK inventory does not automatically cover other archives, addons, separate resources, or possible engine features. The builds were read from `appmanifest_730.acf` and `appmanifest_1422450.acf` in the local installation; the reproducible identity of the index is its SHA-256, whose scope is explicitly limited to the header and tree.

## Checks performed

The standard-library helper read both v2 indexes and extracted exactly one particle from each into new working directories, with correct CRC32 values. The extracted originals remain in local research directories; they are not part of the skill.

Installed VRF: `19.2.0+f86ea981fc37b9f8f23c4eb84e058de2083b6761`. The `--input`, `--block`, `--help`, and `--version` flags were confirmed by this executable's help, then `--block DATA` was run on both extractions.

| Check | CS2 | Deadlock |
| --- | --- | --- |
| Exact path | `particles/ambient/ambient_water_stream.vpcf_c` | `materials/dev/steam_test.vpcf_c` |
| Payload bytes | 4016 | 3207 |
| Resource Type / Header | Particle v1 / header 12 | Particle v1 / header 12 |
| DATA format displayed by VRF | `vpcf54` | `vpcf61` |
| Renderer classes present | `C_OP_RenderTrails` | `C_OP_RenderSprites` |
| External references displayed | One texture and five particle children | One texture |

Two useful findings for research:

- Particles are not all stored under `particles/`: the Deadlock verification sample is under `materials/dev/`, and the CS2 inventory includes, among others, a particle under `models/gameplay/`.
- These two examples use different VPCF formats despite sharing the same resource header. This is enough to require verification of decoding and of the target game; it does not prove that all properties are incompatible between the games.

These observations demonstrate reproducible access to references and inspection of their structure. They prove neither the exact semantics of the properties, nor visual equivalence, nor the availability of a Deadlock feature in CS2.

## Reproduce

From the skill directory, replace the installation and working paths:

```text
python scripts/vpk_reference.py inventory --vpk "CS2/game/csgo/pak01_dir.vpk" --extension vpcf_c --limit 0
python scripts/vpk_reference.py inventory --vpk "Deadlock/game/citadel/pak01_dir.vpk" --extension vpcf_c --limit 0
python scripts/vpk_reference.py extract --vpk "CS2/game/csgo/pak01_dir.vpk" --entry particles/ambient/ambient_water_stream.vpcf_c --output "WORK/new-cs2-sample"
python scripts/vpk_reference.py extract --vpk "Deadlock/game/citadel/pak01_dir.vpk" --entry materials/dev/steam_test.vpcf_c --output "WORK/new-deadlock-sample"
Source2Viewer-CLI --help
Source2Viewer-CLI --version
Source2Viewer-CLI --input "WORK/new-cs2-sample/particles/ambient/ambient_water_stream.vpcf_c" --block DATA
Source2Viewer-CLI --input "WORK/new-deadlock-sample/materials/dev/steam_test.vpcf_c" --block DATA
```

Tooling references: [ValvePak](https://github.com/ValveResourceFormat/ValvePak), [VRF CLI](https://github.com/ValveResourceFormat/ValveResourceFormat/blob/master/docs/guides/command-line.md). The helper does not depend on these projects; VRF is used separately here to inspect DATA.
