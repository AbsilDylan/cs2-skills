from __future__ import annotations

import ast
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from animgraph2_manifest import (  # noqa: E402
    ManifestError,
    canonical_bone_signature,
    dmx_timeframe,
    load_manifest,
    normalize_resource_path,
    reference_dmx_relative,
    reference_vnmclip_relative,
    resolve_cs2_root,
    resolve_tool,
    validate_manifest,
)
import compile_animgraph2 as compiler_tool  # noqa: E402
from compile_animgraph2 import (  # noqa: E402
    compile_resources,
    copy_with_policy,
    generated_sources,
    preflight_artifact_copies,
    restore_nonpackage_output,
    restore_temporary_stage,
    reject_artifact_extras,
    stage_sources,
)
from extract_stock_references import (  # noqa: E402
    cache_entry_is_current,
    exact_vpk_receipt,
    extraction_jobs,
)
from generate_vnmclips import generate_one  # noqa: E402


EXAMPLE = SKILL_ROOT / "examples" / "animgraph2-project.example.json"


def load_blender_only_module(filename: str):
    """Load a Blender-only script with inert modules for pure unit tests."""

    module_path = SCRIPTS / filename
    module_name = f"_test_{module_path.stem}"
    bpy_stub = types.ModuleType("bpy")
    bpy_stub.data = types.SimpleNamespace(filepath="", is_dirty=False)
    bpy_stub.app = types.SimpleNamespace(version_string="test", version=(0, 0, 0))
    mathutils_stub = types.ModuleType("mathutils")
    mathutils_stub.Matrix = type("Matrix", (), {})
    mathutils_stub.Quaternion = type("Quaternion", (), {})
    mathutils_stub.Vector = type("Vector", (), {})
    blender_dmx_stub = types.ModuleType("blender_dmx")
    for name in (
        "armature_rest_signature",
        "convert_to_binary",
        "convert_to_kv2",
        "parse_array_lengths",
        "patch_template",
        "pose_error",
        "pose_for_action",
    ):
        setattr(blender_dmx_stub, name, lambda *args, **kwargs: None)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    injected = {
        "bpy": bpy_stub,
        "mathutils": mathutils_stub,
        module_name: module,
    }
    if filename == "blender_export_dmx.py":
        injected["blender_dmx"] = blender_dmx_stub
    with mock.patch.dict(sys.modules, injected):
        spec.loader.exec_module(module)
    return module


class ManifestTests(unittest.TestCase):
    def test_example_manifest_is_valid_and_covers_both_views(self) -> None:
        _, manifest = load_manifest(EXAMPLE)
        self.assertEqual(
            [entry["id"] for entry in manifest["sets"]],
            ["viewmodel", "worldmodel"],
        )
        self.assertEqual(manifest["sets"][0]["translation_mode"], "absolute")
        self.assertEqual(
            manifest["sets"][1]["translation_mode"], "bind-pose-delta"
        )
        self.assertEqual(len(manifest["stock_dependencies"]), 3)
        self.assertEqual(manifest["stage_sources"], [])

    def test_path_traversal_is_rejected(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][0]["actions"][0]["output_dmx"] = "../escape.dmx"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_invalid_translation_mode_is_rejected(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][1]["translation_mode"] = "guess"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_reference_output_mapping(self) -> None:
        resource = "animation/anims/viewmodel/example/idle.vnmclip_c"
        self.assertEqual(
            reference_dmx_relative(resource),
            "animation/anims/viewmodel/example/idle.dmx",
        )
        self.assertEqual(
            reference_vnmclip_relative(resource),
            "animation/anims/viewmodel/example/idle.vnmclip",
        )

    def test_validation_returns_a_canonical_copy(self) -> None:
        original = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        candidate = copy.deepcopy(original)
        candidate["project"]["namespaces"][0] = (
            " models\\animgraph2\\example\\w\\example_item "
        )
        candidate["sets"][0]["actions"][0]["output_dmx"] = (
            "models\\animgraph2\\example\\w\\example_item\\source\\viewmodel\\draw_example_item.dmx"
        )
        validated = validate_manifest(candidate)
        self.assertEqual(
            validated["sets"][0]["actions"][0]["output_dmx"],
            "models/animgraph2/example/w/example_item/source/viewmodel/draw_example_item.dmx",
        )
        self.assertIn("\\", candidate["sets"][0]["actions"][0]["output_dmx"])

    def test_nonfinite_numbers_and_unordered_preroll_are_rejected(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            manifest["sets"][0]["fps"] = value
            with self.subTest(value=value), self.assertRaises(ManifestError):
                validate_manifest(manifest)
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][0]["preroll_seconds"] = [-0.05, -0.1]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_one_frame_action_and_dmx_timing_are_supported(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][0]["actions"][0]["minimum_frames"] = 1
        validated = validate_manifest(manifest)
        self.assertEqual(validated["sets"][0]["actions"][0]["minimum_frames"], 1)
        self.assertEqual(dmx_timeframe(30, 1), (0.0, 30.0))
        self.assertEqual(dmx_timeframe(30, 31), (1.0, 30.0))
        for fps, frames in ((0, 1), (float("nan"), 1), (30, 0)):
            with self.subTest(fps=fps, frames=frames), self.assertRaises(ManifestError):
                dmx_timeframe(fps, frames)

    def test_bone_signature_covers_parent_and_rest_matrix(self) -> None:
        identity = [
            [1, 0, 0, 0],
            [0, 1, 0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ]
        base = canonical_bone_signature(
            [("root", None, identity), ("hand", "root", identity)]
        )
        moved = copy.deepcopy(identity)
        moved[0][3] = 0.25
        self.assertNotEqual(
            base,
            canonical_bone_signature(
                [("root", None, identity), ("hand", "root", moved)]
            ),
        )
        with self.assertRaises(ManifestError):
            canonical_bone_signature(
                [("root", "hand", identity), ("hand", "root", identity)]
            )

    def test_windows_ambiguous_paths_are_rejected(self) -> None:
        invalid = (
            "models//owner/item.vmdl",
            "models/./owner/item.vmdl",
            "models/owner/con.txt",
            "models/owner/item:stream.vmdl",
            "models/owner/item?.vmdl",
            "models/owner/item./file.vmdl",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ManifestError):
                normalize_resource_path(value, field="test")

    def test_invalid_explicit_tool_and_cs2_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            fallback = root / "fallback.exe"
            fallback.write_bytes(b"fallback")
            with self.assertRaises(ManifestError):
                resolve_tool(
                    str(root / "missing.exe"), (), fallback, "test tool"
                )

            valid_cs2 = root / "valid-cs2"
            gameinfo = valid_cs2 / "game" / "csgo" / "gameinfo.gi"
            gameinfo.parent.mkdir(parents=True)
            gameinfo.write_text("gameinfo", encoding="utf-8")
            with mock.patch.dict("os.environ", {"CS2_ROOT": str(valid_cs2)}):
                with self.assertRaises(ManifestError):
                    resolve_cs2_root(str(root / "invalid-cs2"))

    def test_private_namespace_and_casefold_collisions_are_enforced(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["project"]["namespaces"] = ["animation/graphs/viewmodel"]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][0]["actions"][0]["output_dmx"] = "outside/item.dmx"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        first = manifest["sets"][0]["actions"][0]["output_dmx"]
        manifest["sets"][0]["actions"][1]["output_dmx"] = (
            first.replace("/example/", "/EXAMPLE/")
        )
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_blender_names_are_unique_across_sets(self) -> None:
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][1]["armature"] = manifest["sets"][0]["armature"].lower()
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)
        manifest = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        manifest["sets"][1]["actions"][0]["blender_action"] = (
            manifest["sets"][0]["actions"][0]["blender_action"].lower()
        )
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)


