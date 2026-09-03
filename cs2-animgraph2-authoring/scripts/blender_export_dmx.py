#!/usr/bin/env python3
"""Export manifest-selected Blender actions into complete Source 2 DMX clips.

Run this script through Blender with the authored .blend already open. Every
bone is sampled on every integer frame. The exact stock DMX structure is used
as a template, so the tool never assumes a fixed 56/74-bone rig.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import bpy
from mathutils import Matrix


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
    resolve_cs2_root,
    resolve_secondary_skeleton_dmx,
    resolve_tool,
    selected_sets,
    sha256_file,
    write_json,
    write_json_new,
)
from blender_dmx import (  # noqa: E402
    armature_rest_signature,
    convert_to_binary,
    convert_to_kv2,
    parse_array_lengths,
    patch_template,
    pose_error,
    pose_for_action,
    secondary_joints_from_dmx,
)
from extract_stock_references import verify_reference_cache  # noqa: E402


class DmxRollbackFailure(RuntimeError):
    """A DMX commit failed and at least one rollback could not be verified."""


def transaction_failure_status(exc: BaseException) -> str:
    """Map a structured commit outcome to its persistent journal status."""

    return "rollback-failed" if isinstance(exc, DmxRollbackFailure) else "failed"


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        help="Animation-set id; repeat or omit for all",
    )
    parser.add_argument(
        "--action",
        dest="actions",
        action="append",
        help="Action id; repeat or omit for all actions in selected sets",
    )
    parser.add_argument("--reference-root")
    parser.add_argument("--cs2-root")
    parser.add_argument("--dmxconvert")
    parser.add_argument(
        "--allow-manifest-drift",
        action="store_true",
        help="Permit a .blend created from a different manifest hash",
    )
    parser.add_argument(
        "--allow-reference-drift",
        action="store_true",
        help="Permit stock DMX hashes that differ from scene-creation receipts",
    )
    parser.add_argument(
        "--allow-unsaved-blend",
        action="store_true",
        help=(
            "Forensic override: export when the current .blend has no verifiable "
            "saved filepath; the override is recorded in the export receipt"
        ),
    )
    parser.add_argument(
        "--allow-dirty-blend",
        action="store_true",
        help=(
            "Forensic override: export a dirty .blend with unsaved changes; the "
            "override and dirty state are recorded in the export receipt"
        ),
    )
    parser.add_argument(
        "--allow-unverified-reference-cache",
        action="store_true",
        help=(
            "Forensic override: allow reference templates without a valid "
            "extraction receipt; the bypass is recorded in the export report"
        ),
    )
    return parser.parse_args(blender_arguments())


def local_path(root: Path, resource: str) -> Path:
    return root.joinpath(*PurePosixPath(resource).parts)


def matrix_identity_error(matrix: Matrix) -> float:
    identity = Matrix.Identity(4)
    return max(
        abs(matrix[row][column] - identity[row][column])
        for row in range(4)
        for column in range(4)
    )


def file_state(path: Path) -> dict[str, Any]:
    if path.exists() and not path.is_file():
        raise ManifestError(f"expected a file path, found another object: {path}")
    exists = path.is_file()
    return {
        "exists": exists,
        "sha256": sha256_file(path) if exists else None,
    }


def file_identity(path: Path) -> dict[str, int] | None:
    """Return an identity token preserved by hard-link and rename publication."""

    if not path.is_file():
        return None
    stat = path.stat()
    if int(stat.st_ino) == 0:
        return None
    return {"device": int(stat.st_dev), "inode": int(stat.st_ino)}


def validate_blend_provenance(args: argparse.Namespace) -> dict[str, Any]:
    raw_filepath = str(getattr(bpy.data, "filepath", "") or "")
    saved_path = Path(raw_filepath).expanduser().resolve() if raw_filepath else None
    saved_file_exists = bool(saved_path and saved_path.is_file())
    dirty = bool(getattr(bpy.data, "is_dirty", True))
    if not saved_file_exists and not args.allow_unsaved_blend:
        raise ManifestError(
            "the open Blender scene has no verifiable saved filepath; save the .blend "
            "first, or use --allow-unsaved-blend only for a forensic export"
        )
    if dirty and not args.allow_dirty_blend:
        raise ManifestError(
            "the open Blender scene has unsaved changes; save it first, or use "
            "--allow-dirty-blend only for a forensic export"
        )
    return {
        "filepath": str(saved_path) if saved_path else None,
        "sha256": sha256_file(saved_path) if saved_file_exists else None,
        "saved_file_exists": saved_file_exists,
        "dirty": dirty,
    }


def _temporary_sibling(path: Path, suffix: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=suffix, dir=path.parent
    )
    os.close(descriptor)
    return Path(name)


def _publish_file_no_replace(
    source: Path,
    destination: Path,
    cleanup_errors: list[str] | None = None,
) -> str:
    """Publish a prepared disposable file without clobbering a concurrent writer."""

    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise ManifestError(
            f"destination appeared during no-replace publication; source preserved: "
            f"{source} -> {destination}"
        ) from exc
    except OSError as link_exc:
        if os.name != "nt":
            raise ManifestError(
                "safe no-replace publication requires hard-link support on this "
                f"filesystem; source preserved: {source}"
            ) from link_exc
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise ManifestError(
                f"destination appeared during no-replace publication; source preserved: "
                f"{source} -> {destination}"
            ) from exc
        except OSError as rename_exc:
            raise ManifestError(
                f"safe no-replace publication failed; source preserved: {source}"
            ) from rename_exc
        return "windows-no-replace-rename"
    _best_effort_unlink(source, cleanup_errors if cleanup_errors is not None else [])
    return "hard-link"


def _absent_temporary_sibling(path: Path, suffix: str) -> Path:
    """Reserve a unique sibling name, then return it in the absent state."""

    reserved = _temporary_sibling(path, suffix)
    reserved.unlink()
    return reserved


def _best_effort_unlink(path: Path, errors: list[str]) -> None:
    """Remove a transient file without masking the transaction's real outcome."""

    try:
        if path.exists():
            path.unlink()
    except BaseException as exc:
        errors.append(f"{path}: {type(exc).__name__}: {exc}")


