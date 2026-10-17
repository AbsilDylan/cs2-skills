#!/usr/bin/env python3
"""Discover a bounded page of native field names; not an authoring contract."""

import argparse
import importlib.util
import json
from pathlib import Path
import sys


CATALOG_SCRIPT = Path(__file__).resolve().with_name("schema_catalog.py")
SPEC = importlib.util.spec_from_file_location("_source2_discovery_catalogue", CATALOG_SCRIPT)
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)
DEFAULT_CATALOGUE = CATALOG_SCRIPT.parent.parent / "references"
MAX_OUTPUT_BYTES = 128 * 1024


def native_type_label(value, depth=0):
    """Display reflection identities only; complete type trees stay in exact queries."""
    if depth > 64 or not isinstance(value, dict):
        raise catalog.CatalogError("Invalid or excessively nested field type")
    category = value.get("category", "unknown")
    name = value.get("name")
    if category in ("declared_class", "declared_enum"):
        kind = "class" if category == "declared_class" else "enum"
        return kind + " " + str(value.get("module", "<unscoped>")) + "/" + str(name or "<unnamed>")
    if category == "builtin":
        return str(name or "<unnamed builtin>")
    if category == "atomic":
        label = "atomic " + str(name or "<unnamed>")
        return label + ("<" + native_type_label(value["inner"], depth + 1) + ">" if "inner" in value else "")
    if category == "ptr":
        return "ptr<" + native_type_label(value.get("inner"), depth + 1) + ">"
    if category == "fixed_array":
        return "array[" + str(value.get("count", "?")) + "]<" + native_type_label(value.get("inner"), depth + 1) + ">"
    if category == "bitfield":
        return "bitfield[" + str(value.get("count", "?")) + "]"
    return "unknown category " + str(category) + (" " + str(name) if name else "")


def discover(catalogue, module, class_name, contains="", limit=20, offset=0):
    if not 1 <= limit <= 100 or offset < 0:
        raise catalog.CatalogError("Discovery requires limit 1..100 and a non-negative offset")
    index = catalog.read_catalogue(catalogue)
    if catalog.digest(CATALOG_SCRIPT.read_bytes()) != index["generator"]["sha256"]:
        raise catalog.CatalogError("Generator script differs from the generated catalogue")
    item = next((entry for entry in index["records"] if (entry["kind"], entry["module"], entry["name"]) == ("class", module, class_name)), None)
    if item is None:
        raise catalog.CatalogError("Exact class identity absent: " + module + "/" + class_name)
    listed = next((entry for entry in index["files"] if entry["path"] == item["path"]), None)
    data = catalog.safe_path(catalogue, item["path"]).read_bytes()
    if listed is None or len(data) != listed["bytes"] or catalog.digest(data) != item["sha256"] or item["sha256"] != listed["sha256"]:
        raise catalog.CatalogError("Reference hash/length mismatch: " + item["path"])
    record = json.loads(data)
    if record.get("format") != "source2-particle-class-reference/1" or record.get("identity") != {"module": module, "name": class_name}:
        raise catalog.CatalogError("Class reference identity/format mismatch")
    matches = [entry for entry in record["fields"] if contains.casefold() in entry["field"]["name"].casefold()]
    fields = [{"name": entry["field"]["name"], "native_type": native_type_label(entry["field"]["type"]), "declared_in": entry["declared_in"], "inherited": entry["inherited"]} for entry in matches[offset:offset + limit]]
    return {
        "format": "source2-particle-field-discovery/1",
        "partial": True,
        "selection": "Discovery page only. native_type is a display label, not a complete type tree; metadata and defaults are omitted. For authoring use schema_catalog.py query with exact --field names.",
        "identity": record["identity"],
        "provenance": {**index["provenance"], "index_content_sha256": index["index_content_sha256"], "class_reference_sha256": item["sha256"]},
        "contains": contains, "match": "case-insensitive substring of field name",
        "total_fields": len(record["fields"]), "total": len(matches), "offset": offset, "limit": limit,
        "next_offset": offset + limit if offset + limit < len(matches) else None,
        "fields": fields,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument("--module", required=True)
    parser.add_argument("--class", dest="class_name", required=True)
    parser.add_argument("--contains", default="", help="Case-insensitive substring of the field name")
    parser.add_argument("--limit", type=int, default=20, help="Page size 1..100; default 20")
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        result = discover(args.catalogue, args.module, args.class_name, args.contains, args.limit, args.offset)
        data = (json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
        if len(data) > MAX_OUTPUT_BYTES:
            raise catalog.CatalogError("Discovery page exceeds 128 KiB; lower --limit or use --contains. No output was truncated.")
    except (catalog.CatalogError, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        print("schema-discovery-error: " + str(error), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
