# Read-only local corpus observations

Observed on 2026-10-15 through CRC-checked VPK ranges and Resource2 → Binary KV3 decoding, followed by a finite-number-only text projection for this historical CP inventory. Only compiled particle entries from the explicitly selected `pak01_dir.vpk` are counted; sibling packages, addons, loose/decompiled corpora and shader binaries are outside this count. Local Steam manifest identities are CS2 app 730/build 25640462 and Deadlock app 1422450/build 25660886. These local manifest facts are not cryptographically bound to the VPK bytes; retain the directory hashes below as the inspected package identity.

| Scope | Particle entries | Included in finite-value CP inventory | Excluded from that inventory |
| --- | ---: | ---: | ---: |
| CS2 local installation package | 2,622 | 2,622 | 0 |
| Deadlock local installation package | 16,310 | 16,309 | 1 |

Deadlock's excluded resource has four stored NaN scalars in `particles/npc/neutrals/neutral_mushroom/neutral_attack_spore_warmup.vpcf_c`, under `m_controlPointConfigurations[].m_drivers[].m_vecOffset[]`. Binary KV3 decoding preserves all 16,310 resources, including those values; the finite-number-only projection excludes that one resource. The 16,309 denominator below is specific to these historical CP frequency reports, not a CRC or binary-format failure and not the limit of native KV3. All frequencies below come from package payloads, not a decompiled text snapshot.

The checked reports contain aggregate counts, resource-plan/directory SHA-256 identities and bounded primitive field fragments. They contain no complete assets, extracted payloads, absolute installation paths or bundled Valve schema:

- [CS2 observations](corpus-cs2.json): directory SHA-256 `fac8ff988ab9a20c3175c33fd4c5196da3798a0ddcea9fe0a5565ab33cffb5a9`.
- [Deadlock observations](corpus-deadlock.json): directory SHA-256 `cc77bd7b65752d6d206e623be0db0b31508613b1752f3d2dd1e345077737b48c`.

## Selected native class frequencies

Instance/effect counts are distinct: one effect may contain several components of a class. Fields in the JSON report count explicitly serialized keys; absent keys are not recovered defaults.

| Class | CS2 instances / effects | Deadlock instances / effects |
| --- | ---: | ---: |
| `C_OP_SetSingleControlPointPosition` | 540 / 284 | 1,550 / 1,151 |
| `C_OP_SetControlPointPositions` | 82 / 82 | 160 / 108 |
| `C_OP_SetControlPointOrientation` | 95 / 95 | 292 / 271 |
| `C_OP_SetControlPointToPlayer` | 57 / 57 | 15 / 15 |
| `C_OP_DistanceBetweenCPsToCP` | 51 / 47 | 25 / 22 |
| `C_OP_SetPerChildControlPoint` | 14 / 13 | 198 / 198 |
| `C_INIT_CreateAlongPath` | 26 / 26 | 87 / 87 |
| `C_INIT_RemapTransformOrientationToRotations` | 32 / 31 | 232 / 232 |
| `C_OP_RemapCPtoScalar` | 11 / 11 | 76 / 70 |
| `C_OP_RemapCPtoVector` | 78 / 78 | 32 / 30 |
| `C_OP_RenderRopes` | 168 / 109 | 3,935 / 3,050 |
| `C_OP_SetControlPointRotation` | 0 observed | 94 / 93 |

Deadlock's `C_OP_SetControlPointRotation` example has `m_nCP`, `m_nLocalCP`, `m_flRotRate`, `m_vecRotAxis`. The bundled CS2 schema also declares that class; the absence of a serialized CS2 instance does not remove it from the schema. Neither a Deadlock occurrence nor a CS2 declaration alone proves target-build compilation or behavior. Zero occurrences is not proof a class does not exist.

## Selected CP provider occurrence counts

Counts include nested provider objects throughout each successfully decoded root, including serialized editor/provider metadata. They establish vocabulary and relative presence, not how often each value is evaluated at runtime.

