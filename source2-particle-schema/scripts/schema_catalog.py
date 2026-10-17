#!/usr/bin/env python3
"""Portable, offline Source 2 schema catalogue: Python 3 standard library only."""

import argparse
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 64
MAX_VISITED = 1024
ROOT_MODULES = ("particles", "particleslib")
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "references"
FORMAT = "source2-particle-schema-catalogue/1"
WARNINGS = [
    "Reflection/editor reference only; no native compilation, property retention, runtime behavior or rendering parity is established.",
    "The explicitly selected public snapshot may be newer than the installed game; revision/date/hashes describe the source, not installed-game compatibility.",
    "Offsets and sizes describe the dump's Windows memory layout. Field offsets remain relative to the declaring class, not an effective inherited object.",
    "Fields traverse all parents; defaults merge only the first-parent chain by top-level replacement. Missing defaults and opaque atomic types remain unresolved.",
]


class CatalogError(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def identity(record):
    return (record["module"], record["name"])


def named(key):
    return {"module": key[0], "name": key[1]}


def token(value):
    readable = re.sub(r"[^A-Za-z0-9_-]", "_", value)[:80] or "record"
    return readable + "--" + digest(value.encode("utf-8"))[:12]


def record_path(kind, key):
    return "%s/%s/%s.json" % (kind, token(key[0]), token(key[1]))


def safe_path(root, relative):
    if not isinstance(relative, str) or "\\" in relative or "\0" in relative or ":" in relative:
        raise CatalogError("Invalid generated reference path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CatalogError("Generated reference path must stay inside its catalogue")
    destination = root.joinpath(*parts).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as error:
        raise CatalogError("Generated reference path escapes its catalogue") from error
    return destination


def load_input(filename):
    with Path(filename).open("rb") as handle:
        packed = handle.read(MAX_INPUT_BYTES + 1)
    if len(packed) > MAX_INPUT_BYTES:
        raise CatalogError("Input exceeds the 64 MiB limit")
    raw = packed
    if packed.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
        except (OSError, EOFError) as error:
            raise CatalogError("Invalid gzip snapshot") from error
    if len(raw) > MAX_INPUT_BYTES:
        raise CatalogError("Decompressed JSON exceeds the 64 MiB limit")
    try:
        document = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise CatalogError("Snapshot must be valid UTF-8 JSON with finite JSON numbers") from error
    if not isinstance(document, dict) or not isinstance(document.get("classes"), list) or not isinstance(document.get("enums"), list):
        raise CatalogError("Expected SchemaExplorer classes and enums arrays")
    provenance = {
        "input_name": Path(filename).name,
        "input_encoding": "gzip" if packed.startswith(b"\x1f\x8b") else "json",
        "input_bytes": len(packed), "input_sha256": digest(packed),
        "raw_json_bytes": len(raw), "raw_json_sha256": digest(raw),
        "generator": document.get("generator"), "revision": document.get("revision"),
        "version_date": document.get("version_date"), "version_time": document.get("version_time"),
    }
    return document, provenance


def index_records(records, kind):
    result = {}
    for position, record in enumerate(records):
        if not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key] for key in ("module", "name")):
            raise CatalogError("Invalid %s identity at position %s" % (kind, position))
        key = identity(record)
        if key in result:
            raise CatalogError("Duplicate %s identity: %s/%s" % ((kind,) + key))
        result[key] = (record, position)
    return result


