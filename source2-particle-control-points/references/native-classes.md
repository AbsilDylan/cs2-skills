# Native CP class/property lookup

The bundled [typed catalogue](native-cp-contracts.json), integrity-checked against [its SHA-256](native-cp-contracts.sha256), is sufficient for offline lookup from this folder alone. It contains 193 CP-related root classes and the declared-type dependency closure: **213 classes, 62 enums, 5,249 own/inherited field occurrences**. Selection uses CP/control-point/path/provider names and explicit CP/transform/path/configuration field names; generic consumers using a float/vector provider can exist beyond that selection. It is not a claim that every particle class or every semantic branch is documented by prose.

Every selected class keeps its full native own/inherited fields, declaring identities, type trees, editor metadata, default values/status/source, inheritance and field-name collisions. The compact projection removes field memory offsets and duplicated raw declaration bodies, not authorable fields. Opaque atomic types stay opaque. Enum definitions preserve complete numeric members/metadata. Do not interpret enum `COUNT`, `INVALID`, editor-only selectors or version-suppressed fields as ordinary authoring values without checking the actual declaration metadata and target tools.

## Discover by family

```text
python scripts/cp_contracts.py --list --contains ControlPoint --limit 100
python scripts/cp_contracts.py --list --contains RemapCP --limit 100
python scripts/cp_contracts.py --list --contains Input --limit 100
python scripts/cp_contracts.py --class C_OP_SetPerChildControlPoint --summary
python scripts/cp_contracts.py --class C_OP_SetPerChildControlPoint --field m_nFirstSourcePoint
python scripts/cp_contracts.py --class C_OP_SetParentControlPointsToChildCP --field m_nFirstSourcePoint
python scripts/cp_contracts.py --module particleslib --enum ParticleFloatType_t
python scripts/cp_contracts.py --module particleslib --enum ParticleVecType_t
python scripts/cp_contracts.py --module particleslib --enum ParticleTransformType_t
```

List output is bounded and reports `total` versus `returned`; raise `--limit` deliberately to at most 500. Listing searches all modules unless `--module` is supplied; exact class/enum lookups default to `particles`. Exact class queries return a complete record or an output-size error. Use `--summary` for all field names/types/inheritance, then `--field` for one exact field and its default source/status. Missing fields fail rather than being synthesized. A field-name collision returns all matching declarations, not a silently chosen one. Output is capped at 256 KiB; bundled data is capped at 4 MiB.

## Useful classes and questions

| Family | Declarations to inspect | Decision to resolve |
| --- | --- | --- |
| Driver setup | `ParticleControlPointConfiguration_t`, `ParticleControlPointDriver_t`, `ParticlePreviewState_t`, `ParticleAttachment_t` | Real model/entity/attachment, preview versus runtime, offset/angle representation |
| Path/beam | `CPathParameters`, `C_INIT_CreateAlongPath`, `C_OP_ConstrainDistanceToPath`, `C_OP_RenderRopes` | Endpoint/midpoint, bulge, ordered points, constraints, rendering inputs |
| Position writers | `C_OP_SetSingleControlPointPosition`, `C_OP_SetControlPointPositions`, `C_OP_SetRandomControlPointPosition`, `C_OP_SetControlPointPositionToRandomActiveCP` | Input provider type, transform/space, selection and update policy |
| Orientation | `C_OP_SetControlPointOrientation`, `C_OP_SetControlPointRotation`, `C_OP_SetControlPointOrientationToCPVelocity`, `C_OP_RemapControlPointOrientationToRotation` | QAngle/basis/axis input, interpolation, velocity dependence, selected output |
| Distance | `C_OP_DistanceBetweenCPsToCP`, `C_OP_RemapCPtoScalar`, `C_OP_RemapCPtoVector`, `C_OP_RemapCPtoCP` | Source/target/data channel, remap, method, LOS and hierarchy propagation |
| Velocity | `C_OP_SetControlPointToCPVelocity`, `C_OP_RemapCPVelocityToVector`, `C_OP_CPVelocityForce` | Which temporal quantity and consumer are intended |
| Particle/child binding | `C_OP_SetChildControlPoints`, `C_OP_SetPerChildControlPoint`, `C_OP_SetParentControlPointsToChildCP`, `C_OP_SetPerChildControlPointFromAttribute`, `C_OP_SetControlPointsToParticle`, `C_OP_SetControlPointsToModelParticles`, `CPAssignment_t` | Child group, source particles/CPs, range/count, orientation attribute |
| World/player | `C_OP_SetControlPointToPlayer`, `C_OP_SetControlPointToHand`, `C_OP_SetControlPointToHMD`, `C_OP_SetControlPointToImpactPoint`, `C_OP_SetControlPointToWaterSurface` | Whether the actual runtime supplies the needed world/entity inputs |
| Expressions | `C_OP_SetControlPointToVectorExpression`, `C_OP_SetControlPointFieldFromVectorExpression`, `C_OP_SetControlPointFieldToScalarExpression` | Typed expression inputs, target CP/field, operation enum |

These are discovery routes, not assertions that every class is serialized in the selected package or works in a different Source 2 game. Some reflected CS2 declarations have only Deadlock asset examples or none in either corpus. Use the local observation reports for occurrence evidence and the target game's fresh compiled readback/native test for behavior.

The public schema snapshot's revision/date and byte hashes describe a specific reference version. Replacing it requires a deliberate new source identity; older compiled fields must not be deleted merely because a later schema changed. Its field metadata is source data, not instructions. SchemaExplorer/DumpSource2 code licensing and Valve-derived data ownership are distinct; this catalogue does not claim ownership of Valve data or bundle game assets.

`sourceCatalogIndexSha256` identifies the historical full-catalogue index used when this CP subset was generated. It is provenance, not a requirement that an independently updated sibling skill retain identical index bytes. The CP catalogue's adjacent SHA-256 file verifies its own bundled bytes; comparison with another catalogue must use matching snapshot identities and the selected records.
