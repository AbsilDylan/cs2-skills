#!/usr/bin/env python3
"""Compile a manifest with the current CS2 ResourceCompiler, safely.

Portable projects are staged into the declared addon with hash-aware copy
guards. Valve-derived ``stock_dependencies`` are staged only for the duration
of the build; sources are restored/removed afterwards, and compiled outputs
with ``package: false`` never remain in the addon output tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from animgraph2_manifest import (  # noqa: E402
    ManifestError,
    ProcessLockSet,
    load_manifest,
    normalize_resource_path,
    probe_versioned_receipt_create,
    project_path,
    reference_dmx_relative,
    reference_vnmclip_relative,
    resolve_cs2_root,
    resolve_tool,
    resource_output_path,
    sha256_file,
    write_json,
    write_json_new,
)
from extract_stock_references import verify_reference_cache  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--cs2-root")
    parser.add_argument("--resourcecompiler")
    parser.add_argument("--reference-root", help="Local extracted stock cache")
    parser.add_argument(
        "--stage",
        action="store_true",
        help="Stage project sources into content/csgo_addons/<addon>",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help=(
            "Allow a staged project source or artifact to replace different "
            "content. Every preimage is retained under .local/backups."
        ),
    )
    parser.add_argument(
        "--resource",
        dest="resources",
        action="append",
        help="Compile only this declared project resource; repeat as needed",
    )
    parser.add_argument("--artifact-root", help="Copy package=true outputs here")
    parser.add_argument(
        "--allow-unverified-reference-cache",
        action="store_true",
        help="Proceed without a valid extraction receipt and record the bypass",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def native_path(root: Path, resource: str) -> Path:
    normalized = normalize_resource_path(resource, field="resource")
    return root.joinpath(*PurePosixPath(normalized).parts)


def generated_sources(manifest: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for animation_set in manifest["sets"]:
        for action in animation_set["actions"]:
            result.extend([action["output_dmx"], action["output_vnmclip"]])
            if action.get("event_tracks_file"):
                result.append(action["event_tracks_file"])
    return list(dict.fromkeys(result))


def stock_dependencies(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("stock_dependencies", []))


def required_reference_outputs(manifest: dict[str, Any]) -> list[str]:
    outputs: list[str] = []
    for animation_set in manifest["sets"]:
        for action in animation_set["actions"]:
            resource = action["reference_resource"]
            outputs.extend(
                [reference_dmx_relative(resource), reference_vnmclip_relative(resource)]
            )
    for dependency in stock_dependencies(manifest):
        outputs.extend(dependency["outputs"])
    return list(dict.fromkeys(outputs))


def compile_resources(manifest: dict[str, Any]) -> list[str]:
    explicit = manifest.get("compile_resources", [])
    if explicit:
        return list(explicit)
    return [
        action["output_vnmclip"]
        for animation_set in manifest["sets"]
        for action in animation_set["actions"]
    ]


def stage_sources(manifest: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            generated_sources(manifest)
            + list(manifest.get("stage_sources", []))
            + compile_resources(manifest)
        )
    )


def select_resources(declared: list[str], requested: list[str] | None) -> list[str]:
    if not requested:
        return declared
    normalized_requested = [
        normalize_resource_path(value, field="--resource") for value in requested
    ]
    unknown = set(normalized_requested) - set(declared)
    if unknown:
        raise ManifestError(
            "--resource must be listed in compile_resources; unknown: "
            + ", ".join(sorted(unknown))
        )
    return [resource for resource in declared if resource in normalized_requested]


def file_state(path: Path) -> dict[str, Any]:
    if path.exists() and not path.is_file():
        raise ManifestError(f"expected a file path, found another object: {path}")
    if not path.is_file():
        return {"exists": False}
    stat = path.stat()
    return {
        "exists": True,
        "sha256": sha256_file(path),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def file_identity(path: Path) -> dict[str, int] | None:
    """Return an identity token that survives hard-link/rename publication."""

    if not path.is_file():
        return None
    stat = path.stat()
    if int(stat.st_ino) == 0:
        return None
    return {"device": int(stat.st_dev), "inode": int(stat.st_ino)}


def guarded_destination_path(destination: Path, allowed_root: Path) -> Path:
    """Resolve a write target and reject escapes through symlinks/junctions."""

    root = allowed_root.expanduser().resolve()
    declared = destination.expanduser().absolute()
    try:
        relative = declared.relative_to(root)
    except ValueError as exc:
        raise ManifestError(
            f"write destination escapes its declared root: {destination} -> {root}"
        ) from exc
    cursor = root
    for part in relative.parts:
        cursor /= part
        if cursor.exists() and (
            cursor.is_symlink()
            or (hasattr(cursor, "is_junction") and cursor.is_junction())
        ):
            raise ManifestError(
                f"refusing write through symlink/junction component: {cursor}"
            )
    resolved = destination.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ManifestError(
            f"resolved write destination escapes its declared root: {resolved}"
        )
    return resolved


def _temporary_sibling(path: Path, suffix: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=suffix, dir=path.parent
    )
    os.close(descriptor)
    return Path(name)


def _publish_file_no_replace(source: Path, destination: Path) -> str:
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise ManifestError(
            f"destination appeared during safe publication; recovery preserved: "
            f"{source} -> {destination}"
        ) from exc
    except OSError as link_exc:
        if os.name != "nt":
            raise ManifestError(
                "safe publication requires hard-link support on this filesystem; "
                f"recovery preserved: {source}"
            ) from link_exc
        try:
            os.rename(source, destination)
        except FileExistsError as exc:
            raise ManifestError(
                f"destination appeared during safe publication; recovery preserved: "
                f"{source} -> {destination}"
            ) from exc
        except OSError as rename_exc:
            raise ManifestError(
                f"safe no-replace publication failed; recovery preserved: {source}"
            ) from rename_exc
        return "windows-no-replace-rename"
    source.unlink()
    return "hard-link"


class CompileRollbackFailure(RuntimeError):
    """A compile-side mutation failed and could not be rolled back safely."""


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid managed-stage receipt: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"managed-stage receipt must be an object: {path}")
    return value


def stale_managed_stage_resources(
    installed_content_root: Path,
    current_resources: list[str],
    previous: dict[str, Any] | None,
) -> list[str]:
    if not previous:
        return []
    current = {resource.casefold() for resource in current_resources}
    stale = []
    for resource in previous.get("managed_resources", []):
        normalized = normalize_resource_path(resource, field="managed stage resource")
        if normalized.casefold() not in current and native_path(
            installed_content_root, normalized
        ).is_file():
            stale.append(normalized)
    return sorted(stale, key=str.casefold)


def artifact_inventory(root: Path) -> dict[str, dict[str, Any]]:
    if not root.exists():
        return {}
    if not root.is_dir():
        raise ManifestError(f"artifact root is not a directory: {root}")
    result: dict[str, dict[str, Any]] = {}
    for value in root.rglob("*"):
        if value.is_symlink() or (
            hasattr(value, "is_junction") and value.is_junction()
        ):
            raise ManifestError(f"artifact root contains a symlink/junction: {value}")
    for path in sorted((value for value in root.rglob("*") if value.is_file())):
        relative = path.relative_to(root).as_posix()
        key = relative.casefold()
        if key in result:
            raise ManifestError(f"case-colliding artifact paths under {root}: {relative}")
        result[key] = {"resource": relative, **file_state(path)}
    return result


def reject_artifact_extras(root: Path, expected_resources: list[str]) -> None:
    expected = {resource.casefold() for resource in expected_resources}
    extras = [
        entry["resource"]
        for key, entry in artifact_inventory(root).items()
        if key not in expected
    ]
    if extras:
        raise ManifestError(
            f"artifact root contains stale/undeclared files: {extras}; use a new "
            "empty root or archive/remove them explicitly"
        )


def preflight_artifact_copies(
    root: Path,
    planned: list[tuple[Path, str]],
    *,
    force_overwrite: bool,
) -> None:
    """Validate the complete artifact transaction before copying any file."""

    expected = [resource for _, resource in planned]
    reject_artifact_extras(root, expected)
    conflicts: list[str] = []
    for source, resource in planned:
        if not source.is_file():
            raise FileNotFoundError(f"artifact source missing: {source}")
        destination = guarded_destination_path(native_path(root, resource), root)
        before = file_state(destination)
        if (
            before.get("exists")
            and before["sha256"] != sha256_file(source)
            and not force_overwrite
        ):
            conflicts.append(resource)
    if conflicts:
        raise ManifestError(
            "artifact destinations contain different declared files: "
            f"{sorted(conflicts, key=str.casefold)}; pass --force-overwrite "
            "to preserve every preimage, or use a new empty root"
        )


def verify_artifact_closure(
    root: Path,
    expected_resources: list[str],
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    inventory = artifact_inventory(root)
    expected_keys = {resource.casefold() for resource in expected_resources}
    if set(inventory) != expected_keys:
        raise RuntimeError(
            "artifact closure mismatch after copy: "
            f"expected={sorted(expected_resources)}, "
            f"actual={sorted(value['resource'] for value in inventory.values())}"
        )
    expected_states = {
        receipt["resource"].casefold(): receipt["destination_after"]
        for receipt in receipts
    }
    if set(expected_states) != expected_keys:
        raise RuntimeError(
            "artifact receipt closure mismatch: "
            f"expected={sorted(expected_keys)}, receipts={sorted(expected_states)}"
        )
    drifted = [
        inventory[key]["resource"]
        for key in sorted(expected_keys)
        if not _content_state_matches(inventory[key], expected_states[key])
    ]
    if drifted:
        raise RuntimeError(
            "artifact content drifted after copy; refusing verified closure: "
            f"{drifted}"
        )
    return {
        "verified": True,
        "root": str(root),
        "resources": list(inventory.values()),
    }


def backup_destination(destination: Path, backup_root: Path) -> Path:
    key = hashlib.sha256(str(destination).encode("utf-8")).hexdigest()[:16]
    backup = backup_root / key / destination.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        raise ManifestError(f"refusing to overwrite an existing run backup: {backup}")
    expected = file_state(destination)
    if not expected.get("exists"):
        raise FileNotFoundError(f"cannot back up a missing destination: {destination}")
    shutil.copy2(destination, backup)
    if file_state(backup).get("sha256") != expected["sha256"]:
        raise RuntimeError(f"backup hash mismatch: {destination} -> {backup}")
    return backup


def _content_state_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if bool(actual.get("exists")) != bool(expected.get("exists")):
        return False
    if not actual.get("exists"):
        return True
    return actual.get("sha256") == expected.get("sha256") and (
        "bytes" not in expected or actual.get("bytes") == expected.get("bytes")
    )


def _rollback_owned_destination(
    destination: Path,
    *,
    before: dict[str, Any],
    owned_after: dict[str, Any],
    owned_identity: dict[str, int] | None,
    preimage: Path | None,
    label: str,
) -> dict[str, Any]:
    """Restore a preimage only while the destination is still owned by this run."""

    current = file_state(destination)
    if current == before:
        if preimage is not None and preimage.exists():
            preimage.unlink()
        return {"action": "already-restored", "state": current}
    if not current.get("exists"):
        if before.get("exists"):
            if preimage is None or file_state(preimage) != before:
                raise ManifestError(
                    f"{label} preimage is missing or changed; recovery preserved: "
                    f"{preimage}"
                )
            _publish_file_no_replace(preimage, destination)
            restored = file_state(destination)
            if restored != before:
                raise ManifestError(
                    f"{label} restored preimage failed verification: {destination}"
                )
            return {"action": "restored-preimage", "state": restored}
        return {"action": "already-absent", "state": current}

    ownership_mismatch = not _content_state_matches(
        current, owned_after
    ) or (
        owned_identity is not None
        and file_identity(destination) != owned_identity
    )
    quarantine = _temporary_sibling(destination, ".rollback-current")
    os.replace(destination, quarantine)
    quarantined_state = file_state(quarantine)
    quarantined_identity = file_identity(quarantine)
    if not _content_state_matches(
        quarantined_state, owned_after
    ) or (
        owned_identity is not None
        and quarantined_identity != owned_identity
    ):
        _publish_file_no_replace(quarantine, destination)
        raise ManifestError(
            f"{label} destination changed before rollback ownership could be "
            f"claimed; foreign content restored without clobber: {current}"
        )
    if ownership_mismatch:
        _publish_file_no_replace(quarantine, destination)
        raise ManifestError(
            f"{label} destination ownership changed during rollback inspection"
        )

    if before.get("exists"):
        if preimage is None or file_state(preimage) != before:
            _publish_file_no_replace(quarantine, destination)
            raise ManifestError(
                f"{label} preimage is missing or changed; recovery preserved: "
                f"{preimage}"
            )
        _publish_file_no_replace(preimage, destination)
        restored = file_state(destination)
        if restored != before:
            corrupt = _temporary_sibling(destination, ".rollback-corrupt")
            os.replace(destination, corrupt)
            _publish_file_no_replace(quarantine, destination)
            raise ManifestError(
                f"{label} preimage changed during restoration; validated current "
                f"content restored and suspect bytes preserved: {corrupt}"
            )
        action = "restored-preimage"
    else:
        restored = {"exists": False}
        action = "removed-created"
    if quarantine.exists():
        quarantine.unlink()
    return {"action": action, "state": restored}


def copy_with_policy(
    source: Path,
    destination: Path,
    *,
    allowed_root: Path,
    force_overwrite: bool,
    backup_root: Path,
    dry_run: bool,
    label: str,
    registry: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Copy without silently replacing a different destination."""

    if not source.is_file():
        raise FileNotFoundError(f"{label} missing: {source}")
    source = source.resolve()
    destination = guarded_destination_path(destination, allowed_root)
    source_state = file_state(source)
    before = file_state(destination)
    receipt: dict[str, Any] = {
        "label": label,
        "source": str(source),
        "destination": str(destination),
        "source_state": source_state,
        "destination_before": before,
        "dry_run": dry_run,
    }

    def register_once() -> None:
        if registry is not None and receipt not in registry:
            registry.append(receipt)

    if source == destination:
        receipt["action"] = "same-file"
        receipt["destination_after"] = before
        register_once()
        return receipt
    if before.get("exists") and before["sha256"] == source_state["sha256"]:
        receipt["action"] = "unchanged-identical"
        receipt["destination_after"] = before
        register_once()
        return receipt
    if before.get("exists") and not force_overwrite:
        raise ManifestError(
            f"refusing to overwrite different {label}: {destination}; pass "
            "--force-overwrite to preserve its preimage and continue"
        )
    receipt["action"] = "overwritten" if before.get("exists") else "created"
    if not dry_run:
        if before.get("exists"):
            receipt["backup"] = str(backup_destination(destination, backup_root))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = guarded_destination_path(destination, allowed_root)
        temporary = _temporary_sibling(destination, ".pending")
        preimage: Path | None = None
        mutation_started = False
        preserve_recovery = False
        owned_after = {
            "exists": True,
            "sha256": source_state["sha256"],
            "bytes": source_state["bytes"],
        }
        owned_identity: dict[str, int] | None = None
        try:
            shutil.copy2(source, temporary)
            if file_state(temporary).get("sha256") != source_state["sha256"]:
                raise RuntimeError(f"temporary copy hash mismatch for {label}")
            owned_identity = file_identity(temporary)
            if owned_identity is None:
                raise RuntimeError(f"temporary copy identity missing for {label}")
            receipt["destination_after"] = owned_after
            receipt["destination_identity"] = owned_identity
            register_once()
            if file_state(destination) != before:
                raise ManifestError(
                    f"{label} destination changed immediately before publication: "
                    f"{destination}"
                )
            if before.get("exists"):
                preimage = _temporary_sibling(destination, ".preimage")
                os.replace(destination, preimage)
                mutation_started = True
                if file_state(preimage) != before:
                    _publish_file_no_replace(preimage, destination)
                    preimage = None
                    raise ManifestError(
                        f"{label} destination changed while claiming its preimage"
                    )
            mutation_started = True
            receipt["publication"] = _publish_file_no_replace(
                temporary, destination
            )
            temporary = None
            after = file_state(destination)
            if not _content_state_matches(after, owned_after):
                raise RuntimeError(f"published copy hash mismatch for {label}")
            receipt["destination_after"] = after
            receipt["destination_identity"] = owned_identity
            if preimage is not None and preimage.exists():
                preimage.unlink()
                preimage = None
        except BaseException as exc:
            if mutation_started:
                try:
                    _rollback_owned_destination(
                        destination,
                        before=before,
                        owned_after=owned_after,
                        owned_identity=owned_identity,
                        preimage=preimage,
                        label=label,
                    )
                    preimage = None
                except BaseException as rollback_exc:
                    preserve_recovery = True
                    recovery = [
                        str(path)
                        for path in (temporary, preimage)
                        if path is not None and path.exists()
                    ]
                    raise CompileRollbackFailure(
                        f"{label} copy failed ({exc}); rollback also failed: "
                        f"{rollback_exc}; recovery files preserved: {recovery}"
                    ) from exc
            raise
        finally:
            if not preserve_recovery and temporary is not None and temporary.exists():
                temporary.unlink()
            if not preserve_recovery and preimage is not None and preimage.exists():
                preimage.unlink()
    else:
        receipt["destination_after"] = source_state
        register_once()
    return receipt