| Provider enum string | CS2 | Deadlock |
| --- | ---: | ---: |
| `PF_TYPE_CONTROL_POINT_COMPONENT` | 1,102 | 7,486 |
| `PF_TYPE_CONTROL_POINT_CHANGE_AGE` | 41 | 14 |
| `PF_TYPE_CONTROL_POINT_SPEED` | 5 | 0 observed |
| `PVEC_TYPE_CP_VALUE` | 119 | 500 |
| `PVEC_TYPE_CP_RELATIVE_POSITION` | 10 | 27 |
| `PVEC_TYPE_CP_RELATIVE_DIR` | 6 | 71 |
| `PVEC_TYPE_CP_DELTA` | 0 observed | 4 |
| `PT_TYPE_CONTROL_POINT` | 3 | 141 |
| `PT_TYPE_CONTROL_POINT_RANGE` | 2 | 4 |
| `PM_TYPE_CONTROL_POINT` | 6 | 219 |

CS2's `m_controlPointConfigurations` occurs in 1,868 effects. Its driver inventory includes `m_iControlPoint` 1,260 times, `m_attachmentName` 134, `m_vecOffset` 361, `m_angOffset` 8. Attach-type values: `PATTACH_WORLDORIGIN` 2,675, `PATTACH_POINT_FOLLOW` 128 and `PATTACH_POINT` 6. These are serialized-field counts, not binding success counts.

CS2 has 2,619 child entries in 796 effects. Explicit fields: `m_ChildRef` 2,619; `m_flDelay` 246; `m_bEndCap` 2; `m_nDetailLevel` 51. Deadlock has 12,703 child entries in 3,768 decoded effects, with `m_ChildRef`, `m_flDelay` and `m_bEndCap` observed. Per-child control-point fields belong to the separate operator and do not justify inventing fields on a child resource reference.

## Inspect on a different machine

All facts and the native typed CP catalogue needed by this guide are bundled; lookup does not require a game, another skill or a network connection. For fresh schema queries use this folder's `scripts/cp_contracts.py`. The broader sibling `source2-particle-schema` catalogue is an optional source for declarations beyond the CP subset.

For fresh package evidence, select the target game/build and local `pak01_dir.vpk` explicitly. If the optional sibling reference-research skill is installed, its Python-standard-library helper can list/extract bounded candidates. Run these from this skill directory after replacing the explicit input/output parameters:

```text
python ../source2-particle-reference-research/scripts/vpk_reference.py inventory --vpk "SELECTED_PACKAGE/pak01_dir.vpk" --extension vpcf_c --limit 0
python ../source2-particle-reference-research/scripts/vpk_reference.py extract --vpk "SELECTED_PACKAGE/pak01_dir.vpk" --entry "particles/selected.vpcf_c" --output "NEW_WORK_DIRECTORY"
```

The optional extraction verifies selected payload CRC32 and writes a manifest; inventory alone does not verify payloads. Alternatively use an installed VPK inspection tool with equivalent provenance. Inspect the selected compiled DATA block using a locally installed ValveResourceFormat/Source2Viewer CLI after checking its own `--help` and version. Keep extracted game resources outside the skill bundle. No reader/tool is implicitly downloaded or executed by this guide.

A fresh exhaustive property-frequency scan must document its selection, parser/version, bounds, CRC/hash checks, all resource failures and whether it preserves non-finite Binary KV3 values. A handful of decoded examples cannot reproduce an exhaustive frequency count. Compare game/build/hash identities before carrying these historical counts forward.

Schema source provenance: [SchemaExplorer manifest/format](https://s2v.app/SchemaExplorer/llms.txt), [SchemaExplorer source/notices](https://github.com/ValveResourceFormat/SchemaExplorer), [DumpSource2 extractor](https://github.com/ValveResourceFormat/DumpSource2). The embedded native CP catalogue records revision 11131657, date/time, compressed/decompressed byte hashes and the exact selected data URL. Reflected defaults and serialized asset values are distinct evidence; neither proves runtime formulas, coordinate conventions, timing or visuals. Validate the final graph and drivers in PET/CS2.
