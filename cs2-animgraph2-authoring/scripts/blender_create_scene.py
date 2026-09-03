#!/usr/bin/env python3
"""Create an exact CS2 animation-authoring .blend from stock VNMClip references.

Run this script through Blender. It creates one exact armature per selected
manifest set, imports every stock reference as a read-only reference action,
and duplicates each reference into the manifest's editable action name.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import bpy


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from animgraph2_manifest import (  # noqa: E402
    ManifestError,
    ProcessLockSet,
    load_manifest,
    reference_dmx_relative,
    resolve_cs2_root,
    resolve_tool,
    selected_sets,
    sha256_file,
    resolve_secondary_skeleton_dmx,
)
from blender_dmx import (  # noqa: E402
    armature_rest_signature,
    build_action,
    clear_scene,
    convert_to_kv2,
    create_exact_armature,
    parse_channels,
    parse_dmx_skeleton,
    append_secondary_joints,
    secondary_joints_from_dmx,
)
from extract_stock_references import verify_reference_cache  # noqa: E402


def blender_arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="AnimGraph2 project JSON")
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        help="Animation-set id to include; repeat or omit for all sets",
    )
    parser.add_argument(
        "--reference-root",
        help="Local output from extract_stock_references.py",
    )
    parser.add_argument("--cs2-root", help="CS2 installation root")
    parser.add_argument("--dmxconvert", help="Path to dmxconvert executable")
    parser.add_argument("--output", required=True, help="Destination .blend")
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Replace an existing .blend only after this explicit opt-in",
    )
    parser.add_argument(
        "--allow-clear-scene",
        action="store_true",
        help="Explicitly permit deleting a Blender scene containing objects",
    )
    parser.add_argument(
        "--allow-unverified-reference-cache",
        action="store_true",
        help=(
            "Forensic override: allow references without a valid extraction "
            "receipt; the bypass is embedded in the .blend"
        ),
    )
    return parser.parse_args(blender_arguments())


def local_path(root: Path, resource: str) -> Path:
    return root.joinpath(*PurePosixPath(resource).parts)


def skeleton_signature(
    joints: dict[str, dict[str, Any]], ordered: list[str]
) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            joints[joint_id]["name"],
            joints[joints[joint_id]["parent"]]["name"]
            if joints[joint_id]["parent"] in joints
            else None,
            tuple(round(float(value), 9) for value in joints[joint_id]["pos"]),
            tuple(round(float(value), 9) for value in joints[joint_id]["quat"]),
        )
        for joint_id in ordered
    )


def duplicate_editable(reference: bpy.types.Action, name: str) -> bpy.types.Action:
    if bpy.data.actions.get(name) is not None:
        raise ManifestError(f"duplicate Blender action name across selected sets: {name}")
    editable = reference.copy()
    editable.name = name
    editable.use_fake_user = True
    editable["cs2_editable"] = True
    editable["cs2_reference_action"] = reference.name
    return editable


def blender_factory_startup_requested(argv: list[str]) -> bool:
    """Return whether Blender itself received --factory-startup.

    Only arguments before Blender's ``--`` separator count. This prevents a
    script argument from impersonating an explicit Blender startup safeguard.
    """

    separator = argv.index("--") if "--" in argv else len(argv)
    return "--factory-startup" in argv[:separator]


def main() -> int:
    args = parse_args()
    manifest_path, manifest = load_manifest(args.manifest)
    with ProcessLockSet([manifest_path.parent]):
        return _main_locked(args, manifest_path, manifest)


def _main_locked(
    args: argparse.Namespace, manifest_path: Path, manifest: dict[str, Any]
) -> int:
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
            for action in animation_set["actions"]
        },
        key=str.casefold,
    )
    reference_cache_receipt = verify_reference_cache(
        reference_root,
        manifest_path,
        required_reference_outputs,
        allow_unverified=args.allow_unverified_reference_cache,
    )
    output = Path(args.output).expanduser().resolve()
    if output.suffix.lower() != ".blend":
        raise ManifestError("--output must end in .blend")
    if output.exists() and not args.force_overwrite:
        raise ManifestError(
            f"refusing to overwrite existing Blender file: {output}; "
            "pass --force-overwrite after preserving/reviewing it"
        )
    factory_scene = (
        blender_factory_startup_requested(sys.argv)
        and not str(getattr(bpy.data, "filepath", "") or "")
        and not bool(getattr(bpy.data, "is_dirty", True))
    )
    clear_authorized = args.allow_clear_scene or factory_scene
    if not clear_authorized:
        raise ManifestError(
            "refusing to clear a saved, dirty, or non-factory Blender scene; invoke "
            "Blender with --factory-startup before the -- separator, or pass "
            "--allow-clear-scene only after saving/reviewing the current scene"
        )

    cs2_root = resolve_cs2_root(args.cs2_root) if not args.dmxconvert else None
    dmxconvert = resolve_tool(
        args.dmxconvert,
        ("DMXCONVERT",),
        cs2_root / "game" / "bin" / "win64" / "dmxconvert.exe"
        if cs2_root
        else None,
        "dmxconvert",
    )

    fps_values = {float(entry["fps"]) for entry in animation_sets}
    if len(fps_values) != 1:
        raise ManifestError(
            "selected animation sets use different FPS values; create separate "
            ".blend files with repeated --set instead"
        )
    scene_fps = fps_values.pop()

    clear_scene()
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.context.scene.render.fps = max(1, int(round(scene_fps)))
    bpy.context.scene.render.fps_base = (
        bpy.context.scene.render.fps / scene_fps
    )
    bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
    bpy.context.scene.frame_start = 1
    max_frame = 1
    receipts: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="cs2-animgraph2-scene-") as temp_name:
        temp_root = Path(temp_name)
        for animation_set in animation_sets:
            scale = float(animation_set["blender_units_per_source_unit"])
            fps = float(animation_set["fps"])
            canonical_signature: tuple[tuple[Any, ...], ...] | None = None
            armature: bpy.types.Object | None = None

            for action_index, action in enumerate(animation_set["actions"]):
                dmx_relative = reference_dmx_relative(action["reference_resource"])
                source_dmx = local_path(reference_root, dmx_relative)
                if not source_dmx.is_file():
                    raise FileNotFoundError(
                        f"missing extracted DMX for {animation_set['id']}/{action['id']}: "
                        f"{source_dmx}; run extract_stock_references.py extract first"
                    )
                kv2_path = temp_root / animation_set["id"] / f"{action['id']}.dmx.kv2"
                convert_to_kv2(dmxconvert, source_dmx, kv2_path)
                text = kv2_path.read_text(encoding="utf-8")
                joints, ordered = parse_dmx_skeleton(text)
                signature = skeleton_signature(joints, ordered)
                if canonical_signature is None:
                    canonical_signature = signature
                    armature = create_exact_armature(
                        joints,
                        ordered,
                        name=animation_set["armature"],
                        source_scale=scale,
                        skeleton_resource=animation_set["primary_skeleton"],
                    )
                    secondary_skeleton_value = animation_set.get("secondary_skeleton_dmx")
                    if secondary_skeleton_value:
                        # weapon skeleton under the attach bone: exported as the
                        # clip's secondary animation (see portable-tooling.md 5/7)
                        secondary_skeleton_dmx = resolve_secondary_skeleton_dmx(
                            manifest_path, reference_root, secondary_skeleton_value
                        )
                        secondary_kv2 = (
                            temp_root / animation_set["id"] / "secondary_skeleton.dmx.kv2"
                        )
                        convert_to_kv2(dmxconvert, secondary_skeleton_dmx, secondary_kv2)
                        secondary_joints = secondary_joints_from_dmx(
                            secondary_kv2.read_text(encoding="utf-8")
                        )
                        added_bones = append_secondary_joints(
                            armature,
                            secondary_joints,
                            animation_set.get("secondary_attach_bone", "wpn"),
                            scale,
                        )
                        armature["cs2_secondary_skeleton_dmx"] = str(secondary_skeleton_dmx)
                        armature["cs2_secondary_skeleton_sha256"] = sha256_file(
                            secondary_skeleton_dmx
                        )
                        armature["cs2_secondary_bones"] = added_bones
                    armature["cs2_animation_set"] = animation_set["id"]
                    armature["cs2_manifest"] = str(manifest_path)
                    armature["cs2_manifest_sha256"] = sha256_file(manifest_path)
                    armature["cs2_fps"] = fps
                    armature["cs2_rest_signature"] = json.dumps(
                        armature_rest_signature(armature), sort_keys=True
                    )
                elif signature != canonical_signature:
                    raise ManifestError(
                        f"reference skeleton changed inside set {animation_set['id']} "
                        f"at action {action['id']}; use separate animation sets"
                    )

                assert armature is not None
                reference_name = f"REF_{animation_set['id']}_{action['id']}"
                if bpy.data.actions.get(reference_name) is not None:
                    raise ManifestError(f"duplicate generated action name: {reference_name}")
                channels = parse_channels(text)
                reference_action, last_frame = build_action(
                    armature,
                    reference_name,
                    joints,
                    ordered,
                    channels,
                    fps=fps,
                    source_scale=scale,
                    translation_mode=animation_set.get(
                        "translation_mode", "absolute"
                    ),
                    minimum_frames=int(action.get("minimum_frames", 2)),
                )
                reference_action["cs2_read_only_reference"] = True
                reference_action["cs2_reference_resource"] = action[
                    "reference_resource"
                ]
                editable = duplicate_editable(reference_action, action["blender_action"])
                editable["cs2_action_id"] = action["id"]
                editable["cs2_animation_set"] = animation_set["id"]
                max_frame = max(max_frame, last_frame)
                receipts.append(
                    {
                        "set": animation_set["id"],
                        "action": action["id"],
                        "reference_resource": action["reference_resource"],
                        "reference_dmx": str(source_dmx),
                        "reference_dmx_sha256": sha256_file(source_dmx),
                        "reference_action": reference_action.name,
                        "editable_action": editable.name,
                        "frames": [1, last_frame],
                        "bones": len(ordered),
                        "channels": len(channels),
                    }
                )

            assert armature is not None
            armature.animation_data_create()
            armature.animation_data.action = bpy.data.actions[
                animation_set["actions"][0]["blender_action"]
            ]

    bpy.context.scene.frame_end = max_frame
    bpy.context.scene.frame_set(1)
    bpy.context.scene["cs2_animgraph2_manifest"] = str(manifest_path)
    bpy.context.scene["cs2_animgraph2_manifest_sha256"] = sha256_file(manifest_path)
    bpy.context.scene["cs2_animgraph2_receipt"] = json.dumps(receipts)
    bpy.context.scene["cs2_reference_cache_receipt"] = json.dumps(
        reference_cache_receipt, sort_keys=True
    )
    bpy.context.scene["cs2_allow_unverified_reference_cache"] = bool(
        args.allow_unverified_reference_cache
    )
    bpy.context.scene["cs2_authoring_note"] = (
        "Edit only actions named by the manifest. Preserve armature object transforms, "
        "bone names, hierarchy, and unit scale. Key the complete rig."
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output),
                "sets": [entry["id"] for entry in animation_sets],
                "actions": len(receipts),
                "max_frame": max_frame,
                "reference_cache": reference_cache_receipt,
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
