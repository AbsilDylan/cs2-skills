#!/usr/bin/env python3
"""Generate portable VNMClip sources from current-build stock templates.

The script preserves unknown fields from each decompiled reference, changes
only the source DMX, skeleton contract, and explicitly selected event policy,
then writes a hash receipt. It does not contain a hard-coded weapon or rig.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from animgraph2_manifest import (  # noqa: E402
    ManifestError,
    ProcessLockSet,
    load_manifest,
    probe_versioned_receipt_create,
    project_path,
    reference_dmx_relative,
    reference_vnmclip_relative,
    selected_sets,
    sha256_file,
    write_json,
    write_json_new,
)
from extract_stock_references import verify_reference_cache  # noqa: E402


class VnmclipRollbackFailure(RuntimeError):
    """A VNMClip commit failed and at least one rollback was not verified."""


def generation_failure_status(exc: BaseException) -> str:
    return "rollback-failed" if isinstance(exc, VnmclipRollbackFailure) else "failed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--set", dest="sets", action="append")
    parser.add_argument("--action", dest="actions", action="append")
    parser.add_argument("--reference-root")
    parser.add_argument(
        "--allow-missing-dmx",
        action="store_true",
        help="Generate descriptors before the manifest output_dmx files exist",
    )
    parser.add_argument(
        "--allow-unverified-reference-cache",
        action="store_true",
        help="Proceed without a valid extraction receipt and record the bypass",
    )
    return parser.parse_args()


def local_path(root: Path, resource: str) -> Path:
    return root.joinpath(*PurePosixPath(resource).parts)


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_balanced(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    raise ManifestError(f"unbalanced {opening}{closing} block in VNMClip template")


def field_span(text: str, field: str) -> tuple[int, int, str] | None:
    match = re.search(rf"(?m)^(?P<indent>[ \t]*){re.escape(field)}\s*=\s*", text)
    if not match:
        return None
    value_start = match.end()
    if value_start >= len(text):
        raise ManifestError(f"missing value for {field}")
    char = text[value_start]
    if char == "[":
        value_end = find_balanced(text, value_start, "[", "]")
    elif char == "{":
        value_end = find_balanced(text, value_start, "{", "}")
    elif char == '"':
        value_end = value_start + 1
        escaped = False
        while value_end < len(text):
            current = text[value_end]
            value_end += 1
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                break
        else:
            raise ManifestError(f"unterminated string value for {field}")
    else:
        newline = text.find("\n", value_start)
        value_end = len(text) if newline < 0 else newline
    return value_start, value_end, match.group("indent")


def replace_field(text: str, field: str, value: str) -> str:
    span = field_span(text, field)
    if span is None:
        root_end = text.rfind("}")
        if root_end < 0:
            raise ManifestError("VNMClip template has no root closing brace")
        return text[:root_end] + f"\t{field} = {value}\n" + text[root_end:]
    start, end, _ = span
    return text[:start] + value + text[end:]


def string_array(values: list[str], indent: str = "\t") -> str:
    if not values:
        return "[  ]"
    rendered = ",\n".join(f"{indent}\t{quote(value)}" for value in values)
    return f"[\n{rendered},\n{indent}]"


def load_event_array(event_file: Path) -> tuple[str, dict[str, Any]]:
    raw_text, state = _read_text_with_state(event_file, label="event track input")
    text = raw_text.strip()
    if not text.startswith("["):
        raise ManifestError(
            f"event track replacement must be a KV3 array literal: {event_file}"
        )
    if find_balanced(text, 0, "[", "]") != len(text):
        raise ManifestError(
            f"event track replacement contains trailing content: {event_file}"
        )
    return text, state


def action_filter(
    animation_set: dict[str, Any], requested: list[str] | None
) -> list[dict[str, Any]]:
    wanted = set(requested or [])
    available = {entry["id"] for entry in animation_set["actions"]}
    unknown = wanted - available
    if unknown:
        raise ManifestError(
            f"unknown action(s) for {animation_set['id']}: "
            f"{', '.join(sorted(unknown))}"
        )
    return [
        entry
        for entry in animation_set["actions"]
        if not wanted or entry["id"] in wanted
    ]


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_state(path: Path) -> dict[str, Any]:
    if path.exists() and not path.is_file():
        raise ManifestError(f"expected a file path, found another object: {path}")
    if not path.is_file():
        return {"exists": False}
    return {"exists": True, "sha256": sha256_file(path)}


def _file_identity(path: Path) -> dict[str, int] | None:
    """Return an identity token preserved by hard-link and rename publication."""

    if not path.is_file():
        return None
    stat = path.stat()
    if int(stat.st_ino) == 0:
        return None
    return {"device": int(stat.st_dev), "inode": int(stat.st_ino)}


def _read_text_with_state(path: Path, *, label: str) -> tuple[str, dict[str, Any]]:
    """Read one immutable logical input and bind the consumed bytes to a hash."""

    if not path.is_file():
        raise FileNotFoundError(f"missing {label}: {path}")
    raw = path.read_bytes()
    state = {
        "exists": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if _file_state(path) != state:
        raise ManifestError(f"{label} changed while it was being read: {path}")
    return raw.decode("utf-8"), state


def _temporary_sibling(path: Path, suffix: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=suffix, dir=path.parent
    )
    os.close(descriptor)
    return Path(name)


def _publish_file_no_replace(source: Path, destination: Path) -> str:
    """Move a staged file into an absent destination without clobbering a race."""

    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise ManifestError(
            "destination appeared during VNMClip publication; staged file "
            f"preserved: {source} -> {destination}"
        ) from exc
    except OSError as link_exc:
        if os.name != "nt":
            raise ManifestError(
                "safe VNMClip publication requires hard-link support on this "
                f"filesystem; staged file preserved: {source}"
            ) from link_exc
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise ManifestError(
                "destination appeared during VNMClip publication; staged file "
                f"preserved: {source} -> {destination}"
            ) from exc
        except OSError as rename_exc:
            raise ManifestError(
                "safe VNMClip publication failed; staged file "
                f"preserved: {source}"
            ) from rename_exc
        return "windows-no-replace-rename"
    source.unlink()
    return "hard-link"


def _best_effort_unlink(path: Path) -> str | None:
    try:
        if path.exists():
            path.unlink()
    except BaseException as exc:
        return f"{path}: {type(exc).__name__}: {exc}"
    return None


def _publish_validated_copy_no_replace(
    source: Path,
    destination: Path,
    expected_state: dict[str, Any],
) -> str:
    """Publish a verified copy while retaining the unique recovery source.

    Never hard-link ``source`` itself. A private copy is verified before it is
    handed to the no-replace primitive, so a hard link can never expose the
    only rollback preimage to writes through ``destination``.
    """

    if not expected_state.get("exists"):
        raise ManifestError("cannot publish a copy for a missing expected state")
    if _file_state(source) != expected_state:
        raise ManifestError(
            f"VNMClip recovery source changed before copy publication: {source}"
        )
    pending = _temporary_sibling(destination, ".restore-pending")
    try:
        shutil.copy2(source, pending)
        if _file_state(source) != expected_state:
            raise ManifestError(
                f"VNMClip recovery source changed while copying: {source}"
            )
        if _file_state(pending) != expected_state:
            raise ManifestError(
                f"VNMClip recovery copy hash mismatch: {source} -> {pending}"
            )
        method = _publish_file_no_replace(pending, destination)
        if _file_state(destination) != expected_state:
            raise ManifestError(
                f"VNMClip recovery publication hash mismatch: {destination}"
            )
        if _file_state(source) != expected_state:
            raise ManifestError(
                f"VNMClip recovery source changed during publication: {source}"
            )
        return method
    finally:
        warning = _best_effort_unlink(pending)
        if warning:
            print(f"WARNING: VNMClip recovery cleanup failed: {warning}", file=sys.stderr)


def prepare_one(
    manifest_path: Path,
    reference_root: Path,
    animation_set: dict[str, Any],
    action: dict[str, Any],
    *,
    allow_missing_dmx: bool,
) -> dict[str, Any]:
    template_relative = reference_vnmclip_relative(action["reference_resource"])
    template = local_path(reference_root, template_relative)
    if not template.is_file():
        raise FileNotFoundError(
            f"missing decompiled VNMClip template: {template}; "
            "run extract_stock_references.py extract first"
        )
    output_dmx = project_path(
        manifest_path,
        action["output_dmx"],
        field=f"{animation_set['id']}.{action['id']}.output_dmx",
    )
    if not allow_missing_dmx and not output_dmx.is_file():
        raise FileNotFoundError(
            f"generated DMX is missing: {output_dmx}; run blender_export_dmx.py first"
        )

    text, template_state = _read_text_with_state(
        template, label="decompiled VNMClip template"
    )
    source_filename = action["output_dmx"].replace("/", "\\")
    text = replace_field(text, "m_sourceFilename", quote(source_filename))
    text = replace_field(
        text,
        "m_animationSkeletonName",
        quote(animation_set["primary_skeleton"]),
    )
    text = replace_field(
        text,
        "m_secondaryAnimationSkeletonNames",
        string_array(list(animation_set.get("secondary_skeletons", []))),
    )
    event_policy = action.get("event_policy", "clear")
    event_file_resource = action.get("event_tracks_file")
    event_file_path = (
        project_path(
            manifest_path,
            event_file_resource,
            field=f"{action['id']}.event_tracks_file",
        )
        if event_file_resource
        else None
    )
    event_state: dict[str, Any] | None = None
    if event_policy == "clear":
        text = replace_field(text, "m_eventTracks", "[  ]")
    elif event_policy == "replace":
        if event_file_path is None:
            raise ManifestError(
                f"{action['id']} replace event policy has no event_tracks_file"
            )
        event_text, event_state = load_event_array(event_file_path)
        text = replace_field(text, "m_eventTracks", event_text)

    output = project_path(
        manifest_path,
        action["output_vnmclip"],
        field=f"{animation_set['id']}.{action['id']}.output_vnmclip",
    )
    rendered = text.rstrip() + "\n"
    source_dmx_state = _file_state(output_dmx)
    receipt = {
        "set": animation_set["id"],
        "action": action["id"],
        "event_policy": event_policy,
        "event_tracks_file": event_file_resource,
        "event_tracks_path": str(event_file_path) if event_file_path else None,
        "event_tracks_state": event_state,
        "event_tracks_sha256": event_state.get("sha256") if event_state else None,
        "template": str(template),
        "template_state": template_state,
        "template_sha256": template_state["sha256"],
        "source_dmx": action["output_dmx"],
        "source_dmx_path": str(output_dmx),
        "source_dmx_state": source_dmx_state,
        "source_dmx_sha256": source_dmx_state.get("sha256"),
        "primary_skeleton": animation_set["primary_skeleton"],
        "secondary_skeletons": animation_set.get("secondary_skeletons", []),
        "output": str(output),
        "output_before": _file_state(output),
        "output_sha256": _text_sha256(rendered),
    }
    return {"output": output, "text": rendered, "receipt": receipt}


def commit_generated_outputs(
    prepared: list[dict[str, Any]],
    *,
    validate_inputs: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    """Commit a fully prepared batch with per-file atomic replacement/rollback."""

    staged: list[dict[str, Any]] = []
    committed: list[dict[str, Any]] = []
    preserve_recovery = False
    cleanup_warnings: list[str] = []
    try:
        for entry in prepared:
            destination = Path(entry["output"])
            receipt = entry["receipt"]
            if _file_state(destination) != receipt["output_before"]:
                raise ManifestError(
                    f"VNMClip output changed during preparation: {destination}"
                )
            stage = _temporary_sibling(destination, ".pending")
            staged_entry = {
                **entry,
                "stage": stage,
                "backup": None,
                "quarantine": None,
                "rollback_corrupt": None,
                "stage_identity": None,
            }
            staged.append(staged_entry)
            stage.write_bytes(entry["text"].encode("utf-8"))
            if sha256_file(stage) != receipt["output_sha256"]:
                raise RuntimeError(f"staged VNMClip hash mismatch: {destination}")
            staged_entry["stage_identity"] = _file_identity(stage)
            if staged_entry["stage_identity"] is None:
                raise RuntimeError(
                    f"staged VNMClip identity missing: {destination}"
                )

        if validate_inputs is not None:
            validate_inputs()

        for entry in staged:
            destination = Path(entry["output"])
            before = entry["receipt"]["output_before"]
            if _file_state(destination) != before:
                raise ManifestError(
                    f"VNMClip output changed immediately before commit: {destination}"
                )

            # Register the entry before the first mutating OS call. This covers
            # exceptions (including KeyboardInterrupt) raised after a rename
            # completed but before Python regained control.
            committed.append(entry)
            if before.get("exists"):
                backup = _temporary_sibling(destination, ".rollback")
                entry["backup"] = backup
                os.replace(destination, backup)
                claimed = _file_state(backup)
                if claimed != before:
                    # The preimage changed between inspection and the atomic
                    # claim. Put those exact foreign bytes back without
                    # clobbering another writer, then exclude this entry from
                    # rollback because its manifest preimage was never owned.
                    committed.pop()
                    try:
                        if claimed.get("exists"):
                            _publish_validated_copy_no_replace(
                                backup, destination, claimed
                            )
                    except BaseException as restore_exc:
                        raise VnmclipRollbackFailure(
                            "VNMClip output changed while its preimage was being "
                            "claimed and the claimed bytes could not be restored; "
                            f"recovery file preserved: {backup}"
                        ) from restore_exc
                    raise ManifestError(
                        "VNMClip output changed while its preimage was being "
                        f"claimed; foreign content restored: {destination}"
                    )

            # The destination is now absent by construction. Publication is
            # no-replace, so a concurrent writer wins and is never overwritten.
            _publish_file_no_replace(Path(entry["stage"]), destination)
            if sha256_file(destination) != entry["receipt"]["output_sha256"]:
                raise RuntimeError(f"committed VNMClip hash mismatch: {destination}")

        # Revalidate all consumed inputs while rollback preimages are still
        # available. Provenance drift therefore fails the batch and restores
        # every destination rather than merely tainting a success receipt.
        if validate_inputs is not None:
            validate_inputs()
    except BaseException as exc:
        if isinstance(exc, VnmclipRollbackFailure):
            preserve_recovery = True
        rollback_errors: list[str] = []
        for entry in reversed(committed):
            destination = Path(entry["output"])
            backup = entry["backup"]
            try:
                before = entry["receipt"]["output_before"]
                current = _file_state(destination)
                if current == before:
                    continue
                committed_state = {
                    "exists": True,
                    "sha256": str(entry["receipt"]["output_sha256"]),
                }
                owned_identity = entry.get("stage_identity")
                current_identity = _file_identity(destination)

                if current.get("exists") and (
                    current != committed_state
                    or current_identity != owned_identity
                ):
                    raise ManifestError(
                        "VNMClip destination ownership changed before rollback; "
                        f"foreign content restored/preserved: {destination}"
                    )

                quarantined_state = {"exists": False}
                quarantined_identity = None
                if current.get("exists"):
                    quarantine = _temporary_sibling(
                        destination, ".rollback-current"
                    )
                    entry["quarantine"] = quarantine
                    os.replace(destination, quarantine)
                    quarantined_state = _file_state(quarantine)
                    quarantined_identity = _file_identity(quarantine)

                    if (
                        quarantined_state != committed_state
                        or quarantined_identity != owned_identity
                    ):
                        _publish_validated_copy_no_replace(
                            quarantine, destination, quarantined_state
                        )
                        raise ManifestError(
                            "VNMClip destination changed before rollback ownership "
                            "could be claimed; foreign content restored without "
                            f"clobber: {quarantined_state}"
                        )

                if backup is not None:
                    backup_path = Path(backup)
                    if _file_state(backup_path) != before:
                        if (
                            quarantined_state == committed_state
                            and quarantined_identity == owned_identity
                        ):
                            _publish_validated_copy_no_replace(
                                Path(entry["quarantine"]),
                                destination,
                                committed_state,
                            )
                            warning = _best_effort_unlink(
                                Path(entry["quarantine"])
                            )
                            if warning:
                                cleanup_warnings.append(warning)
                            else:
                                entry["quarantine"] = None
                        raise ManifestError(
                            "VNMClip rollback backup changed before restoration; "
                            f"recovery files preserved: {backup_path}"
                        )
                    _publish_validated_copy_no_replace(
                        backup_path, destination, before
                    )
                    restored_state = _file_state(destination)
                    if restored_state != before:
                        corrupt = _temporary_sibling(
                            destination, ".rollback-corrupt"
                        )
                        entry["rollback_corrupt"] = corrupt
                        os.replace(destination, corrupt)
                        if (
                            quarantined_state == committed_state
                            and quarantined_identity == owned_identity
                        ):
                            _publish_validated_copy_no_replace(
                                Path(entry["quarantine"]),
                                destination,
                                committed_state,
                            )
                        raise ManifestError(
                            "VNMClip rollback backup changed during restoration; "
                            "validated output restored and suspect bytes preserved: "
                            f"{corrupt}"
                        )
                # A missing preimage is restored by leaving the destination absent.
                # A successful rollback leaves only redundant private recovery
                # files. The finally block removes them best-effort.
            except BaseException as rollback_exc:
                rollback_errors.append(
                    f"{destination} (backup={backup}): "
                    f"{type(rollback_exc).__name__}: {rollback_exc}"
                )
        if rollback_errors:
            preserve_recovery = True
            recovery_files = sorted(
                str(Path(path))
                for entry in staged
                for key in (
                    "stage",
                    "backup",
                    "quarantine",
                    "rollback_corrupt",
                )
                if (path := entry.get(key)) and Path(path).exists()
            )
            raise VnmclipRollbackFailure(
                f"VNMClip commit failed ({exc}); rollback also failed: "
                + "; ".join(rollback_errors)
                + f"; recovery files preserved: {recovery_files}"
            ) from exc
        raise
    finally:
        if not preserve_recovery:
            for entry in staged:
                for key in (
                    "stage",
                    "backup",
                    "quarantine",
                    "rollback_corrupt",
                ):
                    path = entry.get(key)
                    if path and Path(path).exists():
                        warning = _best_effort_unlink(Path(path))
                        if warning:
                            cleanup_warnings.append(warning)
        if cleanup_warnings:
            for entry in staged:
                entry["receipt"].setdefault("cleanup_warnings", []).extend(
                    cleanup_warnings
                )
            print(
                "WARNING: VNMClip cleanup was incomplete: "
                + "; ".join(cleanup_warnings),
                file=sys.stderr,
            )

    return [entry["receipt"] for entry in staged]


def generate_one(
    manifest_path: Path,
    reference_root: Path,
    animation_set: dict[str, Any],
    action: dict[str, Any],
    *,
    allow_missing_dmx: bool,
) -> dict[str, Any]:
    prepared = prepare_one(
        manifest_path,
        reference_root,
        animation_set,
        action,
        allow_missing_dmx=allow_missing_dmx,
    )
    return commit_generated_outputs([prepared])[0]


def _consumed_input_provenance(
    manifest_path: Path,
    manifest_state: dict[str, Any],
    prepared: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}

    def add(kind: str, raw_path: str | Path | None, state: Any) -> None:
        if raw_path is None or not isinstance(state, dict):
            return
        path = Path(raw_path).expanduser().resolve()
        key = os.path.normcase(str(path))
        existing = by_path.get(key)
        if existing is not None:
            if existing["before"] != state:
                raise ManifestError(
                    f"inconsistent provenance snapshots for consumed input: {path}"
                )
            if kind not in existing["kinds"]:
                existing["kinds"].append(kind)
            return
        by_path[key] = {
            "path": str(path),
            "kinds": [kind],
            "before": dict(state),
        }

    add("manifest", manifest_path, manifest_state)
    for entry in prepared:
        receipt = entry.get("receipt", {})
        add("template", receipt.get("template"), receipt.get("template_state"))
        add(
            "event-tracks",
            receipt.get("event_tracks_path"),
            receipt.get("event_tracks_state"),
        )
        add(
            "source-dmx",
            receipt.get("source_dmx_path"),
            receipt.get("source_dmx_state"),
        )
    return [by_path[key] for key in sorted(by_path)]


def _verify_consumed_input_provenance(
    provenance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for entry in provenance:
        path = Path(entry["path"])
        after = _file_state(path)
        if after != entry["before"]:
            raise ManifestError(
                "VNMClip consumed input changed during generation: "
                f"{path} ({entry['before']} -> {after})"
            )
        verified.append({**entry, "after": after})
    return verified


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _transaction_structure_error(value: Any, path: Path) -> str | None:
    if not isinstance(value, dict):
        return "journal root is not an object"
    if value.get("schema_version") != 1:
        return "unsupported or missing schema_version"
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return "missing run_id"
    if path.name != f"vnmclip-transaction-{run_id}.json":
        return "journal filename does not match run_id"
    if not isinstance(value.get("status"), str):
        return "missing status"
    if not isinstance(value.get("manifest"), str) or not value["manifest"]:
        return "missing manifest path"
    if not _is_sha256(value.get("manifest_sha256")):
        return "missing or invalid manifest_sha256"
    outputs = value.get("outputs")
    if not isinstance(outputs, list):
        return "missing outputs"
    for output in outputs:
        if not isinstance(output, dict):
            return "invalid output entry"
        if not isinstance(output.get("destination"), str):
            return "output entry lacks destination"
        before = output.get("before")
        if not isinstance(before, dict) or not isinstance(before.get("exists"), bool):
            return "output entry has invalid preimage"
        if before["exists"] and not _is_sha256(before.get("sha256")):
            return "output preimage has invalid sha256"
        if not _is_sha256(output.get("validated_sha256")):
            return "output entry has invalid validated_sha256"
    if value["status"] == "failed":
        error = value.get("error")
        if not isinstance(error, dict) or not isinstance(error.get("type"), str):
            return "failed journal lacks structured error"
    return None


def _reported_transaction_error(value: dict[str, Any], journal: Path) -> str | None:
    run_id = value["run_id"]
    expected_report = journal.parent / f"vnmclip-report-{run_id}.json"
    raw_report = value.get("report")
    if not isinstance(raw_report, str):
        return "reported journal lacks report path"
    try:
        recorded_report = Path(raw_report).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return "reported journal has invalid report path"
    if recorded_report != expected_report.resolve():
        return "reported journal points to a non-matching report"
    expected_hash = value.get("report_sha256")
    if not _is_sha256(expected_hash) or not recorded_report.is_file():
        return "reported journal lacks a valid existing report"
    if sha256_file(recorded_report) != expected_hash:
        return "reported journal report hash mismatch"
    try:
        report = json.loads(recorded_report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "reported journal report is invalid JSON"
    if not isinstance(report, dict):
        return "reported journal report root is not an object"
    if report.get("status") != "ok" or report.get("run_id") != run_id:
        return "reported journal report identity/status mismatch"
    if report.get("manifest") != value.get("manifest"):
        return "reported journal report manifest mismatch"
    if report.get("manifest_sha256") != value.get("manifest_sha256"):
        return "reported journal report manifest hash mismatch"
    raw_journal = report.get("transaction_journal")
    if not isinstance(raw_journal, str):
        return "reported journal report lacks transaction_journal"
    try:
        if Path(raw_journal).expanduser().resolve() != journal.resolve():
            return "reported journal report points to another journal"
    except (OSError, RuntimeError, ValueError):
        return "reported journal report has invalid transaction_journal"
    if report.get("generated") != value.get("generated"):
        return "reported journal generated receipts do not match report"
    return None


def unresolved_vnmclip_transactions(report_root: Path) -> list[dict[str, str]]:
    unresolved: list[dict[str, str]] = []
    if not report_root.is_dir():
        return unresolved
    for path in sorted(report_root.glob("vnmclip-transaction-*.json")):
        reason: str | None = None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            reason = _transaction_structure_error(value, path)
            status = value.get("status") if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            status = "invalid"
            reason = "journal is unreadable or invalid JSON"
            value = None
        if reason is None and status == "reported":
            reason = _reported_transaction_error(value, path)
        terminal = reason is None and status in {"failed", "reported"}
        if not terminal:
            unresolved.append(
                {
                    "path": str(path),
                    "status": (
                        str(status)
                        if isinstance(status, str) and reason is None
                        else "invalid"
                    ),
                    "reason": reason or f"non-terminal status: {status}",
                }
            )
    return unresolved


def main() -> int:
    args = parse_args()
    manifest_candidate = Path(args.manifest).expanduser().resolve()
    reference_root = (
        Path(args.reference_root).expanduser().resolve()
        if args.reference_root
        else (manifest_candidate.parent / ".local" / "references").resolve()
    )
    # Load the manifest only after both roots actually consumed by this run are
    # locked. Non-cooperating writers are still detected by the hash checks.
    with ProcessLockSet([manifest_candidate.parent, reference_root]):
        manifest_state = _file_state(manifest_candidate)
        manifest_path, manifest = load_manifest(manifest_candidate)
        if not manifest_state.get("exists") or _file_state(manifest_path) != manifest_state:
            raise ManifestError(
                f"manifest changed while it was being loaded: {manifest_candidate}"
            )
        return _main_locked(
            args,
            manifest_path,
            manifest,
            reference_root,
            manifest_state,
        )


def _main_locked(
    args: argparse.Namespace,
    manifest_path: Path,
    manifest: dict[str, Any],
    reference_root: Path,
    manifest_state: dict[str, Any],
) -> int:
    manifest_sha256 = str(manifest_state["sha256"])
    run_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    report_root = manifest_path.parent / ".local" / "reports"
    unresolved = unresolved_vnmclip_transactions(report_root)
    if unresolved:
        raise ManifestError(
            "unresolved prior VNMClip transaction(s); inspect/restore outputs and "
            f"archive the journals before retrying: {unresolved}"
        )
    animation_sets = selected_sets(manifest, args.sets)
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    required_outputs: list[str] = []
    for animation_set in animation_sets:
        for action in action_filter(animation_set, args.actions):
            selected.append((animation_set, action))
            resource = action["reference_resource"]
            required_outputs.extend(
                [reference_dmx_relative(resource), reference_vnmclip_relative(resource)]
            )
    reference_cache_receipt: dict[str, Any] | None = None
    prepared: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    receipt_create_method: str | None = None
    transaction: dict[str, Any] | None = None
    input_provenance_before: list[dict[str, Any]] = []
    input_provenance_after: list[dict[str, Any]] | None = None
    reference_cache_after: dict[str, Any] | None = None
    transaction_path = report_root / f"vnmclip-transaction-{run_id}.json"
    report_path = report_root / f"vnmclip-report-{run_id}.json"
    try:
        receipt_create_method = probe_versioned_receipt_create(report_root)
        reference_cache_receipt = verify_reference_cache(
            reference_root,
            manifest_path,
            list(dict.fromkeys(required_outputs)),
            allow_unverified=args.allow_unverified_reference_cache,
        )
        for animation_set, action in selected:
            prepared.append(
                prepare_one(
                    manifest_path,
                    reference_root,
                    animation_set,
                    action,
                    allow_missing_dmx=args.allow_missing_dmx,
                )
            )
        input_provenance_before = _consumed_input_provenance(
            manifest_path, manifest_state, prepared
        )

        def validate_inputs() -> None:
            nonlocal input_provenance_after, reference_cache_after
            input_provenance_after = _verify_consumed_input_provenance(
                input_provenance_before
            )
            current_cache = verify_reference_cache(
                reference_root,
                manifest_path,
                list(dict.fromkeys(required_outputs)),
                allow_unverified=args.allow_unverified_reference_cache,
            )
            if current_cache != reference_cache_receipt:
                raise ManifestError(
                    "reference cache provenance changed during VNMClip generation"
                )
            reference_cache_after = current_cache

        transaction = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "prepared",
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "reference_root": str(reference_root),
            "reference_cache_before": reference_cache_receipt,
            "input_provenance_before": input_provenance_before,
            "outputs": [
                {
                    "destination": str(entry["output"]),
                    "before": entry["receipt"]["output_before"],
                    "validated_sha256": entry["receipt"]["output_sha256"],
                }
                for entry in prepared
            ],
        }
        write_json(transaction_path, transaction)
        try:
            receipts = commit_generated_outputs(
                prepared, validate_inputs=validate_inputs
            )
        except BaseException as exc:
            transaction["status"] = generation_failure_status(exc)
            transaction["reference_cache_after"] = reference_cache_after
            transaction["input_provenance_after"] = input_provenance_after
            transaction["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            try:
                write_json(transaction_path, transaction)
            except BaseException as journal_exc:
                raise RuntimeError(
                    "VNMClip commit failed and its transaction journal could not "
                    f"be updated ({journal_exc}); the prepared journal remains "
                    "unresolved"
                ) from exc
            raise
        transaction["status"] = "committed"
        transaction["generated"] = receipts
        transaction["reference_cache_after"] = reference_cache_after
        transaction["input_provenance_after"] = input_provenance_after
        write_json(transaction_path, transaction)

        report = {
            "schema_version": 2,
            "status": "ok",
            "run_id": run_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "allow_unverified_reference_cache": (
                args.allow_unverified_reference_cache
            ),
            "reference_cache": reference_cache_receipt,
            "reference_cache_after": reference_cache_after,
            "input_provenance_before": input_provenance_before,
            "input_provenance_after": input_provenance_after,
            "versioned_receipt_create_method": receipt_create_method,
            "transaction_journal": str(transaction_path),
            "generated": receipts,
        }
        write_json_new(report_path, report)
        write_json(report_root / "vnmclip-report.json", report)
        transaction["status"] = "reported"
        transaction["report"] = str(report_path)
        transaction["report_sha256"] = sha256_file(report_path)
        write_json(transaction_path, transaction)
    except BaseException as exc:
        failure_report = {
            "schema_version": 2,
            "status": generation_failure_status(exc),
            "run_id": run_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_sha256,
            "allow_unverified_reference_cache": (
                args.allow_unverified_reference_cache
            ),
            "reference_cache": reference_cache_receipt,
            "reference_cache_after": reference_cache_after,
            "input_provenance_before": input_provenance_before,
            "input_provenance_after": input_provenance_after,
            "versioned_receipt_create_method": receipt_create_method,
            "transaction_journal": str(transaction_path)
            if transaction is not None
            else None,
            "transaction_status": transaction.get("status")
            if transaction is not None
            else None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "prepared": [entry["receipt"] for entry in prepared],
            "generated": receipts,
        }
        try:
            write_json_new(
                report_root / f"vnmclip-report-{run_id}.json", failure_report
            )
            write_json(report_root / "vnmclip-report.json", failure_report)
        except BaseException as report_exc:
            print(
                f"WARNING: could not write VNMClip failure receipt: {report_exc}",
                file=sys.stderr,
            )
        raise
    print(
        json.dumps(
            {
                "status": "ok",
                "generated": len(receipts),
                "report": str(report_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
