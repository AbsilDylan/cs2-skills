from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compile_animgraph2 as compiler_tool  # noqa: E402
import generate_vnmclips as generator_tool  # noqa: E402
import animgraph2_manifest as manifest_tool  # noqa: E402
from animgraph2_manifest import (  # noqa: E402
    ManifestError,
    load_manifest,
    probe_versioned_receipt_create,
    reference_vnmclip_relative,
    sha256_file,
    write_json,
    write_json_new,
)
from extract_stock_references import (  # noqa: E402
    extraction_jobs,
    output_path,
    verify_reference_cache,
)


EXAMPLE = SKILL_ROOT / "examples" / "animgraph2-project.example.json"


def write_allowed_manifest(path: Path) -> tuple[Path, dict]:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["project"]["artifact_policy"] = {
        "status": "allowed",
        "basis": "synthetic test fixtures",
        "template_derivative_basis": "synthetic templates authored by this test",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return load_manifest(path)


def write_reference_cache(
    reference_root: Path, manifest_path: Path, manifest: dict
) -> dict:
    provenance_root = reference_root.parent / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    vpk = provenance_root / "pak01_dir.vpk"
    vrf = provenance_root / "Source2Viewer-CLI.exe"
    vpk.write_bytes(b"synthetic-vpk-index")
    vrf.write_bytes(b"synthetic-vrf")
    rows = []
    for job in extraction_jobs(manifest, manifest["sets"]):
        outputs = []
        for relative in job["outputs"]:
            path = output_path(reference_root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture:{relative}", encoding="utf-8")
            outputs.append(
                {
                    "resource": relative,
                    "path": str(path.resolve()),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
        rows.append(
            {
                "resource": job["resource"],
                "vpk_receipt": f"{job['resource']} CRC: DEADBEEF",
                "outputs": outputs,
            }
        )
    report = {
        "schema_version": 2,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "output_root": str(reference_root.resolve()),
        "vpk": str(vpk.resolve()),
        "vpk_sha256": sha256_file(vpk),
        "vrf_cli": str(vrf.resolve()),
        "vrf_cli_sha256": sha256_file(vrf),
        "resources": rows,
    }
    write_json(reference_root / "reference-extraction-report.json", report)
    return report


class ReferenceCacheTests(unittest.TestCase):
    def test_cache_receipt_verifies_manifest_tools_vpk_and_every_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path, manifest = write_allowed_manifest(root / "project.json")
            reference_root = root / "references"
            report = write_reference_cache(reference_root, manifest_path, manifest)
            required = [
                output["resource"]
                for row in report["resources"]
                for output in row["outputs"]
            ]
            receipt = verify_reference_cache(
                reference_root, manifest_path, required
            )
            self.assertTrue(receipt["verified"])
            self.assertEqual(receipt["status"], "verified")

            first = Path(report["resources"][0]["outputs"][0]["path"])
            first.write_text("tampered", encoding="utf-8")
            with self.assertRaises(ManifestError):
                verify_reference_cache(reference_root, manifest_path, required)
            bypass = verify_reference_cache(
                reference_root,
                manifest_path,
                required,
                allow_unverified=True,
            )
            self.assertEqual(bypass["status"], "unverified-allowed")
            self.assertTrue(bypass["allow_unverified"])

    def test_cache_receipt_rejects_manifest_vpk_and_vrf_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path, manifest = write_allowed_manifest(root / "project.json")
            reference_root = root / "references"
            report = write_reference_cache(reference_root, manifest_path, manifest)
            required = [report["resources"][0]["outputs"][0]["resource"]]

            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
            )
            with self.assertRaises(ManifestError):
                verify_reference_cache(reference_root, manifest_path, required)
            manifest_path, manifest = write_allowed_manifest(manifest_path)
            report = write_reference_cache(reference_root, manifest_path, manifest)

            for key in ("vpk", "vrf_cli"):
                path = Path(report[key])
                original = path.read_bytes()
                path.write_bytes(original + b"-changed")
                with self.subTest(key=key), self.assertRaises(ManifestError):
                    verify_reference_cache(reference_root, manifest_path, required)
                path.write_bytes(original)


class ArtifactAndFailureTests(unittest.TestCase):
    def test_process_lock_serializes_shared_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "shared-root"
            first = manifest_tool.ProcessLockSet([root])
            try:
                with self.assertRaisesRegex(ManifestError, "lock busy"):
                    manifest_tool.ProcessLockSet([root])
            finally:
                first.close()
            third = manifest_tool.ProcessLockSet([root])
            third.close()

    def test_copy_policy_rolls_back_interrupt_after_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source"
            destination = root / "destination"
            source.write_bytes(b"new")
            destination.write_bytes(b"old")
            original_publish = compiler_tool._publish_file_no_replace
            invocation = 0

            def interrupt_after_publish(pending, output):
                nonlocal invocation
                invocation += 1
                result = original_publish(pending, output)
                if invocation == 1:
                    raise KeyboardInterrupt("interrupt after publication")
                return result

            with mock.patch.object(
                compiler_tool,
                "_publish_file_no_replace",
                side_effect=interrupt_after_publish,
            ), self.assertRaisesRegex(KeyboardInterrupt, "after publication"):
                compiler_tool.copy_with_policy(
                    source,
                    destination,
                    allowed_root=root,
                    force_overwrite=True,
                    backup_root=root / "backups",
                    dry_run=False,
                    label="test copy",
                )

            self.assertEqual(destination.read_bytes(), b"old")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.preimage")))
            self.assertFalse(list(root.glob(".*.rollback-current")))

    def test_copy_policy_preserves_writer_winning_publication_race(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source"
            destination = root / "destination"
            source.write_bytes(b"new")
            destination.write_bytes(b"old")
            original_publish = compiler_tool._publish_file_no_replace
            invocation = 0
            writer_identity = None

            def writer_before_publish(pending, output):
                nonlocal invocation, writer_identity
                invocation += 1
                if invocation == 1:
                    Path(output).write_bytes(b"new")
                    writer_identity = compiler_tool.file_identity(Path(output))
                return original_publish(pending, output)

            with mock.patch.object(
                compiler_tool,
                "_publish_file_no_replace",
                side_effect=writer_before_publish,
            ), self.assertRaisesRegex(
                compiler_tool.CompileRollbackFailure, "foreign content restored"
            ):
                compiler_tool.copy_with_policy(
                    source,
                    destination,
                    allowed_root=root,
                    force_overwrite=True,
                    backup_root=root / "backups",
                    dry_run=False,
                    label="test copy",
                )

            self.assertEqual(destination.read_bytes(), b"new")
            self.assertEqual(compiler_tool.file_identity(destination), writer_identity)
            self.assertTrue(list(root.glob(".*.preimage")))

    def test_cleanup_refuses_to_overwrite_a_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source"
            destination = root / "destination"
            source.write_bytes(b"temporary")
            destination.write_bytes(b"original")
            receipt = compiler_tool.copy_with_policy(
                source,
                destination,
                allowed_root=root,
                force_overwrite=True,
                backup_root=root / "backups",
                dry_run=False,
                label="temporary dependency",
            )
            destination.write_bytes(b"foreign-writer")
            with self.assertRaisesRegex(ManifestError, "foreign content restored"):
                compiler_tool.restore_temporary_stage(receipt)
            self.assertEqual(destination.read_bytes(), b"foreign-writer")
            self.assertEqual(Path(receipt["backup"]).read_bytes(), b"original")

    def test_copy_policy_rejects_symlink_destination_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            allowed = root / "allowed"
            allowed.mkdir()
            outside = root / "outside"
            outside.write_bytes(b"outside")
            link = allowed / "destination"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            source = root / "source"
            source.write_bytes(b"new")
            with self.assertRaisesRegex(ManifestError, "symlink/junction"):
                compiler_tool.copy_with_policy(
                    source,
                    link,
                    allowed_root=allowed,
                    force_overwrite=True,
                    backup_root=root / "backups",
                    dry_run=False,
                    label="escaped artifact",
                )
            self.assertEqual(outside.read_bytes(), b"outside")

    def test_artifact_closure_verifies_content_hashes_not_only_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            resource = "models/item_c"
            output = compiler_tool.native_path(root, resource)
            output.parent.mkdir(parents=True)
            output.write_bytes(b"expected")
            receipt = {
                "resource": resource,
                "destination_after": compiler_tool.file_state(output),
            }
            closure = compiler_tool.verify_artifact_closure(
                root, [resource], [receipt]
            )
            self.assertTrue(closure["verified"])
            output.write_bytes(b"same-name-different-content")
            with self.assertRaisesRegex(RuntimeError, "content drifted"):
                compiler_tool.verify_artifact_closure(root, [resource], [receipt])

    def test_compile_receipt_probe_failure_precedes_all_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            addon = raw["project"]["addon"]
            project_root = root / "portable-project"
            manifest_path = project_root / "project.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--cs2-root",
                str(cs2_root),
                "--resourcecompiler",
                str(compiler),
                "--stage",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool,
                "probe_versioned_receipt_create",
                side_effect=["hard-link", OSError("installed receipt probe failed")],
            ), mock.patch.object(
                compiler_tool, "copy_with_policy"
            ) as copy, mock.patch.object(
                compiler_tool, "run"
            ) as run_compiler, self.assertRaisesRegex(OSError, "receipt probe failed"):
                compiler_tool.main()
            copy.assert_not_called()
            run_compiler.assert_not_called()

    def test_compile_report_binds_initial_provenance_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            raw["stock_dependencies"] = []
            raw["compile_resources"] = raw["compile_resources"][:1]
            addon = raw["project"]["addon"]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            manifest_path = content_root / "project.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            initial_manifest_hash = sha256_file(manifest_path)
            _, manifest = load_manifest(manifest_path)
            resource = compiler_tool.compile_resources(manifest)[0]
            source = compiler_tool.native_path(content_root, resource)
            source.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")

            def drifting_run(command: list[str], *, timeout_seconds: int = 600):
                compile_source = Path(command[command.index("-i") + 1])
                relative = compile_source.relative_to(content_root)
                output = compiler_tool.resource_output_path(
                    cs2_root, addon, relative.as_posix()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"compiled")
                manifest_path.write_text(
                    manifest_path.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
                return "ok", ""

            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--cs2-root",
                str(cs2_root),
                "--resourcecompiler",
                str(compiler),
                "--allow-unverified-reference-cache",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool, "run", side_effect=drifting_run
            ), self.assertRaisesRegex(ManifestError, "provenance changed"):
                compiler_tool.main()

            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["manifest_sha256"], initial_manifest_hash)
            self.assertEqual(
                report["provenance_before"]["manifest"]["sha256"],
                initial_manifest_hash,
            )
            self.assertNotEqual(
                report["provenance_after"]["manifest"]["sha256"],
                initial_manifest_hash,
            )

    def test_compile_batch_interrupt_restores_prior_packaged_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            raw["stock_dependencies"] = []
            raw["compile_resources"] = raw["compile_resources"][:2]
            addon = raw["project"]["addon"]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            manifest_path = content_root / "project.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            _, manifest = load_manifest(manifest_path)
            resources = compiler_tool.compile_resources(manifest)
            for resource in resources:
                source = compiler_tool.native_path(content_root, resource)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(resource, encoding="utf-8")
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            outputs = [
                compiler_tool.resource_output_path(cs2_root, addon, resource)
                for resource in resources
            ]
            outputs[0].parent.mkdir(parents=True, exist_ok=True)
            outputs[0].write_bytes(b"old-first")
            invocation = 0

            def interrupted_second_compile(
                command: list[str], *, timeout_seconds: int = 600
            ):
                nonlocal invocation
                invocation += 1
                source = Path(command[command.index("-i") + 1])
                relative = source.relative_to(content_root)
                output = compiler_tool.resource_output_path(
                    cs2_root, addon, relative.as_posix()
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"new-{invocation}".encode())
                if invocation == 2:
                    raise KeyboardInterrupt("simulated second compiler interruption")
                return "ok", ""

            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--cs2-root",
                str(cs2_root),
                "--resourcecompiler",
                str(compiler),
                "--allow-unverified-reference-cache",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool, "run", side_effect=interrupted_second_compile
            ), self.assertRaisesRegex(KeyboardInterrupt, "compiler interruption"):
                compiler_tool.main()

            self.assertEqual(outputs[0].read_bytes(), b"old-first")
            self.assertFalse(outputs[1].exists())
            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "failed")
            self.assertFalse(report["cleanup_errors"])

    def test_versioned_receipt_create_is_atomic_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            receipt = root / "compile-report-run.json"
            method = write_json_new(receipt, {"value": "first"})
            self.assertIn(method, {"hard-link", "windows-no-replace-rename"})
            before = receipt.read_bytes()

            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_json_new(receipt, {"value": "second"})

            self.assertEqual(receipt.read_bytes(), before)
            self.assertFalse(list(root.glob(".*.tmp")))

            probe_method = probe_versioned_receipt_create(root)
            self.assertIn(
                probe_method, {"hard-link", "windows-no-replace-rename"}
            )
            self.assertFalse(list(root.glob(".versioned-receipt-probe-*.json")))

    def test_windows_receipt_fallback_is_no_replace_and_cleans_temps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            receipt = root / "receipt.json"
            original_rename = manifest_tool.os.rename
            with mock.patch.object(
                manifest_tool.os, "name", "nt"
            ), mock.patch.object(
                manifest_tool.os, "link", side_effect=OSError("links unsupported")
            ), mock.patch.object(
                manifest_tool.os, "rename", wraps=original_rename
            ):
                method = write_json_new(receipt, {"value": "fallback"})
            self.assertEqual(method, "windows-no-replace-rename")
            self.assertEqual(
                json.loads(receipt.read_text(encoding="utf-8")),
                {"value": "fallback"},
            )

            before = receipt.read_bytes()
            with mock.patch.object(
                manifest_tool.os, "name", "nt"
            ), mock.patch.object(
                manifest_tool.os, "link", side_effect=OSError("links unsupported")
            ), mock.patch.object(
                manifest_tool.os,
                "rename",
                side_effect=FileExistsError("simulated destination race"),
            ), self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_json_new(receipt, {"value": "must-not-win"})
            self.assertEqual(receipt.read_bytes(), before)
            self.assertFalse(list(root.glob(".*.tmp")))

            unsupported = root / "unsupported.json"
            with mock.patch.object(
                manifest_tool.os, "name", "nt"
            ), mock.patch.object(
                manifest_tool.os, "link", side_effect=OSError("links unsupported")
            ), mock.patch.object(
                manifest_tool.os,
                "rename",
                side_effect=OSError("rename unsupported"),
            ), self.assertRaisesRegex(OSError, "neither hard-link nor Windows"):
                write_json_new(unsupported, {"value": "nope"})
            self.assertFalse(unsupported.exists())
            self.assertFalse(list(root.glob(".*.tmp")))

    def test_missing_reference_cache_writes_preflight_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            addon = json.loads(EXAMPLE.read_text(encoding="utf-8"))["project"]["addon"]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            manifest_path, _ = write_allowed_manifest(content_root / "project.json")
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--cs2-root",
                str(cs2_root),
                "--resourcecompiler",
                str(compiler),
                "--reference-root",
                str(root / "missing-references"),
            ]
            with mock.patch.object(sys, "argv", argv), self.assertRaises(ManifestError):
                compiler_tool.main()
            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["phase"], "preflight")
            self.assertIn("receipt", report["error"]["message"])

    def test_artifact_preflight_does_not_copy_before_late_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            sources = root / "sources"
            artifacts = root / "artifacts"
            first_source = sources / "first_c"
            second_source = sources / "second_c"
            first_source.parent.mkdir(parents=True)
            first_source.write_bytes(b"first-new")
            second_source.write_bytes(b"second-new")
            second_destination = artifacts / "items" / "second_c"
            second_destination.parent.mkdir(parents=True)
            second_destination.write_bytes(b"second-old")
            first_destination = artifacts / "items" / "first_c"

            with self.assertRaises(ManifestError):
                compiler_tool.preflight_artifact_copies(
                    artifacts,
                    [
                        (first_source, "items/first_c"),
                        (second_source, "items/second_c"),
                    ],
                    force_overwrite=False,
                )
            self.assertFalse(first_destination.exists())
            self.assertEqual(second_destination.read_bytes(), b"second-old")

    def test_artifact_subset_is_rejected_before_cs2_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path, manifest = write_allowed_manifest(root / "project.json")
            argv = [
                "compile_animgraph2.py",
                "--manifest",
                str(manifest_path),
                "--resource",
                compiler_tool.compile_resources(manifest)[0],
                "--artifact-root",
                str(root / "artifacts"),
            ]
            with mock.patch.object(sys, "argv", argv), self.assertRaises(ManifestError):
                compiler_tool.main()

    def test_resourcecompiler_failure_receipt_survives_cleanup_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            addon = json.loads(EXAMPLE.read_text(encoding="utf-8"))["project"]["addon"]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            manifest_path, manifest = write_allowed_manifest(content_root / "project.json")
            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            for resource in compiler_tool.compile_resources(manifest):
                source = compiler_tool.native_path(content_root, resource)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(resource, encoding="utf-8")
            reference_root = root / "references"
            write_reference_cache(reference_root, manifest_path, manifest)
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
                output.write_text(f"partial-{invocation}", encoding="utf-8")
                if invocation == 2:
                    raise RuntimeError("original compiler failure")
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
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool, "run", side_effect=fake_run
            ), mock.patch.object(
                compiler_tool,
                "restore_nonpackage_output",
                side_effect=RuntimeError("cleanup failure"),
            ), self.assertRaisesRegex(RuntimeError, "original compiler failure"):
                compiler_tool.main()

            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "rollback-failed")
            self.assertEqual(report["error"]["message"], "original compiler failure")
            self.assertTrue(report["cleanup_errors"])
            immutable = list(
                (content_root / ".local" / "reports").glob("compile-report-*.json")
            )
            self.assertEqual(len(immutable), 1)

    def test_artifact_copy_failure_rolls_back_and_writes_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            cs2_root = root / "cs2"
            raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            addon = raw["project"]["addon"]
            raw["project"]["artifact_policy"] = {
                "status": "allowed",
                "basis": "synthetic test outputs",
                "template_derivative_basis": "synthetic test-owned templates",
            }
            raw["stock_dependencies"] = []
            raw["compile_resources"] = raw["compile_resources"][:2]
            content_root = cs2_root / "content" / "csgo_addons" / addon
            manifest_path = content_root / "project.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            _, manifest = load_manifest(manifest_path)

            game_root = cs2_root / "game" / "csgo"
            game_root.mkdir(parents=True)
            (game_root / "gameinfo.gi").write_text("gameinfo", encoding="utf-8")
            compiler = cs2_root / "game" / "bin" / "win64" / "resourcecompiler.exe"
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"fake-compiler")
            for resource in compiler_tool.compile_resources(manifest):
                source = compiler_tool.native_path(content_root, resource)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(resource, encoding="utf-8")
            reference_root = root / "references"
            write_reference_cache(reference_root, manifest_path, manifest)

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
                output.write_text(f"compiled-{invocation}", encoding="utf-8")
                return "ok", ""

            original_copy = compiler_tool.copy_with_policy
            artifact_invocation = 0

            def flaky_copy(*args, **kwargs):
                nonlocal artifact_invocation
                if str(kwargs.get("label", "")).startswith("artifact "):
                    artifact_invocation += 1
                    if artifact_invocation == 2:
                        raise OSError("simulated artifact copy failure")
                return original_copy(*args, **kwargs)

            artifact_root = root / "artifacts"
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
                "--artifact-root",
                str(artifact_root),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                compiler_tool, "run", side_effect=fake_run
            ), mock.patch.object(
                compiler_tool, "copy_with_policy", side_effect=flaky_copy
            ), self.assertRaisesRegex(OSError, "artifact copy failure"):
                compiler_tool.main()

            self.assertEqual(
                [path for path in artifact_root.rglob("*") if path.is_file()], []
            )
            report = json.loads(
                (content_root / ".local" / "reports" / "compile-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["phase"], "artifact-handoff")
            self.assertEqual(report["error"]["type"], "OSError")
            self.assertTrue(report["artifact_cleanup"])


class VnmclipReceiptTests(unittest.TestCase):
    def test_batch_commit_rolls_back_after_a_later_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            destinations = [root / "first.vnmclip", root / "second.vnmclip"]
            for index, destination in enumerate(destinations):
                destination.write_text(f"old-{index}", encoding="utf-8")
            prepared = []
            for index, destination in enumerate(destinations):
                text = f"new-{index}\n"
                prepared.append(
                    {
                        "output": destination,
                        "text": text,
                        "receipt": {
                            "output": str(destination),
                            "output_before": generator_tool._file_state(destination),
                            "output_sha256": generator_tool._text_sha256(text),
                        },
                    }
                )

            original_replace = generator_tool.os.replace
            invocation = 0

            def flaky_replace(source, destination):
                nonlocal invocation
                invocation += 1
                if invocation == 2:
                    raise OSError("simulated second replace failure")
                return original_replace(source, destination)

            with mock.patch.object(
                generator_tool.os, "replace", side_effect=flaky_replace
            ), self.assertRaisesRegex(OSError, "second replace failure"):
                generator_tool.commit_generated_outputs(prepared)

            self.assertEqual(destinations[0].read_text(encoding="utf-8"), "old-0")
            self.assertEqual(destinations[1].read_text(encoding="utf-8"), "old-1")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

    def test_batch_commit_rolls_back_interrupt_after_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            destination = root / "item.vnmclip"
            destination.write_text("old", encoding="utf-8")
            text = "new\n"
            prepared = [
                {
                    "output": destination,
                    "text": text,
                    "receipt": {
                        "output": str(destination),
                        "output_before": generator_tool._file_state(destination),
                        "output_sha256": generator_tool._text_sha256(text),
                    },
                }
            ]
            original_replace = generator_tool.os.replace
            invocation = 0

            def interrupted_replace(source, output):
                nonlocal invocation
                invocation += 1
                result = original_replace(source, output)
                if invocation == 1:
                    raise KeyboardInterrupt("simulated interrupt after replace")
                return result

            with mock.patch.object(
                generator_tool.os, "replace", side_effect=interrupted_replace
            ), self.assertRaisesRegex(KeyboardInterrupt, "after replace"):
                generator_tool.commit_generated_outputs(prepared)

            self.assertEqual(destination.read_text(encoding="utf-8"), "old")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

    def test_batch_rollback_preserves_concurrent_writer_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            destinations = [root / "first.vnmclip", root / "second.vnmclip"]
            prepared = []
            for index, destination in enumerate(destinations):
                destination.write_text(f"old-{index}", encoding="utf-8")
                text = f"new-{index}\n"
                prepared.append(
                    {
                        "output": destination,
                        "text": text,
                        "receipt": {
                            "output": str(destination),
                            "output_before": generator_tool._file_state(destination),
                            "output_sha256": generator_tool._text_sha256(text),
                        },
                    }
                )
            original_publish = generator_tool._publish_file_no_replace
            invocation = 0

            def concurrent_publication(source, output):
                nonlocal invocation
                invocation += 1
                if invocation == 1:
                    Path(output).write_bytes(b"foreign-writer")
                return original_publish(source, output)

            with mock.patch.object(
                generator_tool,
                "_publish_file_no_replace",
                side_effect=concurrent_publication,
            ), self.assertRaisesRegex(
                generator_tool.VnmclipRollbackFailure, "foreign content restored"
            ):
                generator_tool.commit_generated_outputs(prepared)

            self.assertEqual(destinations[0].read_bytes(), b"foreign-writer")
            self.assertEqual(destinations[1].read_text(encoding="utf-8"), "old-1")
            backups = list(root.glob(".*.rollback"))
            self.assertGreaterEqual(len(backups), 1)
            self.assertIn(b"old-0", {path.read_bytes() for path in backups})

    def test_batch_rollback_rejects_tampered_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            destination = root / "item.vnmclip"
            destination.write_text("old", encoding="utf-8")
            text = "new\n"
            prepared = [
                {
                    "output": destination,
                    "text": text,
                    "receipt": {
                        "output": str(destination),
                        "output_before": generator_tool._file_state(destination),
                        "output_sha256": generator_tool._text_sha256(text),
                    },
                }
            ]
            original_replace = generator_tool.os.replace
            replace_invocation = 0
            original_publish = generator_tool._publish_file_no_replace
            publish_invocation = 0

            def tamper_during_quarantine(source, output):
                nonlocal replace_invocation
                replace_invocation += 1
                result = original_replace(source, output)
                if replace_invocation == 2:
                    backups = list(root.glob(".*.rollback"))
                    self.assertEqual(len(backups), 1)
                    backups[0].write_bytes(b"tampered-backup")
                return result

            def fail_after_output_publication(source, output):
                nonlocal publish_invocation
                publish_invocation += 1
                result = original_publish(source, output)
                if publish_invocation == 1:
                    raise OSError("simulated error after output publication")
                return result

            with mock.patch.object(
                generator_tool.os, "replace", side_effect=tamper_during_quarantine
            ), mock.patch.object(
                generator_tool,
                "_publish_file_no_replace",
                side_effect=fail_after_output_publication,
            ), self.assertRaisesRegex(
                generator_tool.VnmclipRollbackFailure,
                "backup changed before restoration",
            ):
                generator_tool.commit_generated_outputs(prepared)

            self.assertEqual(destination.read_text(encoding="utf-8"), text)
            backups = list(root.glob(".*.rollback"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b"tampered-backup")
            self.assertFalse(list(root.glob(".*.rollback-current")))

    def test_staging_failure_cleans_reserved_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            destination = root / "item.vnmclip"
            destination.write_text("old", encoding="utf-8")
            text = "new\n"
            prepared = [
                {
                    "output": destination,
                    "text": text,
                    "receipt": {
                        "output": str(destination),
                        "output_before": generator_tool._file_state(destination),
                        "output_sha256": generator_tool._text_sha256(text),
                    },
                }
            ]

            original_sha256_file = generator_tool.sha256_file

            def staging_hash_failure(path):
                if str(path).endswith(".pending"):
                    raise OSError("simulated staging hash failure")
                return original_sha256_file(path)

            with mock.patch.object(
                generator_tool,
                "sha256_file",
                side_effect=staging_hash_failure,
            ), self.assertRaisesRegex(OSError, "staging hash failure"):
                generator_tool.commit_generated_outputs(prepared)

            self.assertEqual(destination.read_text(encoding="utf-8"), "old")
            self.assertFalse(list(root.glob(".*.pending")))
            self.assertFalse(list(root.glob(".*.rollback")))

    def test_transaction_scan_fails_closed_on_unknown_or_partial_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            report_root = Path(temp_name)
            output = {
                "destination": str(report_root / "output.vnmclip"),
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
                journal = report_root / f"vnmclip-transaction-{run_id}.json"
                transaction = {
                    "schema_version": 1,
                    "run_id": run_id,
                    "status": status,
                    "manifest": "project.json",
                    "manifest_sha256": "b" * 64,
                    "outputs": [output],
                }
                if status == "failed":
                    transaction["error"] = {
                        "type": "RuntimeError",
                        "message": "test",
                    }
                if status == "reported":
                    report_path = report_root / f"vnmclip-report-{run_id}.json"
                    transaction["generated"] = []
                    report = {
                        "schema_version": 2,
                        "status": "ok",
                        "run_id": run_id,
                        "manifest": transaction["manifest"],
                        "manifest_sha256": transaction["manifest_sha256"],
                        "transaction_journal": str(journal),
                        "generated": [],
                    }
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                    transaction["report"] = str(report_path)
                    transaction["report_sha256"] = generator_tool.sha256_file(
                        report_path
                    )
                journal.write_text(json.dumps(transaction), encoding="utf-8")
            (report_root / "vnmclip-transaction-invalid.json").write_text(
                "not json", encoding="utf-8"
            )
            (report_root / "vnmclip-transaction-incomplete.json").write_text(
                json.dumps({"status": "failed"}), encoding="utf-8"
            )
            unresolved = {
                item["status"]
                for item in generator_tool.unresolved_vnmclip_transactions(report_root)
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

    def test_receipt_probe_failure_prevents_vnmclip_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path = root / "project.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            argv = ["generate_vnmclips.py", "--manifest", str(manifest_path)]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                generator_tool, "load_manifest", return_value=(manifest_path, {})
            ), mock.patch.object(
                generator_tool, "selected_sets", return_value=[]
            ), mock.patch.object(
                generator_tool,
                "probe_versioned_receipt_create",
                side_effect=OSError("unsupported receipt filesystem"),
            ), mock.patch.object(
                generator_tool, "commit_generated_outputs"
            ) as commit, self.assertRaisesRegex(OSError, "unsupported receipt"):
                generator_tool.main()
            commit.assert_not_called()
            self.assertFalse(
                list((root / ".local" / "reports").glob("vnmclip-transaction-*.json"))
            )

    def test_report_failure_leaves_committed_transaction_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path = root / "project.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            output = root / "item.vnmclip"
            action = {
                "id": "idle",
                "reference_resource": "animation/anims/test/idle.vnmclip_c",
            }
            animation_set = {"id": "viewmodel", "actions": [action]}
            text = "generated\n"
            prepared = {
                "output": output,
                "text": text,
                "receipt": {
                    "output": str(output),
                    "output_before": {"exists": False},
                    "output_sha256": generator_tool._text_sha256(text),
                },
            }
            argv = ["generate_vnmclips.py", "--manifest", str(manifest_path)]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                generator_tool,
                "load_manifest",
                return_value=(manifest_path, {}),
            ), mock.patch.object(
                generator_tool, "selected_sets", return_value=[animation_set]
            ), mock.patch.object(
                generator_tool, "action_filter", return_value=[action]
            ), mock.patch.object(
                generator_tool, "verify_reference_cache", return_value={"ok": True}
            ), mock.patch.object(
                generator_tool, "prepare_one", return_value=prepared
            ), mock.patch.object(
                generator_tool,
                "commit_generated_outputs",
                return_value=[prepared["receipt"]],
            ), mock.patch.object(
                generator_tool,
                "write_json_new",
                side_effect=OSError("simulated report failure"),
            ), self.assertRaisesRegex(OSError, "report failure"):
                generator_tool.main()

            journals = list(
                (root / ".local" / "reports").glob("vnmclip-transaction-*.json")
            )
            self.assertEqual(len(journals), 1)
            journal = json.loads(journals[0].read_text(encoding="utf-8"))
            self.assertEqual(journal["status"], "committed")

    def test_event_track_receipt_contains_policy_path_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            manifest_path = root / "project.json"
            manifest_path.write_text("{}\n", encoding="utf-8")
            reference_root = root / "references"
            resource = "animation/anims/viewmodel/test/idle.vnmclip_c"
            template = output_path(reference_root, reference_vnmclip_relative(resource))
            template.parent.mkdir(parents=True)
            template.write_text(
                "{\n"
                '\tm_sourceFilename = "old.dmx"\n'
                '\tm_animationSkeletonName = "old.vnmskel"\n'
                "\tm_secondaryAnimationSkeletonNames = [  ]\n"
                "\tm_eventTracks = [  ]\n"
                "}\n",
                encoding="utf-8",
            )
            output_dmx = root / "models" / "owner" / "item" / "source" / "idle.dmx"
            output_dmx.parent.mkdir(parents=True)
            output_dmx.write_bytes(b"dmx")
            event_file = root / "models" / "owner" / "item" / "events" / "idle.kv3"
            event_file.parent.mkdir(parents=True)
            event_file.write_text("[  ]\n", encoding="utf-8")
            animation_set = {
                "id": "viewmodel",
                "primary_skeleton": "animation/test.vnmskel",
                "secondary_skeletons": [],
            }
            action = {
                "id": "idle",
                "reference_resource": resource,
                "output_dmx": "models/owner/item/source/idle.dmx",
                "output_vnmclip": "models/owner/item/clips/idle.vnmclip",
                "event_policy": "replace",
                "event_tracks_file": "models/owner/item/events/idle.kv3",
            }
            receipt = generator_tool.generate_one(
                manifest_path,
                reference_root,
                animation_set,
                action,
                allow_missing_dmx=False,
            )
            self.assertEqual(receipt["event_policy"], "replace")
            self.assertEqual(receipt["event_tracks_path"], str(event_file))
            self.assertEqual(receipt["event_tracks_sha256"], sha256_file(event_file))


if __name__ == "__main__":
    unittest.main()