class BlenderSafetyTests(unittest.TestCase):
    def test_scene_clear_requires_a_real_blender_startup_flag(self) -> None:
        path = SCRIPTS / "blender_create_scene.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "blender_factory_startup_requested"
        )
        namespace: dict[str, object] = {}
        ast.fix_missing_locations(function)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
        requested = namespace["blender_factory_startup_requested"]
        self.assertTrue(requested(["blender", "--factory-startup", "--", "script.py"]))
        self.assertFalse(requested(["blender", "--", "--factory-startup"]))
        self.assertFalse(requested(["blender", "--background", "--", "script.py"]))
        self.assertNotIn("is_pristine_factory_scene", source)
        self.assertNotIn("default_objects", source)
        self.assertNotIn("len(bpy.data.objects)", source)
        self.assertIn("args.allow_clear_scene", source)
        self.assertIn('getattr(bpy.data, "filepath"', source)
        self.assertIn('getattr(bpy.data, "is_dirty"', source)
        self.assertIn("verify_reference_cache", source)
        self.assertIn("--allow-unverified-reference-cache", source)
        self.assertIn("cs2_reference_cache_receipt", source)

    def test_dmx_parser_rejects_missing_joint_transform(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        missing = '''
"DmeJoint"
{
    "id" "elementid" "joint-1"
    "name" "string" "root"
    "children" "element_array" [ ]
}
'''
        with self.assertRaisesRegex(ValueError, "no complete transform"):
            module.parse_dmx_skeleton(missing)

        dangling = '''
"DmeJoint"
{
    "id" "elementid" "joint-1"
    "name" "string" "root"
    "transform" "element" "missing-transform"
    "children" "element_array" [ ]
}
'''
        with self.assertRaisesRegex(ValueError, "missing DmeTransform"):
            module.parse_dmx_skeleton(dangling)

    def test_dmx_parser_rejects_duplicate_channel_names(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        channel = '''
"DmeChannel"
{
    "name" "string" "root_p"
    "times" "time_array" [ "0" ]
    "values" "vector3_array" [ "0 0 0" ]
}
'''
        duplicate = channel + channel
        with self.assertRaisesRegex(ValueError, "duplicate DmeChannel name"):
            module.parse_channels(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate DmeChannel name"):
            module.channel_names(duplicate)

    def test_dmx_channel_lookup_accepts_canonical_whitespace_variants(self) -> None:
        module = load_blender_only_module("blender_dmx.py")
        lines = [
            '"DmeChannel"\n',
            '{\n',
            '\t"name"\t"string"    "root_p"\n',
            '\t"times" "time_array" [ "0" ]\n',
            '\t"values" "vector3_array" [ "0 0 0" ]\n',
            '}\n',
        ]
        self.assertEqual(module.find_channel_block(lines, "root_p"), (0, 6))

    def test_export_refuses_unverifiable_or_dirty_blend_by_default(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        args = types.SimpleNamespace(
            allow_unsaved_blend=False,
            allow_dirty_blend=False,
        )
        with self.assertRaisesRegex(ManifestError, "no verifiable saved filepath"):
            module.validate_blend_provenance(args)

        with tempfile.TemporaryDirectory() as temp_name:
            blend = Path(temp_name) / "authoring.blend"
            blend.write_bytes(b"saved blend")
            module.bpy.data.filepath = str(blend)
            module.bpy.data.is_dirty = True
            with self.assertRaisesRegex(ManifestError, "unsaved changes"):
                module.validate_blend_provenance(args)
            args.allow_dirty_blend = True
            receipt = module.validate_blend_provenance(args)
            self.assertEqual(receipt["filepath"], str(blend.resolve()))
            self.assertEqual(receipt["sha256"], module.sha256_file(blend))
            self.assertTrue(receipt["dirty"])

    def test_validated_output_commit_is_atomic_and_fail_closed(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            before = module.file_state(destination)
            validated_hash = module.sha256_file(source)
            receipt = module.commit_validated_outputs(
                [
                    {
                        "source": source,
                        "destination": destination,
                        "before": before,
                        "validated_sha256": validated_hash,
                    }
                ]
            )
            self.assertEqual(destination.read_bytes(), b"new validated output")
            self.assertEqual(
                receipt[0]["replacement"],
                "atomic-preimage-claim+no-replace-publication",
            )
            self.assertIn(
                receipt[0]["publication_method"],
                {"hard-link", "windows-no-replace-rename"},
            )
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

            source.write_bytes(b"another output")
            unchanged = destination.read_bytes()
            with self.assertRaisesRegex(ManifestError, "changed before commit"):
                module.commit_validated_outputs(
                    [
                        {
                            "source": source,
                            "destination": destination,
                            "before": module.file_state(destination),
                            "validated_sha256": "0" * 64,
                        }
                    ]
                )
            self.assertEqual(destination.read_bytes(), unchanged)

    def test_validated_output_commit_rolls_back_baseexception_after_replace(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            pending = [
                {
                    "source": source,
                    "destination": destination,
                    "before": module.file_state(destination),
                    "validated_sha256": module.sha256_file(source),
                }
            ]
            original_replace = module.os.replace
            invocation = 0

            def interrupted_replace(source_path, destination_path):
                nonlocal invocation
                invocation += 1
                result = original_replace(source_path, destination_path)
                if invocation == 1:
                    raise KeyboardInterrupt("simulated interrupt after replacement")
                return result

            with mock.patch.object(
                module.os, "replace", side_effect=interrupted_replace
            ), self.assertRaisesRegex(KeyboardInterrupt, "after replacement"):
                module.commit_validated_outputs(pending)

            self.assertEqual(destination.read_bytes(), b"old output")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

    def test_multi_output_commit_rolls_back_after_later_replace_failure(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pending = []
            destinations = []
            for index in range(2):
                source = root / f"validated-{index}.dmx"
                destination = root / f"final-{index}.dmx"
                source.write_bytes(f"new-{index}".encode())
                destination.write_bytes(f"old-{index}".encode())
                destinations.append(destination)
                pending.append(
                    {
                        "source": source,
                        "destination": destination,
                        "before": module.file_state(destination),
                        "validated_sha256": module.sha256_file(source),
                    }
                )
            original_replace = module.os.replace
            invocation = 0

            def fail_second_replace(source_path, destination_path):
                nonlocal invocation
                invocation += 1
                if invocation == 2:
                    raise OSError("simulated second replacement failure")
                return original_replace(source_path, destination_path)

            with mock.patch.object(
                module.os, "replace", side_effect=fail_second_replace
            ), self.assertRaisesRegex(OSError, "second replacement failure"):
                module.commit_validated_outputs(pending)

            self.assertEqual(destinations[0].read_bytes(), b"old-0")
            self.assertEqual(destinations[1].read_bytes(), b"old-1")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

    def test_rollback_refuses_to_overwrite_a_concurrent_writer(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pending = []
            destinations = []
            for index in range(2):
                source = root / f"validated-{index}.dmx"
                destination = root / f"final-{index}.dmx"
                source.write_bytes(f"new-{index}".encode())
                destination.write_bytes(f"old-{index}".encode())
                destinations.append(destination)
                pending.append(
                    {
                        "source": source,
                        "destination": destination,
                        "before": module.file_state(destination),
                        "validated_sha256": module.sha256_file(source),
                    }
                )
            original_publish = module._publish_file_no_replace
            invocation = 0

            def writer_wins_publication(source_path, destination_path, errors):
                nonlocal invocation
                invocation += 1
                if invocation == 1:
                    Path(destination_path).write_bytes(b"foreign-writer")
                return original_publish(source_path, destination_path, errors)

            with mock.patch.object(
                module,
                "_publish_file_no_replace",
                side_effect=writer_wins_publication,
            ), self.assertRaisesRegex(
                module.DmxRollbackFailure, "ownership changed before rollback"
            ):
                module.commit_validated_outputs(pending)

            self.assertEqual(destinations[0].read_bytes(), b"foreign-writer")
            self.assertEqual(destinations[1].read_bytes(), b"old-1")
            backups = list(root.glob(".*.rollback"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertIn(b"old-0", {path.read_bytes() for path in backups})

    def test_rollback_quarantines_writer_winning_after_ownership_check(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            pending = []
            destinations = []
            for index in range(2):
                source = root / f"validated-{index}.dmx"
                destination = root / f"final-{index}.dmx"
                source.write_bytes(f"new-{index}".encode())
                destination.write_bytes(f"old-{index}".encode())
                destinations.append(destination)
                pending.append(
                    {
                        "source": source,
                        "destination": destination,
                        "before": module.file_state(destination),
                        "validated_sha256": module.sha256_file(source),
                    }
                )
            original_replace = module.os.replace
            invocation = 0

            def writer_in_check_act_window(source_path, destination_path):
                nonlocal invocation
                invocation += 1
                if invocation == 2:
                    raise OSError("simulated later replacement failure")
                if invocation == 3:
                    # The rollback ownership hash was already checked. Replace
                    # those bytes just before the quarantine rename executes.
                    destinations[0].write_bytes(b"foreign-after-check")
                return original_replace(source_path, destination_path)

            with mock.patch.object(
                module.os, "replace", side_effect=writer_in_check_act_window
            ), self.assertRaisesRegex(RuntimeError, "foreign content restored"):
                module.commit_validated_outputs(pending)

            self.assertEqual(destinations[0].read_bytes(), b"foreign-after-check")
            self.assertEqual(destinations[1].read_bytes(), b"old-1")
            backups = list(root.glob(".*.rollback"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertIn(b"old-0", {path.read_bytes() for path in backups})

    def test_rollback_revalidates_backup_after_quarantining_destination(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            pending = [
                {
                    "source": source,
                    "destination": destination,
                    "before": module.file_state(destination),
                    "validated_sha256": module.sha256_file(source),
                }
            ]
            original_replace = module.os.replace
            replace_invocation = 0
            original_publish = module._publish_file_no_replace
            publish_invocation = 0

            def tamper_backup_during_quarantine(source_path, destination_path):
                nonlocal replace_invocation
                replace_invocation += 1
                result = original_replace(source_path, destination_path)
                if replace_invocation == 2:
                    backups = list(root.glob(".final.dmx.*.rollback"))
                    self.assertEqual(len(backups), 1)
                    backups[0].write_bytes(b"tampered-backup")
                return result

            def fail_after_output_publication(source_path, destination_path, errors):
                nonlocal publish_invocation
                publish_invocation += 1
                result = original_publish(source_path, destination_path, errors)
                if publish_invocation == 1:
                    raise OSError("simulated error after output publication")
                return result

            with mock.patch.object(
                module.os,
                "replace",
                side_effect=tamper_backup_during_quarantine,
            ), mock.patch.object(
                module,
                "_publish_file_no_replace",
                side_effect=fail_after_output_publication,
            ), self.assertRaisesRegex(
                module.DmxRollbackFailure, "backup changed before restoration"
            ):
                module.commit_validated_outputs(pending)

            self.assertEqual(destination.read_bytes(), b"new validated output")
            self.assertEqual(source.read_bytes(), b"new validated output")
            backups = list(root.glob(".final.dmx.*.rollback"))
            quarantines = list(root.glob(".final.dmx.*.rollback-current"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"tampered-backup")
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), b"new validated output")
            self.assertFalse(list(root.glob(".final.dmx.*.pending")))

    def test_rollback_preserves_unique_backup_when_publication_is_tampered(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            pending = [
                {
                    "source": source,
                    "destination": destination,
                    "before": module.file_state(destination),
                    "validated_sha256": module.sha256_file(source),
                }
            ]
            original_publish = module._publish_file_no_replace
            original_link = module.os.link
            publish_invocation = 0

            def fail_after_commit(source_path, destination_path, errors):
                nonlocal publish_invocation
                publish_invocation += 1
                result = original_publish(source_path, destination_path, errors)
                if publish_invocation == 1:
                    raise OSError("simulated error after output publication")
                return result

            def mutate_recovery_copy(source_path, destination_path):
                result = original_link(source_path, destination_path)
                if str(source_path).endswith(".restore-copy"):
                    Path(destination_path).write_bytes(b"tampered-during-publication")
                return result

            with mock.patch.object(
                module,
                "_publish_file_no_replace",
                side_effect=fail_after_commit,
            ), mock.patch.object(
                module.os, "link", side_effect=mutate_recovery_copy
            ), self.assertRaisesRegex(
                module.DmxRollbackFailure, "post-publication validation"
            ):
                module.commit_validated_outputs(pending)

            self.assertEqual(destination.read_bytes(), b"tampered-during-publication")
            backups = list(root.glob(".final.dmx.*.rollback"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"old output")
            quarantines = list(root.glob(".final.dmx.*.rollback-current"))
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), b"new validated output")
            self.assertFalse(list(root.glob(".final.dmx.*.pending")))

    def test_transaction_failure_status_uses_exception_type_not_message(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        misleading = RuntimeError(
            "ordinary failure in a path containing: rollback also failed"
        )
        self.assertEqual(module.transaction_failure_status(misleading), "failed")
        structured = module.DmxRollbackFailure("structured rollback failure")
        self.assertEqual(
            module.transaction_failure_status(structured), "rollback-failed"
        )

    def test_commit_error_message_cannot_spoof_rollback_failure(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            pending = [
                {
                    "source": source,
                    "destination": destination,
                    "before": module.file_state(destination),
                    "validated_sha256": module.sha256_file(source),
                }
            ]
            original_replace = module.os.replace
            sentinel = OSError("literal text: rollback also failed")
            invocation = 0

            def misleading_commit_failure(source_path, destination_path):
                nonlocal invocation
                invocation += 1
                result = original_replace(source_path, destination_path)
                if invocation == 1:
                    raise sentinel
                return result

            with mock.patch.object(
                module.os, "replace", side_effect=misleading_commit_failure
            ), self.assertRaises(OSError) as caught:
                module.commit_validated_outputs(pending)

            self.assertIs(caught.exception, sentinel)
            self.assertEqual(
                module.transaction_failure_status(caught.exception), "failed"
            )
            self.assertEqual(destination.read_bytes(), b"old output")
            self.assertFalse(list(root.glob(".final.dmx.*.pending")))
            self.assertFalse(list(root.glob(".final.dmx.*.rollback")))
            self.assertFalse(list(root.glob(".final.dmx.*.rollback-current")))

    def test_export_transaction_scan_fails_closed_on_unknown_or_partial_state(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            report_root = Path(temp_name)
            output = {
                "destination": str(report_root / "output.dmx"),
                "before": {"exists": False},
                "validated_sha256": "a" * 64,
            }
            statuses = (
                "prepared",
                "committed",
                "rollback-failed",
                "failed",
                "reported",
                "future-status",
            )
            for index, status in enumerate(statuses):
                run_id = str(index)
                journal = report_root / f"dmx-export-transaction-{run_id}.json"
                transaction = {
                    "schema_version": 1,
                    "run_id": run_id,
                    "status": status,
                    "manifest": "project.json",
                    "manifest_sha256": "b" * 64,
                    "outputs": [output],
                }
                if status in {"committed", "reported"}:
                    transaction["commits"] = [
                        {
                            "output": output["destination"],
                            "sha256": output["validated_sha256"],
                            "replacement": "no-replace",
                        }
                    ]
                if status in {"failed", "rollback-failed"}:
                    transaction["error"] = {
                        "type": "RuntimeError",
                        "message": "test",
                    }
                if status == "reported":
                    report_path = report_root / f"dmx-export-report-{run_id}.json"
                    report = {
                        "schema_version": 2,
                        "status": "ok",
                        "run_id": run_id,
                        "manifest": transaction["manifest"],
                        "manifest_sha256": transaction["manifest_sha256"],
                        "transaction_journal": str(journal),
                    }
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                    transaction["report"] = str(report_path)
                    transaction["report_sha256"] = module.sha256_file(report_path)
                journal.write_text(json.dumps(transaction), encoding="utf-8")
            (report_root / "dmx-export-transaction-invalid.json").write_text(
                "not json", encoding="utf-8"
            )
            (report_root / "dmx-export-transaction-incomplete.json").write_text(
                json.dumps({"status": "failed"}), encoding="utf-8"
            )

            unresolved = {
                item["status"]
                for item in module.unresolved_export_transactions(report_root)
            }
            self.assertEqual(
                unresolved,
                {
                    "prepared",
                    "committed",
                    "rollback-failed",
                    "future-status",
                    "invalid",
                },
            )

    def test_validated_output_commit_preserves_backup_when_rollback_fails(self) -> None:
        module = load_blender_only_module("blender_export_dmx.py")
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "validated.dmx"
            destination = root / "final.dmx"
            source.write_bytes(b"new validated output")
            destination.write_bytes(b"old output")
            pending = [
                {
                    "source": source,
                    "destination": destination,
                    "before": module.file_state(destination),
                    "validated_sha256": module.sha256_file(source),
                }
            ]
            original_replace = module.os.replace
            original_publish = module._publish_file_no_replace
            invocation = 0

            def failed_commit_and_rollback(source_path, destination_path, errors):
                nonlocal invocation
                invocation += 1
                if invocation == 1:
                    result = original_publish(source_path, destination_path, errors)
                    raise OSError("simulated error after output publication")
                raise OSError("simulated rollback failure")

            with mock.patch.object(
                module,
                "_publish_file_no_replace",
                side_effect=failed_commit_and_rollback,
            ), self.assertRaisesRegex(RuntimeError, "recovery files preserved"):
                module.commit_validated_outputs(pending)

            self.assertFalse(destination.exists())
            backups = list(root.glob(".*.rollback"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"old output")
            quarantines = list(root.glob(".*.rollback-current"))
            self.assertEqual(len(quarantines), 1)
            self.assertEqual(quarantines[0].read_bytes(), b"new validated output")

    def test_export_validates_temporary_binary_before_final_commit(self) -> None:
        path = SCRIPTS / "blender_export_dmx.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("verify_reference_cache", source)
        self.assertIn("--allow-unverified-reference-cache", source)
        tree = ast.parse(source, filename=str(path))
        binary_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "convert_to_binary"
        ]
        self.assertEqual(len(binary_calls), 1)
        self.assertIsInstance(binary_calls[0].args[2], ast.Name)
        self.assertEqual(binary_calls[0].args[2].id, "generated_binary")
        continuity_lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "validate_continuity"
        ]
        commit_lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "commit_validated_outputs"
        ]
        self.assertEqual(len(commit_lines), 1)
        self.assertGreater(commit_lines[0], max(continuity_lines))
        receipt_probe_lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "probe_versioned_receipt_create"
        ]
        self.assertEqual(len(receipt_probe_lines), 1)
        self.assertLess(receipt_probe_lines[0], commit_lines[0])
        constants = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for required in (
            "version_string",
            "blend_receipt",
            "dirty",
            "allow_manifest_drift",
            "allow_reference_drift",
            "allow_unverified_reference_cache",
            "expected_sha256",
            "current_sha256",
            "reference_receipt",
        ):
            self.assertIn(required, constants)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        _, self.example = load_manifest(EXAMPLE)

    def test_extraction_plan_includes_clips_and_stock_dependencies(self) -> None:
        jobs = extraction_jobs(self.example, self.example["sets"])
        self.assertEqual(len(jobs), 9)
        self.assertEqual(
            {job["kind"] for job in jobs},
            {"vnmclip-reference", "stock-dependency"},
        )

    def test_compile_plan_defaults_to_generated_vnmclips(self) -> None:
        self.assertEqual(len(compile_resources(self.example)), 6)
        self.assertEqual(len(generated_sources(self.example)), 12)
        self.assertEqual(len(stage_sources(self.example)), 12)

    def test_extraction_plan_merges_a_resource_collision(self) -> None:
        resource = self.example["sets"][0]["actions"][0]["reference_resource"]
        data = copy.deepcopy(self.example)
        data["stock_dependencies"].append(
            {
                "resource": resource,
                "outputs": ["extra/local-output.txt"],
                "compile": "extra/local-output.txt",
                "package": False,
            }
        )
        jobs = extraction_jobs(data, [data["sets"][0]])
        matching = [job for job in jobs if job["resource"] == resource]
        self.assertEqual(len(matching), 1)
        self.assertEqual(
            matching[0]["kinds"], ["vnmclip-reference", "stock-dependency"]
        )
        self.assertIn("extra/local-output.txt", matching[0]["outputs"])

    def test_vpk_receipt_must_match_exactly_once(self) -> None:
        resource = "animation/test.vnmclip_c"
        self.assertEqual(
            exact_vpk_receipt(f"{resource} CRC: 1234\n", resource),
            f"{resource} CRC: 1234",
        )
        with self.assertRaises(RuntimeError):
            exact_vpk_receipt("animation/other.vnmclip_c CRC: 1234\n", resource)
        with self.assertRaises(RuntimeError):
            exact_vpk_receipt(
                f"{resource} CRC: 1\n{resource} CRC: 2\n", resource
            )

    def test_cache_is_bound_to_tools_receipt_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            relative = "animation/test.dmx"
            output = root / "animation" / "test.dmx"
            output.parent.mkdir(parents=True)
            output.write_bytes(b"current")
            report = {
                "vpk_sha256": "vpk",
                "vrf_cli_sha256": "vrf",
                "resources": [
                    {
                        "resource": "animation/test.vnmclip_c",
                        "vpk_receipt": "animation/test.vnmclip_c CRC: 1",
                        "outputs": [
                            {
                                "resource": relative,
                                "sha256": compiler_tool.sha256_file(output),
                            }
                        ],
                    }
                ],
            }
            kwargs = {
                "previous": report,
                "vpk_sha256": "vpk",
                "vrf_sha256": "vrf",
                "resource": "animation/test.vnmclip_c",
                "receipt": "animation/test.vnmclip_c CRC: 1",
                "output_root": root,
                "outputs": [relative],
            }
            self.assertTrue(cache_entry_is_current(**kwargs))
            for key, stale in (
                ("vpk_sha256", "new-vpk"),
                ("vrf_sha256", "new-vrf"),
                ("receipt", "animation/test.vnmclip_c CRC: 2"),
            ):
                changed = dict(kwargs)
                changed[key] = stale
                self.assertFalse(cache_entry_is_current(**changed))
            output.write_bytes(b"changed")
            self.assertFalse(cache_entry_is_current(**kwargs))

    def test_hash_aware_copy_refuses_silent_overwrite_and_preserves_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source.txt"
            destination = root / "destination.txt"
            backup = root / "backups"
            source.write_text("new", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")
            with self.assertRaises(ManifestError):
                copy_with_policy(
                    source,
                    destination,
                    allowed_root=root,
                    force_overwrite=False,
                    backup_root=backup,
                    dry_run=False,
                    label="test",
                )
            receipt = copy_with_policy(
                source,
                destination,
                allowed_root=root,
                force_overwrite=True,
                backup_root=backup,
                dry_run=False,
                label="test",
            )
            self.assertEqual(receipt["action"], "overwritten")
            self.assertEqual(destination.read_text(encoding="utf-8"), "new")
            self.assertEqual(Path(receipt["backup"]).read_text(encoding="utf-8"), "old")

    def test_same_file_staging_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "same.txt"
            path.write_text("same", encoding="utf-8")
            receipt = copy_with_policy(
                path,
                path,
                allowed_root=Path(temp_name),
                force_overwrite=False,
                backup_root=Path(temp_name) / "backup",
                dry_run=False,
                label="same",
            )
            self.assertEqual(receipt["action"], "same-file")

    def test_artifact_root_rejects_stale_extras(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            expected = root / "models" / "owner" / "item.vnmclip_c"
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"expected")
            reject_artifact_extras(root, ["models/owner/item.vnmclip_c"])
            stale = root / "models" / "owner" / "renamed-old.vnmclip_c"
            stale.write_bytes(b"stale")
            with self.assertRaises(ManifestError):
                reject_artifact_extras(root, ["models/owner/item.vnmclip_c"])

    def test_artifact_preflight_refuses_all_conflicts_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            sources = root / "sources"
            artifacts = root / "artifacts"
            first_source = sources / "first"
            second_source = sources / "second"
            first_source.parent.mkdir(parents=True)
            first_source.write_bytes(b"first-new")
            second_source.write_bytes(b"second-new")
            second_destination = artifacts / "models" / "owner" / "second_c"
            second_destination.parent.mkdir(parents=True)
            second_destination.write_bytes(b"second-old")
            planned = [
                (first_source, "models/owner/first_c"),
                (second_source, "models/owner/second_c"),
            ]

            with self.assertRaises(ManifestError):
                preflight_artifact_copies(
                    artifacts, planned, force_overwrite=False
                )

            self.assertFalse((artifacts / "models" / "owner" / "first_c").exists())
            self.assertEqual(second_destination.read_bytes(), b"second-old")

    def test_temporary_dependency_cleanup_restores_exact_preimages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source"
            destination = root / "destination"
            backup_root = root / "backup"
            source.write_text("temporary", encoding="utf-8")
            destination.write_text("original", encoding="utf-8")
            receipt = copy_with_policy(
                source,
                destination,
                allowed_root=root,
                force_overwrite=True,
                backup_root=backup_root,
                dry_run=False,
                label="dependency",
            )
            restore_temporary_stage(receipt)
            self.assertEqual(destination.read_text(encoding="utf-8"), "original")

            compiled = root / "compiled_c"
            compiled.write_text("original-output", encoding="utf-8")
            output_before = compiler_tool.file_state(compiled)
            output_backup = root / "output-backup"
            shutil.copy2(compiled, output_backup)
            compiled.write_text("temporary-output", encoding="utf-8")
            compiled_state = compiler_tool.file_state(compiled)
            restore_nonpackage_output(
                {
                    "output": str(compiled),
                    "before": output_before,
                    "backup": str(output_backup),
                    "compiled_state": compiled_state,
                }
            )
            self.assertEqual(compiled.read_text(encoding="utf-8"), "original-output")

    def test_compile_main_cleans_nonpackage_dependencies_and_artifacts_only_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            addon = self.example["project"]["addon"]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            manifest_path = content_root / "project.json"
            manifest_path.parent.mkdir(parents=True)
            compile_fixture = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            compile_fixture["project"]["artifact_policy"] = {
                "status": "allowed",
                "basis": "unit-test fixture with synthetic outputs only",
                "template_derivative_basis": (
                    "unit-test VNMClip templates are synthetic and test-owned"
                ),
            }
            manifest_path.write_text(
                json.dumps(compile_fixture, indent=2) + "\n", encoding="utf-8"
            )
            _, manifest = load_manifest(manifest_path)
            for resource in compile_resources(manifest):
                source = compiler_tool.native_path(content_root, resource)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(resource, encoding="utf-8")
            reference_root = root / "references"
            for dependency in manifest["stock_dependencies"]:
                for resource in dependency["outputs"]:
                    source = compiler_tool.native_path(reference_root, resource)
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text(resource, encoding="utf-8")
            artifact_root = root / "artifacts"
            invocation = 0

            def fake_run(command: list[str], *, timeout_seconds: int = 600):
                nonlocal invocation
                invocation += 1
                source = Path(command[command.index("-i") + 1])
                relative = source.relative_to(content_root)
                output = compiler_tool.resource_output_path(
                    cs2_root, addon, relative.as_posix()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(f"compiled-{invocation}-{relative}", encoding="utf-8")
                return "ok", ""

            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--cs2-root",
                str(cs2_root),
                "--resourcecompiler",
                str(compiler),
                "--reference-root",
                str(reference_root),
                "--allow-unverified-reference-cache",
                "--artifact-root",
                str(artifact_root),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool, "run", side_effect=fake_run
            ):
                self.assertEqual(compiler_tool.main(), 0)

            for dependency in manifest["stock_dependencies"]:
                for resource in dependency["outputs"]:
                    self.assertFalse(
                        compiler_tool.native_path(content_root, resource).exists()
                    )
                compiled = compiler_tool.resource_output_path(
                    cs2_root, addon, dependency["compile"]
                )
                self.assertFalse(compiled.exists())
            artifact_files = [path for path in artifact_root.rglob("*") if path.is_file()]
            self.assertEqual(len(artifact_files), len(compile_resources(manifest)))
            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["schema_version"], 2)
            self.assertTrue(report["allow_unverified_reference_cache"])
            self.assertEqual(report["reference_cache"]["status"], "unverified-allowed")
            self.assertTrue(report["cleanup"])
            self.assertTrue(all(row["package"] for row in report["compiled"][3:]))
            immutable = list(
                (content_root / ".local" / "reports").glob("compile-report-*.json")
            )
            self.assertEqual(len(immutable), 1)
            transactions = list(
                (content_root / ".local" / "reports").glob(
                    "compile-transaction-*.json"
                )
            )
            self.assertEqual(len(transactions), 1)
            success_transaction = json.loads(
                transactions[0].read_text(encoding="utf-8")
            )
            self.assertEqual(success_transaction["status"], "reported")
            self.assertEqual(
                Path(success_transaction["report"]).resolve(),
                immutable[0].resolve(),
            )
            self.assertEqual(
                success_transaction["report_sha256"],
                compiler_tool.sha256_file(immutable[0]),
            )
            self.assertTrue(report["artifact_closure"]["verified"])
            self.assertFalse(report["installed_addon_closure_verified"])

            invocation = 0

            def failing_run(command: list[str], *, timeout_seconds: int = 600):
                nonlocal invocation
                invocation += 1
                source = Path(command[command.index("-i") + 1])
                relative = source.relative_to(content_root)
                output = compiler_tool.resource_output_path(
                    cs2_root, addon, relative.as_posix()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(f"partial-{invocation}", encoding="utf-8")
                if invocation == 2:
                    raise RuntimeError("simulated compiler failure")
                return "ok", ""

            failure_argv = argv[:-2]
            with mock.patch.object(sys, "argv", failure_argv), mock.patch.object(
                compiler_tool, "run", side_effect=failing_run
            ), self.assertRaises(RuntimeError):
                compiler_tool.main()
            transaction_statuses = {
                json.loads(path.read_text(encoding="utf-8"))["status"]
                for path in (content_root / ".local" / "reports").glob(
                    "compile-transaction-*.json"
                )
            }
            self.assertEqual(transaction_statuses, {"reported", "failed"})
            for dependency in manifest["stock_dependencies"]:
                for resource in dependency["outputs"]:
                    self.assertFalse(
                        compiler_tool.native_path(content_root, resource).exists()
                    )
                self.assertFalse(
                    compiler_tool.resource_output_path(
                        cs2_root, addon, dependency["compile"]
                    ).exists()
                )

            def successful_run(command: list[str], *, timeout_seconds: int = 600):
                source = Path(command[command.index("-i") + 1])
                relative = source.relative_to(content_root)
                output = compiler_tool.resource_output_path(
                    cs2_root, addon, relative.as_posix()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(f"reported-failure-{relative}", encoding="utf-8")
                return "ok", ""

            with mock.patch.object(sys, "argv", failure_argv), mock.patch.object(
                compiler_tool, "run", side_effect=successful_run
            ), mock.patch.object(
                compiler_tool,
                "write_compile_report",
                side_effect=RuntimeError("simulated compile report failure"),
            ), self.assertRaisesRegex(RuntimeError, "compile report failure"):
                compiler_tool.main()

            unresolved = compiler_tool.unresolved_compile_transactions(
                content_root / ".local" / "reports"
            )
            self.assertEqual(
                [row["status"] for row in unresolved],
                ["committed"],
            )
            with mock.patch.object(sys, "argv", failure_argv), mock.patch.object(
                compiler_tool, "run"
            ) as blocked_run, self.assertRaisesRegex(
                ManifestError, "unresolved prior compile transaction"
            ):
                compiler_tool.main()
            blocked_run.assert_not_called()

            scanner_root = root / "compile-transaction-scanner"
            scanner_root.mkdir()
            base_transaction = {
                "schema_version": 1,
                "manifest": str(manifest_path),
                "manifest_sha256": compiler_tool.sha256_file(manifest_path),
                "project_root": str(content_root),
                "installed_content_root": str(content_root),
                "resources": [],
                "managed_stage_resources": [],
            }

            def write_scanner_transaction(run_id: str, status: str) -> None:
                payload = dict(base_transaction, run_id=run_id, status=status)
                if status == "failed":
                    payload["error"] = {"type": "RuntimeError", "message": "x"}
                elif status == "reported":
                    report_path = scanner_root / f"compile-report-{run_id}.json"
                    report_path.write_text("{}\n", encoding="utf-8")
                    payload["report"] = str(report_path)
                    payload["report_sha256"] = compiler_tool.sha256_file(report_path)
                (scanner_root / f"compile-transaction-{run_id}.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )

            write_scanner_transaction("terminal-failed", "failed")
            write_scanner_transaction("terminal-reported", "reported")
            blocking_statuses = {
                "prepared",
                "staged",
                "compiling",
                "compiled",
                "artifact-handoff",
                "committed",
                "stage-failed",
                "rollback-failed",
                "future-status",
            }
            for index, status in enumerate(sorted(blocking_statuses)):
                write_scanner_transaction(f"blocking-{index}", status)
            (scanner_root / "compile-transaction-malformed.json").write_text(
                "{not-json", encoding="utf-8"
            )
            (scanner_root / "compile-transaction-incomplete.json").write_text(
                json.dumps({"status": "reported"}), encoding="utf-8"
            )
            scanner_rows = compiler_tool.unresolved_compile_transactions(scanner_root)
            self.assertEqual(
                {row["status"] for row in scanner_rows},
                blocking_statuses | {"invalid", "reported"},
            )

    def test_tool_scripts_are_weapon_and_project_agnostic(self) -> None:
        forbidden = ("fiveseven", "minimal_l0", "example_addon")
        for script in SCRIPTS.glob("*.py"):
            source = script.read_text(encoding="utf-8")
            ast.parse(source, filename=str(script))
            lowered = source.lower()
            for marker in forbidden:
                self.assertNotIn(marker, lowered, f"{marker} leaked into {script.name}")

    def test_vnmclip_generation_preserves_template_and_rewrites_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            reference_root = root / "references"
            resource = "animation/anims/viewmodel/test/idle_stock.vnmclip_c"
            template = reference_root / reference_vnmclip_relative(resource)
            template.parent.mkdir(parents=True)
            template.write_text(
                "<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} "
                "format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->\n"
                "{\n"
                '\tm_sourceFilename = "old\\idle.dmx"\n'
                '\tm_animationSkeletonName = "old/skeleton.vnmskel"\n'
                "\tm_bonesToSampleInModelSpace = [  ]\n"
                "\tm_eventTracks = [ { m_name = \"remove-me\" } ]\n"
                "}\n",
                encoding="utf-8",
            )
            output_dmx = root / "source" / "idle_custom.dmx"
            output_dmx.parent.mkdir(parents=True)
            output_dmx.write_bytes(b"dmx")
            manifest_path = root / "project.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            animation_set = {
                "id": "viewmodel",
                "primary_skeleton": "animation/skeletons/characters/viewmodel.vnmskel",
                "secondary_skeletons": [
                    "animation/skeletons/weapons/example.vnmskel"
                ],
            }
            action = {
                "id": "idle",
                "reference_resource": resource,
                "output_dmx": "source/idle_custom.dmx",
                "output_vnmclip": "clips/idle_custom.vnmclip",
                "event_policy": "clear",
            }
            receipt = generate_one(
                manifest_path,
                reference_root,
                animation_set,
                action,
                allow_missing_dmx=False,
            )
            output = Path(receipt["output"]).read_text(encoding="utf-8")
            self.assertIn('m_sourceFilename = "source\\\\idle_custom.dmx"', output)
            self.assertIn(
                'm_animationSkeletonName = "animation/skeletons/characters/viewmodel.vnmskel"',
                output,
            )
            self.assertIn("animation/skeletons/weapons/example.vnmskel", output)
            self.assertIn("m_eventTracks = [  ]", output)
            self.assertNotIn("remove-me", output)


if __name__ == "__main__":
    unittest.main()