def run(command: list[str], *, timeout_seconds: int = 600) -> tuple[str, str]:
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
            f"ResourceCompiler timed out after {timeout_seconds}s: {' '.join(command)}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"ResourceCompiler failed ({result.returncode})\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}\n\n"
            "If the compiler reports an unknown VNMClip/VNMGraph type, inspect "
            "the current Workshop Tools registration. Back up and obtain approval "
            "before changing installed tool configuration."
        )
    return result.stdout, result.stderr


def restore_temporary_stage(receipt: dict[str, Any]) -> dict[str, Any]:
    """Undo only a dependency source mutation made by this run."""

    destination = Path(receipt["destination"])
    action = receipt["action"]
    cleanup = {"destination": str(destination), "action": "left-preexisting"}
    if action not in {"created", "overwritten"}:
        return cleanup
    before = receipt["destination_before"]
    owned_after = receipt["destination_after"]
    current = file_state(destination)
    if current == before:
        cleanup["action"] = "already-restored"
        cleanup["restored_state"] = current
        return cleanup
    preimage: Path | None = None
    if action == "overwritten":
        backup = Path(receipt["backup"])
        if file_state(backup) != before:
            raise ManifestError(
                f"staging backup changed before cleanup; preserving destination: {backup}"
            )
        preimage = _temporary_sibling(destination, ".restore-preimage")
        shutil.copy2(backup, preimage)
        if file_state(preimage) != before:
            raise RuntimeError(f"staging recovery copy hash mismatch: {destination}")
    result = _rollback_owned_destination(
        destination,
        before=before,
        owned_after=owned_after,
        owned_identity=receipt.get("destination_identity"),
        preimage=preimage,
        label=f"temporary stage {destination}",
    )
    cleanup["action"] = result["action"]
    cleanup["restored_state"] = result["state"]
    return cleanup


