#!/usr/bin/env python3
"""Portable texture-authoring tests; these do not invoke a native compiler."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


class TextureAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cs2skills-texture-")
        self.root = Path(self.temporary.name)
        self.script = Path(__file__).with_name("make_test_texture.py")
        self.evidence = json.loads(
            (self.script.parent.parent / "assets/native-texture-evidence.json").read_text()
        )

    def tearDown(self):
        self.temporary.cleanup()

    def generate(self, target, *arguments):
        return subprocess.run(
            [sys.executable, "-I", str(self.script), "--output", str(target), *arguments],
            capture_output=True, text=True, timeout=20,
        )

    def decode_tga(self, path):
        data = path.read_bytes()
        header = struct.unpack("<BBBHHBHHHHBB", data[:18])
        self.assertEqual(header[2], 2)
        self.assertEqual(header[10:12], (32, 0x28))
        width, height = header[8:10]
        self.assertEqual(len(data), 18 + width * height * 4)
        pixels = list(struct.iter_unpack("4B", data[18:]))
        self.assertTrue(all(b == g == r == 255 for b, g, r, a in pixels))
        self.assertEqual(min(a for b, g, r, a in pixels), 0)
        self.assertGreater(max(a for b, g, r, a in pixels), 0)
        return width, height

    def test_historical_sprite_and_sheet_source_inputs_reproduce(self):
        for fixture in self.evidence["outputs"]:
            kind = fixture["kind"]
            target = self.root / kind
            result = self.generate(
                target, "--kind", kind, "--size", "64", "--resource-path",
                f"materials/skill_tests/{kind}/{kind}.vtex",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for expected in fixture["inputs"]:
                with self.subTest(kind=kind, source=expected["path"]):
                    path = target / expected["path"]
                    self.assertEqual(path.stat().st_size, expected["bytes"])
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
                    if path.suffix == ".tga":
                        self.assertEqual(self.decode_tga(path), (64, 64))
            manifest = json.loads((target / "manifest.json").read_text())
            self.assertFalse(manifest["nativeCompilerVerified"])
            self.assertFalse(manifest["nativeRendered"])

    def test_trail_dimensions_and_custom_sheet_rate(self):
        target = self.root / "trail"
        result = self.generate(target, "--kind", "trail", "--size", "64")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.decode_tga(target / "trail.tga"), (64, 16))
        sheet = self.root / "sheet"
        result = self.generate(sheet, "--kind", "flipbook", "--size", "16",
                               "--frames", "3", "--fps", "12")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = (sheet / "flipbook.mks").read_text().splitlines()
        self.assertEqual(lines[:2], ["sequence 0", "LOOP"])
        frames = [line.split() for line in lines[2:]]
        self.assertEqual(len(frames), 3)
        self.assertTrue(all((sheet / row[1]).is_file() for row in frames))
        self.assertAlmostEqual(sum(float(row[2]) for row in frames), 3 / 12, places=7)

    def test_invalid_arguments_do_not_create_output_and_existing_output_survives(self):
        for index, arguments in enumerate((
            ("--resource-path", "../escape.vtex"),
            ("--resource-path", "materials/con.vtex"),
            ("--fps", "nan"),
            ("--frames", "1"),
            ("--kind", "flipbook", "--size", "2048", "--frames", "64"),
        )):
            target = self.root / f"invalid-{index}"
            result = self.generate(target, *arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(target.exists())
        target = self.root / "existing"
        target.mkdir()
        sentinel = target / "keep.txt"
        sentinel.write_bytes(b"existing content")
        result = self.generate(target)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_bytes(), b"existing content")
        self.assertEqual(list(target.iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main()
