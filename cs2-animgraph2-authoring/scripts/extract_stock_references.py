#!/usr/bin/env python3
"""Discover and extract current stock references with Source2Viewer CLI.

The cache is accepted only when its VPK, VRF executable, exact VPK receipt and
all output hashes match the previous extraction report. Extracted Valve files
remain local and must never be redistributed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from animgraph2_manifest import (
    ManifestError,
    ProcessLockSet,
    load_manifest,
    normalize_resource_path,
    probe_versioned_receipt_create,
    reference_dmx_relative,
    reference_vnmclip_relative,
    resolve_cs2_root,
    resolve_tool,
    selected_sets,
    sha256_file,
    write_json,
    write_json_new,
)


def run(command: list[str], *, timeout_seconds: int = 600) -> str:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {timeout_seconds}s: {' '.join(command)}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
    return result.stdout


def resolve_runtime(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    cs2_root = resolve_cs2_root(args.cs2_root)
    vrf = resolve_tool(
        args.vrf_cli,
        ("VRF_CLI", "SOURCE2VIEWER_CLI"),
        None,
        "Source2Viewer/ValveResourceFormat CLI",
    )
    pak = (
        Path(args.pak).expanduser().resolve()
        if args.pak
        else cs2_root / "game" / "csgo" / "pak01_dir.vpk"
    )
    if not pak.is_file():
        raise ManifestError(f"VPK not found: {pak}")
    return cs2_root, vrf, pak


def list_resources(args: argparse.Namespace) -> int:
    _, vrf, pak = resolve_runtime(args)
    command = [str(vrf), "-i", str(pak), "--vpk_list"]
    if args.prefix:
        command.extend(("--vpk_filepath", args.prefix.replace("\\", "/")))
    output = run(command)
    matcher = re.compile(args.regex, re.IGNORECASE) if args.regex else None
    extensions = {
        extension.lower().lstrip(".") for extension in (args.extensions or [])
    }
    matches = []
    for line in output.splitlines():
        resource = line.split(" CRC:", 1)[0].strip()
        if not resource:
            continue
        if matcher and not matcher.search(resource):
            continue
        if extensions and resource.rsplit(".", 1)[-1].lower() not in extensions:
            continue
        matches.append(line)
    print("\n".join(matches))
    print(f"\nMatched {len(matches)} resource(s).", file=sys.stderr)
    return 0


def unique_references(animation_sets: list[dict]) -> list[str]:
    return sorted(
        {
            action["reference_resource"].replace("\\", "/")
            for animation_set in animation_sets
            for action in animation_set["actions"]
        },
        key=str.casefold,
    )


def extraction_jobs(data: dict, animation_sets: list[dict]) -> list[dict]:
    """Merge duplicate resources instead of silently replacing one job."""

    jobs: dict[str, dict[str, Any]] = {}

    def add_job(kind: str, resource: str, outputs: list[str]) -> None:
        key = resource.casefold()
        job = jobs.setdefault(
            key,
            {"kinds": [], "resource": resource, "outputs": []},
        )
        if job["resource"].casefold() != resource.casefold():
            raise ManifestError(f"case-colliding extraction resources: {resource}")
        if kind not in job["kinds"]:
            job["kinds"].append(kind)
        existing = {value.casefold() for value in job["outputs"]}
        for output in outputs:
            if output.casefold() not in existing:
                job["outputs"].append(output)
                existing.add(output.casefold())

    for resource in unique_references(animation_sets):
        add_job(
            "vnmclip-reference",
            resource,
            [reference_dmx_relative(resource), reference_vnmclip_relative(resource)],
        )
    for dependency in data.get("stock_dependencies", []):
        add_job(
            "stock-dependency",
            dependency["resource"],
            list(dependency["outputs"]),
        )
    result = []
    for key in sorted(jobs):
        job = jobs[key]
        job["kind"] = "+".join(job["kinds"])
        result.append(job)
    return result


def output_path(root: Path, resource: str) -> Path:
    return root.joinpath(*PurePosixPath(resource).parts)


def exact_vpk_receipt(listing: str, resource: str) -> str:
    matches = [
        line.strip()
        for line in listing.splitlines()
        if line.split(" CRC:", 1)[0].strip().casefold() == resource.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one VPK receipt for {resource}, found {len(matches)}"
        )
    return matches[0]


def read_previous_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def cache_entry_is_current(
    previous: dict[str, Any] | None,
    *,
    vpk_sha256: str,
    vrf_sha256: str,
    resource: str,
    receipt: str,
    output_root: Path,
    outputs: list[str],
) -> bool:
    if not previous:
        return False
    if previous.get("vpk_sha256") != vpk_sha256:
        return False
    if previous.get("vrf_cli_sha256") != vrf_sha256:
        return False
    row = next(
        (
            value
            for value in previous.get("resources", [])
            if isinstance(value, dict)
            and str(value.get("resource", "")).casefold() == resource.casefold()
        ),
        None,
    )
    if not row or row.get("vpk_receipt") != receipt:
        return False
    recorded = {
        str(value.get("resource", "")).casefold(): value
        for value in row.get("outputs", [])
        if isinstance(value, dict)
    }
    for relative in outputs:
        path = output_path(output_root, relative)
        record = recorded.get(relative.casefold())
        if not record or not path.is_file():
            return False
        if record.get("sha256") != sha256_file(path):
            return False
    return True


def verify_reference_cache(
    reference_root: Path,
    manifest_path: Path,
    required_outputs: list[str],
    *,
    allow_unverified: bool = False,
) -> dict[str, Any]:
    """Fail closed unless the latest extraction receipt proves the local cache."""

    reference_root = reference_root.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    report_path = reference_root / "reference-extraction-report.json"
    try:
        report = read_previous_report(report_path)
        if report is None:
            raise ManifestError(f"reference extraction receipt missing/invalid: {report_path}")
        manifest_sha256 = sha256_file(manifest_path)
        if report.get("manifest_sha256") != manifest_sha256:
            raise ManifestError("reference cache manifest hash does not match this manifest")
        recorded_root = Path(str(report.get("output_root", ""))).expanduser().resolve()
        if recorded_root != reference_root:
            raise ManifestError(
                f"reference cache root differs from receipt: {reference_root} != {recorded_root}"
            )

        provenance: dict[str, dict[str, Any]] = {}
        for label, path_key, hash_key in (
            ("VPK", "vpk", "vpk_sha256"),
            ("VRF CLI", "vrf_cli", "vrf_cli_sha256"),
        ):
            raw_path = report.get(path_key)
            expected_hash = report.get(hash_key)
            if not isinstance(raw_path, str) or not raw_path:
                raise ManifestError(f"reference receipt lacks {label} path")
            path = Path(raw_path).expanduser().resolve()
            if not path.is_file():
                raise ManifestError(f"receipt-bound {label} is missing: {path}")
            actual_hash = sha256_file(path)
            if not isinstance(expected_hash, str) or actual_hash != expected_hash:
                raise ManifestError(f"receipt-bound {label} hash changed: {path}")
            provenance[label] = {"path": str(path), "sha256": actual_hash}

        verified_outputs: dict[str, dict[str, Any]] = {}
        rows = report.get("resources")
        if not isinstance(rows, list) or not rows:
            raise ManifestError("reference extraction receipt has no resource rows")
        for row in rows:
            if not isinstance(row, dict):
                raise ManifestError("reference extraction receipt has an invalid resource row")
            resource = normalize_resource_path(
                row.get("resource"), field="reference receipt resource"
            )
            receipt = row.get("vpk_receipt")
            if not isinstance(receipt, str) or " CRC:" not in receipt:
                raise ManifestError(f"reference receipt lacks an exact CRC line for {resource}")
            exact_vpk_receipt(receipt, resource)
            outputs = row.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                raise ManifestError(f"reference receipt has no outputs for {resource}")
            for output in outputs:
                if not isinstance(output, dict):
                    raise ManifestError(f"invalid output receipt for {resource}")
                relative = normalize_resource_path(
                    output.get("resource"), field="reference receipt output"
                )
                key = relative.casefold()
                if key in verified_outputs:
                    raise ManifestError(f"duplicate output in reference receipt: {relative}")
                expected_path = output_path(reference_root, relative).resolve()
                recorded_path = Path(str(output.get("path", ""))).expanduser().resolve()
                if recorded_path != expected_path:
                    raise ManifestError(
                        f"reference output path differs from receipt root: {relative}"
                    )
                if not expected_path.is_file():
                    raise ManifestError(f"reference output is missing: {expected_path}")
                actual_hash = sha256_file(expected_path)
                if output.get("sha256") != actual_hash:
                    raise ManifestError(f"reference output hash changed: {relative}")
                verified_outputs[key] = {
                    "resource": relative,
                    "path": str(expected_path),
                    "sha256": actual_hash,
                }

        normalized_required = [
            normalize_resource_path(value, field="required reference output")
            for value in required_outputs
        ]
        missing = [
            value for value in normalized_required if value.casefold() not in verified_outputs
        ]
        if missing:
            raise ManifestError(f"reference extraction receipt lacks required outputs: {missing}")
        return {
            "status": "verified",
            "verified": True,
            "allow_unverified": False,
            "report": str(report_path),
            "report_sha256": sha256_file(report_path),
            "manifest_sha256": manifest_sha256,
            "vpk": provenance["VPK"],
            "vrf_cli": provenance["VRF CLI"],
            "required_outputs": [
                verified_outputs[value.casefold()] for value in normalized_required
            ],
        }
    except (ManifestError, OSError, RuntimeError, TypeError, ValueError) as exc:
        if not allow_unverified:
            if isinstance(exc, ManifestError):
                raise
            raise ManifestError(f"reference cache verification failed: {exc}") from exc
        return {
            "status": "unverified-allowed",
            "verified": False,
            "allow_unverified": True,
            "report": str(report_path),
            "reason": str(exc),
            "required_outputs": list(required_outputs),
        }


def atomic_copy(source: Path, destination: Path) -> dict[str, Any]:
    before = (
        {"exists": True, "sha256": sha256_file(destination)}
        if destination.is_file()
        else {"exists": False}
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp"
    )
    shutil.copy2(source, temporary)
    temporary.replace(destination)
    return {
        "destination_before": before,
        "destination_after": {
            "exists": True,
            "sha256": sha256_file(destination),
        },
    }


def extract_resources(args: argparse.Namespace) -> int:
    cs2_root, vrf, pak = resolve_runtime(args)
    manifest_path, data = load_manifest(args.manifest)
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else manifest_path.parent / ".local" / "references"
    )
    with ProcessLockSet([manifest_path.parent, output_root]):
        return _extract_resources_locked(
            args, cs2_root, vrf, pak, manifest_path, data, output_root
        )


def _extract_resources_locked(
    args: argparse.Namespace,
    cs2_root: Path,
    vrf: Path,
    pak: Path,
    manifest_path: Path,
    data: dict[str, Any],
    output_root: Path,
) -> int:
    animation_sets = selected_sets(data, args.sets)
    output_root.mkdir(parents=True, exist_ok=True)
    receipt_create_method = probe_versioned_receipt_create(output_root)
    report_path = output_root / "reference-extraction-report.json"
    previous = read_previous_report(report_path)
    vpk_sha256 = sha256_file(pak)
    vrf_sha256 = sha256_file(vrf)

    rows = []
    for job in extraction_jobs(data, animation_sets):
        resource = job["resource"]
        listing = run(
            [
                str(vrf),
                "-i",
                str(pak),
                "--vpk_list",
                "--vpk_filepath",
                resource,
            ]
        )
        receipt = exact_vpk_receipt(listing, resource)
        cached = cache_entry_is_current(
            previous,
            vpk_sha256=vpk_sha256,
            vrf_sha256=vrf_sha256,
            resource=resource,
            receipt=receipt,
            output_root=output_root,
            outputs=job["outputs"],
        )
        status = "cached" if cached and not args.force else "extracted"
        writes: list[dict[str, Any]] = []
        if status == "extracted":
            with tempfile.TemporaryDirectory(
                prefix="cs2-reference-extract-", dir=output_root.parent
            ) as temp_name:
                temp_root = Path(temp_name)
                run(
                    [
                        str(vrf),
                        "-i",
                        str(pak),
                        "--vpk_filepath",
                        resource,
                        "-o",
                        str(temp_root),
                        "-d",
                    ]
                )
                missing = [
                    str(output_path(temp_root, relative))
                    for relative in job["outputs"]
                    if not output_path(temp_root, relative).is_file()
                ]
                if missing:
                    raise RuntimeError(
                        f"VRF did not produce expected outputs for {resource}: {missing}"
                    )
                for relative in job["outputs"]:
                    source = output_path(temp_root, relative)
                    destination = output_path(output_root, relative)
                    write = atomic_copy(source, destination)
                    write["resource"] = relative
                    write["path"] = str(destination)
                    writes.append(write)

        expected = [output_path(output_root, path) for path in job["outputs"]]
        missing = [str(path) for path in expected if not path.is_file()]
        if missing:
            raise RuntimeError(
                f"reference cache is incomplete for {resource}: {missing}"
            )
        rows.append(
            {
                "kind": job["kind"],
                "kinds": job["kinds"],
                "resource": resource,
                "vpk_receipt": receipt,
                "status": status,
                "writes": writes,
                "outputs": [
                    {
                        "resource": relative,
                        "path": str(path),
                        "sha256": sha256_file(path),
                        "bytes": path.stat().st_size,
                    }
                    for relative, path in zip(job["outputs"], expected)
                ],
            }
        )
        print(f"{status}: {resource}")

    report = {
        "schema_version": 2,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "project": data["project"],
        "sets": [entry["id"] for entry in animation_sets],
        "cs2_root": str(cs2_root),
        "vpk": str(pak),
        "vpk_sha256": vpk_sha256,
        "vpk_size": pak.stat().st_size,
        "vpk_mtime_ns": pak.stat().st_mtime_ns,
        "vrf_cli": str(vrf),
        "vrf_cli_sha256": vrf_sha256,
        "output_root": str(output_root),
        "versioned_receipt_create_method": receipt_create_method,
        "license_notice": "Local Valve-derived references. Do not commit or redistribute.",
        "resources": rows,
    }
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    report["run_id"] = run_id
    immutable_report = output_root / f"reference-extraction-report-{run_id}.json"
    write_json_new(immutable_report, report)
    write_json(report_path, report)
    print(f"Report: {report_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cs2-root")
    common.add_argument("--vrf-cli")
    common.add_argument("--pak")

    list_parser = subparsers.add_parser(
        "list", parents=[common], help="List/filter stock VPK resources."
    )
    list_parser.add_argument("--prefix", default="animation/anims/")
    list_parser.add_argument("--regex")
    list_parser.add_argument("--extensions", nargs="*", default=["vnmclip_c"])
    list_parser.set_defaults(handler=list_resources)

    extract_parser = subparsers.add_parser(
        "extract", parents=[common], help="Extract references declared by a manifest."
    )
    extract_parser.add_argument("--manifest", required=True)
    extract_parser.add_argument("--set", dest="sets", action="append")
    extract_parser.add_argument("--output-root")
    extract_parser.add_argument("--force", action="store_true")
    extract_parser.set_defaults(handler=extract_resources)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.handler(args))
    except (ManifestError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