def restore_nonpackage_output(guard: dict[str, Any]) -> dict[str, Any]:
    output = Path(guard["output"])
    before = guard["before"]
    cleanup: dict[str, Any] = {"output": str(output)}
    current = file_state(output)
    if current == before:
        cleanup["action"] = "already-restored"
        cleanup["restored_state"] = current
        return cleanup
    compiled_state = guard.get("compiled_state")
    if not isinstance(compiled_state, dict):
        raise ManifestError(
            "compiler output changed but no owned post-compile state was captured; "
            f"preserving for manual review: {output}"
        )
    preimage: Path | None = None
    if before.get("exists"):
        backup = Path(guard["backup"])
        if file_state(backup) != before:
            raise ManifestError(
                f"compiled-output backup changed before cleanup: {backup}"
            )
        preimage = _temporary_sibling(output, ".restore-preimage")
        shutil.copy2(backup, preimage)
        if file_state(preimage) != before:
            raise RuntimeError(f"compiled-output recovery hash mismatch: {output}")
    result = _rollback_owned_destination(
        output,
        before=before,
        owned_after=compiled_state,
        owned_identity=guard.get("compiled_identity"),
        preimage=preimage,
        label=f"non-package compiler output {output}",
    )
    cleanup["action"] = result["action"]
    cleanup["restored_state"] = result["state"]
    return cleanup


