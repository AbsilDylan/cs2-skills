---
name: source2-particle-control-points
description: "Author and diagnose native CS2 particle control points, transforms, providers, attachment drivers and child bindings using offline typed contracts."
---

# Native particle control points

Describe the requested effect as an effect-specific CP contract: index, role, value kind, coordinate space, external driver, internal writer, readers and update timing. CP0 and CP1 have **no universal endpoint convention**. Indices 0–63 identify CP slots; some selector properties separately support sentinel values such as `-1`, which must be interpreted per property. A CP used as a scalar/vector data channel is not simultaneously a geometric endpoint unless the graph explicitly intends that coupling.

Read [input-contract.md](references/input-contract.md) for native typed inputs, rotations and real driver configuration. Read [patterns.md](references/patterns.md) for beams, distance controls, animation and children. Read [corpus-evidence.md](references/corpus-evidence.md) for provenance and the distinction between observed serialized fields and reflected declarations.

## Look up the exact native contract

This folder is self-contained. Python 3 standard library is sufficient; no game, network or other checkout is required for lookup. Run from this skill directory, or pass the script's absolute path:

```text
python scripts/cp_contracts.py --list --contains ControlPoint --limit 100
python scripts/cp_contracts.py --class C_OP_DistanceBetweenCPsToCP --summary
python scripts/cp_contracts.py --class C_OP_DistanceBetweenCPsToCP --field m_nOutputCPField
python scripts/cp_contracts.py --module particleslib --class CParticleVecInput --summary
python scripts/cp_contracts.py --module animationsystem --enum ParticleAttachment_t
python scripts/cp_contracts.py --verify
```

The embedded CS2 snapshot includes 213 classes, 62 enums and 5,249 field occurrences: CP/transform/provider/path-related declarations and their declared-type dependencies. Fields include inherited declarations and full type trees, editor metadata and default sources/status. The catalogue is extensive within that explicit selection, not proof of every engine behavior or every build. Use exact `(module,name,field)` identities; similar names can have different types. Read [native-classes.md](references/native-classes.md) to select a family.

## Author and verify

- Preserve externally driven CPs. A pre-emission position writer can replace a game-provided target. Allocate derived outputs after checking all root/child readers and writer order.
- Preserve native case and provider family. `m_TransformInput`, `m_transformInput`, `PF_TYPE_*`, `PVEC_TYPE_*` and `PT_TYPE_*` are distinct contracts. Never generate four quaternion components into a `QAngle` field or a float where a provider object is required.
- A field missing from a compiled example can still be declared by the schema. Conversely, a field observed in an older compiled asset can be absent from the selected schema. Keep game/build/revision with both facts and verify retention in the target toolchain.
- Distinguish static PET preview drivers from runtime entity/attachment binding. A saved preview configuration does not by itself establish an in-game attachment. Use the actual spawning API or entity configuration supported by the target integration; do not invent an API name.
- Separate declaration/default evidence, serialized-asset evidence, compiler/readback evidence and observed native behavior. None substitutes for another. Missing tooling leaves an explicit unverified result; it does not justify removing valid native properties or inventing behavior.

Deliver native VPCF source/patch, dependency names, the CP contract and a reproducible PET/CS2 setup. Test distinct endpoint/parameter values, a translated origin, a non-identity orientation, and motion after emission when requested. Verify compile logs and fresh compiled property readback, then test the actual effect and drivers. A distance value alone does not prove emissive brightness, a rope renderer alone does not define a beam, and a child reference alone does not define CP mapping.

Validate the portable lookup with `python -m unittest discover -s scripts -p "test_*.py" -v`. These tests establish catalogue/query portability and typed invariants; native behavior still needs the scenarios in the pattern reference.
