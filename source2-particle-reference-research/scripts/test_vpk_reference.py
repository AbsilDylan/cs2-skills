#!/usr/bin/env python3
"""Synthetic format and extraction tests. Run: python -m unittest discover -s <scripts> -p test_vpk_reference.py"""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from vpk_reference import Entry, INLINE_ARCHIVE, MAX_TREE_BYTES, SIGNATURE, Vpk, VpkError, extract, inventory


def tree_entry(folder="particles", filename="original", extension="vpcf_c", body=b"body", preload=b"pre", archive=INLINE_ARCHIVE, offset=0):
    return (extension.encode() + b"\0" + folder.encode() + b"\0" + filename.encode() + b"\0"
            + struct.pack("<IHHIIH", zlib.crc32(preload + body), len(preload), archive, offset, len(body), 0xFFFF)
            + preload + b"\0\0\0")


def write_vpk(folder, tree=None, body=b"body", version=2, name="pak01_dir.vpk"):
    tree = tree_entry(body=body) if tree is None else tree
    header = struct.pack("<III", SIGNATURE, version, len(tree))
    if version == 2:
        header += struct.pack("<IIII", len(body), 0, 0, 0)
    path = folder / name
    path.write_bytes(header + tree + body)
    return path


class VpkReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_v1_and_v2_inline_payload_combines_preload_and_checks_crc(self):
        for version in (1, 2):
            with self.subTest(version=version):
                vpk = Vpk(write_vpk(self.source, version=version))
                self.assertEqual(vpk.read(vpk.find("particles/ORIGINAL.vpcf_c")), b"prebody")
                self.assertEqual(vpk.provenance()["directoryIndexBytes"], (12 if version == 1 else 28) + len(tree_entry()))

    def test_external_chunk_offset_and_preload(self):
        path = write_vpk(self.source, tree=tree_entry(archive=4, offset=5), body=b"")
        (self.source / "pak01_004.vpk").write_bytes(b"skip!body")
        vpk = Vpk(path)
        self.assertEqual(vpk.read(vpk.find("particles/original.vpcf_c")), b"prebody")

    def test_preload_only_does_not_require_a_chunk_file(self):
        path = write_vpk(self.source, tree=tree_entry(archive=4, body=b""), body=b"")
        vpk = Vpk(path)
        self.assertEqual(vpk.read(vpk.find("particles/original.vpcf_c")), b"pre")

    def test_inventory_filters_without_losing_global_counts(self):
        vpk = Vpk(write_vpk(self.source))
        result = inventory(vpk, [".VPCF_C"], "PARTICLES/", 0)
        self.assertEqual(result["matchedEntries"], 1)
        self.assertEqual(result["extensionCounts"], {"vpcf_c": 1})
        self.assertTrue(result["truncated"])
        self.assertEqual(result["entries"], [])
        self.assertFalse(vpk.provenance()["signatureVerified"])
        self.assertFalse(result["payloadsVerified"])
        self.assertEqual(inventory(vpk, ["vpcf_c"], "", 1, "ORIGINAL")["matchedEntries"], 1)
        self.assertEqual(inventory(vpk, ["vpcf_c"], "", 1, "smoke")["matchedEntries"], 0)

    def test_targeted_extraction_is_fresh_and_has_verifiable_manifest(self):
        vpk = Vpk(write_vpk(self.source))
        destination = self.root / "work"
        report = extract(vpk, ["particles/original.vpcf_c"], destination)
        self.assertEqual((destination / "particles/original.vpcf_c").read_bytes(), b"prebody")
        self.assertEqual(json.loads((destination / "vpk-reference-manifest.json").read_text()), report)
        self.assertTrue(report["entries"][0]["crc32Verified"])
        with self.assertRaisesRegex(VpkError, "new directory"):
            extract(vpk, ["particles/original.vpcf_c"], destination)

    def test_bad_crc_and_out_of_range_body_produce_no_output(self):
        path = write_vpk(self.source, body=b"body")
        changed = bytearray(path.read_bytes())
        changed[-1] ^= 1
        path.write_bytes(changed)
        vpk = Vpk(path)
        with self.assertRaisesRegex(VpkError, "CRC32 mismatch"):
            extract(vpk, ["particles/original.vpcf_c"], self.root / "bad")
        self.assertFalse((self.root / "bad").exists())
        path = write_vpk(self.source, tree=tree_entry(offset=500))
        vpk = Vpk(path)
        with self.assertRaisesRegex(VpkError, "inline data section"):
            vpk.read(vpk.find("particles/original.vpcf_c"))

    def test_truncated_and_unbounded_trees_are_rejected(self):
        path = self.source / "bad.vpk"
        for data in (b"", struct.pack("<III", SIGNATURE, 1, MAX_TREE_BYTES + 1),
                     struct.pack("<III", SIGNATURE, 1, 1) + b"a"):
            with self.subTest(data=data):
                path.write_bytes(data)
                with self.assertRaises(VpkError):
                    Vpk(path)

    def test_path_traversal_and_aliases_are_rejected(self):
        for folder, filename in (("../particles", "x"), ("/particles", "x"), ("particles", "../x"), ("particles", "C:x")):
            with self.subTest(folder=folder, filename=filename):
                with self.assertRaises(VpkError):
                    Vpk(write_vpk(self.source, tree=tree_entry(folder=folder, filename=filename)))
        first = tree_entry(filename="A")
        second = tree_entry(filename="a")
        # One extension group, one folder group, two names.
        group_prefix = b"vpcf_c\0particles\0"
        duplicate_tree = first[:-3] + second[len(group_prefix):]
        with self.assertRaisesRegex(VpkError, "case-aliased"):
            Vpk(write_vpk(self.source, tree=duplicate_tree))

    def test_bad_terminator_and_v2_section_sizes_are_rejected(self):
        tree = bytearray(tree_entry())
        metadata = tree.index(b"original\0") + len(b"original\0")
        tree[metadata + 16:metadata + 18] = b"\0\0"
        with self.assertRaisesRegex(VpkError, "terminator"):
            Vpk(write_vpk(self.source, tree=tree))
        path = write_vpk(self.source)
        data = bytearray(path.read_bytes())
        struct.pack_into("<I", data, 12, 100000)
        path.write_bytes(data)
        with self.assertRaisesRegex(VpkError, "declared sections"):
            Vpk(path)

    def test_extract_refuses_source_directory_and_windows_reserved_paths(self):
        vpk = Vpk(write_vpk(self.source))
        with self.assertRaisesRegex(VpkError, "outside the source"):
            extract(vpk, ["particles/original.vpcf_c"], self.source / "new")
        for filename in ("con", "con ", "COM¹", "LPT²", "CONOUT$"):
            with self.subTest(filename=filename):
                path = write_vpk(self.source, tree=tree_entry(filename=filename))
                vpk = Vpk(path)
                with self.assertRaisesRegex(VpkError, "portably"):
                    extract(vpk, list(vpk.entries), self.root / "work")
                self.assertFalse((self.root / "work").exists())

    def test_extract_selection_is_bounded_and_rejects_duplicates(self):
        vpk = Vpk(write_vpk(self.source))
        for names in ([], ["particles/original.vpcf_c"] * 65, ["particles/original.vpcf_c"] * 2):
            with self.subTest(count=len(names)), self.assertRaises(VpkError):
                extract(vpk, names, self.root / "work")

    def test_payload_size_bound_applies_before_read(self):
        vpk = Vpk(write_vpk(self.source))
        with self.assertRaisesRegex(VpkError, "64 MiB"):
            vpk.read(Entry("particles/big.vpcf_c", 0, INLINE_ARCHIVE, 0, 64 * 1024 * 1024 + 1, b""))

    def test_manifest_filename_and_directory_are_reserved_before_any_write(self):
        for folder, filename, extension in ((" ", "vpk-reference-manifest", "json"),
                                             ("VPK-reference-manifest.JSON", "item", "vpcf_c")):
            with self.subTest(folder=folder):
                vpk = Vpk(write_vpk(self.source, tree=tree_entry(folder=folder, filename=filename, extension=extension)))
                with self.assertRaisesRegex(VpkError, "manifest"):
                    extract(vpk, list(vpk.entries), self.root / "work")
                self.assertFalse((self.root / "work").exists())

    def test_root_files_without_extension_are_supported(self):
        path = write_vpk(self.source, tree=tree_entry(folder=" ", filename="readme", extension=" "))
        vpk = Vpk(path)
        self.assertEqual(vpk.read(vpk.find("readme")), b"prebody")


if __name__ == "__main__":
    unittest.main()
