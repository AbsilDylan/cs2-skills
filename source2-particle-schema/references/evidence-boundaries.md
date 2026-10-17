# Scope and evidence

The catalogue is generated from an explicitly selected public Counter-Strike 2 SchemaExplorer snapshot. [catalog-index.json](catalog-index.json) records the exact compressed and decompressed byte hashes, source URL, generator, revision, date/time, selection rules, record counts and generated-file hashes. [catalogue.md](catalogue.md) links every class and enum.

[The historical independent completeness check](schema-completeness-2026-10-15.json) compares the 15 October catalogue with the original snapshot using separate traversal: 464 classes, 3,001 declared fields, 10,921 field occurrences including inheritance, 92 enums and 512 enum members. Exact types, owners, raw metadata/default layers and reconstructed class records match. Its index and generator hashes identify that historical run, not the current distribution. [The distribution verification](distribution-verification-2026-10-16.json) records the current index/generator/document identities and confirms that all 557 class, enum and atomic-type data files remain byte-identical. The generated document gained a Contents section; its inclusion in the index's file tree changes that aggregate without changing schema data. These checks prove reference completeness for that selection, not native property behavior or editability.

Each class reference preserves class-level properties/metadata, all own and inherited field records with their declaring identities, parent structure, editor metadata and defaults. All parents contribute field declarations; diamonds deduplicate the same declaring class, while distinct fields with the same name remain listed as collisions. Field offsets remain relative to the declaring class; effective inherited offsets are not computed.

Defaults follow the first parent only, with top-level replacement by each class's `MGetKV3ClassDefaults`, matching the documented SchemaExplorer format. Nested objects are replaced, not recursively merged. `available`, `partial` and `unavailable` distinguish readable defaults from missing/unreadable layers. The original defaults metadata remains in the class declaration. Missing values are not filled with guessed zeroes. Strings such as `"-nan"` or large numeric strings are preserved.

Declared class and enum references retain their module and recursively enter the catalogue. All enums in the particle modules are included even when no field references them. Atomic types are retained with their type trees and usage index; a named atomic type without a declared class does not become a fabricated structure. Enum members, numeric values and metadata are copied without turning friendly editor names into runtime guarantees.

This is **reflection and editor reference evidence**. It does not demonstrate a property's mathematical formula, units, supported combinations, random stream, scheduling, native compilation acceptance, compiled property retention, material/shader execution or visual fidelity. A compiler accepting a source can still discard unknown fields; describe compiler acceptance, readback retention and runtime/render behavior as separate observations. Memory offsets and class sizes do not certify ABI or behavior. The supplied snapshot may be newer than a user's installed CS2 build.

## Using the snapshot after a game update

The bundled revision identifies reference provenance, not a required CS2
installation. Offline lookup and integrity checks keep working without a
matching installed build. Reuse established contracts; refresh affected
records when a needed field is missing, current native evidence conflicts,
or a relevant change/regression is being investigated. A new build ID alone
does not require rebuilding the catalogue. Preserve the old provenance
when adding current observations rather than silently relabeling it.

## Reflected fields versus authoring keys

An exhaustive reflected-field catalogue is not an exhaustive list of editable VPCF keys. `MNotSaved`, suppression/serialization metadata, runtime-only/internal fields, resource markers and opaque structures must remain visible as such. A field's offset, public-looking name or editor label cannot establish that ResourceCompiler reads it from authored KV3. A value present in `MGetKV3ClassDefaults` is an observed default from that snapshot; it does not prove acceptance of arbitrary overrides, combinations or ranges. Absence from readable defaults does not by itself prove unsupported authoring either.

When a property needs an explanation, combine its exact class/type/default/metadata record with [build-attributed local native help](native-help.md), if available. Keep absence of help explicit, and keep editor descriptions separate from measured behavior. Legacy help tokens mentioning a similar class or field remain separate identities until correspondence is independently established.

## Sources and attribution

- [SchemaExplorer download manifest and format notes](https://s2v.app/SchemaExplorer/llms.txt)
- [SchemaExplorer source and notices](https://github.com/ValveResourceFormat/SchemaExplorer)
- [DumpSource2 extractor](https://github.com/ValveResourceFormat/DumpSource2)

SchemaExplorer's code license and Valve-derived schema data are distinct. Keep these source notices with the generated references; this catalogue does not claim ownership of Valve schema data or redistribute game binaries, textures or materials. Its scripts are independent Python code and require no upstream code execution.

## Rebuild from an explicit local snapshot

The helper does not download or discover anything. Obtain the selected game snapshot through the source manifest, keep the exact input bytes, and run:

```sh
python scripts/schema_catalog.py build --input /local/path/cs2.json.gz --game "Counter-Strike 2" --source-url https://s2v.app/SchemaExplorer/assets/cs2.json-DZ4XVvE1.gz
python scripts/schema_catalog.py verify
python scripts/schema_catalog.py build --check --input /local/path/cs2.json.gz --game "Counter-Strike 2" --source-url https://s2v.app/SchemaExplorer/assets/cs2.json-DZ4XVvE1.gz
```

Plain UTF-8 JSON and gzip are accepted, each bounded to 64 MiB. Generation is deterministic and uses only Python's standard library. `build --check` compares the complete regenerated catalogue without writing. `verify` checks installed reference bytes, paths, aggregate digest, index digest and generator identity without needing the input snapshot. Generation removes only obsolete files listed by its previous machine index, within the selected output directory; it does not delete unrelated files.

For a different game, use a separate skill/catalogue destination and its explicit source URL. Do not merge same-named classes across CS2, Deadlock, s&box or different revisions as if they were one contract.