def _publish_validated_copy_no_replace(
    source: Path,
    destination: Path,
    expected_state: dict[str, Any],
    cleanup_errors: list[str],
) -> str:
    """Restore a validated copy while preserving the unique recovery source.

    The recovery source is deliberately never hard-linked or renamed into the
    destination. A disposable copy is validated, published no-replace, and then
    verified at the destination. The unique backup therefore remains available
    until the caller has proved rollback success.
    """

    if not expected_state.get("exists"):
        raise ManifestError("cannot publish a recovery copy for an absent state")
    if file_state(source) != expected_state:
        raise ManifestError(f"recovery source changed before restoration: {source}")
    restore_copy = _temporary_sibling(destination, ".restore-copy")
    try:
        shutil.copyfile(source, restore_copy)
        if file_state(source) != expected_state:
            raise ManifestError(
                f"recovery source changed while it was being copied: {source}"
            )
        if file_state(restore_copy) != expected_state:
            raise ManifestError(
                f"validated recovery copy differs from its source: {restore_copy}"
            )
        method = _publish_file_no_replace(
            restore_copy, destination, cleanup_errors
        )
        if file_state(destination) != expected_state:
            raise ManifestError(
                f"restored destination failed post-publication validation: "
                f"{destination}"
            )
        if file_state(source) != expected_state:
            raise ManifestError(
                f"recovery source changed during restoration: {source}"
            )
        return method
    finally:
        _best_effort_unlink(restore_copy, cleanup_errors)