def write_compile_report(
    project_root: Path, run_id: str, report: dict[str, Any]
) -> Path:
    report_root = project_root / ".local" / "reports"
    report_path = report_root / f"compile-report-{run_id}.json"
    write_json_new(report_path, report)
    write_json(report_root / "compile-report.json", report)
    return report_path


def unresolved_compile_transactions(report_root: Path) -> list[dict[str, str]]:
    unresolved: list[dict[str, str]] = []
    if not report_root.is_dir():
        return unresolved
    for path in sorted(report_root.glob("compile-transaction-*.json")):
        value: Any = None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            status = value.get("status") if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            status = "invalid"
        terminal = False
        if isinstance(value, dict) and status in {"failed", "reported"}:
            run_id = value.get("run_id")
            digest = value.get("manifest_sha256")
            common_valid = (
                value.get("schema_version") == 1
                and isinstance(run_id, str)
                and bool(run_id)
                and path.name == f"compile-transaction-{run_id}.json"
                and isinstance(value.get("manifest"), str)
                and isinstance(digest, str)
                and len(digest) == 64
                and all(character in "0123456789abcdef" for character in digest)
                and isinstance(value.get("project_root"), str)
                and isinstance(value.get("installed_content_root"), str)
                and isinstance(value.get("resources"), list)
                and isinstance(value.get("managed_stage_resources"), list)
            )
            if common_valid and status == "failed":
                error = value.get("error")
                terminal = (
                    isinstance(error, dict)
                    and isinstance(error.get("type"), str)
                    and isinstance(error.get("message"), str)
                )
            elif common_valid and status == "reported":
                expected_report = (
                    report_root / f"compile-report-{run_id}.json"
                ).resolve()
                try:
                    declared_report = Path(value.get("report", "")).resolve()
                    report_state = file_state(expected_report)
                except (OSError, RuntimeError, TypeError, ValueError, ManifestError):
                    report_state = {"exists": False}
                    declared_report = Path()
                terminal = (
                    declared_report == expected_report
                    and report_state.get("exists") is True
                    and value.get("report_sha256") == report_state.get("sha256")
                )
        if terminal:
            continue
        unresolved.append(
            {
                "path": str(path),
                "status": str(status) if isinstance(status, str) else "invalid",
            }
        )
    return unresolved


def main() -> int:
    args = parse_args()
    manifest_path, manifest = load_manifest(args.manifest)
    artifact_policy = manifest["project"].get(
        "artifact_policy", {"status": "blocked", "basis": "undeclared"}
    )
    if args.artifact_root:
        if args.resources:
            raise ManifestError(
                "--artifact-root is forbidden with --resource subsets; artifacts "
                "must represent the complete declared closure"
            )
        if (
            not isinstance(artifact_policy, dict)
            or artifact_policy.get("status") != "allowed"
            or not isinstance(artifact_policy.get("basis"), str)
            or not artifact_policy["basis"].strip()
            or not isinstance(
                artifact_policy.get("template_derivative_basis"), str
            )
            or not artifact_policy["template_derivative_basis"].strip()
        ):
            raise ManifestError(
                "--artifact-root requires project.artifact_policy with "
                "status='allowed', a non-empty basis, and a non-empty "
                "template_derivative_basis"
            )
    for dependency in stock_dependencies(manifest):
        if dependency.get("package") and (
            not isinstance(dependency.get("redistribution_basis"), str)
            or not dependency["redistribution_basis"].strip()
        ):
            raise ManifestError(
                f"packaged stock dependency {dependency['resource']} requires a "
                "non-empty redistribution_basis"
            )
    cs2_root = resolve_cs2_root(args.cs2_root)
    compiler = resolve_tool(
        args.resourcecompiler,
        ("RESOURCECOMPILER",),
        cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe",
        "ResourceCompiler",
    )
    addon = manifest["project"]["addon"]
    installed_content_root = (
        cs2_root / "content" / "csgo_addons" / addon
    ).resolve()
    project_root = manifest_path.parent.resolve()
    reference_root = (
        Path(args.reference_root).expanduser().resolve()
        if args.reference_root
        else project_root / ".local" / "references"
    )
    artifact_root = (
        Path(args.artifact_root).expanduser().resolve() if args.artifact_root else None
    )
    lock_roots = [project_root, installed_content_root]
    if artifact_root is not None:
        lock_roots.append(artifact_root)
    with ProcessLockSet(lock_roots):
        manifest_locked_state = file_state(manifest_path)
        locked_manifest_path, locked_manifest = load_manifest(manifest_path)
        if locked_manifest_path != manifest_path:
            raise ManifestError("resolved manifest path changed while locking")
        if file_state(manifest_path) != manifest_locked_state:
            raise ManifestError("manifest changed while it was being loaded")
        if locked_manifest != manifest:
            raise ManifestError(
                "manifest changed before compile locks were acquired; retry from "
                "the newly validated manifest"
            )
        return _main_locked(
            args,
            manifest_path,
            locked_manifest,
            artifact_policy,
            cs2_root,
            compiler,
            addon,
            installed_content_root,
            project_root,
            reference_root,
            artifact_root,
            manifest_locked_state,
        )


