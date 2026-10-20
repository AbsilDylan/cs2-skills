#!/usr/bin/env python3
"""Query the portable compiled-particle observations without loading them into chat.

Python 3.10+, standard library only. Reads local metadata, never game assets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024
INDEX_SCHEMA = "source2-particle-native-vpk-observations.v1"
CLASS_SCHEMA = "source2-particle-native-class-observation.v1"
DEFAULT_REFERENCES = Path(__file__).resolve().parent.parent / "references"
INCOMPLETE_EXTREMA_GENERATOR_SHA256 = "fe76359cdca2d96e6de0c99186338441694db19a27d8c3bd76267a302cf0a38e"


class QueryError(ValueError):
    pass


def read_bytes(path: Path, maximum: int = MAX_FILE_BYTES) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or getattr(before, "st_file_attributes", 0) & 0x400 or not stat.S_ISREG(before.st_mode):
        raise QueryError(f"Expected a regular non-link metadata file: {path.name}")
    if before.st_size > maximum:
        raise QueryError(f"Metadata file exceeds the {maximum}-byte limit: {path.name}")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise QueryError("Metadata file changed while opening")
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise QueryError(f"Metadata file exceeds the {maximum}-byte limit: {path.name}")
    return data


def decode_object(data: bytes) -> dict:
    def reject_constant(value):
        raise QueryError(f"Invalid non-finite JSON constant: {value}")
    try:
        value = json.loads(data.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QueryError("Invalid metadata JSON") from exc
    if not isinstance(value, dict):
        raise QueryError("Metadata JSON must be an object")
    return value


def checked_class(references: Path, descriptor: dict, game: str, stage: str, class_name: str) -> tuple[dict, dict]:
    if not isinstance(descriptor, dict):
        raise QueryError("Invalid class-file descriptor")
    name, size, digest = descriptor.get("path"), descriptor.get("bytes"), descriptor.get("sha256")
    if (not isinstance(name, str) or not name or len(name) > 4096 or "\\" in name or ":" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise QueryError("Unsafe class-file path")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts) or not name.endswith(".json"):
        raise QueryError("Unsafe class-file path")
    if type(size) is not int or not 0 < size <= MAX_FILE_BYTES:
        raise QueryError("Class-file descriptor exceeds the 4 MiB limit or has an invalid size")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise QueryError("Invalid class-file SHA-256 descriptor")
    path = references.joinpath(*parts)
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        raise QueryError("Cannot resolve class-file path") from exc
    if not resolved.is_relative_to(references):
        raise QueryError("Class-file path resolves outside the references directory")
    raw = read_bytes(path)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise QueryError(f"Class-file size or SHA-256 mismatch: {name}")
    document = decode_object(raw)
    observation = document.get("classObservation")
    if document.get("schema") != CLASS_SCHEMA or document.get("game") != game or not isinstance(observation, dict):
        raise QueryError("Class-file identity or schema mismatch")
    if observation.get("class") != class_name or observation.get("stage") != stage or not isinstance(observation.get("fields"), dict):
        raise QueryError("Class-file observation does not match its index entry")
    return observation, {"path": name, "bytes": size, "sha256": digest, "verified": True}


def query(references: Path, game: str, class_name: str | None = None, stage: str | None = None,
          field: str | None = None, search: str | None = None, limit: int = 20) -> dict:
    if game not in ("cs2", "deadlock") or not 1 <= limit <= 100:
        raise QueryError("Choose game cs2/deadlock and limit 1..100")
    if (class_name is None) == (search is None) or field is not None and class_name is None:
        raise QueryError("Choose exactly one of class or search; an exact field requires an exact class")
    references = Path(references).resolve()
    raw_index = read_bytes(references / "native-vpk-observations.json")
    index = decode_object(raw_index)
    if index.get("schema") != INDEX_SCHEMA or not isinstance(index.get("games"), list):
        raise QueryError("Unsupported observations index schema")
    selected_games = [item for item in index["games"] if isinstance(item, dict) and item.get("game") == game]
    if len(selected_games) != 1:
        raise QueryError(f"Game {game} is absent or duplicated in the observations index")
    selected = selected_games[0]
    # The historical binary-IR exporter omitted int64/uint64 values from its
    # extrema. Suppress those statistics even when reading an older explicit
    # --references snapshot that predates the published metadata correction.
    method = index.get("method")
    incomplete_extrema = isinstance(method, dict) and method.get("scriptSha256") == INCOMPLETE_EXTREMA_GENERATOR_SHA256
    class_files = selected.get("classFiles")
    witnesses = selected.get("witnesses")
    if not isinstance(class_files, dict) or not isinstance(witnesses, dict):
        raise QueryError("Invalid game observations index")
    matches = []
    for key, descriptor in sorted(class_files.items()):
        if not isinstance(key, str) or ":" not in key:
            raise QueryError("Invalid indexed class/stage key")
        candidate_stage, candidate_class = key.split(":", 1)
        if stage is not None and candidate_stage != stage:
            continue
        if class_name is not None and candidate_class != class_name:
            continue
        if search is not None and search.casefold() not in key.casefold():
            continue
        matches.append((candidate_stage, candidate_class, descriptor))
    if class_name is not None and not matches:
        raise QueryError(f"Class/stage not observed in {game}: {class_name}; this does not establish engine support")
    report = {
        "schema": "source2-particle-observation-query.v1", "game": game,
        "evidenceLevel": "compiled-asset-observation", "observedOn": index.get("observedOn"),
        "indexSha256": hashlib.sha256(raw_index).hexdigest(), "identity": selected.get("identity"),
        "coverage": selected.get("coverage"), "query": {"class": class_name, "stage": stage, "field": field, "search": search, "limit": limit},
        "matchedClasses": len(matches), "returnedClasses": min(len(matches), limit), "truncated": len(matches) > limit,
        "limitations": ["Stored observations do not establish defaults, valid ranges, behavior, visual fidelity or cross-game support."],
        "metadataCorrections": index.get("metadataCorrections", []),
        "results": [],
    }
    if incomplete_extrema:
        report["numericExtremaStatus"] = "unavailable: historical exporter omitted integer scalar representations"
        report["limitations"].append("Historical observedMin/observedMax are incomplete and are not returned; a short example cannot reconstruct the full extrema.")
    # Search intentionally consults class/stage names only: no 427-file scan.
    if search is not None:
        report["searchScope"] = "indexed class/stage names only; field names are not searched"
        report["classFilesVerified"] = False
        report["results"] = [{"class": name, "stage": owner, "classFile": descriptor}
                             for owner, name, descriptor in matches[:limit]]
        return report
    report["classFilesVerified"] = True
    field_found = False
    for owner, name, descriptor in matches[:limit]:
        observation, verified = checked_class(references, descriptor, game, owner, name)
        fields = observation["fields"]
        result = {"class": name, "stage": owner, "instances": observation.get("instances"),
                  "fieldCount": len(fields), "classFile": verified}
        if field is None:
            names = sorted(fields)
            result["fieldNames"] = names[:limit]
            result["fieldNamesTruncated"] = len(names) > limit
            paths = observation.get("witnesses", [])
            if not isinstance(paths, list):
                raise QueryError("Class observation witnesses must be an array")
            paths = paths[:limit]
        elif field in fields:
            field_found = True
            if not isinstance(fields[field], dict):
                raise QueryError("Selected field observation must be an object")
            field_observation = dict(fields[field])
            if incomplete_extrema:
                field_observation.pop("observedMin", None)
                field_observation.pop("observedMax", None)
            result["field"] = {"path": field, "observation": field_observation}
            paths = [fields[field].get("witness")]
        else:
            result["field"] = None
            paths = []
        result["witnesses"] = {}
        for path in paths:
            if not isinstance(path, str) or path not in witnesses:
                raise QueryError("A selected observation has no indexed payload witness")
            result["witnesses"][path] = witnesses[path]
        report["results"].append(result)
    if field is not None and not field_found:
        raise QueryError(f"Exact field not observed in the returned class/stage results: {field}; specify --stage if class results were truncated")
    return report


def encode_report(report: dict) -> str:
    try:
        text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    except (ValueError, RecursionError) as exc:
        raise QueryError("Cannot encode a finite bounded query result") from exc
    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise QueryError("Query output exceeds 128 KiB; request an exact --field or a smaller --limit")
    return text


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, choices=("cs2", "deadlock"))
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--class", dest="class_name", help="Exact case-sensitive class name; default output is a summary")
    selection.add_argument("--search", help="Case-insensitive literal substring of indexed class/stage names; does not scan fields")
    parser.add_argument("--stage", help="Exact case-sensitive stage, for example m_Renderers or system")
    parser.add_argument("--field", help="Exact class-local property path, with [] for array elements; requires --class")
    parser.add_argument("--limit", type=int, default=20, help="Maximum class matches and field-name/witness summaries, 1..100")
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES, help="Explicit local reference snapshot directory")
    args = parser.parse_args(argv)
    try:
        report = query(args.references, args.game, args.class_name, args.stage, args.field, args.search, args.limit)
        sys.stdout.write(encode_report(report))
        return 0
    except (OSError, QueryError) as exc:
        print(f"query_observations: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
