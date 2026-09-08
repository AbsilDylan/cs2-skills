#!/usr/bin/env python3
"""Validate and summarize a definition-shaped AnimGraph2 VNMGraph decompile.

The strict structural parser targets evidence needed for an NPC graph contract.
It is not a general KV3 implementation, cannot prove decompile provenance, and
never modifies inputs.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


CONTROL_TYPES = {
    "CNmControlParameterBoolNode::CDefinition": "Bool",
    "CNmControlParameterFloatNode::CDefinition": "Float",
    "CNmControlParameterIDNode::CDefinition": "ID",
    "CNmControlParameterVectorNode::CDefinition": "Vector",
    "CNmControlParameterTargetNode::CDefinition": "Target",
}

BRIDGE_WRITE_SUPPORT = {
    "Bool": "requires-verified-bridge",
    "Float": "requires-verified-bridge",
    "ID": "requires-verified-bridge",
    "Vector": "diagnostic-only",
    "Target": "diagnostic-only",
}

NUMBER_PATTERN = r"[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
INTEGER_PATTERN = r"[+-]?\d+"
KV3_HEADER_PATTERN = re.compile(
    r"\A(?:\ufeff)?[ \t\r\n]*<!--[ \t]+kv3[ \t]+"
    r"encoding:text:version\{[^{}\s]+\}[ \t]+"
    r"format:generic:version\{[^{}\s]+\}[ \t]*-->",
    re.IGNORECASE,
)
DEPENDENCY_SLOT_SCHEMAS = {
    "m_referencedGraphSlots": {
        "m_nNodeIdx": "node",
        "m_dataSlotIdx": "resource",
    },
    "m_externalGraphSlots": {
        "m_nNodeIdx": "node",
        "m_slotID": "symbol",
    },
    "m_externalPoseSlots": {
        "m_nNodeIdx": "node",
        "m_slotID": "symbol",
    },
}


def _strip_optional_trailing_comma(value: str) -> str:
    """Remove at most one KV3 field delimiter, never arbitrary junk."""

    value = value.strip()
    if value.endswith(","):
        return value[:-1].rstrip()
    return value


def _direct_assignment_heads(block: str) -> list[tuple[str, int]]:
    """Return direct object-field names and assignment-end offsets."""

    start = block.find("{")
    end = block.rfind("}")
    if start < 0 or end <= start or block[:start].strip() or block[end + 1 :].strip():
        raise ValueError("expected one complete object")

    body_start = start + 1
    body = block[body_start:end]
    assignments: list[tuple[str, int]] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    offset = 0
    for line in body.splitlines(keepends=True):
        if not stack and not in_string:
            match = re.match(
                r"[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*", line
            )
            if match:
                assignments.append((match.group(1), body_start + offset + match.end()))
        for char in line:
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
            elif char in "[{":
                stack.append(char)
            elif char in "]}":
                expected = "[" if char == "]" else "{"
                if not stack or stack[-1] != expected:
                    raise ValueError("mismatched nested delimiter in object")
                stack.pop()
        offset += len(line)
    if in_string or stack:
        raise ValueError("unterminated nested value in object")
    return assignments


def _decode_quoted(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid quoted-string escape: {value!r}") from exc


def _scalar_assignments(text: str, field: str) -> list[str]:
    values: list[str] = []
    object_end = text.rfind("}")
    for name, assignment_end in _direct_assignment_heads(text):
        if name != field:
            continue
        line_end = object_end
        for newline in (text.find("\r", assignment_end), text.find("\n", assignment_end)):
            if newline >= 0:
                line_end = min(line_end, newline)
        values.append(text[assignment_end:line_end].strip())
    return values


def _extract_scalar_string(text: str, field: str) -> str | None:
    assignments = _scalar_assignments(text, field)
    if len(assignments) > 1:
        raise ValueError(f"duplicate field {field}")
    if not assignments:
        return None
    raw = _strip_optional_trailing_comma(assignments[0])
    match = re.fullmatch(r'(?:resource\s*:\s*)?"((?:\\.|[^"\\])*)"', raw)
    if not match:
        raise ValueError(f"{field} must be one complete quoted scalar")
    return _decode_quoted(match.group(1))


def _extract_scalar_int(text: str, field: str) -> int | None:
    assignments = _scalar_assignments(text, field)
    if len(assignments) > 1:
        raise ValueError(f"duplicate field {field}")
    if not assignments:
        return None
    raw = _strip_optional_trailing_comma(assignments[0])
    if not re.fullmatch(INTEGER_PATTERN, raw):
        raise ValueError(f"{field} must be one complete integer scalar")
    return int(raw)


def _extract_balanced_at(text: str, assignment_end: int, field: str, opening: str) -> str:
    closing = {"[": "]", "{": "}"}[opening]
    start = text.find(opening, assignment_end)
    if start < 0:
        raise ValueError(f"{field} must contain a {opening}{closing} value")

    unexpected = text[assignment_end:start].strip()
    if unexpected:
        raise ValueError(f"unsupported value before {field} {opening}{closing} body")

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
                line_end = len(text)
                for newline in (text.find("\r", index + 1), text.find("\n", index + 1)):
                    if newline >= 0:
                        line_end = min(line_end, newline)
                trailing = text[index + 1 : line_end].strip()
                compact_trailing = re.sub(r"\s+", "", trailing)
                if compact_trailing not in {"", ",", "}", ",}"}:
                    raise ValueError(
                        f"unsupported content after {field} {opening}{closing} value"
                    )
                return text[start + 1 : index]
    raise ValueError(f"unterminated {opening}{closing} value for {field}")


def _extract_balanced_field(
    text: str,
    field: str,
    opening: str = "[",
    *,
    required: bool = False,
) -> str | None:
    matches = [
        assignment_end
        for name, assignment_end in _direct_assignment_heads(text)
        if name == field
    ]
    if not matches:
        if required:
            raise ValueError(f"missing required field {field}")
        return None
    if len(matches) != 1:
        raise ValueError(f"duplicate field {field}")
    return _extract_balanced_at(text, matches[0], field, opening)


def _parse_array_tokens(
    body: str,
    field: str,
    token_pattern: str,
    decode: Any,
) -> list[Any]:
    values: list[Any] = []
    position = 0
    expect_value = True
    token = re.compile(token_pattern)

    while True:
        whitespace = re.match(r"\s*", body[position:])
        assert whitespace is not None
        position += whitespace.end()
        if position >= len(body):
            return values

        if not expect_value:
            if body[position] != ",":
                raise ValueError(f"unsupported {field} array syntax near offset {position}")
            position += 1
            expect_value = True
            continue

        match = token.match(body, position)
        if not match:
            raise ValueError(f"unsupported {field} array value near offset {position}")
        values.append(decode(match))
        position = match.end()
        expect_value = False


def _quoted_values(text: str | None, field: str = "array") -> list[str]:
    if text is None:
        return []
    return _parse_array_tokens(
        text,
        field,
        r'"((?:\\.|[^"\\])*)"',
        lambda match: _decode_quoted(match.group(1)),
    )


def _resource_values(text: str | None, field: str = "m_resources") -> list[str]:
    if text is None:
        return []
    return _parse_array_tokens(
        text,
        field,
        r'resource\s*:\s*"((?:\\.|[^"\\])*)"',
        lambda match: _decode_quoted(match.group(1)),
    )


def _integer_values(text: str | None, field: str) -> list[int]:
    if text is None:
        return []
    return _parse_array_tokens(
        text,
        field,
        INTEGER_PATTERN,
        lambda match: int(match.group(0)),
    )


def _top_level_objects(array_body: str) -> list[str]:
    objects: list[str] = []
    outside: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(array_body):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            if depth == 0:
                outside.append(char)
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth == 0:
                raise ValueError("unexpected closing brace in m_nodes")
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(array_body[start : index + 1])
                start = None
        elif depth == 0:
            outside.append(char)

    if depth != 0:
        raise ValueError("unterminated object in m_nodes")
    if re.sub(r"[\s,]", "", "".join(outside)):
        raise ValueError("m_nodes contains unsupported non-object entries")
    return objects


def _validate_root_object(text: str) -> str:
    header = KV3_HEADER_PATTERN.match(text)
    if header is None:
        raise ValueError(
            "unsupported editable/unknown graph shape; expected a complete "
            "generic KV3 header"
        )
    start = text.find("{", header.end())
    if start < 0 or text[header.end() : start].strip():
        raise ValueError("expected one root KV3 object after the header")
    stack: list[str] = []
    in_string = False
    escaped = False
    end: int | None = None
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
        elif char in "[{":
            stack.append(char)
        elif char in "]}":
            expected = "[" if char == "]" else "{"
            if not stack or stack[-1] != expected:
                raise ValueError("mismatched delimiter in root KV3 object")
            stack.pop()
            if not stack:
                end = index + 1
                break
    if in_string or stack or end is None:
        raise ValueError("unterminated root KV3 object")
    if text[end:].strip():
        raise ValueError("unsupported trailing content after root KV3 object")
    return text[start:end]


def _top_level_assignments(block: str) -> list[tuple[str, str]]:
    """Return direct object fields without interpreting nested object fields."""

    assignments: list[tuple[str, str]] = []
    object_end = block.rfind("}")
    for name, assignment_end in _direct_assignment_heads(block):
        line_end = object_end
        for newline in (block.find("\r", assignment_end), block.find("\n", assignment_end)):
            if newline >= 0:
                line_end = min(line_end, newline)
        assignments.append(
            (name, _strip_optional_trailing_comma(block[assignment_end:line_end]))
        )
    return assignments


def _validate_node_fields(block: str) -> None:
    assignments = _top_level_assignments(block)
    counts: dict[str, int] = {}
    for field, raw in assignments:
        counts[field] = counts.get(field, 0) + 1
        if field.startswith("m_fl") or re.search(
            r"(?:Duration|TimeValueSeconds|EventOffset|Percentage|Percent)$",
            field,
        ):
            if raw == "" and field.endswith("Percentage"):
                # Current builds decompile transition percentages as a one-field
                # struct on the following lines: `m_boneMaskBlendInTimePercentage =
                # { m_flValue = 0.33 }`. Accept exactly that shape and validate the
                # inner scalar like a bare number.
                wrapped = re.search(
                    re.escape(field)
                    + r"[ \t]*=[ \t\r\n]*\{[ \t\r\n]*m_flValue[ \t]*=[ \t]*("
                    + NUMBER_PATTERN
                    + r")[ \t\r\n]*\}",
                    block,
                )
                if not wrapped:
                    raise ValueError(
                        f"{field} must be one complete finite decimal number "
                        f"or a {{ m_flValue = <number> }} struct, got {raw!r}"
                    )
                if not math.isfinite(float(wrapped.group(1))):
                    raise ValueError(f"{field} must be finite, got {wrapped.group(1)!r}")
                continue
            if not re.fullmatch(NUMBER_PATTERN, raw):
                raise ValueError(
                    f"{field} must be one complete finite decimal number, got {raw!r}"
                )
            if not math.isfinite(float(raw)):
                raise ValueError(f"{field} must be finite, got {raw!r}")
    duplicates = sorted(field for field, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate direct field(s) in object: {duplicates}")


def _field_int(block: str, field: str) -> int | None:
    matches = [raw for name, raw in _top_level_assignments(block) if name == field]
    if not matches:
        return None
    if len(matches) > 1 or not re.fullmatch(INTEGER_PATTERN, matches[0]):
        raise ValueError(f"{field} must be one complete integer scalar")
    return int(matches[0])


def _field_string(block: str, field: str) -> str | None:
    matches = [raw for name, raw in _top_level_assignments(block) if name == field]
    if not matches:
        return None
    match = re.fullmatch(r'"((?:\\.|[^"\\])*)"', matches[0])
    if len(matches) > 1 or not match:
        raise ValueError(f"{field} must be one complete quoted scalar")
    return _decode_quoted(match.group(1))


def _field_bool(block: str, field: str) -> bool | None:
    matches = [raw for name, raw in _top_level_assignments(block) if name == field]
    if not matches:
        return None
    if len(matches) > 1 or matches[0] not in {"true", "false"}:
        raise ValueError(f"{field} must be one complete boolean scalar")
    return matches[0] == "true"


def _field_float(block: str, field: str) -> float | None:
    matches = [raw for name, raw in _top_level_assignments(block) if name == field]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(f"duplicate field {field}")
    raw = matches[0]
    if not re.fullmatch(NUMBER_PATTERN, raw):
        raise ValueError(f"{field} must be a finite decimal number, got {raw!r}")
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite, got {raw!r}")
    return value


def _scalar_node_references(block: str) -> list[tuple[str, int]]:
    references: list[tuple[str, int]] = []
    for field, raw in _top_level_assignments(block):
        if not re.fullmatch(r"m_[A-Za-z0-9_]*NodeIdx[A-Za-z0-9_]*", field):
            continue
        if not re.fullmatch(INTEGER_PATTERN, raw):
            raise ValueError(f"{field} must be an integer node index, got {raw!r}")
        references.append((field, int(raw)))
    return references


def _array_node_references(block: str) -> list[tuple[str, int]]:
    references: list[tuple[str, int]] = []
    for field, _ in _top_level_assignments(block):
        if not re.fullmatch(r"m_[A-Za-z0-9_]*NodeIndices[A-Za-z0-9_]*", field):
            continue
        body = _extract_balanced_field(block, field)
        assert body is not None
        references.extend(
            (field, value)
            for value in _integer_values(body, field)
        )
    return references


def _node_references(block: str) -> list[tuple[str, int]]:
    return _scalar_node_references(block) + _array_node_references(block)


def _input_control_indices(block: str) -> list[int]:
    return [
        value
        for field, value in _node_references(block)
        if re.fullmatch(r"m_nInput(?:Value|Parameter)NodeIdx\d*", field)
        and value >= 0
    ]


def summarize_text(text: str, source: str = "<memory>") -> dict[str, Any]:
    if not text.strip():
        raise ValueError("input is empty")
    root = _validate_root_object(text)

    control_names = _quoted_values(
        _extract_balanced_field(root, "m_controlParameterIDs", required=True),
        "m_controlParameterIDs",
    )
    node_paths = _quoted_values(
        _extract_balanced_field(root, "m_nodePaths", required=True),
        "m_nodePaths",
    )
    resources = _resource_values(
        _extract_balanced_field(root, "m_resources", required=True),
        "m_resources",
    )
    virtual_parameter_ids_body = _extract_balanced_field(root, "m_virtualParameterIDs")
    virtual_parameter_node_indices_body = _extract_balanced_field(
        root, "m_virtualParameterNodeIndices"
    )
    if (virtual_parameter_ids_body is None) != (
        virtual_parameter_node_indices_body is None
    ):
        raise ValueError(
            "m_virtualParameterIDs and m_virtualParameterNodeIndices must both "
            "be present or both be absent"
        )
    virtual_parameter_ids = _quoted_values(
        virtual_parameter_ids_body, "m_virtualParameterIDs"
    )
    top_level_node_arrays: dict[str, list[int]] = {}
    for field, body in (
        ("m_virtualParameterNodeIndices", virtual_parameter_node_indices_body),
        ("m_persistentNodeIndices", _extract_balanced_field(root, "m_persistentNodeIndices")),
    ):
        if body is not None:
            top_level_node_arrays[field] = _integer_values(body, field)
    dependency_slot_bodies = {
        field: _extract_balanced_field(root, field)
        for field in (
            "m_referencedGraphSlots",
            "m_externalGraphSlots",
            "m_externalPoseSlots",
        )
    }
    node_body = _extract_balanced_field(root, "m_nodes", required=True)
    assert node_body is not None
    blocks = _top_level_objects(node_body)
    if not blocks:
        raise ValueError("m_nodes is empty; input is not a compiled graph definition")

    variation = _extract_scalar_string(root, "m_variationID")
    skeleton = _extract_scalar_string(root, "m_skeleton")
    root_node_index = _extract_scalar_int(root, "m_nRootNodeIdx")
    if variation is None:
        raise ValueError("missing required field m_variationID")
    if not skeleton:
        raise ValueError("missing or empty required resource m_skeleton")
    if root_node_index is None:
        raise ValueError("missing required field m_nRootNodeIdx")
    if len(set(control_names)) != len(control_names):
        raise ValueError("m_controlParameterIDs contains duplicate names")
    if any(not name for name in control_names):
        raise ValueError("m_controlParameterIDs contains an empty name")
    if any(not path for path in resources):
        raise ValueError("m_resources contains an empty resource path")
    if len(set(virtual_parameter_ids)) != len(virtual_parameter_ids):
        raise ValueError("m_virtualParameterIDs contains duplicate names")
    if any(not name for name in virtual_parameter_ids):
        raise ValueError("m_virtualParameterIDs contains an empty name")

    node_types: dict[int, str] = {}
    node_classes: dict[int, str] = {}
    node_blocks: dict[int, str] = {}
    id_values: dict[int, set[str]] = {}
    float_comparisons: dict[int, list[dict[str, Any]]] = {}
    clips: list[dict[str, Any]] = []
    references_by_target: dict[int, list[str]] = {}

    for block in blocks:
        _validate_node_fields(block)
        class_name = _field_string(block, "_class")
        node_index = _field_int(block, "m_nNodeIdx")
        if not class_name or not class_name.endswith("::CDefinition"):
            raise ValueError(
                "unsupported editable node shape; every m_nodes entry must be a ::CDefinition"
            )
        if node_index is None or node_index < 0:
            raise ValueError(f"{class_name} has no valid non-negative m_nNodeIdx")
        if node_index in node_blocks:
            raise ValueError(f"duplicate m_nNodeIdx {node_index}")
        node_blocks[node_index] = block
        node_classes[node_index] = class_name

        if class_name.startswith("CNmControlParameter") and class_name not in CONTROL_TYPES:
            raise ValueError(f"unsupported control-parameter node class {class_name}")
        if class_name in CONTROL_TYPES:
            node_types[node_index] = CONTROL_TYPES[class_name]

    node_indices = set(node_blocks)
    if root_node_index < 0 or root_node_index not in node_indices:
        raise ValueError(f"m_nRootNodeIdx {root_node_index} does not identify a node")
    for node_index in sorted(node_indices):
        if node_index >= len(node_paths):
            raise ValueError(
                f"m_nNodeIdx {node_index} is outside m_nodePaths ({len(node_paths)} entries)"
            )
    for field, values in top_level_node_arrays.items():
        invalid = [value for value in values if value < 0 or value not in node_indices]
        if invalid:
            raise ValueError(f"{field} references invalid node indexes: {invalid}")
        if len(set(values)) != len(values):
            raise ValueError(f"{field} contains duplicate node indexes")
    virtual_node_indices = top_level_node_arrays.get(
        "m_virtualParameterNodeIndices", []
    )
    if len(virtual_parameter_ids) != len(virtual_node_indices):
        raise ValueError(
            "m_virtualParameterIDs and m_virtualParameterNodeIndices have different lengths"
        )

    dependency_slot_counts: dict[str, int] = {}
    for field, body in dependency_slot_bodies.items():
        if body is None:
            dependency_slot_counts[field] = 0
            continue
        slot_objects = _top_level_objects(body)
        dependency_slot_counts[field] = len(slot_objects)
        schema = DEPENDENCY_SLOT_SCHEMAS[field]
        seen_slot_keys: set[tuple[object, ...]] = set()
        for slot_index, slot in enumerate(slot_objects):
            _validate_node_fields(slot)
            field_names = {name for name, _ in _top_level_assignments(slot)}
            required_fields = set(schema)
            missing = sorted(required_fields - field_names)
            unknown = sorted(field_names - required_fields)
            if missing or unknown:
                raise ValueError(
                    f"{field}[{slot_index}] does not match the supported slot schema; "
                    f"missing={missing}, unknown={unknown}"
                )

            node_index = _field_int(slot, "m_nNodeIdx")
            if node_index is None or node_index < 0 or node_index not in node_indices:
                raise ValueError(
                    f"{field}[{slot_index}].m_nNodeIdx references invalid node "
                    f"index {node_index}"
                )

            if schema.get("m_dataSlotIdx") == "resource":
                data_slot = _field_int(slot, "m_dataSlotIdx")
                if data_slot is None or data_slot < 0 or data_slot >= len(resources):
                    raise ValueError(
                        f"{field}[{slot_index}].m_dataSlotIdx references invalid "
                        f"resource slot {data_slot}"
                    )
                slot_key: tuple[object, ...] = (node_index, data_slot)
            else:
                slot_id = _field_string(slot, "m_slotID")
                if not slot_id:
                    raise ValueError(f"{field}[{slot_index}].m_slotID must be non-empty")
                slot_key = (node_index, slot_id)

            if slot_key in seen_slot_keys:
                raise ValueError(f"{field} contains duplicate slot {slot_key}")
            seen_slot_keys.add(slot_key)

    for index, name in enumerate(control_names):
        class_name = node_classes.get(index)
        if class_name not in CONTROL_TYPES:
            raise ValueError(
                f"control {name!r} at index {index} has no supported control node at the same index"
            )
    unexpected_control_nodes = sorted(set(node_types) - set(range(len(control_names))))
    if unexpected_control_nodes:
        raise ValueError(
            "control-parameter nodes are not represented by m_controlParameterIDs: "
            + ", ".join(map(str, unexpected_control_nodes))
        )

    for node_index, block in node_blocks.items():
        class_name = node_classes[node_index]
        for field, target in _node_references(block):
            if field == "m_nNodeIdx":
                continue
            if target < -1:
                raise ValueError(f"{field} on node {node_index} uses invalid sentinel {target}")
            if target >= 0:
                if target not in node_indices:
                    raise ValueError(
                        f"{field} on node {node_index} references missing node {target}"
                    )
                references_by_target.setdefault(target, []).append(field)

        for field, raw in _top_level_assignments(block):
            if not re.fullmatch(r"m_[A-Za-z0-9_]*DataSlotIdx[A-Za-z0-9_]*", field):
                continue
            if not re.fullmatch(INTEGER_PATTERN, raw):
                raise ValueError(f"{field} on node {node_index} must be an integer")
            slot = int(raw)
            if slot < -1 or slot >= len(resources):
                raise ValueError(
                    f"{field} on node {node_index} references invalid resource slot {slot}"
                )

        input_indices = _input_control_indices(block)
        if input_indices and class_name:
            if "IDComparisonNode" in class_name or "IDToFloatNode" in class_name:
                values: set[str] = set()
                for field in ("m_comparisionIDs", "m_comparisonIDs", "m_IDs"):
                    body = _extract_balanced_field(block, field)
                    if body is not None:
                        values.update(_quoted_values(body, field))
                if values:
                    for input_index in input_indices:
                        id_values.setdefault(input_index, set()).update(values)
            if "FloatComparisonNode" in class_name:
                threshold = _field_float(block, "m_flComparisonValue")
                comparison = _field_string(block, "m_comparison")
                if threshold is not None:
                    for input_index in input_indices:
                        float_comparisons.setdefault(input_index, []).append(
                            {"comparison": comparison or "unknown", "value": threshold}
                        )

        if class_name == "CNmClipNode::CDefinition" and node_index is not None:
            data_slot = _field_int(block, "m_nDataSlotIdx")
            if data_slot is None or data_slot < 0 or data_slot >= len(resources):
                raise ValueError(
                    f"clip node {node_index} has no valid m_nDataSlotIdx resource"
                )
            resource = resources[data_slot]
            clips.append(
                {
                    "node_index": node_index,
                    "node_path": node_paths[node_index]
                    if 0 <= node_index < len(node_paths)
                    else None,
                    "data_slot": data_slot,
                    "resource": resource,
                    "looping": _field_bool(block, "m_bAllowLooping"),
                    "speed_multiplier": _field_float(block, "m_flSpeedMultiplier"),
                }
            )

    controls: list[dict[str, Any]] = []
    for index, name in enumerate(control_names):
        control_type = node_types[index]
        controls.append(
            {
                "index": index,
                "name": name,
                "type": control_type,
                "bridge_write_support": BRIDGE_WRITE_SUPPORT[control_type],
                "node_path": node_paths[index] if index < len(node_paths) else None,
                "id_values": sorted(id_values.get(index, set())),
                "float_comparisons": float_comparisons.get(index, []),
                "reference_count": len(references_by_target.get(index, [])),
            }
        )

    warnings: list[str] = []
    warnings.append(
        "graph structure cannot verify a native bridge; Bool/Float/ID writes "
        "require strict current-build resolution and a live typed probe"
    )
    unsupported = [
        control["name"]
        for control in controls
        if control["bridge_write_support"] == "diagnostic-only"
    ]
    if unsupported:
        warnings.append(
            "no native write contract is bundled for Vector/Target controls: "
            + ", ".join(unsupported)
        )
    warnings.append(
        "event IDs, event timing, transition semantics, and unrecognized optional "
        "tables are not reconstructed by this first-pass helper; inspect them manually"
    )

    return {
        "source": source,
        "variation": variation,
        "skeleton": skeleton,
        "root_node_index": root_node_index,
        "control_count": len(controls),
        "controls": controls,
        "node_count": len(blocks),
        "node_path_count": len(node_paths),
        "resource_count": len(resources),
        "resources": resources,
        "virtual_parameter_ids": virtual_parameter_ids,
        "top_level_node_arrays": top_level_node_arrays,
        "dependency_slot_counts": dependency_slot_counts,
        "clip_node_count": len(clips),
        "clips": clips,
        "warnings": warnings,
    }


def _markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: dict[str, Any], include_clips: bool = False) -> str:
    lines = [
        "# AnimGraph2 Contract Summary",
        "",
        f"- Source: `{_markdown_escape(summary['source'])}`",
        f"- Variation: `{_markdown_escape(summary['variation'])}`",
        f"- Skeleton: `{_markdown_escape(summary['skeleton'])}`",
        f"- Root node: `{summary['root_node_index']}`",
        f"- Controls: `{summary['control_count']}`",
        f"- Nodes: `{summary['node_count']}`",
        f"- Resources: `{summary['resource_count']}`",
        f"- Clip nodes: `{summary['clip_node_count']}`",
        "",
        "## Controls",
        "",
        "| Index | Name | Type | Native bridge | Observed IDs / Float comparisons | References |",
        "|---:|---|---|---|---|---:|",
    ]
    for control in summary["controls"]:
        evidence: list[str] = list(control["id_values"])
        evidence.extend(
            f"{item['comparison']} {item['value']:g}"
            for item in control["float_comparisons"]
        )
        lines.append(
            "| {index} | `{name}` | {type} | {bridge} | {evidence} | {references} |".format(
                index=control["index"],
                name=_markdown_escape(control["name"]),
                type=control["type"],
                bridge=control["bridge_write_support"],
                evidence=_markdown_escape(", ".join(evidence) or "-"),
                references=control["reference_count"],
            )
        )

    if include_clips:
        lines.extend(
            [
                "",
                "## Clip Nodes",
                "",
                "| Node | Path | Slot | Loop | Resource |",
                "|---:|---|---:|---|---|",
            ]
        )
        for clip in summary["clips"]:
            lines.append(
                "| {node} | `{path}` | {slot} | {loop} | `{resource}` |".format(
                    node=clip["node_index"],
                    path=_markdown_escape(clip["node_path"]),
                    slot=clip["data_slot"],
                    loop=clip["looping"],
                    resource=_markdown_escape(clip["resource"]),
                )
            )

    if summary["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in summary["warnings"])
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize structural controls and clips in a decompiled VNMGraph."
    )
    parser.add_argument("input", type=Path, help="Source2Viewer-decompiled .vnmgraph")
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    parser.add_argument(
        "--include-clips",
        action="store_true",
        help="Include the clip-node table in Markdown output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        text = args.input.read_text(encoding="utf-8")
        summary = summarize_text(text, str(args.input))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(render_markdown(summary, args.include_clips), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