def _main_locked(
    args: argparse.Namespace,
    manifest_path: Path,
    manifest: dict[str, Any],
    artifact_policy: dict[str, Any],
    cs2_root: Path,
    compiler: Path,
    addon: str,
    installed_content_root: Path,
    project_root: Path,
    reference_root: Path,
    artifact_root: Path | None,
    manifest_locked_state: dict[str, Any],
) -> int:
    if file_state(manifest_path) != manifest_locked_state:
        raise ManifestError("manifest changed after compile locks were acquired")
    run_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    backup_root = project_root / ".local" / "backups" / run_id
    staged_project: list[dict[str, Any]] = []
    staged_dependencies: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    cleanup_errors: list[dict[str, str]] = []
    reference_cache_receipt: dict[str, Any] | None = None
    receipt_create_methods: dict[str, str] = {}
    project_report_root = project_root / ".local" / "reports"
    transaction: dict[str, Any] | None = None
    transaction_path: Path | None = None
    if not args.dry_run:
        unresolved = unresolved_compile_transactions(project_report_root)
        if unresolved:
            raise ManifestError(
                "unresolved prior compile transaction(s); inspect/restore outputs "
                f"and archive the journals before retrying: {unresolved}"
            )
        receipt_create_methods["project"] = probe_versioned_receipt_create(
            project_report_root
        )
        transaction_path = project_report_root / f"compile-transaction-{run_id}.json"
        if args.stage:
            installed_report_root = installed_content_root / ".local" / "reports"
            if installed_report_root.resolve() == project_report_root.resolve():
                receipt_create_methods["installed"] = receipt_create_methods[
                    "project"
                ]
            else:
                receipt_create_methods["installed"] = (
                    probe_versioned_receipt_create(installed_report_root)
                )
    gameinfo = cs2_root / "game" / "csgo" / "gameinfo.gi"
    provenance_before = {
        "manifest": manifest_locked_state,
        "gameinfo": file_state(gameinfo),
        "compiler": file_state(compiler),
    }

    def current_provenance() -> dict[str, dict[str, Any]]:
        return {
            "manifest": file_state(manifest_path),
            "gameinfo": file_state(gameinfo),
            "compiler": file_state(compiler),
        }

    def assert_provenance_unchanged() -> dict[str, dict[str, Any]]:
        current = current_provenance()
        drift = {
            key: {"before": provenance_before[key], "after": current[key]}
            for key in provenance_before
            if current[key] != provenance_before[key]
        }
        if drift:
            raise ManifestError(
                f"build provenance changed during the compile run: {drift}"
            )
        return current

    def current_provenance_for_report() -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for key, path in (
            ("manifest", manifest_path),
            ("gameinfo", gameinfo),
            ("compiler", compiler),
        ):
            try:
                result[key] = file_state(path)
            except BaseException as exc:
                result[key] = {
                    "capture_error": f"{type(exc).__name__}: {exc}"
                }
        return result

    def transition_transaction(status: str, **fields: Any) -> None:
        if args.dry_run:
            return
        if transaction is None or transaction_path is None:
            raise RuntimeError("compile transaction journal is not initialized")
        transaction["status"] = status
        transaction.update(fields)
        write_json(transaction_path, transaction)

    def write_prebuild_failure(phase: str, exc: BaseException) -> None:
        if args.dry_run:
            return
        payload = {
            "schema_version": 2,
            "status": "failed",
            "phase": phase,
            "run_id": run_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path),
            "manifest_sha256": provenance_before["manifest"]["sha256"],
            "artifact_policy": artifact_policy,
            "allow_unverified_reference_cache": (
                args.allow_unverified_reference_cache
            ),
            "reference_cache": reference_cache_receipt,
            "cs2_root": str(cs2_root),
            "gameinfo": str(gameinfo),
            "gameinfo_state": provenance_before["gameinfo"],
            "compiler": str(compiler),
            "compiler_state": provenance_before["compiler"],
            "provenance_before": provenance_before,
            "provenance_after": current_provenance_for_report(),
            "versioned_receipt_create_methods": receipt_create_methods,
            "project_root": str(project_root),
            "installed_content_root": str(installed_content_root),
            "reference_root": str(reference_root),
            "force_overwrite": args.force_overwrite,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "staged_project": staged_project,
            "staged_dependencies": staged_dependencies,
            "cleanup": cleanup,
            "cleanup_errors": cleanup_errors,
            "compiled": receipts,
            "artifacts": [],
            "artifact_closure": None,
            "installed_addon_closure_verified": False,
            "transaction_journal": (
                None if transaction is None or transaction_path is None
                else str(transaction_path)
            ),
            "transaction_status": (
                None if transaction is None else transaction.get("status")
            ),
        }
        try:
            write_compile_report(project_root, run_id, payload)
        except BaseException as report_exc:
            print(
                f"WARNING: could not write pre-build failure receipt: {report_exc}",
                file=sys.stderr,
            )

    try:
        reference_cache_receipt = verify_reference_cache(
            reference_root,
            manifest_path,
            required_reference_outputs(manifest),
            allow_unverified=args.allow_unverified_reference_cache,
        )
        resources = select_resources(compile_resources(manifest), args.resources)
        if not resources:
            raise ManifestError("there are no resources to compile")
        if project_root != installed_content_root and not args.stage:
            raise ManifestError(
                f"manifest directory is not the installed addon content root:\n"
                f"  project: {project_root}\n  installed: {installed_content_root}\n"
                "Pass --stage to copy declared/generated sources before compiling."
            )
    except BaseException as exc:
        write_prebuild_failure("preflight", exc)
        raise

    try:
        managed_stage_resources = stage_sources(manifest)
        stage_report_root = installed_content_root / ".local" / "reports"
        stage_index_latest = stage_report_root / "animgraph2-stage-index.json"
        previous_stage_index = read_json_object(stage_index_latest)
        stale_stage = stale_managed_stage_resources(
            installed_content_root, managed_stage_resources, previous_stage_index
        )
        if stale_stage:
            raise ManifestError(
                "previously managed staged sources are no longer declared but still "
                f"exist: {stale_stage}; archive/remove them explicitly before staging"
            )
    except BaseException as exc:
        write_prebuild_failure("managed-stage-preflight", exc)
        raise

    if not args.dry_run:
        transaction = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "prepared",
            "manifest": str(manifest_path),
            "manifest_sha256": provenance_before["manifest"]["sha256"],
            "project_root": str(project_root),
            "installed_content_root": str(installed_content_root),
            "artifact_root": str(artifact_root) if artifact_root else None,
            "resources": resources,
            "managed_stage_resources": managed_stage_resources,
        }
        write_json(transaction_path, transaction)

    def write_stage_receipt(status: str, managed: list[str]) -> None:
        if args.dry_run or not args.stage:
            return
        payload = {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "manifest": str(manifest_path),
            "manifest_sha256": provenance_before["manifest"]["sha256"],
            "versioned_receipt_create_method": receipt_create_methods.get(
                "installed"
            ),
            "managed_resources": managed,
            "staged": staged_project,
        }
        write_json_new(
            stage_report_root / f"animgraph2-stage-index-{run_id}.json", payload
        )
        write_json(stage_index_latest, payload)

    if args.stage:
        staged_resource_names: list[str] = []
        try:
            for resource in managed_stage_resources:
                source = project_path(manifest_path, resource, field=f"stage source {resource}")
                if not source.is_file():
                    if resource in resources:
                        raise FileNotFoundError(f"compile source missing: {source}")
                    continue
                receipt = copy_with_policy(
                    source,
                    native_path(installed_content_root, resource),
                    allowed_root=installed_content_root,
                    force_overwrite=args.force_overwrite,
                    backup_root=backup_root / "project-stage",
                    dry_run=args.dry_run,
                    label=f"project source {resource}",
                )
                receipt["resource"] = resource
                staged_project.append(receipt)
                staged_resource_names.append(resource)
        except BaseException as exc:
            try:
                transition_transaction(
                    "stage-failed",
                    staged_project=staged_project,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except BaseException as journal_exc:
                print(
                    f"WARNING: could not update compile transaction: {journal_exc}",
                    file=sys.stderr,
                )
            try:
                write_stage_receipt("partial-failed", staged_resource_names)
            except BaseException as stage_report_exc:
                print(
                    "WARNING: could not write partial stage receipt: "
                    f"{stage_report_exc}",
                    file=sys.stderr,
                )
            write_prebuild_failure("project-staging", exc)
            raise
        try:
            write_stage_receipt("staged", staged_resource_names)
        except BaseException as exc:
            try:
                transition_transaction(
                    "stage-failed",
                    staged_project=staged_project,
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except BaseException as journal_exc:
                print(
                    f"WARNING: could not update compile transaction: {journal_exc}",
                    file=sys.stderr,
                )
            write_prebuild_failure("stage-receipt", exc)
            raise

    # Dependencies are always sourced from the extraction cache, even when the
    # manifest already lives in the installed addon. Their staging is temporary.
    try:
        for dependency in stock_dependencies(manifest):
            for resource in dependency["outputs"]:
                receipt = copy_with_policy(
                    native_path(reference_root, resource),
                    native_path(installed_content_root, resource),
                    allowed_root=installed_content_root,
                    force_overwrite=args.force_overwrite,
                    backup_root=backup_root / "dependency-stage",
                    dry_run=args.dry_run,
                    label=f"stock dependency source {resource}",
                    registry=staged_dependencies,
                )
                receipt["temporary"] = True
        transition_transaction(
            "staged",
            staged_project=staged_project,
            staged_dependencies=staged_dependencies,
        )
    except BaseException as exc:
        if not args.dry_run:
            for receipt in reversed(staged_dependencies):
                try:
                    cleanup.append(restore_temporary_stage(receipt))
                except BaseException as cleanup_exc:
                    cleanup_errors.append(
                        {
                            "operation": "restore-temporary-stage",
                            "target": receipt.get("destination", "<unknown>"),
                            "error_type": type(cleanup_exc).__name__,
                            "error": str(cleanup_exc),
                        }
                    )
        try:
            transition_transaction(
                "rollback-failed" if cleanup_errors else "failed",
                staged_project=staged_project,
                staged_dependencies=staged_dependencies,
                cleanup=cleanup,
                cleanup_errors=cleanup_errors,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        except BaseException as journal_exc:
            print(
                f"WARNING: could not update compile transaction: {journal_exc}",
                file=sys.stderr,
            )
        write_prebuild_failure("dependency-staging", exc)
        raise

    game_root = cs2_root / "game" / "csgo"
    compiled_output_root = (cs2_root / "game" / "csgo_addons" / addon).resolve()
    build_plan = [
        {
            "resource": dependency["compile"],
            "kind": "stock-dependency",
            "package": bool(dependency.get("package", False)),
        }
        for dependency in stock_dependencies(manifest)
    ]
    build_plan.extend(
        {"resource": resource, "kind": "project-resource", "package": True}
        for resource in resources
    )
    unique_plan: list[dict[str, Any]] = []
    seen_plan: set[str] = set()
    for entry in build_plan:
        key = entry["resource"].casefold()
        if key not in seen_plan:
            unique_plan.append(entry)
            seen_plan.add(key)

    output_guards: list[dict[str, Any]] = []
    build_error: BaseException | None = None
    failed_operation: dict[str, Any] | None = None
    try:
        transition_transaction("compiling", build_plan=unique_plan)
        for plan_entry in unique_plan:
            resource = plan_entry["resource"]
            source = native_path(installed_content_root, resource)
            source_for_receipt = source
            if not source.is_file():
                if not args.dry_run:
                    raise FileNotFoundError(f"compile source missing: {source}")
                source_for_receipt = (
                    native_path(reference_root, resource)
                    if plan_entry["kind"] == "stock-dependency"
                    else project_path(
                        manifest_path, resource, field=f"compile source {resource}"
                    )
                )
                if not source_for_receipt.is_file():
                    raise FileNotFoundError(
                        f"planned compile source missing: {source_for_receipt}"
                    )
            output = guarded_destination_path(
                resource_output_path(cs2_root, addon, resource),
                compiled_output_root,
            )
            output_before = file_state(output)
            source_state_before = file_state(source_for_receipt)
            guard: dict[str, Any] | None = None
            if not args.dry_run:
                guard = {
                    "output": str(output),
                    "before": output_before,
                    "package": bool(plan_entry["package"]),
                    "resource": resource,
                }
                if output_before.get("exists"):
                    guard["backup"] = str(
                        backup_destination(output, backup_root / "compiler-output")
                    )
                output_guards.append(guard)

            command = [str(compiler), "-game", str(game_root), "-i", str(source), "-f"]
            failed_operation = {
                "resource": resource,
                "kind": plan_entry["kind"],
                "package": plan_entry["package"],
                "source": str(source),
                "source_state_before": source_state_before,
                "output": str(output),
                "command": command,
            }
            stdout = stderr = ""
            started_ns = time.time_ns()
            if not args.dry_run:
                try:
                    stdout, stderr = run(command)
                except BaseException:
                    if guard is not None:
                        output_after_attempt = file_state(output)
                        if output_after_attempt != output_before:
                            guard["compiled_state"] = output_after_attempt
                            guard["compiled_identity"] = file_identity(output)
                            guard["compiler_failed_after_output_change"] = True
                    raise
                output_after = file_state(output)
                if guard is not None:
                    guard["compiled_state"] = output_after
                    guard["compiled_identity"] = file_identity(output)
                if not output_after.get("exists"):
                    raise FileNotFoundError(
                        f"ResourceCompiler returned success but output is missing: {output}"
                    )
                if (
                    output_before.get("exists")
                    and output_after["sha256"] == output_before["sha256"]
                ):
                    raise RuntimeError(
                        f"ResourceCompiler returned success but output bytes did not "
                        f"change: {output}; refusing a potentially stale receipt"
                    )
            else:
                output_after = {"exists": False, "planned": True}
            source_state_after = file_state(source_for_receipt)
            if source_state_after != source_state_before:
                raise ManifestError(
                    f"compile source changed during ResourceCompiler run: "
                    f"{source_for_receipt}"
                )
            assert_provenance_unchanged()
            receipt = {
                "resource": resource,
                "kind": plan_entry["kind"],
                "package": plan_entry["package"],
                "source": str(source),
                "source_origin": str(source_for_receipt),
                "source_state": source_state_before,
                "source_state_after": source_state_after,
                "command": command,
                "started_ns": started_ns,
                "output": str(output),
                "output_before": output_before,
                "output_after": output_after,
                "stdout": stdout,
                "stderr": stderr,
                "dry_run": args.dry_run,
            }
            receipts.append(receipt)
            failed_operation = None
    except BaseException as exc:
        build_error = exc
    finally:
        if not args.dry_run:
            guards_to_restore = (
                output_guards
                if build_error is not None
                else [guard for guard in output_guards if not guard["package"]]
            )
            for guard in reversed(guards_to_restore):
                try:
                    cleanup.append(restore_nonpackage_output(guard))
                except BaseException as cleanup_exc:
                    cleanup_errors.append(
                        {
                            "operation": "restore-nonpackage-output",
                            "target": guard.get("output", "<unknown>"),
                            "error_type": type(cleanup_exc).__name__,
                            "error": str(cleanup_exc),
                        }
                    )
            for receipt in reversed(staged_dependencies):
                try:
                    cleanup.append(restore_temporary_stage(receipt))
                except BaseException as cleanup_exc:
                    cleanup_errors.append(
                        {
                            "operation": "restore-temporary-stage",
                            "target": receipt.get("destination", "<unknown>"),
                            "error_type": type(cleanup_exc).__name__,
                            "error": str(cleanup_exc),
                        }
                    )
    if build_error is None and cleanup_errors:
        build_error = RuntimeError("post-compile cleanup failed; inspect failure receipt")
    if build_error is not None:
        failure_status = "rollback-failed" if cleanup_errors else "failed"
        try:
            transition_transaction(
                failure_status,
                compiled=receipts,
                compiler_output_guards=output_guards,
                cleanup=cleanup,
                cleanup_errors=cleanup_errors,
                error={
                    "type": type(build_error).__name__,
                    "message": str(build_error),
                },
            )
        except BaseException as journal_exc:
            print(
                f"WARNING: could not update compile transaction: {journal_exc}",
                file=sys.stderr,
            )
        failure_report = {
            "schema_version": 2,
            "status": failure_status,
            "run_id": run_id,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": str(manifest_path),
            "manifest_sha256": provenance_before["manifest"]["sha256"],
            "artifact_policy": artifact_policy,
            "allow_unverified_reference_cache": args.allow_unverified_reference_cache,
            "reference_cache": reference_cache_receipt,
            "cs2_root": str(cs2_root),
            "gameinfo": str(gameinfo),
            "gameinfo_sha256": provenance_before["gameinfo"]["sha256"],
            "compiler": str(compiler),
            "compiler_state": provenance_before["compiler"],
            "provenance_before": provenance_before,
            "provenance_after": current_provenance_for_report(),
            "versioned_receipt_create_methods": receipt_create_methods,
            "project_root": str(project_root),
            "installed_content_root": str(installed_content_root),
            "reference_root": str(reference_root),
            "force_overwrite": args.force_overwrite,
            "error": {
                "type": type(build_error).__name__,
                "message": str(build_error),
            },
            "failed_operation": failed_operation,
            "staged_project": staged_project,
            "staged_dependencies": staged_dependencies,
            "compiled": receipts,
            "compiler_output_guards": output_guards,
            "cleanup": cleanup,
            "cleanup_errors": cleanup_errors,
            "artifacts": [],
            "artifact_closure": None,
            "installed_addon_closure_verified": False,
            "transaction_journal": (
                None if transaction_path is None else str(transaction_path)
            ),
            "transaction_status": failure_status,
        }
        if not args.dry_run:
            try:
                write_compile_report(project_root, run_id, failure_report)
            except BaseException as report_exc:
                print(
                    f"WARNING: could not write compile failure receipt: {report_exc}",
                    file=sys.stderr,
                )
        raise build_error

    try:
        assert_provenance_unchanged()
    except BaseException as exc:
        write_prebuild_failure("post-compile-provenance", exc)
        raise
    transition_transaction(
        "compiled",
        compiled=receipts,
        compiler_output_guards=output_guards,
        cleanup=cleanup,
    )

    artifacts: list[dict[str, Any]] = []
    artifact_closure: dict[str, Any] | None = None
    artifact_cleanup: list[dict[str, Any]] = []
    artifact_cleanup_errors: list[dict[str, str]] = []
    if artifact_root and not args.dry_run:
        transition_transaction(
            "artifact-handoff",
            artifact_root=str(artifact_root),
        )
        try:
            planned_artifacts = [
                (Path(receipt["output"]), receipt["resource"] + "_c")
                for receipt in receipts
                if receipt["package"]
            ]
            expected_artifacts = [resource for _, resource in planned_artifacts]
            preflight_artifact_copies(
                artifact_root,
                planned_artifacts,
                force_overwrite=args.force_overwrite,
            )
            for receipt in receipts:
                if not receipt["package"]:
                    continue
                resource = receipt["resource"] + "_c"
                artifact_source = Path(receipt["output"])
                artifact_source_state = file_state(artifact_source)
                if not _content_state_matches(
                    artifact_source_state, receipt["output_after"]
                ):
                    raise ManifestError(
                        "compiled output drifted before artifact handoff: "
                        f"{artifact_source}"
                    )
                artifact_receipt = copy_with_policy(
                    artifact_source,
                    native_path(artifact_root, resource),
                    allowed_root=artifact_root,
                    force_overwrite=args.force_overwrite,
                    backup_root=backup_root / "artifact",
                    dry_run=False,
                    label=f"artifact {resource}",
                    registry=artifacts,
                )
                artifact_receipt["resource"] = resource
                if not _content_state_matches(
                    artifact_receipt["source_state"], receipt["output_after"]
                ):
                    raise ManifestError(
                        "artifact source does not match the compiler receipt: "
                        f"{artifact_source}"
                    )
            assert_provenance_unchanged()
            artifact_closure = verify_artifact_closure(
                artifact_root, expected_artifacts, artifacts
            )
        except BaseException as artifact_exc:
            for artifact_receipt in reversed(artifacts):
                try:
                    artifact_cleanup.append(
                        restore_temporary_stage(artifact_receipt)
                    )
                except BaseException as cleanup_exc:
                    artifact_cleanup_errors.append(
                        {
                            "operation": "rollback-artifact-copy",
                            "target": artifact_receipt.get(
                                "destination", "<unknown>"
                            ),
                            "error_type": type(cleanup_exc).__name__,
                            "error": str(cleanup_exc),
                        }
                    )
            artifact_failure_status = (
                "rollback-failed" if artifact_cleanup_errors else "failed"
            )
            try:
                transition_transaction(
                    artifact_failure_status,
                    artifacts_before_rollback=artifacts,
                    artifact_cleanup=artifact_cleanup,
                    artifact_cleanup_errors=artifact_cleanup_errors,
                    error={
                        "type": type(artifact_exc).__name__,
                        "message": str(artifact_exc),
                    },
                )
            except BaseException as journal_exc:
                print(
                    f"WARNING: could not update compile transaction: {journal_exc}",
                    file=sys.stderr,
                )
            artifact_failure_report = {
                "schema_version": 2,
                "status": artifact_failure_status,
                "phase": "artifact-handoff",
                "run_id": run_id,
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "manifest": str(manifest_path),
                "manifest_sha256": provenance_before["manifest"]["sha256"],
                "artifact_policy": artifact_policy,
                "allow_unverified_reference_cache": (
                    args.allow_unverified_reference_cache
                ),
                "reference_cache": reference_cache_receipt,
                "cs2_root": str(cs2_root),
                "gameinfo": str(gameinfo),
                "gameinfo_sha256": provenance_before["gameinfo"]["sha256"],
                "compiler": str(compiler),
                "compiler_state": provenance_before["compiler"],
                "provenance_before": provenance_before,
                "provenance_after": current_provenance_for_report(),
                "versioned_receipt_create_methods": receipt_create_methods,
                "project_root": str(project_root),
                "installed_content_root": str(installed_content_root),
                "reference_root": str(reference_root),
                "force_overwrite": args.force_overwrite,
                "error": {
                    "type": type(artifact_exc).__name__,
                    "message": str(artifact_exc),
                },
                "staged_project": staged_project,
                "staged_dependencies": staged_dependencies,
                "compiled": receipts,
                "compiler_output_guards": output_guards,
                "cleanup": cleanup,
                "cleanup_errors": cleanup_errors,
                "artifacts_before_rollback": artifacts,
                "artifact_cleanup": artifact_cleanup,
                "artifact_cleanup_errors": artifact_cleanup_errors,
                "artifact_closure": None,
                "installed_addon_closure_verified": False,
                "transaction_journal": (
                    None if transaction_path is None else str(transaction_path)
                ),
                "transaction_status": artifact_failure_status,
            }
            try:
                write_compile_report(project_root, run_id, artifact_failure_report)
            except BaseException as report_exc:
                print(
                    f"WARNING: could not write artifact failure receipt: {report_exc}",
                    file=sys.stderr,
                )
            raise

    final_provenance = assert_provenance_unchanged()
    transition_transaction(
        "committed",
        artifacts=artifacts,
        artifact_closure=artifact_closure,
        artifact_cleanup=artifact_cleanup,
        artifact_cleanup_errors=artifact_cleanup_errors,
    )

    report = {
        "schema_version": 2,
        "status": "ok",
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "manifest_sha256": provenance_before["manifest"]["sha256"],
        "artifact_policy": artifact_policy,
        "allow_unverified_reference_cache": args.allow_unverified_reference_cache,
        "reference_cache": reference_cache_receipt,
        "cs2_root": str(cs2_root),
        "gameinfo": str(gameinfo),
        "gameinfo_sha256": provenance_before["gameinfo"]["sha256"],
        "compiler": str(compiler),
        "compiler_state": provenance_before["compiler"],
        "provenance_before": provenance_before,
        "provenance_after": final_provenance,
        "versioned_receipt_create_methods": receipt_create_methods,
        "project_root": str(project_root),
        "installed_content_root": str(installed_content_root),
        "reference_root": str(reference_root),
        "force_overwrite": args.force_overwrite,
        "staged_project": staged_project,
        "staged_dependencies": staged_dependencies,
        "compiled": receipts,
        "compiler_output_guards": output_guards,
        "cleanup": cleanup,
        "cleanup_errors": cleanup_errors,
        "artifact_cleanup": artifact_cleanup,
        "artifact_cleanup_errors": artifact_cleanup_errors,
        "artifacts": artifacts,
        "artifact_closure": artifact_closure,
        "installed_addon_closure_verified": False,
        "transaction_journal": (
            None if transaction_path is None else str(transaction_path)
        ),
    }
    report_path: Path | None = None
    if not args.dry_run:
        report["provenance_after"] = assert_provenance_unchanged()
        report_path = write_compile_report(project_root, run_id, report)
        transition_transaction(
            "reported",
            report=str(report_path),
            report_sha256=sha256_file(report_path),
        )
    print(
        json.dumps(
            {
                "status": "dry-run" if args.dry_run else "ok",
                "resources": len(receipts),
                "report": None if report_path is None else str(report_path),
                "commands": [entry["command"] for entry in receipts],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
