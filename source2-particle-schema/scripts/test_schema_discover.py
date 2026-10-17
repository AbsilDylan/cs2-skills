#!/usr/bin/env python3
"""Portable discovery tests using synthetic schema records."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("schema_discover.py")
SPEC = importlib.util.spec_from_file_location("schema_discover_test_subject", SCRIPT)
discover = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discover)
catalog = discover.catalog


def field(name, type_value=None):
    return {"name": name, "offset": 4, "type": type_value or {"category": "builtin", "name": "float32"}, "metadata": [{"name": "MPropertyFriendlyName", "value": "Synthetic metadata"}]}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="schema discovery ")
        self.root = Path(self.temp.name)
        self.refs = self.root / "references"
        source = {
            "classes": [
                {"module": "particles", "name": "Base", "fields": [field("m_flAlpha")], "metadata": [{"name": "MGetKV3ClassDefaults", "value": {"m_flAlpha": 1}}]},
                {"module": "particles", "name": "Wanted", "parents": [{"module": "particles", "name": "Base"}], "fields": [field("m_nSequence"), field("m_hTexture"), field("m_vecTextures", {"category": "atomic", "name": "CUtlLeanVector", "inner": {"category": "declared_class", "module": "particleslib", "name": "Provider"}, "size": 16, "alignment": 8})]},
                {"module": "particleslib", "name": "Provider", "fields": []},
                {"module": "particleslib", "name": "Wanted", "fields": []},
            ],
            "enums": [],
        }
        provenance = {"raw_json_sha256": "synthetic-snapshot", "revision": 7, "version_date": "synthetic-day", "version_time": "synthetic-time"}
        files, self.index = catalog.make_catalogue(source, provenance, "Synthetic game", "https://example.invalid/schema.json", discover.CATALOG_SCRIPT)
        for relative, data in files.items():
            path = self.refs / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def tearDown(self):
        self.temp.cleanup()

    def query(self, **kwargs):
        return discover.discover(self.refs, "particles", "Wanted", **kwargs)

    def test_pages_cover_every_field_in_order_with_declaring_and_inherited_identity(self):
        first = self.query(limit=2)
        last = self.query(limit=2, offset=first["next_offset"])
        self.assertEqual(first["total_fields"], 4)
        self.assertEqual(first["total"], 4)
        self.assertEqual(first["next_offset"], 2)
        self.assertIsNone(last["next_offset"])
        fields = first["fields"] + last["fields"]
        self.assertEqual([entry["name"] for entry in fields], ["m_flAlpha", "m_nSequence", "m_hTexture", "m_vecTextures"])
        self.assertEqual(fields[0]["declared_in"], {"module": "particles", "name": "Base"})
        self.assertTrue(fields[0]["inherited"])
        self.assertFalse(fields[1]["inherited"])
        self.assertEqual(fields[1]["declared_in"]["name"], "Wanted")

    def test_case_insensitive_name_filter_and_empty_or_exhausted_pages(self):
        page = self.query(contains="TEXTURE", limit=1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["fields"][0]["name"], "m_hTexture")
        self.assertEqual(self.query(contains="texture", offset=1)["fields"][0]["name"], "m_vecTextures")
        self.assertEqual(self.query(contains="absent")["fields"], [])
        self.assertEqual(self.query(contains="float32")["total"], 0)
        self.assertEqual(self.query(offset=999)["fields"], [])
        self.assertIsNone(self.query(offset=999)["next_offset"])

    def test_module_class_identity_is_exact_without_fallback(self):
        other = discover.discover(self.refs, "particleslib", "Wanted")
        self.assertEqual(other["identity"], {"module": "particleslib", "name": "Wanted"})
        self.assertEqual(other["total_fields"], 0)
        for module, name in [("missing", "Wanted"), ("particles", "wanted")]:
            with self.assertRaisesRegex(catalog.CatalogError, "Exact class identity absent"):
                discover.discover(self.refs, module, name)

    def test_provenance_once_and_discovery_is_explicitly_partial(self):
        page = self.query()
        self.assertTrue(page["partial"])
        self.assertIn("not a complete type tree", page["selection"])
        self.assertIn("--field", page["selection"])
        self.assertEqual(page["provenance"]["raw_json_sha256"], "synthetic-snapshot")
        self.assertEqual(page["provenance"]["revision"], 7)
        self.assertEqual(page["provenance"]["index_content_sha256"], self.index["index_content_sha256"])
        self.assertEqual(json.dumps(page).count('"provenance"'), 1)
        for entry in page["fields"]:
            self.assertEqual(set(entry), {"name", "native_type", "declared_in", "inherited"})

    def test_page_limits_and_offsets(self):
        self.assertEqual(self.query()["limit"], 20)
        self.assertEqual(self.query(limit=100)["limit"], 100)
        for options in [{"limit": 0}, {"limit": 101}, {"limit": -1}, {"offset": -1}]:
            with self.assertRaisesRegex(catalog.CatalogError, "limit 1..100"):
                self.query(**options)

    def test_native_type_labels_keep_categories_modules_and_container_shape(self):
        inner = {"category": "declared_class", "module": "particleslib", "name": "Provider"}
        label = discover.native_type_label
        self.assertEqual(label(inner), "class particleslib/Provider")
        self.assertEqual(label({"category": "declared_enum", "module": "particles", "name": "Modes"}), "enum particles/Modes")
        self.assertEqual(label({"category": "ptr", "inner": inner}), "ptr<class particleslib/Provider>")
        self.assertEqual(label({"category": "fixed_array", "count": 8, "inner": {"category": "builtin", "name": "char"}}), "array[8]<char>")
        self.assertEqual(label({"category": "bitfield", "count": 1}), "bitfield[1]")
        self.assertEqual(self.query()["fields"][-1]["native_type"], "atomic CUtlLeanVector<class particleslib/Provider>")
        self.assertIn("<unscoped>", label({"category": "declared_class", "name": "Unknown"}))
        self.assertIn("unknown category", label({"category": "future", "name": "Unresolved"}))

    def test_index_and_selected_reference_sha_are_checked(self):
        item = next(entry for entry in self.index["records"] if entry["name"] == "Wanted" and entry["module"] == "particles")
        path = self.refs / item["path"]
        before = path.read_bytes()
        path.write_bytes(before + b" ")
        with self.assertRaisesRegex(catalog.CatalogError, "hash/length mismatch"):
            self.query()
        path.write_bytes(before)
        invalid_index = dict(self.index, counts={"classes": 999})
        (self.refs / "catalog-index.json").write_bytes(catalog.encoded(invalid_index))
        with self.assertRaisesRegex(catalog.CatalogError, "index content digest mismatch"):
            self.query()
        invalid_index = {**self.index, "generator": {**self.index["generator"], "sha256": "0" * 64}}
        invalid_index["index_content_sha256"] = catalog.digest(catalog.canonical({key: value for key, value in invalid_index.items() if key != "index_content_sha256"}))
        (self.refs / "catalog-index.json").write_bytes(catalog.encoded(invalid_index))
        with self.assertRaisesRegex(catalog.CatalogError, "Generator script differs"):
            self.query()

    def test_isolated_cli_works_outside_skill_and_errors_emit_no_partial_stdout(self):
        command = [sys.executable, "-I", "-S", "-B", str(SCRIPT), "--catalogue", str(self.refs), "--module", "particles", "--class", "Wanted"]
        result = subprocess.run(command + ["--contains", "texture", "--limit", "1"], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["next_offset"], 1)
        self.assertEqual(result.stdout.count(b"\n"), 1)
        for args in [["--limit", "101"], ["--offset", "-1"], ["--class", "Missing"]]:
            failed = subprocess.run(command + args, cwd=self.root, capture_output=True)
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stdout, b"")
            self.assertNotIn(b"Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
