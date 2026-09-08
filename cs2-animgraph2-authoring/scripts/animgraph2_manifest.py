#!/usr/bin/env python3
"""Shared manifest helpers for the portable CS2 AnimGraph2 tools.

This module intentionally has no third-party dependencies. It validates paths
before any other bundled script reads, writes, extracts, or compiles assets.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
WINDOWS_FORBIDDEN_CHARS = set('<>:"|?*')
RESERVED_GLOBAL_NAMESPACES = {
    ("animation", "anims"),
    ("animation", "graphs"),
    ("animation", "skeletons"),
    ("models", "characters"),
    ("models", "player"),
    ("models", "weapons"),
}


class ManifestError(ValueError):
    """Raised when a project manifest violates the portable contract."""


class ProcessLockSet:
    """Non-blocking OS locks for one or more canonical project/output roots."""

    def __init__(self, roots: Iterable[Path]) -> None:
        canonical = sorted(
            {
                str(Path(root).expanduser().resolve()).casefold()
                if os.name == "nt"
                else str(Path(root).expanduser().resolve())
                for root in roots
            }
        )
        lock_root = Path(tempfile.gettempdir()) / "cs2-animgraph2-locks"
        lock_root.mkdir(parents=True, exist_ok=True)
        self._handles: list[Any] = []
        self.paths: list[str] = []
        try:
            for value in canonical:
                digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                path = lock_root / f"{digest}.lock"
                if path.is_symlink() or (
                    hasattr(path, "is_junction") and path.is_junction()
                ):
                    raise ManifestError(f"refusing symlink/junction lock file: {path}")
                handle = path.open("a+b")
                if path.stat().st_size == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, BlockingIOError) as exc:
                    handle.close()
                    raise ManifestError(
                        "another AnimGraph2 tool is already mutating a shared root; "
                        f"lock busy: {path}"
                    ) from exc
                self._handles.append(handle)
                self.paths.append(str(path))
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        while self._handles:
            handle = self._handles.pop()
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def __enter__(self) -> "ProcessLockSet":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json_new(path: Path, payload: Any) -> str:
    """Atomically create a versioned receipt without replacing an existing one.

    Hard links provide no-replace publication on normal NTFS/ext4 project
    volumes. Windows additionally guarantees that ``os.rename`` refuses an
    existing destination, so it is a safe fallback for shares that reject hard
    links. POSIX filesystems without hard-link support fail closed because a
    portable rename could overwrite a concurrent destination.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        method = "hard-link"
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite versioned receipt: {path}"
            ) from exc
        except OSError as link_exc:
            if os.name != "nt":
                raise OSError(
                    "atomic non-overwriting receipt creation requires hard-link "
                    f"support on this filesystem: {path.parent}"
                ) from link_exc
            try:
                os.rename(temporary, path)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"refusing to overwrite versioned receipt: {path}"
                ) from exc
            except OSError as rename_exc:
                raise OSError(
                    "filesystem supports neither hard-link nor Windows atomic "
                    f"no-replace rename for receipt creation: {path.parent}"
                ) from rename_exc
            method = "windows-no-replace-rename"
        return method
    finally:
        if temporary.exists():
            temporary.unlink()


def probe_versioned_receipt_create(directory: Path) -> str:
    """Verify immutable-receipt publication before a mutating transaction."""

    probe = directory / f".versioned-receipt-probe-{uuid.uuid4().hex}.json"
    method = write_json_new(probe, {"probe": True})
    try:
        if json.loads(probe.read_text(encoding="utf-8")) != {"probe": True}:
            raise OSError(f"versioned receipt probe did not round-trip: {probe}")
    finally:
        if probe.exists():
            probe.unlink()
    return method