def commit_validated_outputs(
    pending: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Claim preimages atomically and publish validated outputs no-replace."""

    staged: list[dict[str, Any]] = []
    committed: list[dict[str, Any]] = []
    preserve_recovery = False
    cleanup_errors: list[str] = []
    try:
        for entry in pending:
            source = Path(entry["source"])
            destination = Path(entry["destination"])
            expected_before = entry["before"]
            if file_state(destination) != expected_before:
                raise ManifestError(
                    f"output changed during validation, refusing replacement: "
                    f"{destination}"
                )
            validated_hash = str(entry["validated_sha256"])
            if sha256_file(source) != validated_hash:
                raise ManifestError(
                    f"validated temporary DMX changed before commit: {source}"
                )
            stage = _temporary_sibling(destination, ".pending")
            staged_entry = {
                **entry,
                "stage": stage,
                "backup": None,
                "quarantine": None,
                "rollback_corrupt": None,
                "preimage_state": None,
                "settled": False,
                "publication_method": None,
                "stage_identity": None,
            }
            staged.append(staged_entry)
            shutil.copyfile(source, stage)
            if sha256_file(stage) != validated_hash:
                raise ManifestError(
                    f"staged DMX hash mismatch before commit: {destination}"
                )
            staged_entry["stage_identity"] = file_identity(stage)
            if staged_entry["stage_identity"] is None:
                raise ManifestError(
                    f"staged DMX identity missing before commit: {destination}"
                )
        for entry in staged:
            destination = Path(entry["destination"])
            if file_state(destination) != entry["before"]:
                raise ManifestError(
                    f"output changed immediately before commit: {destination}"
                )
            # Register rollback ownership before either claim or publication.
            # An existing preimage is first moved atomically to a unique sibling;
            # only then may the staged output be published no-replace. Thus a
            # writer winning either race is preserved rather than overwritten.
            committed.append(entry)
            if entry["before"]["exists"]:
                backup = _absent_temporary_sibling(destination, ".rollback")
                entry["backup"] = backup
                os.replace(destination, backup)
                claimed_state = file_state(backup)
                entry["preimage_state"] = claimed_state
                if claimed_state != entry["before"]:
                    _publish_validated_copy_no_replace(
                        backup,
                        destination,
                        claimed_state,
                        cleanup_errors,
                    )
                    entry["settled"] = True
                    raise ManifestError(
                        "output changed while its preimage was being claimed; "
                        f"foreign content restored without clobber: {destination}"
                    )
            elif file_state(destination) != entry["before"]:
                raise ManifestError(
                    f"output appeared immediately before publication: {destination}"
                )

            entry["publication_method"] = _publish_file_no_replace(
                Path(entry["stage"]), destination, cleanup_errors
            )
            if sha256_file(destination) != entry["validated_sha256"]:
                raise ManifestError(
                    f"committed DMX hash mismatch: {destination}"
                )

    except BaseException as exc:
        rollback_errors: list[str] = []
        for entry in reversed(committed):
            destination = Path(entry["destination"])
            backup = entry["backup"]
            try:
                if entry.get("settled"):
                    continue
                current = file_state(destination)
                if current == entry["before"]:
                    # Replacement failed before changing this destination (or a
                    # prior recovery already restored it); do not rewrite it.
                    continue
                committed_state: dict[str, Any] = {
                    "exists": True,
                    "sha256": str(entry["validated_sha256"]),
                }
                owned_identity = entry.get("stage_identity")
                current_identity = file_identity(destination)
                if current["exists"] and (
                    current != committed_state
                    or current_identity != owned_identity
                ):
                    raise ManifestError(
                        "destination ownership changed before rollback; "
                        f"recovery files preserved: {destination}"
                    )

                if current == committed_state and current_identity == owned_identity:
                    quarantine = _absent_temporary_sibling(
                        destination, ".rollback-current"
                    )
                    entry["quarantine"] = quarantine
                    os.replace(destination, quarantine)
                    quarantined_state = file_state(quarantine)
                    quarantined_identity = file_identity(quarantine)
                    if (
                        quarantined_state != committed_state
                        or quarantined_identity != owned_identity
                    ):
                        _publish_validated_copy_no_replace(
                            quarantine,
                            destination,
                            quarantined_state,
                            cleanup_errors,
                        )
                        entry["settled"] = True
                        raise ManifestError(
                            "destination changed while rollback ownership was being "
                            f"claimed; foreign content restored: {destination}"
                        )

                if backup is not None:
                    backup_path = Path(backup)
                    backup_state = file_state(backup_path)
                    expected_preimage = entry.get("preimage_state")
                    if expected_preimage is None:
                        # A BaseException may have interrupted immediately after
                        # the atomic claim. The unique absent target proves that
                        # an existing backup is the exact preimage claimed by the
                        # rename, including a concurrent writer that won the race.
                        expected_preimage = backup_state
                        entry["preimage_state"] = backup_state
                    if backup_state != expected_preimage:
                        quarantine = entry.get("quarantine")
                        if quarantine is not None:
                            quarantine_path = Path(quarantine)
                            if (
                                file_state(quarantine_path) == committed_state
                                and file_identity(quarantine_path) == owned_identity
                            ):
                                _publish_validated_copy_no_replace(
                                    quarantine_path,
                                    destination,
                                    committed_state,
                                    cleanup_errors,
                                )
                        raise ManifestError(
                            "rollback backup changed before restoration; recovery "
                            f"files preserved: {backup_path}"
                        )
                    _publish_validated_copy_no_replace(
                        backup_path,
                        destination,
                        expected_preimage,
                        cleanup_errors,
                    )
                # A missing preimage is restored by leaving destination absent.
                entry["settled"] = True
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
            raise DmxRollbackFailure(
                f"DMX commit failed ({exc}); rollback also failed: "
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
                    if path:
                        _best_effort_unlink(Path(path), cleanup_errors)

    return [
        {
            "output": str(entry["destination"]),
            "sha256": str(entry["validated_sha256"]),
            "replacement": "atomic-preimage-claim+no-replace-publication",
            "publication_method": entry.get("publication_method"),
            "cleanup_warnings": list(cleanup_errors),
        }
        for entry in staged
    ]


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_file_state(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("exists"), bool):
        return False
    digest = value.get("sha256")
    return _is_sha256(digest) if value["exists"] else digest is None


def _valid_export_transaction(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != 1:
        return False
    if not isinstance(value.get("run_id"), str) or not value["run_id"]:
        return False
    if not isinstance(value.get("manifest"), str) or not value["manifest"]:
        return False
    if not _is_sha256(value.get("manifest_sha256")):
        return False
    outputs = value.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return False
    for output in outputs:
        if not isinstance(output, dict):
            return False
        if not isinstance(output.get("destination"), str) or not output["destination"]:
            return False
        if not _valid_file_state(output.get("before")):
            return False
        if not _is_sha256(output.get("validated_sha256")):
            return False
    status = value.get("status")
    if not isinstance(status, str):
        return False
    if status in {"committed", "reported"}:
        commits = value.get("commits")
        if not isinstance(commits, list) or len(commits) != len(outputs):
            return False
        for output, commit in zip(outputs, commits, strict=True):
            if not isinstance(commit, dict):
                return False
            if commit.get("output") != output["destination"]:
                return False
            if commit.get("sha256") != output["validated_sha256"]:
                return False
            if not isinstance(commit.get("replacement"), str):
                return False
    if status in {"failed", "rollback-failed"}:
        error = value.get("error")
        if not isinstance(error, dict):
            return False
        if not isinstance(error.get("type"), str) or not error["type"]:
            return False
        if not isinstance(error.get("message"), str):
            return False
    return True


def _reported_transaction_matches_report(
    journal_path: Path, report_root: Path, transaction: dict[str, Any]
) -> bool:
    run_id = transaction["run_id"]
    expected_report = (report_root / f"dmx-export-report-{run_id}.json").resolve()
    raw_report = transaction.get("report")
    if not isinstance(raw_report, str):
        return False
    try:
        report_path = Path(raw_report).expanduser().resolve()
        if report_path != expected_report or not report_path.is_file():
            return False
        if not _is_sha256(transaction.get("report_sha256")):
            return False
        if sha256_file(report_path) != transaction["report_sha256"]:
            return False
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(report, dict):
        return False
    raw_journal = report.get("transaction_journal")
    if not isinstance(raw_journal, str):
        return False
    try:
        reported_journal = Path(raw_journal).expanduser().resolve()
    except (OSError, ValueError):
        return False
    return (
        report.get("schema_version") == 2
        and report.get("status") == "ok"
        and report.get("run_id") == run_id
        and report.get("manifest") == transaction["manifest"]
        and report.get("manifest_sha256") == transaction["manifest_sha256"]
        and reported_journal == journal_path.resolve()
    )


def unresolved_export_transactions(report_root: Path) -> list[dict[str, str]]:
    unresolved: list[dict[str, str]] = []
    if not report_root.is_dir():
        return unresolved
    for path in sorted(report_root.glob("dmx-export-transaction-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            structurally_valid = _valid_export_transaction(value)
            if structurally_valid:
                structurally_valid = (
                    path.name
                    == f"dmx-export-transaction-{value['run_id']}.json"
                )
            status = value.get("status") if structurally_valid else None
            terminal = status == "failed" or (
                status == "reported"
                and _reported_transaction_matches_report(path, report_root, value)
            )
        except (OSError, ValueError, json.JSONDecodeError):
            status = "invalid"
            terminal = False
        if not terminal:
            unresolved.append(
                {
                    "path": str(path),
                    "status": str(status) if isinstance(status, str) else "invalid",
                }
            )
    return unresolved


def validate_armature(
    armature: bpy.types.Object,
    animation_set: dict[str, Any],
) -> None:
    if armature.type != "ARMATURE":
        raise ManifestError(f"{armature.name} is not an armature")
    if not armature.pose.bones:
        raise ManifestError(f"{armature.name} has no pose bones")
    determinant = armature.matrix_world.to_3x3().determinant()
    if determinant < 0.0:
        raise ManifestError(
            f"{armature.name} has a mirrored object transform (det={determinant})"
        )
    identity_error = matrix_identity_error(armature.matrix_world)
    if identity_error > 1e-5:
        raise ManifestError(
            f"{armature.name} object transform must remain identity; max error "
            f"is {identity_error:.8f}. Pose bones instead of the armature object."
        )
    expected_scale = float(animation_set["blender_units_per_source_unit"])
    stored_scale = armature.get("source_unit_scale")
    if stored_scale is not None and abs(float(stored_scale) - expected_scale) > 1e-8:
        raise ManifestError(
            f"{armature.name} source scale {stored_scale} differs from manifest "
            f"{expected_scale}"
        )
    stored_skeleton = armature.get("source_skeleton")
    if stored_skeleton and stored_skeleton != animation_set["primary_skeleton"]:
        raise ManifestError(
            f"{armature.name} skeleton {stored_skeleton!r} differs from manifest "
            f"{animation_set['primary_skeleton']!r}"
        )
    stored_rest = armature.get("cs2_rest_signature")
    if not stored_rest:
        raise ManifestError(
            f"{armature.name} has no creation-time rest-pose receipt; regenerate the scene"
        )
    try:
        expected_rest = json.loads(stored_rest)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ManifestError(
            f"{armature.name} has an invalid rest-pose receipt"
        ) from exc
    current_rest = armature_rest_signature(armature)
    if current_rest != expected_rest:
        raise ManifestError(
            f"{armature.name} bone hierarchy/rest pose changed since scene creation; "
            "regenerate the scene or restore its original edit bones"
        )


def selected_actions(
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


def validate_continuity(
    animation_set: dict[str, Any], actions_by_id: dict[str, bpy.types.Action]
) -> list[dict[str, Any]]:
    armature = bpy.data.objects[animation_set["armature"]]
    results = []
    for rule in animation_set.get("continuity", []):
        source_action = actions_by_id.get(rule["from"])
        target_action = actions_by_id.get(rule["to"])
        if source_action is None or target_action is None:
            continue
        source_endpoint = rule.get("from_frame", "last")
        target_endpoint = rule.get("to_frame", "first")
        position, rotation = pose_error(
            pose_for_action(armature, source_action, source_endpoint),
            pose_for_action(armature, target_action, target_endpoint),
        )
        max_position = float(rule.get("max_position_error", 1e-5))
        max_rotation = float(rule.get("max_rotation_error_radians", 1e-5))
        passed = position <= max_position and rotation <= max_rotation
        result = {
            "from": rule["from"],
            "to": rule["to"],
            "position_error": position,
            "rotation_error_radians": rotation,
            "max_position_error": max_position,
            "max_rotation_error_radians": max_rotation,
            "passed": passed,
        }
        results.append(result)
        if not passed:
            raise ManifestError(
                f"continuity failed for {animation_set['id']} "
                f"{rule['from']}->{rule['to']}: position={position:.8f}, "
                f"rotation={rotation:.8f} rad"
            )
    return results


def main() -> int:
    args = parse_args()
    manifest_candidate = Path(args.manifest).expanduser().resolve()
    # Lock the manifest namespace before loading it. The additional input locks
    # are derived from that validated manifest and held for the complete export.
    with ProcessLockSet([manifest_candidate.parent]):
        manifest_before = file_state(manifest_candidate)
        if not manifest_before["exists"]:
            raise FileNotFoundError(f"manifest not found: {manifest_candidate}")
        manifest_path, manifest = load_manifest(manifest_candidate)
        if manifest_path != manifest_candidate:
            raise ManifestError("resolved manifest path changed while loading")
        if file_state(manifest_path) != manifest_before:
            raise ManifestError("manifest changed while it was being loaded")

        animation_sets = selected_sets(manifest, args.sets)
        reference_root = (
            Path(args.reference_root).expanduser().resolve()
            if args.reference_root
            else manifest_path.parent / ".local" / "references"
        )
        required_reference_outputs = sorted(
            {
                reference_dmx_relative(action["reference_resource"])
                for animation_set in animation_sets
                for action in selected_actions(animation_set, args.actions)
            },
            key=str.casefold,
        )
        template_paths = [
            local_path(reference_root, relative)
            for relative in required_reference_outputs
        ]
        cs2_root = resolve_cs2_root(args.cs2_root) if not args.dmxconvert else None
        dmxconvert = resolve_tool(
            args.dmxconvert,
            ("DMXCONVERT",),
            cs2_root / "game" / "bin" / "win64" / "dmxconvert.exe"
            if cs2_root
            else None,
            "dmxconvert",
        )
        with ProcessLockSet([reference_root, dmxconvert, *template_paths]):
            return _main_locked(
                args,
                manifest_path,
                manifest_before,
                animation_sets,
                reference_root,
                required_reference_outputs,
                dmxconvert,
                template_paths,
            )


def _main_locked(
    args: argparse.Namespace,
    manifest_path: Path,
    manifest_before: dict[str, Any],
    animation_sets: list[dict[str, Any]],
    reference_root: Path,
    required_reference_outputs: list[str],
    dmxconvert: Path,
    template_paths: list[Path],
) -> int:
    blend_receipt = validate_blend_provenance(args)
    dmxconvert_before = file_state(dmxconvert)
    if not dmxconvert_before["exists"]:
        raise FileNotFoundError(f"dmxconvert not found: {dmxconvert}")
    templates_before: list[dict[str, Any]] = []
    for template_path in template_paths:
        state = file_state(template_path)
        if not state["exists"]:
            raise FileNotFoundError(
                f"missing extracted DMX template: {template_path}"
            )
        templates_before.append({"path": str(template_path), "before": state})
    input_provenance: dict[str, Any] = {
        "manifest": {
            "path": str(manifest_path),
            "before": manifest_before,
            "after": None,
        },
        "dmxconvert": {
            "path": str(dmxconvert),
            "before": dmxconvert_before,
            "after": None,
        },
        "templates": templates_before,
    }
    template_before_by_path = {
        entry["path"]: entry["before"] for entry in templates_before
    }
    reference_cache_receipt = verify_reference_cache(
        reference_root,
        manifest_path,
        required_reference_outputs,
        allow_unverified=args.allow_unverified_reference_cache,
    )
    current_manifest_hash = str(manifest_before["sha256"])
    scene_hash = bpy.context.scene.get("cs2_animgraph2_manifest_sha256")
    if not scene_hash and not args.allow_manifest_drift:
        raise ManifestError(
            "the open .blend has no manifest receipt; regenerate it or pass "
            "--allow-manifest-drift after manually validating its origin"
        )
    if scene_hash != current_manifest_hash and not args.allow_manifest_drift:
        raise ManifestError(
            "the open .blend was created from a different manifest; regenerate the "
            "scene or pass --allow-manifest-drift after reviewing the diff"
        )

    raw_scene_receipts = bpy.context.scene.get("cs2_animgraph2_receipt")
    try:
        scene_receipts = json.loads(raw_scene_receipts) if raw_scene_receipts else []
    except (TypeError, json.JSONDecodeError) as exc:
        raise ManifestError("the .blend has an invalid stock-reference receipt") from exc
    receipt_by_action = {
        (entry.get("set"), entry.get("action")): entry
        for entry in scene_receipts
        if isinstance(entry, dict)
    }
    raw_scene_cache_receipt = bpy.context.scene.get("cs2_reference_cache_receipt")
    try:
        scene_cache_receipt = (
            json.loads(raw_scene_cache_receipt) if raw_scene_cache_receipt else None
        )
    except (TypeError, json.JSONDecodeError) as exc:
        raise ManifestError("the .blend has an invalid reference-cache receipt") from exc

    report: dict[str, Any] = {
        "schema_version": 2,
        "status": "prepared",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "manifest_sha256": current_manifest_hash,
        "manifest_receipt": {
            "expected_sha256": scene_hash,
            "current_sha256": current_manifest_hash,
            "matched": scene_hash == current_manifest_hash,
        },
        "blend": blend_receipt["filepath"] or "<unsaved>",
        "blend_sha256": blend_receipt["sha256"],
        "blend_receipt": blend_receipt,
        "blender": {
            "version_string": str(getattr(bpy.app, "version_string", "unknown")),
            "version": list(getattr(bpy.app, "version", ())),
        },
        "override_flags": {
            "allow_manifest_drift": bool(args.allow_manifest_drift),
            "allow_reference_drift": bool(args.allow_reference_drift),
            "allow_unsaved_blend": bool(args.allow_unsaved_blend),
            "allow_dirty_blend": bool(args.allow_dirty_blend),
            "allow_unverified_reference_cache": bool(
                args.allow_unverified_reference_cache
            ),
        },
        "reference_cache_receipt": reference_cache_receipt,
        "scene_reference_cache_receipt": scene_cache_receipt,
        "input_provenance": input_provenance,
        "dmxconvert": str(dmxconvert),
        "dmxconvert_sha256": dmxconvert_before["sha256"],
        "sets": [],
    }
    audit_root = manifest_path.parent / ".local" / "audit" / "dmx"
    run_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    report["run_id"] = run_id
    report_root = manifest_path.parent / ".local" / "reports"
    unresolved = unresolved_export_transactions(report_root)
    if unresolved:
        raise ManifestError(
            "unresolved prior DMX export transaction(s); inspect/restore outputs "
            f"and archive the journals before retrying: {unresolved}"
        )
    report["versioned_receipt_create_method"] = probe_versioned_receipt_create(
        report_root
    )
    transaction_path = report_root / f"dmx-export-transaction-{run_id}.json"
    pending_outputs: list[dict[str, Any]] = []
    pending_audits: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="cs2-animgraph2-export-") as temp_name:
        temp_root = Path(temp_name)
        for animation_set in animation_sets:
            armature = bpy.data.objects.get(animation_set["armature"])
            if armature is None:
                raise ManifestError(
                    f"armature {animation_set['armature']!r} is missing from the .blend"
                )
            validate_armature(armature, animation_set)
            action_entries = selected_actions(animation_set, args.actions)
            actions_by_id: dict[str, bpy.types.Action] = {}
            secondary_joints: list[dict[str, Any]] | None = None
            secondary_skeleton_value = animation_set.get("secondary_skeleton_dmx")
            if secondary_skeleton_value:
                secondary_skeleton_dmx = resolve_secondary_skeleton_dmx(
                    manifest_path, reference_root, secondary_skeleton_value
                )
                secondary_kv2 = temp_root / animation_set["id"] / "secondary_skeleton.dmx.kv2"
                convert_to_kv2(dmxconvert, secondary_skeleton_dmx, secondary_kv2)
                secondary_joints = secondary_joints_from_dmx(
                    secondary_kv2.read_text(encoding="utf-8")
                )
            set_report: dict[str, Any] = {
                "id": animation_set["id"],
                "armature": armature.name,
                "bone_count": len(armature.pose.bones),
                "actions": [],
            }

            for action_entry in action_entries:
                action = bpy.data.actions.get(action_entry["blender_action"])
                if action is None:
                    raise ManifestError(
                        f"Blender action {action_entry['blender_action']!r} is missing"
                    )
                actions_by_id[action_entry["id"]] = action
                dmx_relative = reference_dmx_relative(
                    action_entry["reference_resource"]
                )
                template = local_path(reference_root, dmx_relative)
                if not template.is_file():
                    raise FileNotFoundError(
                        f"missing extracted DMX template: {template}"
                    )
                template_state = file_state(template)
                expected_template_state = template_before_by_path.get(str(template))
                if template_state != expected_template_state:
                    raise ManifestError(
                        f"stock DMX template changed before consumption: {template}"
                    )
                template_sha256 = str(template_state["sha256"])
                scene_receipt = receipt_by_action.get(
                    (animation_set["id"], action_entry["id"])
                )
                expected_reference_hash = (
                    scene_receipt.get("reference_dmx_sha256")
                    if scene_receipt
                    else None
                )
                if not args.allow_reference_drift:
                    if not scene_receipt:
                        raise ManifestError(
                            f"the .blend has no stock-reference receipt for "
                            f"{animation_set['id']}/{action_entry['id']}; regenerate it"
                        )
                    if expected_reference_hash != template_sha256:
                        raise ManifestError(
                            f"stock DMX changed since scene creation for "
                            f"{animation_set['id']}/{action_entry['id']}; regenerate "
                            "the scene or pass --allow-reference-drift after review"
                        )

                work = temp_root / animation_set["id"] / action_entry["id"]
                template_kv2 = work / "template.dmx.kv2"
                convert_to_kv2(dmxconvert, template, template_kv2)
                patched_text, metrics = patch_template(
                    template_kv2.read_text(encoding="utf-8"),
                    armature,
                    action,
                    fps=float(animation_set["fps"]),
                    source_scale=float(
                        animation_set["blender_units_per_source_unit"]
                    ),
                    preroll_seconds=[
                        float(value)
                        for value in animation_set.get(
                            "preroll_seconds", [-0.1, -0.05]
                        )
                    ],
                    translation_mode=animation_set.get(
                        "translation_mode", "absolute"
                    ),
                    max_abs_source_position=float(
                        animation_set.get("max_abs_source_position", 1000.0)
                    ),
                    reference_dmx_frame=animation_set.get(
                        "reference_dmx_frame", "source-axes"
                    ),
                    secondary_joints=secondary_joints,
                    secondary_attach_bone=animation_set.get(
                        "secondary_attach_bone", "wpn"
                    ),
                )
                patched_kv2 = work / "generated.dmx.kv2"
                patched_kv2.parent.mkdir(parents=True, exist_ok=True)
                patched_kv2.write_text(patched_text, encoding="utf-8")

                output_dmx = project_path(
                    manifest_path,
                    action_entry["output_dmx"],
                    field=f"{animation_set['id']}.{action_entry['id']}.output_dmx",
                )
                output_before = file_state(output_dmx)
                generated_binary = work / "generated.dmx"
                convert_to_binary(dmxconvert, patched_kv2, generated_binary)
                roundtrip = work / "roundtrip.dmx.kv2"
                convert_to_kv2(dmxconvert, generated_binary, roundtrip)
                roundtrip_text = roundtrip.read_text(encoding="utf-8")
                lengths = parse_array_lengths(roundtrip_text)
                expected_samples = int(metrics["samples"])
                invalid = {
                    channel: values
                    for channel, values in lengths.items()
                    if values != (expected_samples, expected_samples)
                }
                if invalid or len(lengths) != int(metrics["channel_count"]):
                    raise ManifestError(
                        f"DMX round-trip validation failed for "
                        f"{animation_set['id']}/{action_entry['id']}: "
                        f"channels={len(lengths)}, invalid={invalid}"
                    )

                audit_path = (
                    audit_root
                    / animation_set["id"]
                    / f"{action_entry['id']}.dmx.kv2"
                )
                validated_hash = sha256_file(generated_binary)
                action_report = {
                    "id": action_entry["id"],
                    "blender_action": action.name,
                    "template": str(template),
                    "template_sha256": template_sha256,
                    "reference_receipt": {
                        "scene": scene_receipt,
                        "expected_sha256": expected_reference_hash,
                        "current_sha256": template_sha256,
                        "matched": expected_reference_hash == template_sha256,
                        "drift_allowed": bool(args.allow_reference_drift),
                    },
                    "output_dmx": str(output_dmx),
                    "output_before": output_before,
                    "output_sha256": validated_hash,
                    "audit_kv2": str(audit_path),
                    **metrics,
                }
                set_report["actions"].append(action_report)
                pending_outputs.append(
                    {
                        "source": generated_binary,
                        "destination": output_dmx,
                        "before": output_before,
                        "validated_sha256": validated_hash,
                        "report": action_report,
                    }
                )
                pending_audits.append(
                    {
                        "path": audit_path,
                        "text": roundtrip_text,
                        "report": action_report,
                    }
                )

            set_report["continuity"] = validate_continuity(
                animation_set, actions_by_id
            )
            report["sets"].append(set_report)

        # Re-hash every consumed immutable input before touching final outputs.
        # Process locks coordinate bundled tools; these comparisons also detect
        # an uncooperative external writer and bind the receipt to actual bytes.
        manifest_after = file_state(manifest_path)
        dmxconvert_after = file_state(dmxconvert)
        input_provenance["manifest"]["after"] = manifest_after
        input_provenance["dmxconvert"]["after"] = dmxconvert_after
        input_drift: list[str] = []
        if manifest_after != manifest_before:
            input_drift.append(str(manifest_path))
        if dmxconvert_after != dmxconvert_before:
            input_drift.append(str(dmxconvert))
        for entry in templates_before:
            after = file_state(Path(entry["path"]))
            entry["after"] = after
            if after != entry["before"]:
                input_drift.append(entry["path"])
        if input_drift:
            raise ManifestError(
                "export inputs changed while being consumed; refusing commit: "
                + ", ".join(input_drift)
            )

        # No final DMX is touched until every selected action has passed template
        # parsing, binary round-trip validation, and every applicable continuity
        # rule across all selected sets.
        transaction = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "prepared",
            "manifest": str(manifest_path),
            "manifest_sha256": current_manifest_hash,
            "input_provenance": input_provenance,
            "outputs": [
                {
                    "destination": str(entry["destination"]),
                    "before": entry["before"],
                    "validated_sha256": entry["validated_sha256"],
                }
                for entry in pending_outputs
            ],
        }
        write_json(transaction_path, transaction)
        try:
            commits = commit_validated_outputs(pending_outputs)
        except BaseException as exc:
            transaction["status"] = transaction_failure_status(exc)
            transaction["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
            }
            write_json(transaction_path, transaction)
            raise
        transaction["status"] = "committed"
        transaction["commits"] = commits
        write_json(transaction_path, transaction)
        for pending, commit in zip(pending_outputs, commits, strict=True):
            pending["report"]["atomic_commit"] = commit
        for audit in pending_audits:
            audit_path = Path(audit["path"])
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(audit["text"], encoding="utf-8")
            audit["report"]["audit_kv2_sha256"] = sha256_file(audit_path)

    report["status"] = "ok"
    report["transaction_journal"] = str(transaction_path)
    report["transaction_journal_sha256_before_report"] = sha256_file(
        transaction_path
    )
    report_path = report_root / f"dmx-export-report-{run_id}.json"
    write_json_new(report_path, report)
    write_json(report_root / "dmx-export-report.json", report)
    transaction["status"] = "reported"
    transaction["report"] = str(report_path)
    transaction["report_sha256"] = sha256_file(report_path)
    write_json(transaction_path, transaction)
    print(json.dumps({"status": "ok", "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
