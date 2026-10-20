#!/usr/bin/env python3
"""Behavioral tests for the standalone helper; no game installation is needed."""
import dataclasses
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from compile_native import Config, ProcessResult, canonical_resource, compile_assets, prepare, reparse, run_process


class NativeCompileTests(unittest.TestCase):
    def setUp(self):
        self.temp_parent = Path(tempfile.gettempdir()).resolve()
        self.temporary = tempfile.TemporaryDirectory(prefix='cs2skills-native-', dir=self.temp_parent)
        self.root = Path(self.temporary.name).resolve()
        self.root.relative_to(self.temp_parent)
        self.cs2 = self.root / 'cs2'
        self.source = self.root / 'source'
        self.work = self.root / 'work'
        for relative in ('game/csgo', 'game/bin/win64', 'content/csgo_addons', 'game/csgo_addons'):
            (self.cs2 / relative).mkdir(parents=True)
        self.source.mkdir()
        (self.cs2 / 'game/csgo/steam.inf').write_text('appID=730\nProductName=cs2\nSourceRevision=test\n')
        (self.cs2 / 'game/csgo/gameinfo.gi').write_text('"GameInfo" { game "Counter-Strike 2" }')
        (self.cs2 / 'game/bin/win64/resourcecompiler.exe').write_bytes(b'MZ-fake-runner-only')
        (self.source / 'particles/example').mkdir(parents=True)
        (self.source / 'materials/example').mkdir(parents=True)
        (self.source / 'particles/example/root.vpcf').write_text(
            '{_class="CParticleSystemDefinition" m_Children=[{m_ChildRef=resource:"particles/example/child.vpcf"}]}')
        (self.source / 'particles/example/child.vpcf').write_text(
            '{_class="CParticleSystemDefinition" m_Renderers=[{_class="C_OP_RenderSprites"}]}')
        (self.source / 'materials/example/sprite.vtex').write_text('owned synthetic test source')
        (self.source / 'materials/example/sprite.tga').write_bytes(bytes(18))
        self.config = Config(self.cs2, self.source, self.work, effect_root='particles/example/root.vpcf')
        self.calls = []

    def tearDown(self):
        # The only recursive cleanup target is the exact test-owned directory.
        self.root.resolve().relative_to(self.temp_parent)
        self.temporary.cleanup()

    def runner(self, executable, arguments, cwd, timeout, max_output_bytes):
        self.calls.append((executable, list(arguments), cwd, timeout, max_output_bytes))
        if '--block' in arguments:
            return ProcessResult(0, False, b'owned DATA readback', 19, False)
        self.assertEqual(executable, self.cs2 / 'game/bin/win64/resourcecompiler.exe')
        self.assertIn('-nop4', arguments)
        self.assertIn('-fshallow', arguments)
        self.assertNotIn('-skiptype', arguments)
        source = Path(arguments[arguments.index('-i') + 1])
        relative = source.relative_to(self.cs2 / 'content/csgo_addons')
        output = self.cs2 / 'game/csgo_addons' / (str(relative) + '_c')
        output.parent.mkdir(parents=True, exist_ok=True)
        # A synthetic Resource2-sized blob, not a native-fidelity fixture.
        output.write_bytes(struct.pack('<IHHII', 32, 12, 1, 8, 0) + bytes(16))
        return ProcessResult(0, False, b'OK: 1 compiled', 14, False)

    def test_plan_is_read_only_and_compiles_textures_before_particles(self):
        (self.source / 'effect-plan.json').write_text('{"kind":"sidecar"}')
        plan = prepare(self.config)
        self.assertEqual(plan['inputs'][0], 'materials/example/sprite.vtex')
        self.assertFalse(self.work.exists())
        self.assertEqual(plan['ignored_files'], ['effect-plan.json'])
        self.assertEqual(list((self.cs2 / 'content/csgo_addons').iterdir()), [])
        outcome = compile_assets(self.config, runner=self.runner)
        report = outcome['report']
        self.assertEqual(report['execution']['nativeCompilation'], 'passed')
        self.assertEqual(report['execution']['nativeVisualValidation'], 'not-run')
        self.assertEqual(report['execution']['propertyRetention'], 'not-run')
        self.assertEqual(len(report['outputs']), 3)
        self.assertEqual(len(report['sourceInventory']), 4)
        self.assertEqual(report['runs'][0]['input'], 'materials/example/sprite.vtex')
        self.assertTrue(all(item['fresh'] for item in report['outputs']))
        self.assertEqual(json.loads(outcome['report_path'].read_text())['execution']['nativeCompilation'], 'passed')
        self.assertNotIn(str(self.root), outcome['report_path'].read_text())
        second = compile_assets(self.config, runner=self.runner)
        self.assertNotEqual(report['addonName'], second['report']['addonName'])

    def test_existing_addon_is_never_reused(self):
        run_id = 'a' * 32
        existing = self.cs2 / 'content/csgo_addons' / ('s2_particle_validation_' + run_id)
        existing.mkdir()
        sentinel = existing / 'leave-alone.txt'
        sentinel.write_text('unchanged')
        with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
            compile_assets(self.config, self.runner, lambda: run_id)
        self.assertEqual(sentinel.read_text(), 'unchanged')
        self.assertFalse(self.work.exists())

    def test_changed_source_snapshot_is_not_compiled_under_old_hashes(self):
        planned = prepare(self.config)
        (self.source / 'materials/example/sprite.vtex').write_text('changed after inventory')
        with patch('compile_native.prepare', return_value=planned):
            outcome = compile_assets(self.config, self.runner)
        self.assertEqual(outcome['report']['execution']['nativeCompilation'], 'failed')
        self.assertRegex(outcome['report']['errors'][0], 'between preflight and staging')
        self.assertEqual(len(self.calls), 0)

    def test_device_paths_and_external_child_graphs_fail_before_writes(self):
        for value in ('../outside.vpcf', '/absolute.vpcf', 'particles/con.vpcf', 'particles/a//b.vpcf', 'C:/drive.vpcf'):
            with self.assertRaises(ValueError):
                canonical_resource(value)
        (self.source / 'particles/example/root.vpcf').write_text(
            '{_class="CParticleSystemDefinition" m_Children=[{m_ChildRef="particles/missing.vpcf"}]}')
        with self.assertRaisesRegex(ValueError, 'referenced particle'):
            compile_assets(self.config, self.runner)
        self.assertFalse(self.work.exists())
        self.assertEqual(len(self.calls), 0)

    def test_identity_pin_budget_and_work_overlap_fail_before_process(self):
        with self.assertRaisesRegex(ValueError, 'pinned fingerprint'):
            compile_assets(dataclasses.replace(self.config, expected_compiler_sha256='0' * 64), self.runner)
        with self.assertRaisesRegex(ValueError, 'budget'):
            compile_assets(dataclasses.replace(self.config, max_files=1), self.runner)
        with self.assertRaisesRegex(ValueError, 'separate'):
            compile_assets(dataclasses.replace(self.config, work_root=self.source / 'logs'), self.runner)
        (self.cs2 / 'game/csgo/steam.inf').write_text('appID=1422450\nProductName=deadlock\n')
        with self.assertRaisesRegex(ValueError, 'CS2 app 730'):
            compile_assets(self.config, self.runner)
        self.assertEqual(len(self.calls), 0)

    def test_windows_reparse_attribute_is_rejected(self):
        self.assertTrue(reparse(SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)))
        self.assertFalse(reparse(SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0)))

    def test_real_symlink_source_rejected_where_supported(self):
        alias = self.root / 'source-link'
        try:
            alias.symlink_to(self.source, target_is_directory=True)
        except OSError:
            self.skipTest('Account does not permit creating a directory symlink')
        with self.assertRaisesRegex(ValueError, 'symbolic|reparse|redirected'):
            compile_assets(dataclasses.replace(self.config, source_root=alias), self.runner)

    def test_nonzero_timeout_missing_and_stale_outputs_keep_failed_reports(self):
        for mode in ('nonzero', 'timeout', 'missing', 'stale'):
            def failing(executable, arguments, cwd, timeout, max_output_bytes):
                if mode == 'stale':
                    self.runner(executable, arguments, cwd, timeout, max_output_bytes)
                    source = Path(arguments[1])
                    relative = source.relative_to(self.cs2 / 'content/csgo_addons')
                    output = self.cs2 / 'game/csgo_addons' / (str(relative) + '_c')
                    os.utime(output, (1, 1))
                return ProcessResult(1 if mode == 'nonzero' else 0, mode == 'timeout', b'diagnostic', 10, False)
            with self.subTest(mode=mode):
                outcome = compile_assets(self.config, failing)
                report = outcome['report']
                self.assertEqual(report['execution']['nativeCompilation'], 'failed')
                self.assertTrue(report['errors'])
                self.assertNotIn(str(self.root), outcome['report_path'].read_text())
                self.assertTrue((outcome['report_path'].parent / report['runs'][0]['log']).is_file())

    def test_optional_viewer_captures_text_without_claiming_retention(self):
        viewer = self.root / 'viewer.exe'
        viewer.write_bytes(b'MZ-fake-readback-runner-only')
        outcome = compile_assets(dataclasses.replace(self.config, viewer_cli=viewer), self.runner)
        report = outcome['report']
        self.assertEqual(report['execution']['nativeCompilation'], 'passed')
        self.assertEqual(report['execution']['propertyRetention'], 'not-run')
        self.assertTrue(all(item['readback']['status'] == 'text-captured' for item in report['outputs']))
        self.assertTrue(all(item['readback']['propertyRetention'] == 'manual-inspection-required' for item in report['outputs']))
        self.assertTrue(all(call[1][-2:] == ['--block', 'DATA'] for call in self.calls if '--block' in call[1]))

    def test_empty_viewer_output_is_not_reported_as_captured_text(self):
        viewer = self.root / 'viewer.exe'
        viewer.write_bytes(b'MZ-fake-readback-runner-only')
        for payload in (b'', b'\r\n \t'):
            def empty_viewer(executable, arguments, cwd, timeout, max_output_bytes):
                if '--block' in arguments:
                    return ProcessResult(0, False, payload, len(payload), False)
                return self.runner(executable, arguments, cwd, timeout, max_output_bytes)
            with self.subTest(payload=payload):
                outcome = compile_assets(dataclasses.replace(self.config, viewer_cli=viewer), empty_viewer)
                report = outcome['report']
                self.assertEqual(report['execution']['nativeCompilation'], 'passed')
                self.assertEqual(report['execution']['propertyRetention'], 'not-run')
                for item in report['outputs']:
                    self.assertEqual(item['readback']['status'], 'empty')
                    self.assertEqual(item['readback']['outputBytesSeen'], len(payload))
                    self.assertEqual(
                        (outcome['report_path'].parent / item['readback']['log']).read_bytes(), payload)

    def test_output_budget_counts_unselected_dependency_outputs(self):
        def extra_output(executable, arguments, cwd, timeout, max_output_bytes):
            result = self.runner(executable, arguments, cwd, timeout, max_output_bytes)
            source = Path(arguments[1])
            relative = source.relative_to(self.cs2 / 'content/csgo_addons')
            addon = relative.parts[0]
            dependency = self.cs2 / 'game/csgo_addons' / addon / 'materials/implicit.vtex_c'
            dependency.parent.mkdir(parents=True, exist_ok=True)
            dependency.write_bytes(bytes(2048))
            return result
        config = dataclasses.replace(self.config, inputs=('particles/example/root.vpcf',), max_compiled_bytes=1024)
        outcome = compile_assets(config, extra_output)
        self.assertEqual(outcome['report']['execution']['nativeCompilation'], 'failed')
        self.assertRegex(outcome['report']['errors'][0], 'including dependencies')

    def test_process_runner_bounds_output_and_stops_on_timeout(self):
        output = run_process(Path(sys.executable), ['-c', 'import sys;sys.stdout.write("x"*100000);sys.stderr.write("y"*100000)'], self.root, 10, 1024)
        self.assertEqual(output.exit_code, 0)
        self.assertTrue(output.truncated)
        self.assertLessEqual(len(output.output), 1024)
        self.assertGreater(output.output_bytes_seen, 1024)
        started = time.monotonic()
        timeout = run_process(Path(sys.executable), ['-c', 'import time;time.sleep(10)'], self.root, 0.1, 1024)
        self.assertTrue(timeout.timed_out)
        self.assertLess(time.monotonic() - started, 5)


if __name__ == '__main__':
    unittest.main()