def normalize_resource_path(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ManifestError(f"{field} must be an addon/VPK-relative path: {value}")
    raw_parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ManifestError(
            f"{field} must be canonical (no empty, '.' or '..' components): {value}"
        )
    for part in raw_parts:
        if any(ord(character) < 32 for character in part):
            raise ManifestError(f"{field} contains a control character: {value}")
        if any(character in WINDOWS_FORBIDDEN_CHARS for character in part):
            raise ManifestError(f"{field} is not a Windows-safe resource path: {value}")
        if part.endswith((" ", ".")):
            raise ManifestError(
                f"{field} has a Windows-ambiguous trailing dot/space: {value}"
            )
        if part.split(".", 1)[0].casefold() in WINDOWS_RESERVED_NAMES:
            raise ManifestError(f"{field} uses a reserved Windows name: {value}")
    pure = PurePosixPath(*raw_parts)
    if pure.is_absolute():
        raise ManifestError(f"{field} must be an addon/VPK-relative path: {value}")
    return pure.as_posix()


def canonical_resource_key(value: str) -> str:
    """Return the Windows/VPK collision key for an already normalized path."""

    return value.casefold()


def resource_is_within_namespace(resource: str, namespace: str) -> bool:
    resource_parts = tuple(part.casefold() for part in PurePosixPath(resource).parts)
    namespace_parts = tuple(part.casefold() for part in PurePosixPath(namespace).parts)
    return resource_parts[: len(namespace_parts)] == namespace_parts


def resource_is_within_namespaces(resource: str, namespaces: Iterable[str]) -> bool:
    return any(resource_is_within_namespace(resource, value) for value in namespaces)


def _normalize_private_namespace(value: Any, field: str) -> str:
    namespace = normalize_resource_path(
        _require_string(value, field),
        field=field,
    )
    if "." in PurePosixPath(namespace).name:
        raise ManifestError(f"{field} must be a resource directory")
    parts = tuple(part.casefold() for part in PurePosixPath(namespace).parts)
    if len(parts) < 3:
        raise ManifestError(
            f"{field} must contain at least three components "
            "(resource root/owner/project)"
        )
    if parts[:2] in RESERVED_GLOBAL_NAMESPACES:
        raise ManifestError(
            f"{field} shadows a Valve global resource family; choose a private "
            "owner path such as animation/<owner>/<project> or "
            "models/<owner>/<project>"
        )
    return namespace


def dmx_timeframe(fps: float, frame_count: int) -> tuple[float, float]:
    """Return DMX duration and sample rate for inclusive integer frames."""

    fps_value = _require_positive_number(fps, "fps")
    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 1:
        raise ManifestError("frame_count must be an integer >= 1")
    return (frame_count - 1) / fps_value, fps_value


def canonical_bone_signature(
    records: Iterable[tuple[str, str | None, Any]],
) -> list[dict[str, Any]]:
    """Canonicalize Blender bone name/parent/rest-matrix records."""

    bones: dict[str, dict[str, Any]] = {}
    for name, parent, matrix in records:
        if not isinstance(name, str) or not name:
            raise ManifestError("bone signature contains an empty name")
        if parent is not None and (not isinstance(parent, str) or not parent):
            raise ManifestError(f"bone {name} has an invalid parent")
        key = name.casefold()
        if key in bones:
            raise ManifestError(f"duplicate bone name in rest signature: {name}")
        rows = list(matrix)
        flattened: list[float] = []
        if len(rows) == 4 and all(hasattr(row, "__iter__") for row in rows):
            flattened = [float(value) for row in rows for value in list(row)]
        else:
            flattened = [float(value) for value in rows]
        if len(flattened) != 16 or not all(math.isfinite(value) for value in flattened):
            raise ManifestError(f"bone {name} must have a finite 4x4 rest matrix")
        bones[key] = {
            "name": name,
            "parent": parent,
            "matrix_local": [round(value, 9) for value in flattened],
        }
    name_keys = {entry["name"].casefold() for entry in bones.values()}
    for entry in bones.values():
        if entry["parent"] is not None and entry["parent"].casefold() not in name_keys:
            raise ManifestError(
                f"bone {entry['name']} references unknown parent {entry['parent']}"
            )
    for entry in bones.values():
        seen: set[str] = set()
        parent = entry["parent"]
        while parent is not None:
            key = parent.casefold()
            if key in seen or key == entry["name"].casefold():
                raise ManifestError(f"cycle in bone rest signature at {entry['name']}")
            seen.add(key)
            parent = bones[key]["parent"]
    return sorted(bones.values(), key=lambda value: value["name"].casefold())


def project_path(manifest_path: Path, relative: str, *, field: str) -> Path:
    normalized = normalize_resource_path(relative, field=field)
    root = manifest_path.resolve().parent
    resolved = (root / Path(*PurePosixPath(normalized).parts)).resolve()
    if resolved != root and root not in resolved.parents:
        raise ManifestError(f"{field} escapes the manifest directory: {relative}")
    return resolved


def reference_dmx_relative(resource: str) -> str:
    normalized = normalize_resource_path(resource, field="reference_resource")
    if not normalized.endswith(".vnmclip_c"):
        raise ManifestError(
            f"reference_resource must end in .vnmclip_c, got {resource}"
        )
    return normalized[: -len(".vnmclip_c")] + ".dmx"


def reference_vnmclip_relative(resource: str) -> str:
    normalized = normalize_resource_path(resource, field="reference_resource")
    if not normalized.endswith(".vnmclip_c"):
        raise ManifestError(
            f"reference_resource must end in .vnmclip_c, got {resource}"
        )
    return normalized[: -len("_c")]


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str, *, non_empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (non_empty and not value):
        suffix = " non-empty" if non_empty else ""
        raise ManifestError(f"{field} must be a{suffix} array")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _require_id(value: Any, field: str) -> str:
    result = _require_string(value, field)
    if not ID_RE.fullmatch(result):
        raise ManifestError(
            f"{field} must contain lowercase letters, digits, underscores, or hyphens"
        )
    return result


def _require_positive_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ManifestError(f"{field} must be a positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ManifestError(f"{field} must be a finite positive number")
    return result


def validate_manifest(data: dict[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(data)
    if canonical.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"schema_version must be {SCHEMA_VERSION}, got {canonical.get('schema_version')!r}"
        )

    project = _require_mapping(canonical.get("project"), "project")
    project["name"] = _require_id(project.get("name"), "project.name")
    project["addon"] = _require_id(project.get("addon"), "project.addon")
    if project["addon"].casefold() in WINDOWS_RESERVED_NAMES:
        raise ManifestError("project.addon is a reserved Windows name")
    legacy_namespace = project.get("namespace")
    raw_namespaces = project.get("namespaces")
    if legacy_namespace is not None and raw_namespaces is not None:
        raise ManifestError("project must use namespace or namespaces, not both")
    if raw_namespaces is None:
        raw_namespaces = [legacy_namespace]
    namespaces: list[str] = []
    namespace_keys: set[str] = set()
    for index, raw_namespace in enumerate(
        _require_list(raw_namespaces, "project.namespaces", non_empty=True)
    ):
        namespace = _normalize_private_namespace(
            raw_namespace, f"project.namespaces[{index}]"
        )
        key = canonical_resource_key(namespace)
        if key in namespace_keys:
            raise ManifestError(f"duplicate project namespace: {namespace}")
        namespace_keys.add(key)
        namespaces.append(namespace)
    project.pop("namespace", None)
    project["namespaces"] = namespaces

    raw_artifact_policy = project.get(
        "artifact_policy",
        {"status": "blocked", "basis": "not declared by this manifest"},
    )
    artifact_policy = _require_mapping(
        raw_artifact_policy, "project.artifact_policy"
    )
    artifact_status = artifact_policy.get("status")
    if artifact_status not in {"blocked", "allowed"}:
        raise ManifestError(
            "project.artifact_policy.status must be blocked or allowed"
        )
    artifact_policy["status"] = artifact_status
    artifact_policy["basis"] = _require_string(
        artifact_policy.get("basis"), "project.artifact_policy.basis"
    )
    template_basis = artifact_policy.get("template_derivative_basis")
    if artifact_status == "allowed":
        artifact_policy["template_derivative_basis"] = _require_string(
            template_basis,
            "project.artifact_policy.template_derivative_basis",
        )
    elif template_basis is not None:
        artifact_policy["template_derivative_basis"] = _require_string(
            template_basis,
            "project.artifact_policy.template_derivative_basis",
        )
    project["artifact_policy"] = artifact_policy

    sets = _require_list(canonical.get("sets"), "sets", non_empty=True)
    set_ids: set[str] = set()
    output_paths: set[str] = set()
    armature_names: set[str] = set()
    blender_action_names: set[str] = set()

    for set_index, raw_set in enumerate(sets):
        field = f"sets[{set_index}]"
        animation_set = _require_mapping(raw_set, field)
        set_id = _require_id(animation_set.get("id"), f"{field}.id")
        animation_set["id"] = set_id
        set_key = set_id.casefold()
        if set_key in set_ids:
            raise ManifestError(f"duplicate animation-set id: {set_id}")
        set_ids.add(set_key)

        armature = _require_string(animation_set.get("armature"), f"{field}.armature")
        armature_key = armature.casefold()
        if armature_key in armature_names:
            raise ManifestError(f"duplicate Blender armature name: {armature}")
        armature_names.add(armature_key)
        animation_set["armature"] = armature
        animation_set["fps"] = _require_positive_number(
            animation_set.get("fps"), f"{field}.fps"
        )
        animation_set["blender_units_per_source_unit"] = _require_positive_number(
            animation_set.get("blender_units_per_source_unit"),
            f"{field}.blender_units_per_source_unit",
        )
        translation_mode = animation_set.get("translation_mode", "absolute")
        if translation_mode not in {"absolute", "bind-pose-delta"}:
            raise ManifestError(
                f"{field}.translation_mode must be absolute or bind-pose-delta"
            )
        animation_set["translation_mode"] = translation_mode
        # DMX frame of the decompiled references: the pinned VRF 19.1 CLI writes raw
        # Source axes ("source-axes", converted to the compiler frame on export);
        # Source 2 Viewer >= 19.2 already writes the compiler frame ("compiler").
        reference_dmx_frame = animation_set.get("reference_dmx_frame", "source-axes")
        if reference_dmx_frame not in {"source-axes", "compiler"}:
            raise ManifestError(
                f"{field}.reference_dmx_frame must be source-axes or compiler"
            )
        animation_set["reference_dmx_frame"] = reference_dmx_frame
        secondary_skeleton_dmx = animation_set.get("secondary_skeleton_dmx")
        if secondary_skeleton_dmx is not None:
            animation_set["secondary_skeleton_dmx"] = normalize_resource_path(
                _require_string(secondary_skeleton_dmx, f"{field}.secondary_skeleton_dmx"),
                field=f"{field}.secondary_skeleton_dmx",
            )
        animation_set["secondary_attach_bone"] = _require_string(
            animation_set.get("secondary_attach_bone", "wpn"),
            f"{field}.secondary_attach_bone",
        )
        # Scene parenting controls pose sampling; the DMX parent controls how
        # ResourceCompiler extracts the secondary skeleton. Keep legacy exports
        # unchanged unless a project has measured a different compiler contract.
        animation_set["secondary_export_attach_bone"] = _require_string(
            animation_set.get(
                "secondary_export_attach_bone", animation_set["secondary_attach_bone"]
            ),
            f"{field}.secondary_export_attach_bone",
        )
        animation_set["max_abs_source_position"] = _require_positive_number(
            animation_set.get("max_abs_source_position", 1000.0),
            f"{field}.max_abs_source_position",
        )
        animation_set["primary_skeleton"] = normalize_resource_path(
            _require_string(
                animation_set.get("primary_skeleton"),
                f"{field}.primary_skeleton",
            ),
            field=f"{field}.primary_skeleton",
        )

        secondary = animation_set.get("secondary_skeletons", [])
        normalized_secondary: list[str] = []
        skeleton_keys = {canonical_resource_key(animation_set["primary_skeleton"])}
        for skeleton_index, skeleton in enumerate(
            _require_list(secondary, f"{field}.secondary_skeletons")
        ):
            normalized_skeleton = normalize_resource_path(
                _require_string(
                    skeleton,
                    f"{field}.secondary_skeletons[{skeleton_index}]",
                ),
                field=f"{field}.secondary_skeletons[{skeleton_index}]",
            )
            key = canonical_resource_key(normalized_skeleton)
            if key in skeleton_keys:
                raise ManifestError(f"duplicate skeleton in {field}: {normalized_skeleton}")
            skeleton_keys.add(key)
            normalized_secondary.append(normalized_skeleton)
        animation_set["secondary_skeletons"] = normalized_secondary

        preroll = animation_set.get("preroll_seconds", [-0.1, -0.05])
        normalized_preroll: list[float] = []
        for time_index, time_value in enumerate(
            _require_list(preroll, f"{field}.preroll_seconds")
        ):
            if not isinstance(time_value, (int, float)) or isinstance(time_value, bool):
                raise ManifestError(
                    f"{field}.preroll_seconds[{time_index}] must be numeric"
                )
            normalized_time = float(time_value)
            if not math.isfinite(normalized_time):
                raise ManifestError(
                    f"{field}.preroll_seconds[{time_index}] must be finite"
                )
            if normalized_time >= 0:
                raise ManifestError(
                    f"{field}.preroll_seconds[{time_index}] must be negative"
                )
            if normalized_preroll and normalized_time <= normalized_preroll[-1]:
                raise ManifestError(
                    f"{field}.preroll_seconds must be strictly increasing"
                )
            normalized_preroll.append(normalized_time)
        animation_set["preroll_seconds"] = normalized_preroll

        actions = _require_list(
            animation_set.get("actions"), f"{field}.actions", non_empty=True
        )
        local_actions: set[str] = set()
        for action_index, raw_action in enumerate(actions):
            action_field = f"{field}.actions[{action_index}]"
            action = _require_mapping(raw_action, action_field)
            action_id = _require_id(action.get("id"), f"{action_field}.id")
            action["id"] = action_id
            action_key = action_id.casefold()
            if action_key in local_actions:
                raise ManifestError(f"duplicate action id in {set_id}: {action_id}")
            local_actions.add(action_key)

            blender_action = _require_string(
                action.get("blender_action"), f"{action_field}.blender_action"
            )
            blender_action_key = blender_action.casefold()
            if blender_action_key in blender_action_names:
                raise ManifestError(
                    f"duplicate Blender action name across sets: {blender_action}"
                )
            blender_action_names.add(blender_action_key)
            action["blender_action"] = blender_action
            minimum_frames = action.get("minimum_frames", 2)
            if (
                not isinstance(minimum_frames, int)
                or isinstance(minimum_frames, bool)
                or minimum_frames < 1
            ):
                raise ManifestError(f"{action_field}.minimum_frames must be an integer >= 1")
            action["minimum_frames"] = minimum_frames
            reference = normalize_resource_path(
                _require_string(
                    action.get("reference_resource"),
                    f"{action_field}.reference_resource",
                ),
                field=f"{action_field}.reference_resource",
            )
            if not reference.endswith(".vnmclip_c"):
                raise ManifestError(
                    f"{action_field}.reference_resource must end in .vnmclip_c"
                )
            action["reference_resource"] = reference

            for key, suffix in (("output_dmx", ".dmx"), ("output_vnmclip", ".vnmclip")):
                output = normalize_resource_path(
                    _require_string(action.get(key), f"{action_field}.{key}"),
                    field=f"{action_field}.{key}",
                )
                if not output.endswith(suffix):
                    raise ManifestError(f"{action_field}.{key} must end in {suffix}")
                if not resource_is_within_namespaces(output, namespaces):
                    raise ManifestError(
                        f"{action_field}.{key} must be inside one of "
                        f"project.namespaces ({namespaces})"
                    )
                output_key = canonical_resource_key(output)
                if output_key in output_paths:
                    raise ManifestError(f"duplicate generated output path: {output}")
                output_paths.add(output_key)
                action[key] = output

            policy = action.get("event_policy", "clear")
            if policy not in {"clear", "preserve-reference", "replace"}:
                raise ManifestError(
                    f"{action_field}.event_policy must be clear, preserve-reference, or replace"
                )
            action["event_policy"] = policy
            if policy == "replace":
                event_file = normalize_resource_path(
                    _require_string(
                        action.get("event_tracks_file"),
                        f"{action_field}.event_tracks_file",
                    ),
                    field=f"{action_field}.event_tracks_file",
                )
                if not event_file.endswith((".kv3", ".txt")):
                    raise ManifestError(
                        f"{action_field}.event_tracks_file must be .kv3 or .txt"
                    )
                if not resource_is_within_namespaces(event_file, namespaces):
                    raise ManifestError(
                        f"{action_field}.event_tracks_file must be inside "
                        f"project.namespaces ({namespaces})"
                    )
                action["event_tracks_file"] = event_file

        continuity = animation_set.get("continuity", [])
        for rule_index, raw_rule in enumerate(
            _require_list(continuity, f"{field}.continuity")
        ):
            rule_field = f"{field}.continuity[{rule_index}]"
            rule = _require_mapping(raw_rule, rule_field)
            source = _require_id(rule.get("from"), f"{rule_field}.from")
            target = _require_id(rule.get("to"), f"{rule_field}.to")
            rule["from"] = source
            rule["to"] = target
            if source.casefold() not in local_actions or target.casefold() not in local_actions:
                raise ManifestError(
                    f"{rule_field} references unknown action(s): {source}, {target}"
                )
            if rule.get("from_frame", "last") not in {"first", "last"}:
                raise ManifestError(f"{rule_field}.from_frame must be first or last")
            if rule.get("to_frame", "first") not in {"first", "last"}:
                raise ManifestError(f"{rule_field}.to_frame must be first or last")
            rule["max_position_error"] = _require_positive_number(
                rule.get("max_position_error", 1e-5),
                f"{rule_field}.max_position_error",
            )
            rule["max_rotation_error_radians"] = _require_positive_number(
                rule.get("max_rotation_error_radians", 1e-5),
                f"{rule_field}.max_rotation_error_radians",
            )

    compile_resources = canonical.get("compile_resources", [])
    normalized_compile_resources: list[str] = []
    compile_keys: set[str] = set()
    for index, resource in enumerate(
        _require_list(compile_resources, "compile_resources")
    ):
        normalized_resource = normalize_resource_path(
            _require_string(resource, f"compile_resources[{index}]"),
            field=f"compile_resources[{index}]",
        )
        if normalized_resource.endswith("_c"):
            raise ManifestError(
                f"compile_resources[{index}] must name a source, not a compiled _c file"
            )
        if not resource_is_within_namespaces(normalized_resource, namespaces):
            raise ManifestError(
                f"compile_resources[{index}] must be inside one of "
                f"project.namespaces ({namespaces})"
            )
        key = canonical_resource_key(normalized_resource)
        if key in compile_keys:
            raise ManifestError(f"duplicate compile resource: {normalized_resource}")
        compile_keys.add(key)
        normalized_compile_resources.append(normalized_resource)
    canonical["compile_resources"] = normalized_compile_resources

    stage_sources = canonical.get("stage_sources", [])
    normalized_stage_sources: list[str] = []
    stage_keys: set[str] = set()
    for index, resource in enumerate(_require_list(stage_sources, "stage_sources")):
        normalized_resource = normalize_resource_path(
            _require_string(resource, f"stage_sources[{index}]"),
            field=f"stage_sources[{index}]",
        )
        if normalized_resource.endswith("_c"):
            raise ManifestError(
                f"stage_sources[{index}] must name an editable source, not _c"
            )
        if not resource_is_within_namespaces(normalized_resource, namespaces):
            raise ManifestError(
                f"stage_sources[{index}] must be inside one of "
                f"project.namespaces ({namespaces})"
            )
        key = canonical_resource_key(normalized_resource)
        if key in stage_keys:
            raise ManifestError(f"duplicate staged source: {normalized_resource}")
        stage_keys.add(key)
        normalized_stage_sources.append(normalized_resource)
    canonical["stage_sources"] = normalized_stage_sources

    stock_dependencies = canonical.get("stock_dependencies", [])
    dependency_resources: set[str] = set()
    dependency_outputs: set[str] = set()
    for index, raw_dependency in enumerate(
        _require_list(stock_dependencies, "stock_dependencies")
    ):
        field = f"stock_dependencies[{index}]"
        dependency = _require_mapping(raw_dependency, field)
        resource = normalize_resource_path(
            _require_string(dependency.get("resource"), f"{field}.resource"),
            field=f"{field}.resource",
        )
        if not resource.endswith("_c"):
            raise ManifestError(f"{field}.resource must be a compiled VPK path ending _c")
        resource_key = canonical_resource_key(resource)
        if resource_key in dependency_resources:
            raise ManifestError(f"duplicate stock dependency: {resource}")
        dependency_resources.add(resource_key)
        dependency["resource"] = resource
        outputs = []
        for output_index, output in enumerate(
            _require_list(dependency.get("outputs"), f"{field}.outputs", non_empty=True)
        ):
            normalized_output = normalize_resource_path(
                    _require_string(output, f"{field}.outputs[{output_index}]"),
                    field=f"{field}.outputs[{output_index}]",
                )
            output_key = canonical_resource_key(normalized_output)
            if output_key in dependency_outputs:
                raise ManifestError(
                    f"duplicate stock dependency output: {normalized_output}"
                )
            if output_key in output_paths or output_key in compile_keys:
                raise ManifestError(
                    f"stock dependency output collides with a project resource: "
                    f"{normalized_output}"
                )
            dependency_outputs.add(output_key)
            outputs.append(normalized_output)
        dependency["outputs"] = outputs
        compile_source = normalize_resource_path(
            _require_string(
                dependency.get("compile", outputs[0]), f"{field}.compile"
            ),
            field=f"{field}.compile",
        )
        matching_compile = next(
            (output for output in outputs if output.casefold() == compile_source.casefold()),
            None,
        )
        if matching_compile is None:
            raise ManifestError(f"{field}.compile must also appear in {field}.outputs")
        dependency["compile"] = matching_compile
        package = dependency.get("package", False)
        if not isinstance(package, bool):
            raise ManifestError(f"{field}.package must be true or false")
        dependency["package"] = package
        redistribution_basis = dependency.get("redistribution_basis")
        if package:
            dependency["redistribution_basis"] = _require_string(
                redistribution_basis, f"{field}.redistribution_basis"
            )
        elif redistribution_basis is not None:
            dependency["redistribution_basis"] = _require_string(
                redistribution_basis, f"{field}.redistribution_basis"
            )

    canonical["stock_dependencies"] = stock_dependencies
    return canonical


def resolve_secondary_skeleton_dmx(
    manifest_path: Path, reference_root: Path, value: str
) -> Path:
    """Locate a set's `secondary_skeleton_dmx`: a decompiled stock skeleton under
    the reference root (e.g. animation/skeletons/weapons/<proxy>.dmx) or a
    project-relative custom skeleton DMX."""

    candidate = reference_root.joinpath(*PurePosixPath(value).parts)
    if candidate.is_file():
        return candidate
    project_candidate = project_path(manifest_path, value, field="secondary_skeleton_dmx")
    if project_candidate.is_file():
        return project_candidate
    raise ManifestError(
        f"secondary_skeleton_dmx not found under the reference root or the project: {value}"
    )


def load_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {manifest_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    return manifest_path, validate_manifest(data)


def selected_sets(
    data: dict[str, Any], requested: Iterable[str] | None
) -> list[dict[str, Any]]:
    wanted = set(requested or [])
    available = {entry["id"]: entry for entry in data["sets"]}
    unknown = wanted - available.keys()
    if unknown:
        raise ManifestError(
            f"unknown animation set(s): {', '.join(sorted(unknown))}; "
            f"available: {', '.join(sorted(available))}"
        )
    return [entry for entry in data["sets"] if not wanted or entry["id"] in wanted]


def find_set(data: dict[str, Any], set_id: str) -> dict[str, Any]:
    return selected_sets(data, [set_id])[0]


def find_action(animation_set: dict[str, Any], action_id: str) -> dict[str, Any]:
    for action in animation_set["actions"]:
        if action["id"] == action_id:
            return action
    raise ManifestError(
        f"unknown action {action_id!r} in animation set {animation_set['id']!r}"
    )


def resolve_tool(
    explicit: str | None,
    env_names: Iterable[str],
    fallback: Path | None,
    label: str,
) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if not candidate.is_file():
            raise ManifestError(f"explicit {label} path is not a file: {candidate}")
        return candidate
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value).expanduser())
    if fallback is not None:
        candidates.append(fallback)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    rendered = ", ".join(str(candidate) for candidate in candidates) or "none"
    raise ManifestError(f"{label} not found; checked: {rendered}")


def resolve_cs2_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / "game" / "csgo" / "gameinfo.gi").is_file():
            raise ManifestError(
                f"explicit CS2 root is invalid (game/csgo/gameinfo.gi missing): {root}"
            )
        return root
    candidates = [os.environ.get("CS2_ROOT"), os.environ.get("CS2_LOCAL_ROOT")]
    for value in candidates:
        if not value:
            continue
        root = Path(value).expanduser().resolve()
        if (root / "game" / "csgo" / "gameinfo.gi").is_file():
            return root
    raise ManifestError(
        "CS2 root not found; pass --cs2-root or set CS2_ROOT/CS2_LOCAL_ROOT"
    )


def resource_output_path(cs2_root: Path, addon: str, resource: str) -> Path:
    normalized = normalize_resource_path(resource, field="compiled resource")
    relative = Path(*PurePosixPath(normalized).parts)
    return cs2_root / "game" / "csgo_addons" / addon / Path(str(relative) + "_c")
