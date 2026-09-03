#!/usr/bin/env python3
"""Blender-only DMX helpers shared by scene creation and action export."""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

import bpy
from mathutils import Matrix, Quaternion, Vector

from animgraph2_manifest import canonical_bone_signature, dmx_timeframe


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
    return result.stdout


def convert_to_kv2(dmxconvert: Path, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(dmxconvert),
            "-i",
            str(source),
            "-ie",
            "binary",
            "-o",
            str(target),
            "-oe",
            "keyvalues2",
            "-of",
            "model",
        ]
    )


def convert_to_binary(dmxconvert: Path, source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(dmxconvert),
            "-i",
            str(source),
            "-ie",
            "keyvalues2",
            "-o",
            str(target),
            "-oe",
            "binary",
            "-of",
            "model",
        ]
    )


def scan_blocks(text: str, marker: str) -> Iterable[str]:
    start = 0
    while True:
        marker_index = text.find(marker, start)
        if marker_index < 0:
            return
        brace_start = text.find("{", marker_index)
        if brace_start < 0:
            return
        depth = 0
        for index in range(brace_start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[brace_start + 1 : index]
                    start = index + 1
                    break
        else:
            return


def parse_vec(raw: str) -> Vector:
    return Vector(float(part) for part in raw.split())


def parse_quat_xyzw(raw: str) -> Quaternion:
    x, y, z, w = (float(part) for part in raw.split())
    quat = Quaternion((w, x, y, z))
    quat.normalize()
    return quat


def parse_element_array(block: str, name: str) -> list[str]:
    match = re.search(
        rf'"{re.escape(name)}"\s+"element_array"\s*\[(.*?)\]',
        block,
        flags=re.S,
    )
    return re.findall(r'"element"\s+"([^"]+)"', match.group(1)) if match else []


def parse_dmx_skeleton(text: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    transforms: dict[str, tuple[Vector, Quaternion]] = {}
    for block in scan_blocks(text, '"DmeTransform"'):
        id_match = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', block)
        pos_match = re.search(r'"position"\s+"vector3"\s+"([^"]+)"', block)
        quat_match = re.search(
            r'"orientation"\s+"quaternion"\s+"([^"]+)"', block
        )
        if not (id_match and pos_match and quat_match):
            raise ValueError(
                "malformed DmeTransform: id, position, and orientation are required"
            )
        transform_id = id_match.group(1)
        if transform_id in transforms:
            raise ValueError(f"duplicate DmeTransform id: {transform_id}")
        transforms[transform_id] = (
            parse_vec(pos_match.group(1)),
            parse_quat_xyzw(quat_match.group(1)),
        )

    joints: dict[str, dict[str, Any]] = {}
    source_order: list[str] = []
    for block in scan_blocks(text, '"DmeJoint"'):
        id_match = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', block)
        name_match = re.search(r'"name"\s+"string"\s+"([^"]+)"', block)
        transform_match = re.search(
            r'"transform"\s+"element"\s+"([^"]+)"', block
        )
        if not (id_match and name_match):
            raise ValueError("malformed DmeJoint: id and name are required")
        if transform_match:
            transform_id = transform_match.group(1)
            if transform_id not in transforms:
                raise ValueError(
                    f"DmeJoint {name_match.group(1)!r} references missing "
                    f"DmeTransform id {transform_id}"
                )
            position, orientation = transforms[transform_id]
            position = position.copy()
            orientation = orientation.copy()
        else:
            pos_match = re.search(r'"position"\s+"vector3"\s+"([^"]+)"', block)
            quat_match = re.search(
                r'"orientation"\s+"quaternion"\s+"([^"]+)"', block
            )
            if not (pos_match and quat_match):
                raise ValueError(
                    f"DmeJoint {name_match.group(1)!r} has no complete transform; "
                    "provide a valid transform element or inline position/orientation"
                )
            position = parse_vec(pos_match.group(1))
            orientation = parse_quat_xyzw(quat_match.group(1))
        joint_id = id_match.group(1)
        if joint_id in joints:
            raise ValueError(f"duplicate DmeJoint id: {joint_id}")
        if any(joint["name"] == name_match.group(1) for joint in joints.values()):
            raise ValueError(f"duplicate DmeJoint name: {name_match.group(1)}")
        joints[joint_id] = {
            "id": joint_id,
            "name": name_match.group(1),
            "pos": position,
            "quat": orientation,
            "children": parse_element_array(block, "children"),
            "parent": None,
            "global": None,
        }
        source_order.append(joint_id)

    if not joints:
        raise ValueError("no DmeJoint skeleton found in the DMX template")
    for joint in joints.values():
        for child_id in joint["children"]:
            if child_id not in joints:
                raise ValueError(
                    f"joint {joint['name']} references unknown child id {child_id}"
                )
            if joints[child_id]["parent"] is not None:
                raise ValueError(
                    f"joint {joints[child_id]['name']} has multiple parents"
                )
            joints[child_id]["parent"] = joint["id"]
    roots = [joint_id for joint_id in source_order if joints[joint_id]["parent"] is None]
    if not roots:
        raise ValueError("DmeJoint skeleton has no root (cycle detected)")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(joint_id: str, parent_matrix: Matrix) -> None:
        if joint_id in visiting:
            raise ValueError(f"cycle detected at DmeJoint id {joint_id}")
        if joint_id in visited:
            return
        visiting.add(joint_id)
        joint = joints[joint_id]
        local = (
            Matrix.Translation(joint["pos"])
            @ joint["quat"].to_matrix().to_4x4()
        )
        joint["global"] = parent_matrix @ local
        for child_id in joint["children"]:
            visit(child_id, joint["global"])
        visiting.remove(joint_id)
        visited.add(joint_id)

    for root_id in roots:
        visit(root_id, Matrix.Identity(4))
    if len(visited) != len(joints):
        missing = sorted(set(joints) - visited)
        raise ValueError(f"unreachable/cyclic DmeJoint ids: {missing}")

    ordered: list[str] = []

    def collect(joint_id: str) -> None:
        ordered.append(joint_id)
        for child_id in joints[joint_id]["children"]:
            if child_id in joints:
                collect(child_id)

    for root_id in roots:
        collect(root_id)
    return joints, ordered


def parse_channels(text: str) -> dict[str, dict[str, Any]]:
    channels: dict[str, dict[str, Any]] = {}
    for block in scan_blocks(text, '"DmeChannel"'):
        name_match = re.search(r'"name"\s+"string"\s+"([^"]+)"', block)
        times_match = re.search(
            r'"times"\s+"time_array"\s*\[(.*?)\]', block, flags=re.S
        )
        values_match = re.search(
            r'"values"\s+"(vector3_array|quaternion_array)"\s*\[(.*?)\]',
            block,
            flags=re.S,
        )
        if not (name_match and times_match and values_match):
            raise ValueError(
                "malformed DmeChannel: name, times, and values are required"
            )
        channel_name = name_match.group(1)
        if channel_name in channels:
            raise ValueError(f"duplicate DmeChannel name: {channel_name}")
        times = [float(value) for value in re.findall(r'"([^"]+)"', times_match.group(1))]
        values = [
            [float(part) for part in raw.split()]
            for raw in re.findall(r'"([^"]+)"', values_match.group(2))
        ]
        if len(times) != len(values) or not times:
            raise ValueError(
                f"invalid DMX channel {channel_name}: "
                f"times={len(times)} values={len(values)}"
            )
        channels[channel_name] = {
            "kind": "quat" if values_match.group(1) == "quaternion_array" else "vec",
            "times": times,
            "values": values,
        }
    if not channels:
        raise ValueError("no DmeChannel animation data found in the DMX template")
    return channels


def sample_vector(channel: dict[str, Any], time_value: float) -> Vector:
    times, values = channel["times"], channel["values"]
    if len(values) == 1 or time_value <= times[0]:
        return Vector(values[0])
    if time_value >= times[-1]:
        return Vector(values[-1])
    for index in range(1, len(times)):
        if time_value <= times[index]:
            span = times[index] - times[index - 1]
            factor = 0.0 if span == 0.0 else (time_value - times[index - 1]) / span
            return Vector(values[index - 1]).lerp(Vector(values[index]), factor)
    return Vector(values[-1])


def quat_from_xyzw(values: list[float]) -> Quaternion:
    quat = Quaternion((values[3], values[0], values[1], values[2]))
    quat.normalize()
    return quat


def sample_quaternion(channel: dict[str, Any], time_value: float) -> Quaternion:
    times, values = channel["times"], channel["values"]
    if len(values) == 1 or time_value <= times[0]:
        return quat_from_xyzw(values[0])
    if time_value >= times[-1]:
        return quat_from_xyzw(values[-1])
    for index in range(1, len(times)):
        if time_value <= times[index]:
            span = times[index] - times[index - 1]
            factor = 0.0 if span == 0.0 else (time_value - times[index - 1]) / span
            return quat_from_xyzw(values[index - 1]).slerp(
                quat_from_xyzw(values[index]), factor
            )
    return quat_from_xyzw(values[-1])


def global_matrices_for_time(
    joints: dict[str, dict[str, Any]],
    ordered: list[str],
    channels: dict[str, dict[str, Any]],
    time_value: float,
    source_scale: float,
    translation_mode: str = "absolute",
) -> dict[str, Matrix]:
    matrices: dict[str, Matrix] = {}
    for joint_id in ordered:
        joint = joints[joint_id]
        name = joint["name"]
        position = joint["pos"].copy()
        orientation = joint["quat"].copy()
        if f"{name}_p" in channels:
            channel_position = sample_vector(channels[f"{name}_p"], time_value)
            position = (
                position + channel_position
                if translation_mode == "bind-pose-delta"
                else channel_position
            )
        if f"{name}_o" in channels:
            orientation = sample_quaternion(channels[f"{name}_o"], time_value)
        local = (
            Matrix.Translation(position * source_scale)
            @ orientation.to_matrix().to_4x4()
        )
        parent_id = joint["parent"]
        if parent_id in joints:
            matrices[name] = matrices[joints[parent_id]["name"]] @ local
        else:
            matrices[name] = local
    return matrices


def clear_scene() -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def armature_rest_signature(armature: bpy.types.Object) -> list[dict[str, Any]]:
    return canonical_bone_signature(
        (
            bone.name,
            bone.parent.name if bone.parent else None,
            bone.matrix_local,
        )
        for bone in armature.data.bones
    )


def create_exact_armature(
    joints: dict[str, dict[str, Any]],
    ordered: list[str],
    *,
    name: str,
    source_scale: float,
    skeleton_resource: str,
) -> bpy.types.Object:
    arm_data = bpy.data.armatures.new(f"{name}_data")
    arm_obj = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    arm_obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    for joint_id in ordered:
        joint = joints[joint_id]
        global_matrix = joint["global"].copy()
        global_matrix.translation *= source_scale
        rotation = global_matrix.to_3x3().normalized()
        head = global_matrix.translation
        child_lengths = [
            (joints[child_id]["global"].translation - joint["global"].translation).length
            * source_scale
            for child_id in joint["children"]
            if child_id in joints
        ]
        length = max(
            source_scale * 1.5,
            min(source_scale * 10.0, max(child_lengths, default=source_scale * 4.0)),
        )
        y_axis = (rotation @ Vector((0.0, 1.0, 0.0))).normalized()
        z_axis = (rotation @ Vector((0.0, 0.0, 1.0))).normalized()
        edit_bone = arm_data.edit_bones.new(joint["name"])
        edit_bone.head = head
        edit_bone.tail = head + y_axis * length
        edit_bone.align_roll(z_axis)
        edit_bone.use_connect = False

    for joint_id in ordered:
        joint = joints[joint_id]
        if joint["parent"] in joints:
            arm_data.edit_bones[joint["name"]].parent = arm_data.edit_bones[
                joints[joint["parent"]]["name"]
            ]

    bpy.ops.object.mode_set(mode="OBJECT")
    arm_obj.scale = (1.0, 1.0, 1.0)
    arm_obj["source_unit_scale"] = source_scale
    arm_obj["source_skeleton"] = skeleton_resource
    arm_obj["authoring_rule"] = (
        "Keep object transform determinant +1 and do not non-uniformly scale the rig."
    )
    for joint_id in ordered:
        joint = joints[joint_id]
        bone = arm_data.bones[joint["name"]]
        bone["cs2_source_rest_position"] = list(joint["pos"])
    arm_data.display_type = "STICK"
    arm_data.show_names = True
    arm_obj.show_in_front = True
    return arm_obj


def set_pose_matrix_from_dmx(pose_bone: Any, target_matrix: Matrix) -> None:
    rest_matrix = pose_bone.bone.matrix_local.copy()
    if pose_bone.parent:
        parent_rest = pose_bone.parent.bone.matrix_local.copy()
        parent_pose = pose_bone.parent.matrix.copy()
        pose_bone.matrix_basis = (
            rest_matrix.inverted()
            @ parent_rest
            @ parent_pose.inverted()
            @ target_matrix
        )
    else:
        pose_bone.matrix_basis = rest_matrix.inverted() @ target_matrix


def build_action(
    armature: bpy.types.Object,
    name: str,
    joints: dict[str, dict[str, Any]],
    ordered: list[str],
    channels: dict[str, dict[str, Any]],
    *,
    fps: float,
    source_scale: float,
    translation_mode: str = "absolute",
    minimum_frames: int = 2,
) -> tuple[bpy.types.Action, int]:
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    all_times = sorted(
        {round(value, 6) for channel in channels.values() for value in channel["times"]}
    )
    times = [value for value in all_times if value >= 0.0] or all_times
    first_time = times[0]
    keyed_frames: list[tuple[int, float]] = []
    for time_value in times:
        frame = int(round((time_value - first_time) * fps)) + 1
        if keyed_frames and keyed_frames[-1][0] == frame:
            keyed_frames[-1] = (frame, time_value)
        else:
            keyed_frames.append((frame, time_value))
    last_required_frame = keyed_frames[0][0] + minimum_frames - 1
    if keyed_frames[-1][0] < last_required_frame:
        keyed_frames.append((last_required_frame, keyed_frames[-1][1]))

    previous_pose_quaternions: dict[str, Quaternion] = {}
    for frame, time_value in keyed_frames:
        bpy.context.scene.frame_set(frame)
        matrices = global_matrices_for_time(
            joints,
            ordered,
            channels,
            time_value,
            source_scale,
            translation_mode,
        )
        for joint_id in ordered:
            pose_bone = armature.pose.bones.get(joints[joint_id]["name"])
            if pose_bone is None:
                continue
            pose_bone.rotation_mode = "QUATERNION"
            if translation_mode == "bind-pose-delta":
                # World clips already produced complete armature-space globals.
                # Direct assignment avoids applying the bind transform twice.
                pose_bone.matrix = matrices[pose_bone.name]
                bpy.context.view_layer.update()
            else:
                set_pose_matrix_from_dmx(pose_bone, matrices[pose_bone.name])
                bpy.context.view_layer.update()
        bpy.context.view_layer.update()
        for pose_bone in armature.pose.bones:
            orientation = pose_bone.rotation_quaternion.copy()
            orientation.normalize()
            previous = previous_pose_quaternions.get(pose_bone.name)
            if previous is not None and previous.dot(orientation) < 0.0:
                orientation.negate()
                pose_bone.rotation_quaternion = orientation
            previous_pose_quaternions[pose_bone.name] = orientation.copy()
            pose_bone.keyframe_insert(data_path="location", frame=frame)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            pose_bone.keyframe_insert(data_path="scale", frame=frame)

    for fcurve in action.fcurves:
        for keyframe in fcurve.keyframe_points:
            keyframe.interpolation = "LINEAR"
    return action, keyed_frames[-1][0]


def action_frames(action: bpy.types.Action) -> list[int]:
    start, end = action.frame_range
    first, last = int(round(start)), int(round(end))
    if abs(start - first) > 1e-4 or abs(end - last) > 1e-4:
        raise ValueError(f"{action.name} must have integer frame bounds: {start}-{end}")
    return list(range(first, last + 1))


def sample_blender_action(
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frames: list[int],
    *,
    source_scale: float,
    translation_mode: str = "absolute",
    scale_tolerance: float = 1e-3,
) -> list[dict[str, dict[str, list[float]]]]:
    armature.animation_data_create()
    armature.animation_data.action = action
    samples = []
    previous_quaternions: dict[str, Quaternion] = {}
    for frame in frames:
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        global_matrices = {
            pose_bone.name: pose_bone.matrix.copy()
            for pose_bone in armature.pose.bones
        }
        frame_sample: dict[str, dict[str, list[float]]] = {}
        for pose_bone in armature.pose.bones:
            matrix = global_matrices[pose_bone.name]
            if pose_bone.parent:
                matrix = global_matrices[pose_bone.parent.name].inverted() @ matrix
            position, orientation, scale = matrix.decompose()
            if any(abs(component - 1.0) > scale_tolerance for component in scale):
                raise ValueError(
                    f"bone scale is unsupported in {action.name}/{pose_bone.name} "
                    f"at frame {frame}: {tuple(scale)}"
                )
            position /= source_scale
            if translation_mode == "bind-pose-delta":
                stored_rest = pose_bone.bone.get("cs2_source_rest_position")
                if stored_rest is None:
                    raise ValueError(
                        f"{pose_bone.name} lacks cs2_source_rest_position; "
                        "regenerate the authoring scene"
                    )
                position -= Vector(stored_rest)
            orientation.normalize()
            previous = previous_quaternions.get(pose_bone.name)
            if previous is not None and previous.dot(orientation) < 0.0:
                orientation.negate()
            previous_quaternions[pose_bone.name] = orientation.copy()
            values = [position.x, position.y, position.z]
            quaternion = [orientation.x, orientation.y, orientation.z, orientation.w]
            if not all(math.isfinite(value) for value in values + quaternion):
                raise ValueError(
                    f"non-finite transform in {action.name}/{pose_bone.name} at {frame}"
                )
            frame_sample[pose_bone.name] = {
                "position": values,
                "orientation": quaternion,
            }
        samples.append(frame_sample)
    return samples


def channel_names(text: str) -> list[str]:
    names = re.findall(
        r'"DmeChannel"\s*\{.*?"name"\s+"string"\s+"([^"]+)"',
        text,
        flags=re.S,
    )
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate DmeChannel name(s): {duplicates}")
    return names


def find_channel_block(lines: list[str], channel_name: str) -> tuple[int, int] | None:
    marker = re.compile(
        rf'"name"\s+"string"\s+"{re.escape(channel_name)}"'
    )
    name_index = next(
        (i for i, line in enumerate(lines) if marker.search(line)), None
    )
    if name_index is None:
        return None
    start = name_index
    while start >= 0 and '"DmeChannel"' not in lines[start]:
        start -= 1
    if start < 0:
        return None
    depth, seen_open = 0, False
    for end in range(start, len(lines)):
        depth += lines[end].count("{")
        seen_open = seen_open or "{" in lines[end]
        depth -= lines[end].count("}")
        if seen_open and depth == 0:
            return start, end + 1
    return None


def find_array_range(
    lines: list[str], start: int, end: int, array_name: str
) -> tuple[int, int]:
    declaration = next(
        (i for i in range(start, end) if f'"{array_name}"' in lines[i]), None
    )
    if declaration is None:
        raise ValueError(f"array not found: {array_name}")
    open_index = next((i for i in range(declaration, end) if "[" in lines[i]), None)
    if open_index is None:
        raise ValueError(f"array opening bracket not found: {array_name}")
    close_index = next(
        (i for i in range(open_index + 1, end) if "]" in lines[i]), None
    )
    if close_index is None:
        raise ValueError(f"array closing bracket not found: {array_name}")
    return open_index + 1, close_index


def quote_value(value: Any, decimals: int) -> str:
    if isinstance(value, (int, float)):
        return f'"{float(value):.{decimals}f}"'
    return '"' + " ".join(f"{float(component):.{decimals}f}" for component in value) + '"'


def replace_channel_array(
    lines: list[str], channel_name: str, array_name: str, values: list[Any]
) -> None:
    block = find_channel_block(lines, channel_name)
    if block is None:
        raise ValueError(f"DMX channel not found: {channel_name}")
    value_start, value_end = find_array_range(lines, *block, array_name)
    base_line = lines[value_start] if value_start < value_end else lines[value_start - 1]
    indent = re.match(r"^(\s*)", base_line).group(1)
    if value_start == value_end:
        indent += "\t"
    replacement = [
        f"{indent}{quote_value(value, 4 if array_name == 'times' else 10)}"
        f"{',' if index < len(values) - 1 else ''}\n"
        for index, value in enumerate(values)
    ]
    lines[value_start:value_end] = replacement


def patch_template(
    template_text: str,
    armature: bpy.types.Object,
    action: bpy.types.Action,
    *,
    fps: float,
    source_scale: float,
    preroll_seconds: list[float],
    translation_mode: str = "absolute",
    max_abs_source_position: float = 1000.0,
    reference_dmx_frame: str = "source-axes",
    secondary_joints: list[dict[str, Any]] | None = None,
    secondary_attach_bone: str = "wpn",
) -> tuple[str, dict[str, Any]]:
    frames = action_frames(action)
    samples = sample_blender_action(
        armature,
        action,
        frames,
        source_scale=source_scale,
        translation_mode=translation_mode,
    )
    # ResourceCompiler reads the compiler frame (what Source 2 Viewer >= 19.2
    # writes). References decompiled by the pinned 19.1 CLI are raw Source axes:
    # convert the root-level bones on the way out, or the clip renders off-screen.
    if reference_dmx_frame == "source-axes":
        samples = to_compiler_frame(samples, root_level_bone_names(armature))
    elif reference_dmx_frame != "compiler":
        raise ValueError(
            f"unsupported reference_dmx_frame {reference_dmx_frame!r}; "
            "use source-axes (VRF <= 19.1 references) or compiler (VRF >= 19.2)"
        )
    if secondary_joints:
        template_text = add_secondary_joints(
            template_text, secondary_joints, secondary_attach_bone
        )
    padded_samples = [samples[0] for _ in preroll_seconds] + samples
    times = list(preroll_seconds) + [index / fps for index in range(len(frames))]
    expected_channels = {
        f"{bone.name}_{suffix}"
        for bone in armature.pose.bones
        for suffix in ("p", "o")
    }
    actual_channels = set(channel_names(template_text))
    if actual_channels != expected_channels:
        raise ValueError(
            "template/armature channel mismatch; "
            f"missing={sorted(expected_channels - actual_channels)}, "
            f"extra={sorted(actual_channels - expected_channels)}"
        )
    lines = template_text.splitlines(keepends=True)
    max_abs_position = 0.0
    for bone in armature.pose.bones:
        positions = [sample[bone.name]["position"] for sample in padded_samples]
        orientations = [sample[bone.name]["orientation"] for sample in padded_samples]
        max_abs_position = max(
            max_abs_position,
            *(abs(component) for position in positions for component in position),
        )
        if max_abs_position > max_abs_source_position:
            raise ValueError(
                f"implausible Source-space position in {action.name}: "
                f"{max_abs_position} exceeds {max_abs_source_position}; check the "
                "set translation_mode, unit scale, and armature transforms"
            )
        replace_channel_array(lines, f"{bone.name}_p", "times", times)
        replace_channel_array(lines, f"{bone.name}_p", "values", positions)
        replace_channel_array(lines, f"{bone.name}_o", "times", times)
        replace_channel_array(lines, f"{bone.name}_o", "values", orientations)
    # Integer frames are inclusive: N samples span N-1 frame intervals.  The
    # DMX sample rate remains the authoring FPS, including a one-frame static
    # action whose duration is legitimately zero.
    duration, frame_rate = dmx_timeframe(fps, len(frames))
    patched = "".join(lines)
    patched, count = re.subn(
        r'("duration"\s+"time"\s+")[^"]+("\s*)',
        rf"\g<1>{duration:.4f}\g<2>",
        patched,
        count=1,
    )
    if count != 1:
        raise ValueError("could not patch DmeTimeFrame duration")
    patched, count = re.subn(
        r'("frameRate"\s+"float"\s+")[^"]+("\s*)',
        rf"\g<1>{frame_rate:.10g}\g<2>",
        patched,
        count=1,
    )
    if count != 1:
        raise ValueError("could not patch DMX frameRate")
    return patched, {
        "frames": [frames[0], frames[-1]],
        "samples": len(times),
        "duration_seconds": duration,
        "dmx_frame_rate": frame_rate,
        "bone_count": len(armature.pose.bones),
        "channel_count": len(expected_channels),
        "max_abs_source_position": max_abs_position,
        "reference_dmx_frame": reference_dmx_frame,
        "secondary_joint_count": len(secondary_joints or []),
        "secondary_attach_bone": secondary_attach_bone if secondary_joints else None,
    }


def parse_array_lengths(text: str) -> dict[str, tuple[int, int]]:
    result = {}
    for channel in channel_names(text):
        marker = f'"name" "string" "{channel}"'
        start = text.find(marker)
        next_channel = text.find('"DmeChannel"', start + len(marker))
        block = text[start : next_channel if next_channel >= 0 else len(text)]
        times_match = re.search(r'"times"\s+"time_array"\s*\[(.*?)\]', block, re.S)
        values_match = re.search(
            r'"values"\s+"(?:vector3|quaternion)_array"\s*\[(.*?)\]',
            block,
            re.S,
        )
        result[channel] = (
            len(re.findall(r'"[^"]+"', times_match.group(1))) if times_match else 0,
            len(re.findall(r'"[^"]+"', values_match.group(1))) if values_match else 0,
        )
    return result


def pose_for_action(
    armature: bpy.types.Object, action: bpy.types.Action, endpoint: str
) -> dict[str, Matrix]:
    armature.animation_data.action = action
    frame = action.frame_range[0] if endpoint == "first" else action.frame_range[1]
    whole = int(math.floor(frame))
    bpy.context.scene.frame_set(whole, subframe=frame - whole)
    bpy.context.view_layer.update()
    return {bone.name: bone.matrix.copy() for bone in armature.pose.bones}


def pose_error(
    left: dict[str, Matrix], right: dict[str, Matrix]
) -> tuple[float, float]:
    max_position, max_rotation = 0.0, 0.0
    if left.keys() != right.keys():
        raise ValueError("pose bone sets differ")
    for name, left_matrix in left.items():
        right_matrix = right[name]
        max_position = max(
            max_position,
            (left_matrix.translation - right_matrix.translation).length,
        )
        angle = (
            left_matrix.to_quaternion()
            .rotation_difference(right_matrix.to_quaternion())
            .angle
        )
        max_rotation = max(max_rotation, min(angle, (2.0 * math.pi) - angle))
    return max_position, max_rotation


# ---------------------------------------------------------------- compiler frame

# (w, x, y, z): -120 degrees about (1, 1, 1) / sqrt(3).  ResourceCompiler reads
# clip DMX in the convention Source 2 Viewer >= 19.2 decompiles to: compared with
# the raw Source axes written by the 19.1 CLI, the direct children of the root
# bone have their positions permuted (x, y, z) -> (y, z, x) and their
# orientations pre-multiplied by this rotation; the root bone and deeper
# parent-local transforms are unchanged.  Observed on build 2000899
# (2026-09-03): raw-axes viewmodel clips compile cleanly but render off-screen
# (no arms, no weapon); converted clips render.  Proven for clips whose root
# bone stays at identity (first person); a moving root (third-person
# locomotion) has not been tested.
COMPILER_FRAME_ROTATION = (0.5, -0.5, -0.5, -0.5)


def quat_mul_wxyz(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def to_compiler_frame(
    samples: list[dict[str, dict[str, list[float]]]], root_level_bones: set[str]
) -> list[dict[str, dict[str, list[float]]]]:
    """Convert raw Source-axes samples to the compiler frame (root-level bones only).

    `samples[i][bone] = {"position": [x, y, z], "orientation": [x, y, z, w]}`
    as produced by `sample_blender_action`; `root_level_bones` are the direct
    children of the root bone (`root_level_bone_names`).
    """

    converted = []
    for frame_sample in samples:
        new_sample: dict[str, dict[str, list[float]]] = {}
        for bone, data in frame_sample.items():
            if bone in root_level_bones:
                px, py, pz = data["position"]
                qx, qy, qz, qw = data["orientation"]
                w, x, y, z = quat_mul_wxyz(COMPILER_FRAME_ROTATION, (qw, qx, qy, qz))
                new_sample[bone] = {"position": [py, pz, px], "orientation": [x, y, z, w]}
            else:
                new_sample[bone] = data
        converted.append(new_sample)
    return converted


def root_level_bone_names(armature: Any) -> set[str]:
    """Bones whose parent is a root bone (e.g. `wpn` and the shoulders under `root_motion`)."""

    return {
        pose_bone.name
        for pose_bone in armature.pose.bones
        if pose_bone.parent is not None and pose_bone.parent.parent is None
    }


# ---------------------------------------------------------------- secondary (weapon) skeletons
#
# CS2 first-person clips carry the arms skeleton and a "secondary animation" for
# the weapon skeleton attached at `wpn` (`m_secondaryAnimations` in the compiled
# NmClip, declared by `m_secondaryAnimationSkeletonNames` in the document).  That
# is how pistol slides and grenade pins move; weapon models carry no AnimGraph2
# of their own.  VRF decompiles drop those channels, so a template-based export
# has to add the weapon joints (under the attach bone) and their channels back.
# The functions below are text-level (KV2) and need no Blender.

_KV2_UUID_FIELDS = 8


def _kv2_uuid() -> str:
    import uuid as _uuid

    return str(_uuid.uuid4())


def _kv2_number(value: float) -> str:
    text = f"{float(value):.10f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _kv2_vector(values: Iterable[float]) -> str:
    return " ".join(_kv2_number(v) for v in values)


def secondary_joints_from_dmx(text: str) -> list[dict[str, Any]]:
    """Read a skeleton DMX (KV2 text) into a hierarchy-ordered joint list.

    Each entry: {name, parent (name or None), position [x, y, z], orientation
    [x, y, z, w]} with parent-local rest transforms in Source units.  Pure text
    parsing (inline or referenced DmeTransform), usable without Blender.
    """

    transforms: dict[str, tuple[list[float], list[float]]] = {}
    for block in scan_blocks(text, '"DmeTransform"'):
        id_match = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', block)
        pos_match = re.search(r'"position"\s+"vector3"\s+"([^"]+)"', block)
        quat_match = re.search(r'"orientation"\s+"quaternion"\s+"([^"]+)"', block)
        if id_match and pos_match and quat_match:
            transforms[id_match.group(1)] = (
                [float(v) for v in pos_match.group(1).split()],
                [float(v) for v in quat_match.group(1).split()],
            )
    joints: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for block in scan_blocks(text, '"DmeJoint"'):
        id_match = re.search(r'"id"\s+"elementid"\s+"([^"]+)"', block)
        name_match = re.search(r'"name"\s+"string"\s+"([^"]+)"', block)
        if not (id_match and name_match):
            continue
        transform_ref = re.search(r'"transform"\s+"element"\s+"([^"]+)"', block)
        if transform_ref and transform_ref.group(1) in transforms:
            position, orientation = transforms[transform_ref.group(1)]
        else:
            pos_match = re.search(r'"position"\s+"vector3"\s+"([^"]+)"', block)
            quat_match = re.search(r'"orientation"\s+"quaternion"\s+"([^"]+)"', block)
            if not (pos_match and quat_match):
                raise ValueError(f"DmeJoint {name_match.group(1)!r} has no transform")
            position = [float(v) for v in pos_match.group(1).split()]
            orientation = [float(v) for v in quat_match.group(1).split()]
        joint = {
            "id": id_match.group(1),
            "name": name_match.group(1),
            "parent": None,
            "position": list(position),
            "orientation": list(orientation),
            "children": parse_element_array(block, "children"),
        }
        joints.append(joint)
        by_id[joint["id"]] = joint
    if not joints:
        raise ValueError("no DmeJoint found in the secondary skeleton DMX")
    for joint in joints:
        for child_id in joint["children"]:
            if child_id in by_id:
                by_id[child_id]["parent"] = joint["name"]
    ordered: list[dict[str, Any]] = []

    def visit(joint: dict[str, Any]) -> None:
        ordered.append(
            {
                "name": joint["name"],
                "parent": joint["parent"],
                "position": joint["position"],
                "orientation": joint["orientation"],
            }
        )
        for child_id in joint["children"]:
            if child_id in by_id:
                visit(by_id[child_id])

    for joint in joints:
        if joint["parent"] is None:
            visit(joint)
    return ordered


def _secondary_channel_block(bone: str, transform_id: str, attribute: str) -> list[str]:
    if attribute == "position":
        log_class, layer_class, log_name, array_type = (
            "DmeVector3Log", "DmeVector3LogLayer", "vector3 log", "vector3_array"
        )
        default_line = '"defaultvalue" "vector3" "0 0 0"'
        suffix = "_p"
    else:
        log_class, layer_class, log_name, array_type = (
            "DmeQuaternionLog", "DmeQuaternionLogLayer", "quaternion log", "quaternion_array"
        )
        default_line = '"defaultvalue" "quaternion" "0 0 0 1"'
        suffix = "_o"
    i = "\t" * 5
    return [
        f'{i}"DmeChannel"\n',
        f"{i}{{\n",
        f'{i}\t"id" "elementid" "{_kv2_uuid()}"\n',
        f'{i}\t"name" "string" "{bone}{suffix}"\n',
        f'{i}\t"fromElement" "element" ""\n',
        f'{i}\t"fromAttribute" "string" ""\n',
        f'{i}\t"fromIndex" "int" "0"\n',
        f'{i}\t"toElement" "element" "{transform_id}"\n',
        f'{i}\t"toAttribute" "string" "{attribute}"\n',
        f'{i}\t"toIndex" "int" "0"\n',
        f'{i}\t"mode" "int" "3"\n',
        f'{i}\t"log" "{log_class}"\n',
        f"{i}\t{{\n",
        f'{i}\t\t"id" "elementid" "{_kv2_uuid()}"\n',
        f'{i}\t\t"name" "string" "{log_name}"\n',
        f'{i}\t\t"layers" "element_array" \n',
        f"{i}\t\t[\n",
        f'{i}\t\t\t"{layer_class}"\n',
        f"{i}\t\t\t{{\n",
        f'{i}\t\t\t\t"id" "elementid" "{_kv2_uuid()}"\n',
        f'{i}\t\t\t\t"name" "string" "{log_name}"\n',
        f'{i}\t\t\t\t"times" "time_array" \n',
        f"{i}\t\t\t\t[\n",
        f"{i}\t\t\t\t]\n",
        f'{i}\t\t\t\t"curvetypes" "int_array" \n',
        f"{i}\t\t\t\t[\n",
        f"{i}\t\t\t\t]\n",
        f'{i}\t\t\t\t"values" "{array_type}" \n',
        f"{i}\t\t\t\t[\n",
        f"{i}\t\t\t\t]\n",
        f"{i}\t\t\t}}\n",
        f"{i}\t\t]\n",
        f'{i}\t\t"curveinfo" "element" ""\n',
        f'{i}\t\t"usedefaultvalue" "bool" "0"\n',
        f"{i}\t\t{default_line}\n",
        f'{i}\t\t"bookmarksX" "time_array" \n',
        f"{i}\t\t[\n",
        f"{i}\t\t]\n",
        f'{i}\t\t"bookmarksY" "time_array" \n',
        f"{i}\t\t[\n",
        f"{i}\t\t]\n",
        f'{i}\t\t"bookmarksZ" "time_array" \n',
        f"{i}\t\t[\n",
        f"{i}\t\t]\n",
        f'{i}\t\t"layerCount" "int" "1"\n',
        f"{i}\t}}\n",
        f"{i}\n",
        f"{i}}},\n",
    ]


def _secondary_joint_element(joint: dict[str, Any], joint_id: str, transform_id: str, child_ids: list[str]) -> str:
    children = "\n".join(
        f'\t\t"element" "{child}"' + ("," if index < len(child_ids) - 1 else "")
        for index, child in enumerate(child_ids)
    )
    children_text = (
        f'\t"children" "element_array" \n\t[\n{children}\n\t]'
        if child_ids
        else '\t"children" "element_array" \n\t[\n\t]'
    )
    return "\n".join(
        [
            '"DmeJoint"',
            "{",
            f'\t"id" "elementid" "{joint_id}"',
            f'\t"name" "string" "{joint["name"]}"',
            f'\t"transform" "element" "{transform_id}"',
            '\t"shape" "DmeShape"',
            "\t{",
            f'\t\t"id" "elementid" "{_kv2_uuid()}"',
            '\t\t"visible" "bool" "1"',
            "\t}",
            "",
            '\t"visible" "bool" "1"',
            children_text,
            "}",
            "",
            "",
        ]
    )


def _secondary_transform_element(joint: dict[str, Any], transform_id: str) -> str:
    return "\n".join(
        [
            '"DmeTransform"',
            "{",
            f'\t"id" "elementid" "{transform_id}"',
            f'\t"name" "string" "{joint["name"]}"',
            f'\t"position" "vector3" "{_kv2_vector(joint.get("position", (0, 0, 0)))}"',
            f'\t"orientation" "quaternion" "{_kv2_vector(joint.get("orientation", (0, 0, 0, 1)))}"',
            "}",
            "",
            "",
        ]
    )


def _find_top_level_joint(lines: list[str], bone: str) -> tuple[int, int]:
    marker = f'"name" "string" "{bone}"'
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        start = index
        while start >= 0 and '"DmeJoint"' not in lines[start] and index - start <= 3:
            start -= 1
        if start < 0 or '"DmeJoint"' not in lines[start]:
            continue
        depth = 0
        for end in range(start, len(lines)):
            depth += lines[end].count("{") - lines[end].count("}")
            if depth == 0 and end > start:
                return start, end + 1
    raise ValueError(f"DmeJoint not found in template: {bone}")


def _append_to_element_array(lines: list[str], start: int, end: int, array_name: str, element_ids: list[str]) -> None:
    declaration = next(
        (
            i
            for i in range(start, end)
            if f'"{array_name}"' in lines[i] and '"element_array"' in lines[i]
        ),
        None,
    )
    if declaration is None:
        raise ValueError(f"element_array not found: {array_name}")
    open_index = next(i for i in range(declaration, end) if "[" in lines[i])
    close_index = next(i for i in range(open_index + 1, end) if lines[i].strip().startswith("]"))
    indent = re.match(r"^(\s*)", lines[open_index]).group(1) + "\t"
    existing = [i for i in range(open_index + 1, close_index) if lines[i].strip()]
    if existing:
        last = existing[-1]
        if not lines[last].rstrip("\r\n").endswith(","):
            lines[last] = lines[last].rstrip("\r\n") + ",\n"
    new_lines = [
        f'{indent}"element" "{element_id}"' + ("," if index < len(element_ids) - 1 else "") + "\n"
        for index, element_id in enumerate(element_ids)
    ]
    lines[close_index:close_index] = new_lines


def add_secondary_joints(template_text: str, joints: list[dict[str, Any]], attach_bone: str = "wpn") -> str:
    """Insert weapon joints under `attach_bone` plus empty position/orientation channels.

    `joints` come from `secondary_joints_from_dmx` (hierarchy order, parent None
    = weapon root).  KV2 separates inline array elements with "},": the previous
    last channel receives a comma and the final inserted block closes the array
    without one.  Existing channels are untouched, so `patch_template` fills the
    new channels like the arm bones.
    """

    if not joints:
        return template_text
    existing = set(re.findall(r'"name"\s+"string"\s+"([^"]+)_p"', template_text))
    clash = [joint["name"] for joint in joints if joint["name"] in existing]
    if clash:
        raise ValueError(f"secondary joints already present in the template: {clash}")
    lines = template_text.splitlines(keepends=True)
    joint_ids = {joint["name"]: _kv2_uuid() for joint in joints}
    transform_ids = {joint["name"]: _kv2_uuid() for joint in joints}
    children: dict[str, list[str]] = {joint["name"]: [] for joint in joints}
    roots = []
    for joint in joints:
        if joint.get("parent") is None:
            roots.append(joint["name"])
        elif joint["parent"] not in children:
            raise ValueError(f"secondary joint {joint['name']} has unknown parent {joint['parent']}")
        else:
            children[joint["parent"]].append(joint_ids[joint["name"]])

    start, end = _find_top_level_joint(lines, attach_bone)
    _append_to_element_array(lines, start, end, "children", [joint_ids[root] for root in roots])

    model_start = next(
        i for i, line in enumerate(lines) if '"skeleton" "DmeModel"' in line or ('"DmeModel"' in line and '"skeleton"' not in line)
    )
    depth = 0
    model_end = model_start
    for model_end in range(model_start, len(lines)):
        depth += lines[model_end].count("{") - lines[model_end].count("}")
        if depth == 0 and model_end > model_start:
            break
    _append_to_element_array(lines, model_start, model_end + 1, "jointList", [joint_ids[joint["name"]] for joint in joints])

    frame_rate_index = next(i for i, line in enumerate(lines) if '"frameRate" "float"' in line)
    close_index = frame_rate_index - 1
    while lines[close_index].strip() != "]":
        close_index -= 1
    previous = close_index - 1
    while previous > 0 and not lines[previous].strip():
        previous -= 1
    if lines[previous].strip() == "}":
        lines[previous] = lines[previous].rstrip("\r\n") + ",\n"
    new_channels: list[str] = []
    for joint in joints:
        new_channels += _secondary_channel_block(joint["name"], transform_ids[joint["name"]], "position")
        new_channels += _secondary_channel_block(joint["name"], transform_ids[joint["name"]], "orientation")
    new_channels[-1] = new_channels[-1].replace("},", "}")
    lines[close_index:close_index] = new_channels

    text = "".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    for joint in joints:
        text += _secondary_transform_element(joint, transform_ids[joint["name"]])
    for joint in joints:
        text += _secondary_joint_element(joint, joint_ids[joint["name"]], transform_ids[joint["name"]], children[joint["name"]])
    return text


def skeleton_dmx_text(joints: list[dict[str, Any]]) -> str:
    """KV2 text of a weapon skeleton DMX (`format model 22`, the layout of the stock
    weapon skeleton DMX files) for a custom `.vnmskel`; exactly one root joint."""

    roots = [joint for joint in joints if joint.get("parent") is None]
    if len(roots) != 1:
        raise ValueError(f"a weapon skeleton needs exactly one root joint, got {[j['name'] for j in roots]}")
    ids = {joint["name"]: _kv2_uuid() for joint in joints}
    model_id = _kv2_uuid()
    children: dict[str, list[str]] = {joint["name"]: [] for joint in joints}
    for joint in joints:
        if joint.get("parent") is not None:
            if joint["parent"] not in children:
                raise ValueError(f"joint {joint['name']} has unknown parent {joint['parent']}")
            children[joint["parent"]].append(joint["name"])

    def element_array(names: list[str], indent: str) -> str:
        if not names:
            return f'{indent}"children" "element_array" \n{indent}[\n{indent}]'
        items = ",\n".join(f'{indent}\t"element" "{ids[name]}"' for name in names)
        return f'{indent}"children" "element_array" \n{indent}[\n{items}\n{indent}]'

    joint_list = ",\n".join([f'\t\t"element" "{model_id}"'] + [f'\t\t"element" "{ids[joint["name"]]}"' for joint in joints])
    out = [
        "<!-- dmx encoding keyvalues2 4 format model 22 -->",
        '"DmElement"',
        "{",
        f'\t"id" "elementid" "{_kv2_uuid()}"',
        '\t"name" "string" "root"',
        f'\t"skeleton" "element" "{model_id}"',
        '\t"animationList" "DmeAnimationList"',
        "\t{",
        f'\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t"animations" "element_array" ',
        "\t\t[",
        '\t\t\t"DmeChannelsClip"',
        "\t\t\t{",
        f'\t\t\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t\t\t"timeFrame" "DmeTimeFrame"',
        "\t\t\t\t{",
        f'\t\t\t\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t\t\t\t"start" "time" "0.0000"',
        '\t\t\t\t\t"duration" "time" "0.0000"',
        '\t\t\t\t\t"offset" "time" "0.0000"',
        '\t\t\t\t\t"scale" "float" "1"',
        "\t\t\t\t}",
        "",
        '\t\t\t\t"color" "color" "0 0 0 0"',
        '\t\t\t\t"text" "string" ""',
        '\t\t\t\t"mute" "bool" "0"',
        '\t\t\t\t"trackGroups" "element_array" ',
        "\t\t\t\t[",
        "\t\t\t\t]",
        '\t\t\t\t"displayScale" "float" "1"',
        '\t\t\t\t"channels" "element_array" ',
        "\t\t\t\t[",
        "\t\t\t\t]",
        '\t\t\t\t"frameRate" "float" "0"',
        "\t\t\t}",
        "\t\t]",
        "\t}",
        "",
        '\t"exportTags" "DmeExportTags"',
        "\t{",
        f'\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t"name" "string" "exportTags"',
        '\t\t"app" "string" "cs2-animgraph2-authoring"',
        '\t\t"source" "string" "skeleton_dmx_text"',
        "\t}",
        "",
        "}",
        "",
        '"DmeModel"',
        "{",
        f'\t"id" "elementid" "{model_id}"',
        '\t"transform" "DmeTransform"',
        "\t{",
        f'\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t"position" "vector3" "0 0 0"',
        '\t\t"orientation" "quaternion" "0 0 0 1"',
        "\t}",
        "",
        '\t"shape" "element" ""',
        '\t"visible" "bool" "1"',
        element_array([roots[0]["name"]], "\t"),
        '\t"jointList" "element_array" ',
        "\t[",
        joint_list,
        "\t]",
        '\t"baseStates" "element_array" ',
        "\t[",
        "\t]",
        '\t"axisSystem" "DmeAxisSystem"',
        "\t{",
        f'\t\t"id" "elementid" "{_kv2_uuid()}"',
        '\t\t"upAxis" "int" "3"',
        '\t\t"forwardParity" "int" "1"',
        '\t\t"coordSys" "int" "0"',
        "\t}",
        "",
        "}",
        "",
    ]
    for joint in joints:
        out += [
            '"DmeJoint"',
            "{",
            f'\t"id" "elementid" "{ids[joint["name"]]}"',
            f'\t"name" "string" "{joint["name"]}"',
            '\t"transform" "DmeTransform"',
            "\t{",
            f'\t\t"id" "elementid" "{_kv2_uuid()}"',
            f'\t\t"name" "string" "{joint["name"]}"',
            f'\t\t"position" "vector3" "{_kv2_vector(joint.get("position", (0, 0, 0)))}"',
            f'\t\t"orientation" "quaternion" "{_kv2_vector(joint.get("orientation", (0, 0, 0, 1)))}"',
            "\t}",
            "",
            '\t"shape" "DmeShape"',
            "\t{",
            f'\t\t"id" "elementid" "{_kv2_uuid()}"',
            '\t\t"visible" "bool" "1"',
            "\t}",
            "",
            '\t"visible" "bool" "1"',
            element_array(children[joint["name"]], "\t"),
            "}",
            "",
        ]
    return "\n".join(out)


def write_skeleton_dmx(joints: list[dict[str, Any]], target: Path, dmxconvert: Path) -> Path:
    """Write a custom weapon skeleton DMX (binary) next to a KV2 text copy."""

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    text_path = target.with_suffix(".keyvalues2.dmx")
    text_path.write_text(skeleton_dmx_text(joints), encoding="utf-8", newline="\n")
    convert_to_binary(dmxconvert, text_path, target)
    return target


def append_secondary_joints(
    armature: bpy.types.Object,
    joints: list[dict[str, Any]],
    attach_bone: str,
    source_scale: float,
) -> list[str]:
    """Add a weapon skeleton under `attach_bone` of the authoring armature.

    Bones get the same head/tail/roll conventions as `create_exact_armature`
    and a `cs2_source_rest_position` custom property (parent-local, Source
    units) so `bind-pose-delta` sets keep working.  Call it before the rest
    signature is recorded.
    """

    arm_data = armature.data
    if attach_bone not in arm_data.bones:
        raise ValueError(f"attach bone not found: {attach_bone}")
    attach_global = arm_data.bones[attach_bone].matrix_local.copy()
    globals_: dict[str, Matrix] = {}
    for joint in joints:
        qx, qy, qz, qw = joint["orientation"]
        local = Matrix.Translation(Vector(joint["position"]) * source_scale) @ Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4()
        parent_global = attach_global if joint.get("parent") is None else globals_[joint["parent"]]
        globals_[joint["name"]] = parent_global @ local
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    added: list[str] = []
    for joint in joints:
        if joint["name"] in arm_data.edit_bones:
            raise ValueError(f"bone already exists: {joint['name']}")
        global_matrix = globals_[joint["name"]]
        rotation = global_matrix.to_3x3().normalized()
        head = global_matrix.translation
        child_lengths = [
            (globals_[child["name"]].translation - head).length
            for child in joints
            if child.get("parent") == joint["name"]
        ]
        length = max(source_scale * 0.75, min(source_scale * 6.0, max(child_lengths, default=source_scale * 2.5)))
        edit_bone = arm_data.edit_bones.new(joint["name"])
        edit_bone.head = head
        edit_bone.tail = head + (rotation @ Vector((0.0, 1.0, 0.0))).normalized() * length
        edit_bone.align_roll((rotation @ Vector((0.0, 0.0, 1.0))).normalized())
        edit_bone.use_connect = False
        edit_bone.parent = arm_data.edit_bones[attach_bone if joint.get("parent") is None else joint["parent"]]
        added.append(joint["name"])
    bpy.ops.object.mode_set(mode="OBJECT")
    for joint in joints:
        arm_data.bones[joint["name"]]["cs2_source_rest_position"] = list(joint["position"])
        armature.pose.bones[joint["name"]].rotation_mode = "QUATERNION"
    return added
