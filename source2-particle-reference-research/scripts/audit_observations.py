#!/usr/bin/env python3
"""Check every bundled observation record without a game install or network access.

This validates metadata consistency, not engine behavior or original payloads.
Only a fresh read of the matching VPK payload can verify a historical witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from query_observations import (
    DEFAULT_REFERENCES, INDEX_SCHEMA, QueryError, checked_class, decode_object,
    encode_report, read_bytes,
)

EXTREMA_CORRECTION = "remove-incomplete-numeric-extrema-2026-10-20"


def numeric_example(value):
    """Compare integer evidence exactly, including binary KV3 int64 tags."""
    if type(value) in (int, float):
        return value
    if isinstance(value, dict) and set(value) == {"$bigint"}:
        text = value["$bigint"]
        if isinstance(text, str) and re.fullmatch(r"-?\d+", text):
            return int(text)
    return None


def audit(references: Path) -> dict:
    references = Path(references).resolve()
    raw = read_bytes(references / "native-vpk-observations.json")
    index = decode_object(raw)
    if index.get("schema") != INDEX_SCHEMA or not isinstance(index.get("games"), list):
        raise QueryError("Unsupported observations index schema")
    corrections = index.get("metadataCorrections", [])
    if not isinstance(corrections, list):
        raise QueryError("Invalid metadata correction list")
    corrected = any(isinstance(item, dict) and item.get("id") == EXTREMA_CORRECTION
                    for item in corrections)
    issues = []
    reports = []
    seen_games = set()
    indexed_paths = set()
    class_sets = {}

    def issue(game, key, message, field=None):
        row = {"game": game, "classStage": key, "message": message}
        if field is not None:
            row["field"] = field
        issues.append(row)

    for correction in corrections:
        if not isinstance(correction, dict) or correction.get("id") != EXTREMA_CORRECTION:
            continue
        descriptor = correction.get("details", {})
        relative = descriptor.get("path", "") if isinstance(descriptor, dict) else ""
        parts = relative.split("/") if isinstance(relative, str) else []
        if (not parts or any(part in ("", ".", "..") for part in parts)
                or "\\" in relative or ":" in relative):
            issue(None, None, "Missing or unsafe correction provenance descriptor")
            continue
        target = references.joinpath(*parts).resolve()
        if not target.is_relative_to(references):
            raise QueryError("Correction provenance resolves outside references")
        data = read_bytes(target)
        if len(data) != descriptor.get("bytes") or hashlib.sha256(data).hexdigest() != descriptor.get("sha256"):
            raise QueryError("Correction provenance size or SHA-256 mismatch")
        details = decode_object(data)
        if (details.get("id") != EXTREMA_CORRECTION
                or details.get("sourceIndexSha256") != correction.get("sourceIndexSha256")
                or details.get("removedExtremaFields") != correction.get("removedExtremaFields")):
            issue(None, None, "Correction provenance disagrees with the index")
        previous = details.get("previousClassFiles")
        if not isinstance(previous, list):
            issue(None, None, "Missing previous class-file identities")
        elif any(not isinstance(row, dict) or type(row.get("removedExtremaFields")) is not int
                 for row in previous):
            issue(None, None, "Invalid previous class-file identity")
        elif (len(previous) != details.get("recordsChecked")
              or sum(row["removedExtremaFields"] for row in previous) != details.get("removedExtremaFields")):
            issue(None, None, "Correction provenance record totals disagree")

    for game in index["games"]:
        if not isinstance(game, dict) or not isinstance(game.get("game"), str):
            raise QueryError("Invalid game identity")
        name = game["game"]
        if name in seen_games:
            raise QueryError("Duplicate game in observations index")
        seen_games.add(name)
        descriptors, witnesses = game.get("classFiles"), game.get("witnesses")
        if not isinstance(descriptors, dict) or not isinstance(witnesses, dict):
            raise QueryError("Invalid class-file or witness index")
        for witness, identity in witnesses.items():
            if (not isinstance(witness, str) or not isinstance(identity, dict)
                    or type(identity.get("bytes")) is not int or identity["bytes"] <= 0
                    or not re.fullmatch(r"[0-9a-f]{64}", str(identity.get("sha256", "")))
                    or not re.fullmatch(r"0x[0-9a-f]{8}", str(identity.get("crc32", "")))):
                issue(name, None, "Invalid payload witness identity")
        field_count, instance_count, classes = 0, 0, set()
        for key, descriptor in descriptors.items():
            if not isinstance(key, str) or ":" not in key:
                raise QueryError("Invalid class/stage key")
            stage, class_name = key.split(":", 1)
            observation, verified = checked_class(references, descriptor, name, stage, class_name)
            indexed_paths.add(verified["path"])
            document = decode_object(read_bytes(references / verified["path"]))
            if document.get("steamBuildId") != game.get("identity", {}).get("steamBuildId"):
                issue(name, key, "Class-file build identity differs from its index")
            classes.add(class_name)
            instances = observation.get("instances")
            if type(instances) is not int or instances < 1:
                issue(name, key, "Invalid component instance count")
            else:
                instance_count += instances
            class_witnesses = observation.get("witnesses")
            if not isinstance(class_witnesses, list) or not class_witnesses:
                issue(name, key, "Missing class witnesses")
            elif any(w not in witnesses for w in class_witnesses):
                issue(name, key, "Class witness is absent from the payload index")
            for field, value in observation["fields"].items():
                field_count += 1
                if not isinstance(field, str) or not isinstance(value, dict):
                    issue(name, key, "Invalid field record")
                    continue
                count, kinds = value.get("occurrences"), value.get("kinds")
                if (type(count) is not int or count < 1 or not isinstance(kinds, dict)
                        or not kinds or any(type(n) is not int or n < 1 for n in kinds.values())
                        or sum(kinds.values()) != count):
                    issue(name, key, "Field occurrences do not match kind counts", field)
                if value.get("witness") not in witnesses:
                    issue(name, key, "Field witness is absent from the payload index", field)
                examples = value.get("examples")
                if not isinstance(examples, list) or len(examples) > 1:
                    issue(name, key, "Expected at most one bounded example", field)
                    continue
                if corrected and ("observedMin" in value or "observedMax" in value):
                    issue(name, key, "Withdrawn numeric extrema reintroduced", field)
                if "observedMin" in value or "observedMax" in value:
                    low, high = value.get("observedMin"), value.get("observedMax")
                    if type(low) not in (int, float) or type(high) not in (int, float) or low > high:
                        issue(name, key, "Invalid numeric extrema", field)
                    else:
                        for example in examples:
                            number = numeric_example(example)
                            if number is not None and not low <= number <= high:
                                issue(name, key, "Witness example lies outside reported extrema", field)
        coverage = game.get("coverage", {})
        actual = {"classStagePairs": len(descriptors), "uniqueClasses": len(classes),
                  "classFieldPaths": field_count}
        for field, count in actual.items():
            if coverage.get(field) != count:
                issue(name, None, f"Coverage {field} disagrees with the indexed records")
        reports.append({"game": name, **actual, "summedInstancesIncludingSystem": instance_count,
                        "indexedWitnesses": len(witnesses)})
        class_sets[name] = classes
    actual_paths = {p.relative_to(references).as_posix()
                    for p in (references / "observations").rglob("*.json")}
    if indexed_paths != actual_paths:
        issue(None, None, "Indexed class files and observation JSON files differ")
    summary = index.get("summary", {})
    if class_sets:
        union = set.union(*class_sets.values())
        if summary.get("uniqueClassesAcrossGames") != len(union):
            issue(None, None, "Cross-game unique class count disagrees with records")
    if set(class_sets) == {"cs2", "deadlock"}:
        for game, other, key in (
                ("cs2", "deadlock", "observedOnlyCs2Classes"),
                ("deadlock", "cs2", "observedOnlyDeadlockClasses")):
            if summary.get(key) != sorted(class_sets[game] - class_sets[other]):
                issue(game, None, "Cross-game observed-only class list disagrees with records")
    return {"schema": "source2-particle-observation-audit.v1",
            "indexSha256": hashlib.sha256(raw).hexdigest(),
            "metadataValid": not issues, "payloadsVerified": False,
            "runtimeBehaviorVerified": False, "numericExtremaWithdrawn": corrected,
            "games": reports, "issueCount": len(issues), "issues": issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    args = parser.parse_args(argv)
    try:
        result = audit(args.references)
        # Bound diagnostic output even for a damaged or old snapshot.
        if len(result["issues"]) > 100:
            result["issues"] = result["issues"][:100]
            result["issuesTruncated"] = True
        print(encode_report(result), end="")
        return 0 if result["metadataValid"] else 2
    except (OSError, QueryError) as exc:
        print(f"audit_observations: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
