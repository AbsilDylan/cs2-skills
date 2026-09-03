"""Compiler-frame conversion and secondary weapon skeleton insertion (pure text tests)."""

from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_tooling import EXAMPLE, load_blender_only_module  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from animgraph2_manifest import ManifestError, validate_manifest  # noqa: E402


SYNTHETIC_TEMPLATE = '''<!-- dmx encoding keyvalues2 4 format model 22 -->
"DmElement"
{
	"id" "elementid" "root-element"
	"name" "string" "root"
	"skeleton" "DmeModel"
	{
		"id" "elementid" "model-1"
		"children" "element_array"
		[
			"element" "joint-root"
		]
		"jointList" "element_array"
		[
			"element" "model-1",
			"element" "joint-root",
			"element" "joint-wpn"
		]
	}

	"animationList" "DmeAnimationList"
	{
		"id" "elementid" "anim-list"
		"animations" "element_array"
		[
			"DmeChannelsClip"
			{
				"id" "elementid" "clip-1"
				"channels" "element_array"
				[
					"DmeChannel"
					{
						"id" "elementid" "chan-1"
						"name" "string" "wpn_p"
						"toElement" "element" "transform-wpn"
						"toAttribute" "string" "position"
						"log" "DmeVector3Log"
						{
							"id" "elementid" "log-1"
							"layers" "element_array"
							[
								"DmeVector3LogLayer"
								{
									"id" "elementid" "layer-1"
									"times" "time_array"
									[
										"0.0000"
									]
									"values" "vector3_array"
									[
										"0 0 0"
									]
								}
							]
						}

					}
				]
				"frameRate" "float" "30"
			}
		]
	}

}

"DmeTransform"
{
	"id" "elementid" "transform-wpn"
	"name" "string" "wpn"
	"position" "vector3" "0 0 17"
	"orientation" "quaternion" "0 0 0 1"
}

"DmeJoint"
{
	"id" "elementid" "joint-root"
	"name" "string" "root_motion"
	"transform" "element" "transform-root"
	"children" "element_array"
	[
		"element" "joint-wpn"
	]
}

"DmeJoint"
{
	"id" "elementid" "joint-wpn"
	"name" "string" "wpn"
	"transform" "element" "transform-wpn"
	"children" "element_array"
	[
	]
}
'''

WEAPON_SKELETON = '''<!-- dmx encoding keyvalues2 4 format model 22 -->
"DmeJoint"
{
	"id" "elementid" "j-weapon"
	"name" "string" "weapon"
	"transform" "DmeTransform"
	{
		"id" "elementid" "t-weapon"
		"position" "vector3" "0 0 0"
		"orientation" "quaternion" "0 0 0 1"
	}

	"children" "element_array"
	[
		"element" "j-offset"
	]
}

"DmeJoint"
{
	"id" "elementid" "j-offset"
	"name" "string" "weapon_offset"
	"transform" "DmeTransform"
	{
		"id" "elementid" "t-offset"
		"position" "vector3" "0 0 0"
		"orientation" "quaternion" "0 0 0 1"
	}

	"children" "element_array"
	[
		"element" "j-slide"
	]
}

"DmeJoint"
{
	"id" "elementid" "j-slide"
	"name" "string" "slide"
	"transform" "DmeTransform"
	{
		"id" "elementid" "t-slide"
		"position" "vector3" "1.5 0 0.25"
		"orientation" "quaternion" "0 0 0 1"
	}

	"children" "element_array"
	[
	]
}
'''


