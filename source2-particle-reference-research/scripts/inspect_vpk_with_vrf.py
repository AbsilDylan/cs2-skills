#!/usr/bin/env python3
"""Inspect selected or all local VPK particles with an explicitly installed VRF CLI.

Uses Python 3.10+ and its standard library. Writes a new local research snapshot;
never overwrites archives or downloads tools.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from vpk_reference import Vpk, VpkError, _is_link, _regular_file
from process_limits import bounded_process

MAX_ENTRY = 16 * 1024 * 1024
MAX_READ = 512 * 1024 * 1024
MAX_TEXT = 16 * 1024 * 1024
MAX_TEXT_TOTAL = 2 * 1024 * 1024 * 1024
MAX_REPORT = 32 * 1024 * 1024
MAX_FILES = 20_000


class InspectionError(ValueError):
    pass


def write_new(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)


def file_identity(path: Path) -> dict:
    with _regular_file(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        if size > 128 * 1024 * 1024:
            raise InspectionError("VRF executable or assembly exceeds 128 MiB")
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {"file": path.name, "bytes": size, "sha256": digest.hexdigest()}


def tool_identity(executable: Path, timeout: int) -> tuple[list[str], dict, bytes]:
    executable = executable.absolute()
    identity = file_identity(executable)
    companion = executable.with_suffix(".dll")
    if executable.suffix.lower() == ".exe" and companion.exists():
        identity["companionAssembly"] = file_identity(companion)
    command = ["dotnet", str(executable)] if executable.suffix.lower() == ".dll" else [str(executable)]
    help_result = bounded_process(command + ["--help"], timeout, 128 * 1024, 128 * 1024)
    version_result = bounded_process(command + ["--version"], timeout, 16 * 1024, 16 * 1024)
    for result in (help_result, version_result):
        if result["exitCode"] or result["timedOut"] or result["outputLimitExceeded"]:
            raise InspectionError("Installed VRF help/version probe failed, timed out or exceeded its output limit")
    help_text = help_result["stdout"].decode("utf-8", errors="replace")
    if not all(flag in help_text for flag in ("--input", "--block")):
        raise InspectionError("Installed VRF help does not advertise --input and --block; inspect its interface manually")
    version = version_result["stdout"].decode("utf-8", errors="replace").strip()
    if not version:
        raise InspectionError("Installed VRF --version produced no version text")
    return command, {**identity, "versionOutput": version,
                     "helpSha256": hashlib.sha256(help_result["stdout"]).hexdigest(),
                     "argumentsVerifiedFromHelp": ["--input", "--block"]}, help_result["stdout"]


def data_format(transcript: bytes) -> str:
    try:
        text = transcript.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InspectionError("VRF DATA transcript is not UTF-8") from exc
    header = re.search(r"<!--\s*kv3\s+[^\r\n]{1,4096}?\s*-->", text)
    if not header:
        raise InspectionError("VRF output has no bounded text KV3 header")
    format_match = re.search(r"\bformat:(vpcf[0-9]*)\s*:", header.group())
    if not format_match or not text[header.end():].lstrip().startswith("{"):
        raise InspectionError("VRF output is not a recognized particle KV3 DATA document")
    return format_match.group(1)


def fresh_directory(output: Path, archive: Vpk):
    output = output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise InspectionError("Output must be a new directory with an existing parent")
    for ancestor in (output.parent, *output.parent.parents):
        if _is_link(ancestor.lstat()):
            raise InspectionError("Output ancestors cannot be symlinks or reparse points")
    if output.resolve().is_relative_to(archive.path.parent.resolve()):
        raise InspectionError("Choose a work directory outside the source archive directory")
    output.mkdir()
    (output / "data").mkdir()
    (output / "logs").mkdir()
    return output


def manifest_identity(path: Path | None) -> dict | None:
    if path is None:
        return None
    with _regular_file(path) as stream:
        if os.fstat(stream.fileno()).st_size > 1024 * 1024:
            raise InspectionError("Steam manifest exceeds 1 MiB")
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise InspectionError("Steam manifest exceeds 1 MiB")
    text = raw.decode("utf-8-sig")
    values = {}
    for key in ("appid", "buildid"):
        matches = re.findall(r'"' + key + r'"\s*"([0-9]+)"', text, re.IGNORECASE)
        if len(matches) != 1:
            raise InspectionError(f"Steam manifest must contain exactly one {key}")
        values[key] = matches[0]
    return {"file": path.name, "steamAppId": values["appid"], "steamBuildId": values["buildid"],
            "sha256": hashlib.sha256(raw).hexdigest(), "binding": "local metadata, not a cryptographic binding to the VPK"}


def inspect(archive: Vpk, vrf: Path, output: Path, game: str, names: list[str] | None,
            maximum_files: int = 64, timeout: int = 30, maximum_text_total: int = 512 * 1024 * 1024,
            manifest: Path | None = None) -> dict:
    if not 1 <= maximum_files <= MAX_FILES or not 1 <= timeout <= 60 or not 1 <= maximum_text_total <= MAX_TEXT_TOTAL:
        raise InspectionError("Limits: files 1..20000, timeout 1..60 seconds, total text 1..2147483648 bytes")
    if names is not None:
        if not names or len(names) > maximum_files or len(set(name.casefold() for name in names)) != len(names):
            raise InspectionError("Explicit selection must be nonempty, unique and within --max-files")
        selected = [archive.find(name) for name in names]
        if any(not entry.path.lower().endswith(".vpcf_c") for entry in selected):
            raise InspectionError("This helper accepts particle .vpcf_c entries only")
        matching = len(selected)
    else:
        all_particles = sorted((entry for entry in archive.entries.values() if entry.path.lower().endswith(".vpcf_c")), key=lambda entry: entry.path)
        matching = len(all_particles)
        selected = all_particles[:maximum_files]
    steam = manifest_identity(manifest)
    command, tool, help_bytes = tool_identity(vrf, timeout)
    output = fresh_directory(output, archive)
    write_new(output / "vrf-help.txt", help_bytes)
    report = {"schema": "source2-vpk-vrf-inspection.v1", "game": game,
              "archive": archive.provenance(), "steam": steam, "tool": tool,
              "method": {"scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "bundledScriptSha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                                 for name in ("inspect_vpk_with_vrf.py", "vpk_reference.py", "process_limits.py")},
                         "arguments": ["--input", "LOCAL_TEMPORARY_PARTICLE", "--block", "DATA"],
                         "payloadCrc32Required": True, "payloadsRetained": False,
                         "textIsVrfTranscript": True, "historicalCatalogReproduction": False},
              "limits": {"maxFiles": maximum_files, "maxPayloadBytes": MAX_ENTRY, "maxTotalPayloadBytes": MAX_READ,
                         "maxTextBytesPerFile": MAX_TEXT, "maxTotalTextBytes": maximum_text_total, "timeoutSecondsPerInvocation": timeout},
              "coverage": {"matching": matching, "selected": len(selected), "attempted": 0, "decoded": 0,
                           "failed": 0, "payloadBytesRead": 0, "payloadBytesBudgeted": 0,
                           "textBytesWritten": 0, "selectionTruncated": matching > len(selected)},
              "limitations": ["Independent VRF text inspection, not reproduction of the historical binary-IR class aggregates.",
                              "DATA text and field presence do not prove defaults, valid ranges, runtime behavior or native appearance."],
              "entries": []}
    coverage = report["coverage"]
    for number, entry in enumerate(selected, 1):
        size = entry.length + len(entry.preload)
        if (size <= MAX_ENTRY and coverage["payloadBytesBudgeted"] + size > MAX_READ) or coverage["textBytesWritten"] >= maximum_text_total:
            coverage["stoppedAtLimit"] = True
            break
        coverage["attempted"] += 1
        result = {**entry.metadata(), "status": "failed"}
        try:
            if size > MAX_ENTRY:
                raise InspectionError("Selected payload exceeds the 16 MiB limit")
            # Failed CRC/short reads still consume the conservative read budget.
            coverage["payloadBytesBudgeted"] += size
            payload = archive.read(entry)
            coverage["payloadBytesRead"] += len(payload)
            result.update(sha256=hashlib.sha256(payload).hexdigest(), crc32Verified=True)
            with tempfile.TemporaryDirectory(prefix="staging-", dir=output) as staging:
                source = Path(staging) / "particle.vpcf_c"
                write_new(source, payload)
                process = bounded_process(command + ["--input", str(source), "--block", "DATA"], timeout)
            stdout, stderr = process.pop("stdout"), process.pop("stderr")
            result["process"] = process
            result["stdoutSha256"] = hashlib.sha256(stdout).hexdigest()
            result["stderrSha256"] = hashlib.sha256(stderr).hexdigest()
            if stderr:
                if coverage["textBytesWritten"] + len(stderr) > maximum_text_total:
                    coverage["stoppedAtLimit"] = True
                    raise InspectionError("VRF diagnostics exceed the remaining total-text budget")
                write_new(output / "logs" / f"{number:06d}.stderr.txt", stderr)
                result["stderrTranscript"] = f"logs/{number:06d}.stderr.txt"
                coverage["textBytesWritten"] += len(stderr)
            if process["exitCode"] or process["timedOut"] or process["outputLimitExceeded"]:
                raise InspectionError("VRF failed, timed out or exceeded the per-file output limit")
            if coverage["textBytesWritten"] + len(stdout) > maximum_text_total:
                coverage["stoppedAtLimit"] = True
                raise InspectionError("VRF transcript exceeds the remaining total-text budget")
            format_name = data_format(stdout)
            relative = f"data/{number:06d}.vrf-data.txt"
            write_new(output / relative, stdout)
            coverage["textBytesWritten"] += len(stdout)
            result.update(status="decoded", dataFormat=format_name, transcript=relative, transcriptBytes=len(stdout))
            coverage["decoded"] += 1
        except (OSError, VpkError, InspectionError, UnicodeError) as exc:
            result["error"] = str(exc)[:1024]
            coverage["failed"] += 1
        report["entries"].append(result)
        if coverage.get("stoppedAtLimit"):
            break
    coverage["complete"] = coverage["attempted"] == matching and coverage["decoded"] == matching
    encoded = (json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_REPORT:
        raise InspectionError("Inspection report exceeds 32 MiB; select a smaller batch")
    with (output / "inspection.json").open("xb") as stream:
        stream.write(encoded)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vpk", required=True, type=Path)
    parser.add_argument("--vrf", required=True, type=Path, help="Installed Source2Viewer-CLI executable or assembly; no download")
    parser.add_argument("--output", required=True, type=Path, help="New local work directory; existing parent required")
    parser.add_argument("--game", required=True, help="Game label recorded with the observations")
    parser.add_argument("--manifest", type=Path, help="Optional installed Steam appmanifest for build provenance")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--entry", action="append", help="Exact indexed .vpcf_c path; repeat for a targeted batch")
    selection.add_argument("--all-particles", action="store_true", help="Select every indexed .vpcf_c, subject to the explicit bounds")
    parser.add_argument("--max-files", type=int, default=64, help="1..20000; full scans must explicitly raise the default 64")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="1..60, per VRF invocation")
    parser.add_argument("--max-total-text-bytes", type=int, default=512 * 1024 * 1024, help="Total transcript budget, at most 2147483648")
    args = parser.parse_args(argv)
    try:
        report = inspect(Vpk(args.vpk), args.vrf, args.output, args.game, args.entry, args.max_files,
                         args.timeout_seconds, args.max_total_text_bytes, args.manifest)
        print(json.dumps({"schema": report["schema"], "game": report["game"], "coverage": report["coverage"]}, indent=2))
        return 0 if report["coverage"]["complete"] else 2
    except (OSError, VpkError, InspectionError, UnicodeError) as exc:
        print(f"inspect_vpk_with_vrf: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
