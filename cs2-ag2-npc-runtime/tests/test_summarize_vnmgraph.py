#!/usr/bin/env python3
"""Tests for the decompiled VNMGraph summarizer using original fixture text."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_vnmgraph.py"
SPEC = importlib.util.spec_from_file_location("summarize_vnmgraph", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


FIXTURE = r'''<!-- kv3 encoding:text:version{test} format:generic:version{test} -->
{
    m_variationID = "Default"
    m_skeleton = resource:"animation/example/example.vnmskel"
    m_nRootNodeIdx = 4
    m_controlParameterIDs = [ "move_speed", "base_action", "aim_vector", "target" ]
    m_nodePaths = [ "move_speed", "base_action", "aim_vector", "target", "float_gate", "id_gate", "consumer", "run" ]
    m_resources = [ resource:"animation/example/run.vnmclip" ]
    m_nodes =
    [
        {
            _class = "CNmControlParameterFloatNode::CDefinition"
            m_nNodeIdx = 0
        },
        {
            _class = "CNmControlParameterIDNode::CDefinition"
            m_nNodeIdx = 1
        },
        {
            _class = "CNmControlParameterVectorNode::CDefinition"
            m_nNodeIdx = 2
        },
        {
            _class = "CNmControlParameterTargetNode::CDefinition"
            m_nNodeIdx = 3
        },
        {
            _class = "CNmFloatComparisonNode::CDefinition"
            m_nNodeIdx = 4
            m_nInputValueNodeIdx = 0
            m_comparison = "GreaterThan"
            m_flComparisonValue = -1.25e+2
        },
        {
            _class = "CNmIDComparisonNode::CDefinition"
            m_nNodeIdx = 5
            m_nInputValueNodeIdx = 1
            m_comparisionIDs = [ "ground_jump" ]
        },
        {
            _class = "CNmSyntheticConsumerNode::CDefinition"
            m_nNodeIdx = 6
            m_nInputParameterNodeIdx1 = 2
            m_conditionNodeIndices = [ 3 ]
        },
        {
            _class = "CNmClipNode::CDefinition"
            m_nNodeIdx = 7
            m_bAllowLooping = true
            m_nDataSlotIdx = 0
            m_flSpeedMultiplier = 1.0
        },
    ]
}
'''


def with_top_level(fragment: str) -> str:
    return FIXTURE.replace("    m_nodes =", fragment + "\n    m_nodes =", 1)


class SummarizeVnmGraphTests(unittest.TestCase):
    def test_extracts_controls_types_evidence_and_clip(self) -> None:
        summary = MODULE.summarize_text(FIXTURE, "fixture.vnmgraph")

        self.assertEqual(summary["control_count"], 4)
        self.assertEqual(summary["controls"][0]["type"], "Float")
        self.assertEqual(
            summary["controls"][0]["float_comparisons"],
            [{"comparison": "GreaterThan", "value": -125.0}],
        )
        self.assertEqual(summary["controls"][1]["type"], "ID")
        self.assertEqual(summary["controls"][1]["id_values"], ["ground_jump"])
        self.assertEqual(summary["controls"][2]["type"], "Vector")
        self.assertEqual(
            summary["controls"][0]["bridge_write_support"],
            "requires-verified-bridge",
        )
        self.assertEqual(
            summary["controls"][2]["bridge_write_support"], "diagnostic-only"
        )
        self.assertEqual(summary["controls"][2]["reference_count"], 1)
        self.assertEqual(summary["controls"][3]["type"], "Target")
        self.assertEqual(summary["controls"][3]["reference_count"], 1)
        self.assertIn("cannot verify a native bridge", summary["warnings"][0])
        self.assertIn("no native write contract", summary["warnings"][1])
        self.assertEqual(summary["clip_node_count"], 1)
        self.assertEqual(summary["clips"][0]["resource"], "animation/example/run.vnmclip")
        self.assertTrue(summary["clips"][0]["looping"])

    def test_markdown_contains_contract_table(self) -> None:
        rendered = MODULE.render_markdown(MODULE.summarize_text(FIXTURE))
        self.assertIn(
            "| 0 | `move_speed` | Float | requires-verified-bridge |", rendered
        )
        self.assertIn(
            "| 1 | `base_action` | ID | requires-verified-bridge | ground_jump |",
            rendered,
        )
        self.assertIn("| 2 | `aim_vector` | Vector | diagnostic-only |", rendered)

    def test_rejects_empty_and_non_definition_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "input is empty"):
            MODULE.summarize_text("  \n")
        with self.assertRaisesRegex(ValueError, "editable/unknown graph shape"):
            MODULE.summarize_text(FIXTURE.replace("format:generic", "format:animgraph2"))
        with self.assertRaisesRegex(ValueError, "editable node shape"):
            MODULE.summarize_text(FIXTURE.replace("::CDefinition", "", 1))

    def test_rejects_missing_or_malformed_required_arrays(self) -> None:
        without_resources = FIXTURE.replace(
            '    m_resources = [ resource:"animation/example/run.vnmclip" ]\n', ""
        )
        with self.assertRaisesRegex(ValueError, "missing required field m_resources"):
            MODULE.summarize_text(without_resources)

        malformed = FIXTURE.replace(
            '[ "move_speed", "base_action", "aim_vector", "target" ]',
            '[ "move_speed" "base_action", "aim_vector", "target" ]',
        )
        with self.assertRaisesRegex(ValueError, "unsupported m_controlParameterIDs array syntax"):
            MODULE.summarize_text(malformed)

        trailing_control_junk = FIXTURE.replace(
            '[ "move_speed", "base_action", "aim_vector", "target" ]',
            '[ "move_speed", "base_action", "aim_vector", "target" ] MALFORMED',
            1,
        )
        repeated_control_delimiter = FIXTURE.replace(
            '[ "move_speed", "base_action", "aim_vector", "target" ]',
            '[ "move_speed", "base_action", "aim_vector", "target" ],,,,',
            1,
        )
        trailing_node_junk = FIXTURE.replace("    ]\n}", "    ] MALFORMED\n}", 1)
        repeated_node_delimiter = FIXTURE.replace("    ]\n}", "    ],,,,\n}", 1)
        unclosed_unknown_array = with_top_level("    m_unknown = [ 1, 2")
        for malformed in (
            trailing_control_junk,
            repeated_control_delimiter,
            trailing_node_junk,
            repeated_node_delimiter,
            unclosed_unknown_array,
        ):
            with self.subTest(malformed=malformed[:120]), self.assertRaises(ValueError):
                MODULE.summarize_text(malformed)

    def test_rejects_duplicate_and_invalid_node_indices(self) -> None:
        duplicate = FIXTURE.replace("m_nNodeIdx = 7", "m_nNodeIdx = 6")
        with self.assertRaisesRegex(ValueError, "duplicate m_nNodeIdx 6"):
            MODULE.summarize_text(duplicate)

        invalid_root = FIXTURE.replace("m_nRootNodeIdx = 4", "m_nRootNodeIdx = 99")
        with self.assertRaisesRegex(ValueError, "does not identify a node"):
            MODULE.summarize_text(invalid_root)

        invalid_reference = FIXTURE.replace(
            "m_nInputParameterNodeIdx1 = 2", "m_nInputParameterNodeIdx1 = 99"
        )
        with self.assertRaisesRegex(ValueError, "references missing node 99"):
            MODULE.summarize_text(invalid_reference)

        invalid_array_reference = FIXTURE.replace(
            "m_conditionNodeIndices = [ 3 ]", "m_conditionNodeIndices = [ 99 ]"
        )
        with self.assertRaisesRegex(ValueError, "references missing node 99"):
            MODULE.summarize_text(invalid_array_reference)

    def test_rejects_invalid_resource_slots_and_unknown_control_shapes(self) -> None:
        invalid_slot = FIXTURE.replace("m_nDataSlotIdx = 0", "m_nDataSlotIdx = 4")
        with self.assertRaisesRegex(ValueError, "invalid resource slot 4"):
            MODULE.summarize_text(invalid_slot)

        unknown_control = FIXTURE.replace(
            "CNmControlParameterVectorNode", "CNmControlParameterBoneMaskNode"
        )
        with self.assertRaisesRegex(ValueError, "unsupported control-parameter node class"):
            MODULE.summarize_text(unknown_control)

    def test_rejects_nonfinite_exponential_float(self) -> None:
        nonfinite = FIXTURE.replace(
            "m_flSpeedMultiplier = 1.0", "m_flSpeedMultiplier = 1e9999"
        )
        with self.assertRaisesRegex(ValueError, "must be finite"):
            MODULE.summarize_text(nonfinite)

    def test_rejects_truncated_root_invalid_scalars_and_escapes(self) -> None:
        malformed_inputs = (
            FIXTURE.rsplit("}", 1)[0],
            FIXTURE.replace("\n{\n", "\n", 1),
            FIXTURE.replace(
                FIXTURE.splitlines()[0], "garbage format:generic -->", 1
            ),
            FIXTURE.replace("m_nRootNodeIdx = 4", "m_nRootNodeIdx = 4.5"),
            FIXTURE.replace("m_nRootNodeIdx = 4", "m_nRootNodeIdx = 4garbage"),
            FIXTURE.replace("m_nRootNodeIdx = 4", "m_nRootNodeIdx = 4,,,,,"),
            FIXTURE.replace(
                'm_variationID = "Default"', 'm_variationID = "Default",,,,,', 1
            ),
            FIXTURE.replace('"move_speed"', '"move\\q_speed"', 1),
        )
        for malformed in malformed_inputs:
            with self.subTest(malformed=malformed[:80]), self.assertRaises(ValueError):
                MODULE.summarize_text(malformed)

    def test_rejects_duplicate_direct_node_fields(self) -> None:
        duplicate_index = FIXTURE.replace(
            "m_nNodeIdx = 0", "m_nNodeIdx = 0\n            m_nNodeIdx = 1", 1
        )
        with self.assertRaisesRegex(ValueError, "duplicate direct field"):
            MODULE.summarize_text(duplicate_index)

        duplicate_float = FIXTURE.replace(
            "m_flSpeedMultiplier = 1.0",
            "m_flSpeedMultiplier = 1.0\n            m_flSpeedMultiplier = 1e9999",
        )
        with self.assertRaises(ValueError):
            MODULE.summarize_text(duplicate_float)

    def test_validates_known_top_level_node_and_dependency_tables(self) -> None:
        dangling_array = FIXTURE.replace(
            "    m_nodes =",
            "    m_persistentNodeIndices = [ 999 ]\n    m_nodes =",
        )
        with self.assertRaisesRegex(ValueError, "m_persistentNodeIndices"):
            MODULE.summarize_text(dangling_array)

        dangling_slot = FIXTURE.replace(
            "    m_nodes =",
            "    m_referencedGraphSlots =\n"
            "    [\n"
            "        {\n"
            "            m_nNodeIdx = 999\n"
            "            m_dataSlotIdx = 999\n"
            "        },\n"
            "    ]\n"
            "    m_nodes =",
        )
        with self.assertRaisesRegex(ValueError, "invalid node index 999"):
            MODULE.summarize_text(dangling_slot)

        valid_slots = with_top_level(
            "    m_referencedGraphSlots =\n"
            "    [\n"
            "        { m_nNodeIdx = 4\n"
            "          m_dataSlotIdx = 0 },\n"
            "    ]\n"
            "    m_externalGraphSlots =\n"
            "    [\n"
            '        { m_nNodeIdx = 4\n          m_slotID = "child" },\n'
            "    ]\n"
            "    m_externalPoseSlots =\n"
            "    [\n"
            '        { m_nNodeIdx = 4\n          m_slotID = "pose" },\n'
            "    ]"
        )
        counts = MODULE.summarize_text(valid_slots)["dependency_slot_counts"]
        self.assertEqual(counts["m_referencedGraphSlots"], 1)
        self.assertEqual(counts["m_externalGraphSlots"], 1)
        self.assertEqual(counts["m_externalPoseSlots"], 1)

    def test_rejects_unpaired_or_invalid_virtual_parameter_tables(self) -> None:
        malformed_inputs = (
            with_top_level('    m_virtualParameterIDs = [ "orphan" ]'),
            with_top_level("    m_virtualParameterNodeIndices = [ 4 ]"),
            with_top_level(
                '    m_virtualParameterIDs = [ "orphan" ]\n'
                "    m_virtualParameterNodeIndices = [  ]"
            ),
            with_top_level(
                '    m_virtualParameterIDs = [ "v", "v" ]\n'
                "    m_virtualParameterNodeIndices = [ 4, 5 ]"
            ),
            with_top_level(
                '    m_virtualParameterIDs = [ "" ]\n'
                "    m_virtualParameterNodeIndices = [ 4 ]"
            ),
            with_top_level(
                '    m_virtualParameterIDs = [ "v" ]\n'
                "    m_virtualParameterNodeIndices = [ -1 ]"
            ),
            with_top_level("    m_persistentNodeIndices = [ -1 ]"),
            with_top_level("    m_persistentNodeIndices = [ 4, 4 ]"),
        )
        for malformed in malformed_inputs:
            with self.subTest(malformed=malformed[:120]), self.assertRaises(ValueError):
                MODULE.summarize_text(malformed)

    def test_rejects_incomplete_or_malformed_dependency_slots(self) -> None:
        malformed_fragments = (
            "    m_referencedGraphSlots = [ { } ]",
            "    m_referencedGraphSlots = [ { m_nNodeIdx = 4 } ]",
            "    m_referencedGraphSlots =\n"
            "    [ { m_nNodeIdx = 4\n          m_dataSlotIdx = -1 } ]",
            "    m_externalGraphSlots =\n"
            "    [ { m_nNodeIdx = 4\n          m_slotID = 123 } ]",
            "    m_externalGraphSlots =\n"
            '    [ { m_nNodeIdx = 4\n          m_slotID = "bad\\q" } ]',
            "    m_externalPoseSlots =\n"
            '    [ { m_nNodeIdx = -1\n          m_slotID = "pose" } ]',
        )
        for fragment in malformed_fragments:
            with self.subTest(fragment=fragment), self.assertRaises(ValueError):
                MODULE.summarize_text(with_top_level(fragment))

    def test_required_contract_fields_must_be_direct_root_fields(self) -> None:
        header_end = FIXTURE.index("-->") + 3
        original_root = FIXTURE[FIXTURE.index("{", header_end) :].strip()
        nested = (
            FIXTURE[:header_end]
            + "\n{\n    unrelated =\n    "
            + original_root.replace("\n", "\n    ")
            + "\n}\n"
        )
        with self.assertRaisesRegex(ValueError, "missing required field"):
            MODULE.summarize_text(nested)

    def test_nested_lookalike_fields_cannot_forge_control_evidence(self) -> None:
        nested_metadata = FIXTURE.replace(
            '            m_comparisionIDs = [ "ground_jump" ]',
            '            m_comparisionIDs = [ "ground_jump" ]\n'
            "            m_metadata =\n"
            "            {\n"
            "                m_nInputValueNodeIdx = 0\n"
            '                m_comparisionIDs = [ "forged" ]\n'
            "            }",
            1,
        )
        summary = MODULE.summarize_text(nested_metadata)
        self.assertEqual(summary["controls"][0]["id_values"], [])
        self.assertEqual(summary["controls"][1]["id_values"], ["ground_jump"])
        self.assertEqual(summary["controls"][0]["reference_count"], 1)


if __name__ == "__main__":
    unittest.main()
