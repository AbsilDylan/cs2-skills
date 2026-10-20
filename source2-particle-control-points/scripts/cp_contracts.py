#!/usr/bin/env python3
"""Query the bundled native CP schema subset using only Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REFERENCES = Path(__file__).resolve().parent.parent / "references"
MAX_DATA_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 256 * 1024


def load_catalogue():
    data_path = REFERENCES / "native-cp-contracts.json"
    if data_path.stat().st_size > MAX_DATA_BYTES:
        raise ValueError("Bundled CP catalogue exceeds the 4 MiB bound")
    data = data_path.read_bytes()
    expected = (REFERENCES / "native-cp-contracts.sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Bundled CP catalogue SHA-256 does not match")
    catalogue = json.loads(data)
    if catalogue.get("format") != "source2-native-cp-contracts/1":
        raise ValueError("Unsupported CP catalogue format")
    records = catalogue["records"]
    keys = [(record["kind"], record["identity"]["module"], record["identity"]["name"]) for record in records]
    if len(set(keys)) != len(keys):
        raise ValueError("Ambiguous catalogue identities")
    return catalogue


def query(catalogue, module, name, kind, field=None, summary=False):
    matches = [record for record in catalogue["records"] if record["kind"] == kind
               and record["identity"] == {"module": module, "name": name}]
    if len(matches) != 1:
        raise ValueError(f"No unique {kind} declaration for {module}::{name}")
    record = matches[0]
    if field is not None:
        if kind != "class":
            raise ValueError("--field applies to classes only")
        fields = [item for item in record["fields"] if item["name"] == field]
        if not fields:
            raise ValueError(f"No declared field {module}::{name}.{field}")
        defaults = record["defaults"]
        return {"identity": record["identity"], "fields": fields,
                "defaults": {"status": defaults["status"], "merge": defaults["merge"],
                             "issues": defaults["issues"], "value_present": field in defaults["values"],
                             "value": defaults["values"].get(field),
                             "source": defaults["sources"].get(field)},
                "source": record["source"], "evidence": record["evidence"]}
    if summary and kind == "class":
        return {"identity": record["identity"], "fields": [{"name": item["name"], "type": item["type"],
                "inherited": item["inherited"], "declared_in": item["declared_in"]} for item in record["fields"]],
                "defaults_status": record["defaults"]["status"], "source": record["source"],
                "evidence": record["evidence"]}
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--list", action="store_true")
    operation.add_argument("--class", dest="class_name")
    operation.add_argument("--enum", dest="enum_name")
    operation.add_argument("--verify", action="store_true")
    parser.add_argument("--module", help="Filter a listing by module; exact lookups default to particles")
    parser.add_argument("--field")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--contains", default="")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be between 1 and 500")
    if args.field and not args.class_name:
        parser.error("--field requires --class")
    catalogue = load_catalogue()
    if args.verify:
        result = {"valid": True, "counts": catalogue["counts"], "selection": catalogue["selection"],
                  "provenance": catalogue["provenance"]}
    elif args.list:
        records = [record for record in catalogue["records"]
                   if (args.module is None or record["identity"]["module"] == args.module)
                   and args.contains.casefold() in record["identity"]["name"].casefold()]
        result = {"total": len(records), "returned": min(len(records), args.limit),
                  "records": [{"kind": record["kind"], **record["identity"],
                               "selection": record["selection"]} for record in records[:args.limit]]}
    else:
        result = query(catalogue, args.module or "particles", args.class_name or args.enum_name,
                       "class" if args.class_name else "enum", args.field, args.summary)
    result = {"provenance": catalogue["provenance"], "result": result,
              "limitations": "Reflected CS2 declaration/defaults only; compiler retention, runtime math and visuals require separate native verification."}
    # ASCII JSON keeps all metadata round-trippable even on legacy Windows console encodings.
    output = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError("Output exceeds 256 KiB; request --summary or one exact --field")
    sys.stdout.write(output)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        sys.stderr.write(f"cp-contract-error: {error}\n")
        sys.exit(1)