def type_references(value, depth=0):
    if depth > MAX_DEPTH:
        raise CatalogError("Field type tree exceeds depth 64")
    found = []
    if isinstance(value, dict):
        if value.get("category") in ("declared_class", "declared_enum") and isinstance(value.get("name"), str):
            found.append({"kind": "classes" if value["category"] == "declared_class" else "enums", "name": value["name"], "module": value.get("module")})
        for child in value.values():
            found.extend(type_references(child, depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.extend(type_references(child, depth + 1))
    return found


def atomic_types(value, depth=0):
    if depth > MAX_DEPTH:
        raise CatalogError("Field type tree exceeds depth 64")
    found = []
    if isinstance(value, dict):
        if value.get("category") == "atomic" and isinstance(value.get("name"), str):
            found.append(value)
        for child in value.values():
            found.extend(atomic_types(child, depth + 1))
    elif isinstance(value, list):
        for child in value:
            found.extend(atomic_types(child, depth + 1))
    return found


def parents(record):
    result = record.get("parents", [])
    if not isinstance(result, list) or any(not isinstance(parent, dict) or any(not isinstance(parent.get(key), str) or not parent[key] for key in ("module", "name")) for parent in result):
        raise CatalogError("Invalid parent list for %s/%s" % identity(record))
    return result


def own_fields(record):
    fields = record.get("fields", [])
    if not isinstance(fields, list) or any(not isinstance(field, dict) or not isinstance(field.get("name"), str) or not isinstance(field.get("type"), dict) for field in fields):
        raise CatalogError("Invalid fields for %s/%s" % identity(record))
    if len({field["name"] for field in fields}) != len(fields):
        raise CatalogError("Duplicate field names within %s/%s" % identity(record))
    return fields


def all_parents(key, classes):
    ordered, active, visited = [], set(), set()

    def visit(current, depth):
        if current in active:
            raise CatalogError("Inheritance cycle at %s/%s" % current)
        if depth > MAX_DEPTH or len(active) + len(visited) >= MAX_VISITED:
            raise CatalogError("Inheritance limit exceeded at %s/%s" % current)
        if current in visited:
            return
        if current not in classes:
            raise CatalogError("Missing parent class %s/%s" % current)
        active.add(current)
        for parent in parents(classes[current][0]):
            visit(identity(parent), depth + 1)
        active.remove(current)
        visited.add(current)
        ordered.append(current)

    visit(key, 0)
    return ordered


def class_defaults(key, classes):
    chain, current = [], key
    while current is not None:
        chain.insert(0, current)
        bases = parents(classes[current][0])
        current = identity(bases[0]) if bases else None
    values, sources, issues, readable = {}, {}, [], 0
    for owner in chain:
        metadata = classes[owner][0].get("metadata", [])
        if not isinstance(metadata, list):
            raise CatalogError("Invalid metadata on %s/%s" % owner)
        layers = [entry for entry in metadata if isinstance(entry, dict) and entry.get("name") == "MGetKV3ClassDefaults"]
        if len(layers) > 1:
            raise CatalogError("Repeated defaults metadata on %s/%s" % owner)
        if not layers:
            issues.append({"class": named(owner), "code": "defaults-absent"})
        elif not isinstance(layers[0].get("value"), dict):
            issues.append({"class": named(owner), "code": "defaults-unreadable", "value": layers[0].get("value")})
        else:
            readable += 1
            for name, value in layers[0]["value"].items():
                values[name], sources[name] = copy.deepcopy(value), named(owner)
    return {
        "status": "available" if not issues else "partial" if readable else "unavailable",
        "merge": "first-parent-top-level", "chain": [named(owner) for owner in chain],
        "values": values, "sources": sources, "issues": issues,
    }


def resolve_reference(reference, lookup):
    result = dict(reference)
    result["status"] = "unscoped" if not isinstance(reference.get("module"), str) else "present" if (reference["module"], reference["name"]) in lookup else "missing"
    return result


def make_catalogue(document, provenance, game, source_url, script_path):
    classes = index_records(document["classes"], "classes")
    enums = index_records(document["enums"], "enums")
    roots = {key for key in classes if key[0] in ROOT_MODULES}
    if not roots:
        raise CatalogError("Snapshot has no classes in particles or particleslib")
    selected_classes, selected_enums = set(), {key for key in enums if key[0] in ROOT_MODULES}
    pending, unresolved = sorted(roots), {}
    while pending:
        key = pending.pop()
        if key in selected_classes:
            continue
        if key not in classes:
            raise CatalogError("Missing declared parent %s/%s" % key)
        selected_classes.add(key)
        row = classes[key][0]
        pending.extend(identity(parent) for parent in parents(row))
        for field in own_fields(row):
            for reference in type_references(field["type"]):
                table = classes if reference["kind"] == "classes" else enums
                resolved = resolve_reference(reference, table)
                if resolved["status"] != "present":
                    unresolved[canonical(resolved)] = resolved
                elif reference["kind"] == "classes":
                    pending.append((reference["module"], reference["name"]))
                else:
                    selected_enums.add((reference["module"], reference["name"]))

    provenance.update({
        "game": game, "game_identity": "explicit source selection; not independently encoded/attested by schema format",
        "data_url": source_url, "manifest_url": "https://s2v.app/SchemaExplorer/llms.txt",
        "explorer_url": "https://github.com/ValveResourceFormat/SchemaExplorer",
    })
    snapshot_id = provenance["raw_json_sha256"]
    files, records, atomic_usage = {}, [], {}
    declared_field_count = inherited_field_count = 0
    default_status_counts = {"available": 0, "partial": 0, "unavailable": 0}
    for key in sorted(selected_classes):
        row, position = classes[key]
        ordered = all_parents(key, classes)
        fields = []
        by_name = {}
        references = {}
        for owner in ordered:
            for field in own_fields(classes[owner][0]):
                fields.append({"declared_in": named(owner), "inherited": owner != key, "field": copy.deepcopy(field)})
                by_name.setdefault(field["name"], []).append(named(owner))
                for reference in type_references(field["type"]):
                    resolved = resolve_reference(reference, classes if reference["kind"] == "classes" else enums)
                    references[canonical(resolved)] = resolved
        for field in own_fields(row):
            for atom in atomic_types(field["type"]):
                usage = atomic_usage.setdefault(atom["name"], {"name": atom["name"], "status": "opaque-atomic-type", "type_variants": {}, "uses": []})
                usage["type_variants"][canonical(atom)] = atom
                use = {"class": named(key), "field": field["name"]}
                if use not in usage["uses"]:
                    usage["uses"].append(use)
        defaults = class_defaults(key, classes)
        default_status_counts[defaults["status"]] += 1
        own_count = len(own_fields(row))
        declared_field_count += own_count
        inherited_field_count += len(fields) - own_count
        reference = {
            "format": "source2-particle-class-reference/1", "identity": named(key),
            "role": "particle-module-class" if key in roots else "declared-type-or-parent-dependency",
            "evidence": "reflection-and-editor-metadata; behavior-unverified",
            "source": {"snapshot_id": snapshot_id, "url": source_url, "json_pointer": "/classes/%s" % position, "canonical_record_sha256": digest(canonical(row))},
            "declaration": {name: copy.deepcopy(value) for name, value in row.items() if name != "fields"},
            "inheritance": [named(owner) for owner in ordered if owner != key], "fields": fields,
            "field_name_collisions": [{"name": name, "declared_in": owners} for name, owners in sorted(by_name.items()) if len(owners) > 1],
            "defaults": defaults, "references": [references[name] for name in sorted(references)],
        }
        relative = record_path("classes", key)
        data = encoded(reference)
        files[relative] = data
        records.append({"kind": "class", **named(key), "path": relative, "sha256": digest(data), "declared_fields": own_count, "inherited_fields": len(fields) - own_count, "defaults_status": defaults["status"], "root": key in roots})
    for key in sorted(selected_enums):
        row, position = enums[key]
        reference = {"format": "source2-particle-enum-reference/1", "identity": named(key), "evidence": "reflected-enum-values-and-editor-metadata; behavior-unverified", "source": {"snapshot_id": snapshot_id, "url": source_url, "json_pointer": "/enums/%s" % position, "canonical_record_sha256": digest(canonical(row))}, "declaration": copy.deepcopy(row)}
        relative = record_path("enums", key)
        data = encoded(reference)
        files[relative] = data
        records.append({"kind": "enum", **named(key), "path": relative, "sha256": digest(data), "members": len(row.get("members", [])), "root": key[0] in ROOT_MODULES})
    atoms = [{**value, "type_variants": [value["type_variants"][variant] for variant in sorted(value["type_variants"])]} for _, value in sorted(atomic_usage.items())]
    files["atomic-types.json"] = encoded({"format": "source2-particle-atomic-types/1", "snapshot_id": snapshot_id, "evidence": "opaque type names and usages; no fabricated declarations or behavior", "types": atoms})
    index = {
        "format": FORMAT, "provenance": provenance, "warnings": WARNINGS,
        "generator": {"script": "scripts/schema_catalog.py", "sha256": digest(Path(script_path).read_bytes()), "dependencies": "Python 3 standard library only"},
        "selection": {"root_modules": list(ROOT_MODULES), "rules": "all classes and enums in root modules; transitive declared field-type and parent dependencies; no unscoped module guesses"},
        "counts": {"snapshot_classes": len(classes), "snapshot_enums": len(enums), "root_classes": len(roots), "classes": len(selected_classes), "enums": len(selected_enums), "enum_members": sum(len(enums[key][0].get("members", [])) for key in selected_enums), "declared_fields": declared_field_count, "inherited_field_occurrences": inherited_field_count, "defaults_status": default_status_counts, "opaque_atomic_types": len(atoms), "unresolved_declared_references": len(unresolved)},
        "records": records, "unresolved_references": [unresolved[key] for key in sorted(unresolved)],
    }
    lines = ["# CS2 particle schema catalogue", "", "## Contents", "", "- [Classes](#classes)", "- [Enums](#enums)", "", "Game: %s. Revision: %s. Snapshot: %s %s." % (game, provenance["revision"], provenance["version_date"], provenance["version_time"]), "", "Reflection and editor metadata only. Read [evidence boundaries](evidence-boundaries.md) before making behavioral or compatibility claims.", "", "The complete machine contracts preserve inherited fields, defaults, raw type trees and metadata. Use the Python query helper for bounded exact lookups.", "", "[Opaque atomic types and uses](atomic-types.json) have no invented structures.", ""]
    for kind in ("class", "enum"):
        lines.extend(["## " + ("Classes" if kind == "class" else "Enums"), "", "| Module | Name | %s |" % ("Own / inherited fields" if kind == "class" else "Members"), "| --- | --- | ---: |"])
        for record in records:
            if record["kind"] == kind:
                measure = "%s / %s" % (record["declared_fields"], record["inherited_fields"]) if kind == "class" else str(record["members"])
                lines.append("| %s | [%s](%s) | %s |" % (record["module"], record["name"].replace("|", "\\|"), record["path"], measure))
        lines.append("")
    files["catalogue.md"] = "\n".join(lines).encode("utf-8")
    index["files"] = [{"path": relative, "bytes": len(data), "sha256": digest(data)} for relative, data in sorted(files.items())]
    index["records_tree_sha256"] = digest("".join(item["path"] + "\0" + item["sha256"] + "\n" for item in index["files"]).encode("utf-8"))
    index["index_content_sha256"] = digest(canonical(index))
    files["catalog-index.json"] = encoded(index)
    return files, index


def read_catalogue(directory):
    try:
        index = json.loads((directory / "catalog-index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError("Cannot read catalogue index") from error
    if index.get("format") != FORMAT:
        raise CatalogError("Unsupported catalogue format")
    expected = index.get("index_content_sha256")
    unsigned = {key: value for key, value in index.items() if key != "index_content_sha256"}
    if digest(canonical(unsigned)) != expected:
        raise CatalogError("Catalogue index content digest mismatch")
    return index


def verify(directory, script_path):
    index = read_catalogue(directory)
    for item in index["files"]:
        filename = safe_path(directory, item["path"])
        if not filename.is_file():
            raise CatalogError("Missing reference: " + item["path"])
        data = filename.read_bytes()
        if len(data) != item["bytes"] or digest(data) != item["sha256"]:
            raise CatalogError("Reference hash/length mismatch: " + item["path"])
    aggregate = digest("".join(item["path"] + "\0" + item["sha256"] + "\n" for item in index["files"]).encode("utf-8"))
    if aggregate != index["records_tree_sha256"]:
        raise CatalogError("Catalogue aggregate digest mismatch")
    if digest(Path(script_path).read_bytes()) != index["generator"]["sha256"]:
        raise CatalogError("Generator script differs from the generated catalogue")
    return index


def emit(value, maximum):
    data = encoded(value)
    if len(data) > maximum:
        raise CatalogError("Complete output exceeds %s bytes; request fewer records or explicitly raise --max-output-bytes. No fields/defaults were truncated." % maximum)
    sys.stdout.buffer.write(data)


def local_help_module():
    # Explicit adjacent loading also works under Python -I -S after copying
    # this skill; it never resolves application or globally installed modules.
    module_path = Path(__file__).resolve().with_name("particle_help.py")
    spec = importlib.util.spec_from_file_location("_source2_particle_help", module_path)
    if spec is None or spec.loader is None:
        raise CatalogError("The adjacent native-help helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select_record(record, field_names, summary):
    if not field_names and not summary:
        return record
    if record.get("format") != "source2-particle-class-reference/1":
        raise CatalogError("--field and --summary apply to class references only")
    if summary:
        return {
            "format": "source2-particle-class-summary/1", "selection": "explicit discovery summary; use exact --field or the complete record for values/metadata",
            "identity": record["identity"], "source": record["source"], "evidence": record["evidence"],
            "parents": record["declaration"].get("parents", []), "inheritance": record["inheritance"],
            "class_metadata": [entry for entry in record["declaration"].get("metadata", []) if entry.get("name") != "MGetKV3ClassDefaults"],
            "fields": [{"name": entry["field"]["name"], "declared_in": entry["declared_in"], "inherited": entry["inherited"], "type": entry["field"]["type"]} for entry in record["fields"]],
            "defaults_status": record["defaults"]["status"], "references": record["references"],
        }
    known = {entry["field"]["name"] for entry in record["fields"]}
    missing = sorted(set(field_names) - known)
    if missing:
        raise CatalogError("Exact field absent: " + ", ".join(missing))
    defaults = record["defaults"]
    return {
        "format": "source2-particle-field-reference/1", "selection": {"exact_requested_fields": field_names},
        "identity": record["identity"], "source": record["source"], "evidence": record["evidence"],
        "fields": [entry for entry in record["fields"] if entry["field"]["name"] in field_names],
        "defaults": {
            "class_status": defaults["status"], "merge": defaults["merge"], "chain": defaults["chain"], "issues": defaults["issues"],
            "values": {name: defaults["values"][name] for name in field_names if name in defaults["values"]},
            "sources": {name: defaults["sources"][name] for name in field_names if name in defaults["sources"]},
            "missing_requested_values": [name for name in field_names if name not in defaults["values"]],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Generate deterministic references from an explicit local JSON/gzip snapshot")
    build.add_argument("--input", required=True)
    build.add_argument("--game", required=True)
    build.add_argument("--source-url", required=True, help="Provenance only; this script never fetches it")
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    build.add_argument("--check", action="store_true")
    query = commands.add_parser("query", help="Read complete exact class/enum contracts")
    query.add_argument("--catalogue", type=Path, default=DEFAULT_OUTPUT)
    query.add_argument("--module", required=True)
    query.add_argument("--class", dest="classes", action="append", default=[])
    query.add_argument("--enum", dest="enums", action="append", default=[])
    selection = query.add_mutually_exclusive_group()
    selection.add_argument("--field", dest="fields", action="append", default=[], help="Read complete metadata/defaults for exact requested fields in one class")
    selection.add_argument("--summary", action="store_true", help="Explicit discovery summary: property names/types/owners without large defaults")
    query.add_argument("--max-output-bytes", type=int, default=256 * 1024)
    query.add_argument("--help-file", type=Path, help="Optional user-supplied local toolhelp_particles_english.txt; no network requests")
    query.add_argument("--help-manifest", type=Path, help="Optional CRC/SHA-checked VPK extraction manifest for --help-file")
    query.add_argument("--game-version-file", type=Path, help="Optional local steam.inf for installed-build provenance alongside native help")
    search = commands.add_parser("search", help="Discover identities without dumping complete contracts")
    search.add_argument("--catalogue", type=Path, default=DEFAULT_OUTPUT)
    search.add_argument("--module")
    search.add_argument("--contains", default="")
    search.add_argument("--kind", choices=("class", "enum"))
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--offset", type=int, default=0)
    check = commands.add_parser("verify", help="Verify generated bytes and provenance without the input snapshot")
    check.add_argument("--catalogue", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.command == "build":
        document, provenance = load_input(args.input)
        files, index = make_catalogue(document, provenance, args.game, args.source_url, __file__)
        if args.check:
            if any(not safe_path(args.output, relative).is_file() or safe_path(args.output, relative).read_bytes() != data for relative, data in files.items()):
                raise CatalogError("Generated catalogue differs from the installed references")
        else:
            previous = read_catalogue(args.output) if (args.output / "catalog-index.json").exists() else None
            for relative, data in files.items():
                filename = safe_path(args.output, relative)
                filename.parent.mkdir(parents=True, exist_ok=True)
                filename.write_bytes(data)
            if previous:
                for item in previous["files"]:
                    if item["path"] not in files:
                        filename = safe_path(args.output, item["path"])
                        if filename.is_file():
                            filename.unlink()
        emit({"status": "matched" if args.check else "generated", "counts": index["counts"], "records_tree_sha256": index["records_tree_sha256"]}, 16384)
    elif args.command == "verify":
        index = verify(args.catalogue, __file__)
        emit({"status": "verified", "counts": index["counts"], "records_tree_sha256": index["records_tree_sha256"]}, 16384)
    elif args.command == "search":
        if not 1 <= args.limit <= 100 or args.offset < 0:
            raise CatalogError("Search requires limit 1..100 and a non-negative offset")
        index = read_catalogue(args.catalogue)
        matches = [item for item in index["records"] if (not args.module or item["module"] == args.module) and (not args.kind or item["kind"] == args.kind) and args.contains.casefold() in item["name"].casefold()]
        emit({"provenance": index["provenance"], "total": len(matches), "offset": args.offset, "records": matches[args.offset:args.offset + args.limit], "next_offset": args.offset + args.limit if args.offset + args.limit < len(matches) else None}, 256 * 1024)
    else:
        requests = [("class", name) for name in args.classes] + [("enum", name) for name in args.enums]
        if not 1 <= len(requests) <= 16 or len(set(requests)) != len(requests):
            raise CatalogError("Request 1..16 distinct exact class/enum identities")
        if args.fields and (len(args.classes) != 1 or args.enums or len(args.fields) > 16 or len(set(args.fields)) != len(args.fields)):
            raise CatalogError("--field requires one exact class and 1..16 distinct field names")
        if not 1024 <= args.max_output_bytes <= 4 * 1024 * 1024:
            raise CatalogError("--max-output-bytes must be 1024..4194304")
        if (args.help_manifest or args.game_version_file) and not args.help_file:
            raise CatalogError("Native help manifest/build provenance requires --help-file")
        native_help = None
        help_module = None
        if args.help_file:
            help_module = local_help_module()
            try:
                native_help = help_module.load_help(args.help_file, args.help_manifest, args.game_version_file)
            except help_module.HelpError as error:
                raise CatalogError(str(error)) from error
        index = read_catalogue(args.catalogue)
        table = {(item["kind"], item["module"], item["name"]): item for item in index["records"]}
        records = []
        report = {"provenance": index["provenance"], "warnings": index["warnings"], "records": records}
        if native_help:
            report["native_help_provenance"] = native_help.provenance
            report["warnings"] = list(report["warnings"]) + native_help.provenance.get("warnings", [])
        for kind, name in requests:
            item = table.get((kind, args.module, name))
            if not item:
                raise CatalogError("Exact identity absent: %s %s/%s" % (kind, args.module, name))
            data = safe_path(args.catalogue, item["path"]).read_bytes()
            if digest(data) != item["sha256"]:
                raise CatalogError("Reference digest mismatch: " + item["path"])
            full_record = json.loads(data)
            selected = select_record(full_record, args.fields, args.summary)
            if native_help:
                if kind == "enum":
                    selected["native_help"] = {"status": "not-applicable-to-enum", "reason": "This native helper maps exact Element/Attribute class and field tokens, not enum meanings."}
                else:
                    try:
                        selected["native_help"] = native_help.query(name) if args.summary else help_module.contract_help(native_help, selected)
                    except help_module.HelpError as error:
                        raise CatalogError(str(error)) from error
            records.append(selected)
            if len(encoded(report)) > args.max_output_bytes:
                raise CatalogError("Complete output exceeds %s bytes; request fewer records or explicitly raise --max-output-bytes. No fields/defaults were truncated." % args.max_output_bytes)
        emit(report, args.max_output_bytes)


if __name__ == "__main__":
    try:
        main()
    except (CatalogError, OSError, RecursionError) as error:
        print("schema-catalog-error: " + str(error), file=sys.stderr)
        sys.exit(2)
