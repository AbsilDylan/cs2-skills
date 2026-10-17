#!/usr/bin/env python3
"""Standalone VRF orchestration tests; no installed game or VRF required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from inspect_vpk_with_vrf import InspectionError, bounded_process, data_format, inspect
from test_vpk_reference import tree_entry, write_vpk
from vpk_reference import Vpk

TRANSCRIPT = (b'Resource summary\n--- Data for block "DATA" ---\n'
              b'<!-- kv3 encoding:text:version{example} format:vpcf61:version{example} -->\n'
              b'{ _class = "CParticleSystemDefinition" }\n')


class VrfInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.archive = Vpk(write_vpk(self.source))
        self.output = self.root / "work"

    def tearDown(self):
        self.temp.cleanup()

    def run_inspection(self, **kwargs):
        process = {"exitCode": 0, "timedOut": False, "outputLimitExceeded": False, "stdout": TRANSCRIPT, "stderr": b""}
        with patch("inspect_vpk_with_vrf.tool_identity", return_value=(["synthetic-vrf"], {"versionOutput": "test-double"}, b"--input --block")), \
             patch("inspect_vpk_with_vrf.bounded_process", side_effect=lambda *_: dict(process)):
            return inspect(self.archive, self.root / "not-executed", self.output, "synthetic",
                           kwargs.pop("names", ["particles/original.vpcf_c"]), **kwargs)

    def test_targeted_snapshot_records_hashes_and_leaves_no_payload(self):
        report = self.run_inspection()
        self.assertTrue(report["coverage"]["complete"])
        self.assertTrue(report["entries"][0]["crc32Verified"])
        self.assertEqual(report["entries"][0]["dataFormat"], "vpcf61")
        self.assertEqual((self.output / report["entries"][0]["transcript"]).read_bytes(), TRANSCRIPT)
        self.assertEqual(json.loads((self.output / "inspection.json").read_text()), report)
        self.assertEqual(list(self.output.glob("staging-*")), [])
        self.assertEqual(list(self.output.rglob("*.vpcf_c")), [])

    def test_existing_output_and_archive_subdirectory_are_refused(self):
        self.output.mkdir()
        (self.output / "keep.txt").write_text("unchanged")
        with self.assertRaisesRegex(InspectionError, "new directory"):
            self.run_inspection()
        self.assertEqual((self.output / "keep.txt").read_text(), "unchanged")
        self.output = self.source / "new"
        with self.assertRaisesRegex(InspectionError, "outside"):
            self.run_inspection()

    def test_all_selection_reports_cap_instead_of_claiming_completion(self):
        first = tree_entry(filename="first", body=b"body")
        second = tree_entry(filename="second", body=b"tail", offset=4)
        prefix = b"vpcf_c\0particles\0"
        self.archive = Vpk(write_vpk(self.source, tree=first[:-3] + second[len(prefix):], body=b"bodytail"))
        report = self.run_inspection(names=None, maximum_files=1)
        self.assertEqual(report["coverage"]["matching"], 2)
        self.assertEqual(report["coverage"]["decoded"], 1)
        self.assertTrue(report["coverage"]["selectionTruncated"])
        self.assertFalse(report["coverage"]["complete"])

    def test_crc_failure_is_reported_without_running_decoder(self):
        raw = bytearray(self.archive.path.read_bytes())
        raw[-1] ^= 1
        self.archive.path.write_bytes(raw)
        report = self.run_inspection()
        self.assertEqual(report["coverage"]["failed"], 1)
        self.assertFalse(report["coverage"]["complete"])
        self.assertIn("CRC32", report["entries"][0]["error"])
        self.assertEqual(report["coverage"]["payloadBytesBudgeted"], 7)
        self.assertEqual(list((self.output / "data").iterdir()), [])

    def test_total_transcript_budget_stops_without_oversized_write(self):
        report = self.run_inspection(maximum_text_total=1)
        self.assertTrue(report["coverage"]["stoppedAtLimit"])
        self.assertEqual(report["coverage"]["textBytesWritten"], 0)
        self.assertFalse(report["coverage"]["complete"])

    def test_data_format_requires_particle_header_and_data_object(self):
        self.assertEqual(data_format(TRANSCRIPT), "vpcf61")
        for text in (b"no header", TRANSCRIPT.replace(b"vpcf61", b"vmat"), TRANSCRIPT.replace(b"{ _class", b"[ _class")):
            with self.subTest(text=text[:30]), self.assertRaises(InspectionError):
                data_format(text)

    def test_process_output_is_bounded_and_timeout_is_enforced(self):
        overflowing = bounded_process([sys.executable, "-c", "import sys; sys.stdout.write('x'*200000)"], 5, 1024, 1024)
        self.assertTrue(overflowing["outputLimitExceeded"])
        self.assertLessEqual(len(overflowing["stdout"]), 1024)
        timed = bounded_process([sys.executable, "-c", "import time; time.sleep(10)"], 1, 1024, 1024)
        self.assertTrue(timed["timedOut"])


if __name__ == "__main__":
    unittest.main()
