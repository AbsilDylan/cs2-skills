#!/usr/bin/env python3
"""Bounded capture tests using only short-lived Python child processes."""
from pathlib import Path
import sys
import tempfile
import time
import unittest

from process_limits import bounded_process


class ProcessLimitsTests(unittest.TestCase):
    def test_success_keeps_stdout_stderr_and_status(self):
        result = bounded_process([sys.executable, "-c", "import sys; print('out'); print('err',file=sys.stderr)"], 5, 1024, 1024)
        self.assertEqual(result["exitCode"], 0)
        self.assertFalse(result["timedOut"])
        self.assertFalse(result["outputLimitExceeded"])
        self.assertEqual(result["stdout"].strip(), b"out")
        self.assertEqual(result["stderr"].strip(), b"err")

    def test_stdout_and_stderr_overflow_are_bounded(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                started = time.monotonic()
                result = bounded_process([sys.executable, "-c", f"import sys,time; sys.{stream}.write('x'*200000); sys.{stream}.flush(); time.sleep(10)"], 5, 1024, 2048)
                self.assertTrue(result["outputLimitExceeded"])
                self.assertLessEqual(len(result["stdout"]), 1024)
                self.assertLessEqual(len(result["stderr"]), 2048)
                self.assertLess(time.monotonic() - started, 3)

    def test_direct_timeout_is_bounded(self):
        started = time.monotonic()
        result = bounded_process([sys.executable, "-c", "import time; time.sleep(10)"], 1, 1024, 1024)
        self.assertTrue(result["timedOut"])
        self.assertLess(time.monotonic() - started, 3)

    def test_small_overflow_is_detected_without_waiting_for_eof(self):
        started = time.monotonic()
        result = bounded_process([sys.executable, "-c", "import sys,time; sys.stdout.write('x'*2048); sys.stdout.flush(); time.sleep(10)"], 5, 1024, 1024)
        self.assertTrue(result["outputLimitExceeded"])
        self.assertFalse(result["timedOut"])
        self.assertLess(time.monotonic() - started, 3)

    def test_default_limits_match_inspection_caller(self):
        result = bounded_process([sys.executable, "-c", "print('default limits')"], 5)
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["stdout"].strip(), b"default limits")

    def test_descendant_inherited_pipes_share_deadline_and_are_terminated(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "descendant-survived"
            descendant = "import time; from pathlib import Path; time.sleep(2); Path(" + repr(str(marker)) + ").write_text('alive'); time.sleep(8)"
            parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(descendant) + "]); print('parent exited')"
            started = time.monotonic()
            result = bounded_process([sys.executable, "-c", parent], 1, 1024, 1024)
            self.assertTrue(result["timedOut"])
            self.assertEqual(result["exitCode"], 0)
            self.assertLess(time.monotonic() - started, 3)
            time.sleep(max(0, 2.3 - (time.monotonic() - started)))
            self.assertFalse(marker.exists(), "Descendant survived process-tree cleanup")

    def test_parent_closing_its_pipes_still_has_execution_deadline(self):
        started = time.monotonic()
        result = bounded_process([sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(10)"], 1, 1024, 1024)
        self.assertTrue(result["timedOut"])
        self.assertLess(time.monotonic() - started, 3)

    def test_invalid_bounds_and_missing_executable(self):
        for timeout, stdout, stderr in ((0, 1, 1), (1, -1, 1), (1, 1, -1)):
            with self.subTest(bounds=(timeout, stdout, stderr)), self.assertRaises(ValueError):
                bounded_process([sys.executable], timeout, stdout, stderr)
        with self.assertRaises(OSError):
            bounded_process(["this-executable-does-not-exist-for-process-limits-tests"], 1, 1024, 1024)


if __name__ == "__main__":
    unittest.main()