class CompilerFrameTests(unittest.TestCase):
    def test_root_level_conversion_matches_the_recorded_example(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        samples = [
            {
                "wpn": {"position": [23.27, -5.46, -5.42], "orientation": [0.0, 0.0, 0.0, 1.0]},
                "hand_R": {"position": [1.0, 2.0, 3.0], "orientation": [0.0, 0.0, 0.0, 1.0]},
            }
        ]
        converted = module.to_compiler_frame(samples, {"wpn"})
        self.assertEqual(converted[0]["wpn"]["position"], [-5.46, -5.42, 23.27])
        self.assertEqual(converted[0]["hand_R"], samples[0]["hand_R"])
        x, y, z, w = converted[0]["wpn"]["orientation"]
        self.assertAlmostEqual(math.sqrt(x * x + y * y + z * z + w * w), 1.0, places=9)
        # a -120 degree rotation about the (1,1,1) diagonal: w = cos(60 deg)
        self.assertAlmostEqual(w, 0.5, places=9)

    def test_three_conversions_return_to_the_source_frame(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        sample = {"wpn": {"position": [1.0, 2.0, 3.0], "orientation": [0.1, 0.2, 0.3, 0.927]}}
        current = [sample]
        for _ in range(3):
            current = module.to_compiler_frame(current, {"wpn"})
        self.assertEqual([round(v, 9) for v in current[0]["wpn"]["position"]], [1.0, 2.0, 3.0])
        original = sample["wpn"]["orientation"]
        result = current[0]["wpn"]["orientation"]
        sign = 1.0 if sum(a * b for a, b in zip(original, result)) >= 0 else -1.0
        for a, b in zip(original, result):
            self.assertAlmostEqual(a, sign * b, places=9)


class SecondarySkeletonTests(unittest.TestCase):
    def test_skeleton_dmx_is_read_in_hierarchy_order(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        joints = module.secondary_joints_from_dmx(WEAPON_SKELETON)
        self.assertEqual([j["name"] for j in joints], ["weapon", "weapon_offset", "slide"])
        self.assertEqual([j["parent"] for j in joints], [None, "weapon", "weapon_offset"])
        self.assertEqual(joints[2]["position"], [1.5, 0.0, 0.25])

    def test_secondary_joints_are_inserted_with_kv2_separators(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        joints = module.secondary_joints_from_dmx(WEAPON_SKELETON)
        patched = module.add_secondary_joints(SYNTHETIC_TEMPLATE, joints, "wpn")
        names = module.channel_names(patched)
        self.assertEqual(
            sorted(names),
            sorted(
                f"{bone}_{suffix}"
                for bone in ("wpn", "weapon", "weapon_offset", "slide")
                for suffix in ("p", "o")
                if not (bone == "wpn" and suffix == "o")
            ),
        )
        # the previous last channel now ends with "}," and the new last one with "}"
        lines = patched.splitlines()
        frame_rate = next(i for i, line in enumerate(lines) if '"frameRate" "float"' in line)
        closing = frame_rate - 1
        while lines[closing].strip() != "]":
            closing -= 1
        last_block_end = closing - 1
        while not lines[last_block_end].strip():
            last_block_end -= 1
        self.assertEqual(lines[last_block_end].strip(), "}")
        self.assertIn('"name" "string" "slide_o"', patched)
        self.assertGreaterEqual(patched.count('"DmeJoint"'), 5)
        # the weapon root is attached under wpn and every joint is registered
        wpn_start = patched.index('"name" "string" "wpn"\n\t"transform" "element" "transform-wpn"')
        wpn_children = patched[wpn_start:patched.index("}", wpn_start)]
        self.assertIn('"element" "', wpn_children)
        joint_list = patched[patched.index('"jointList"'):patched.index('"animationList"')]
        self.assertEqual(joint_list.count('"element" "'), 3 + len(joints))
        with self.assertRaisesRegex(ValueError, "already present"):
            module.add_secondary_joints(patched, joints, "wpn")

    def test_custom_skeleton_text_round_trips(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        joints = [
            {"name": "weapon", "parent": None, "position": [0, 0, 0], "orientation": [0, 0, 0, 1]},
            {"name": "weapon_offset", "parent": "weapon", "position": [0, 0, 0], "orientation": [0, 0, 0, 1]},
            {"name": "orb", "parent": "weapon_offset", "position": [0, 0, 2.5], "orientation": [0, 0, 0, 1]},
        ]
        text = module.skeleton_dmx_text(joints)
        self.assertTrue(text.startswith("<!-- dmx encoding keyvalues2 4 format model 22 -->"))
        parsed = module.secondary_joints_from_dmx(text)
        self.assertEqual([(j["name"], j["parent"]) for j in parsed], [(j["name"], j["parent"]) for j in joints])
        self.assertEqual(parsed[2]["position"], [0.0, 0.0, 2.5])
        with self.assertRaisesRegex(ValueError, "exactly one root"):
            module.skeleton_dmx_text(joints + [{"name": "loose", "parent": None, "position": [0, 0, 0], "orientation": [0, 0, 0, 1]}])


class ManifestFrameFieldsTests(unittest.TestCase):
    def test_defaults_and_rejections(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        validated = validate_manifest(copy.deepcopy(manifest))
        self.assertEqual(validated["sets"][0]["reference_dmx_frame"], "source-axes")
        self.assertEqual(validated["sets"][0]["secondary_attach_bone"], "wpn")
        self.assertNotIn("secondary_skeleton_dmx", validated["sets"][0])
        manifest["sets"][0]["reference_dmx_frame"] = "compiler"
        manifest["sets"][0]["secondary_skeleton_dmx"] = "animation\\skeletons\\weapons\\fiveseven.dmx"
        validated = validate_manifest(copy.deepcopy(manifest))
        self.assertEqual(validated["sets"][0]["reference_dmx_frame"], "compiler")
        self.assertEqual(
            validated["sets"][0]["secondary_skeleton_dmx"],
            "animation/skeletons/weapons/fiveseven.dmx",
        )
        manifest["sets"][0]["reference_dmx_frame"] = "guess"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
