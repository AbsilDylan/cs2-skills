#!/usr/bin/env python3
"""Synthetic behavioral tests for catalogue lookup and local native help."""

import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("schema_catalog.py")
spec = importlib.util.spec_from_file_location("schema_catalog", SCRIPT)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


def record(name, **values):
    return {"module": "particles", "name": name, **values}


def defaults(value):
    return [{"name": "MGetKV3ClassDefaults", "value": value}]


def field(name, type_value=None):
    return {"name": name, "offset": 4, "type": type_value or {"category": "builtin", "name": "float32"}, "metadata": [{"name": "MPropertyFriendlyName", "value": '"editor label"'}]}


def document():
    return {
        "generator": "synthetic-tests", "revision": 7, "version_date": "fixture-day", "version_time": "fixture-time",
        "classes": [
            record("Base", fields=[field("m_Base")], metadata=defaults({"m_Base": {"x": 1, "y": 2}, "large": "18446744073709551615"})),
            record("Left", parents=[{"module": "particles", "name": "Base", "offset": 8}], fields=[field("m_Left")], metadata=defaults({"m_Left": 2})),
            record("Right", parents=[{"module": "particles", "name": "Base"}], fields=[field("m_Right")], metadata=defaults({"m_Right": 3})),
            record("Wanted", parents=[{"module": "particles", "name": "Left"}, {"module": "particles", "name": "Right"}], fields=[
                field("m_Dependency", {"category": "atomic", "name": "CUtlVector", "inner": {"category": "ptr", "inner": {"category": "declared_class", "module": "external", "name": "Provider"}}}),
                field("m_Mode", {"category": "declared_enum", "module": "external", "name": "Modes"}),
                field("m_Curve", {"category": "atomic", "name": "OpaqueCurve"}),
            ], metadata=defaults({"m_Base": {"x": 9}, "m_Dependency": [], "m_Mode": "FIRST", "m_Curve": {"points": []}})),
            {"module": "external", "name": "Provider", "fields": [field("m_Provider")], "metadata": defaults({"m_Provider": "-nan"})},
        ],
        "enums": [
            {"module": "external", "name": "Modes", "members": [{"name": "FIRST", "value": 0}, {"name": "ALIAS", "value": 0}]},
            {"module": "particleslib", "name": "Unreferenced", "members": [{"name": "KEPT", "value": 2}]},
            {"module": "unrelated", "name": "NotSelected", "members": []},
        ],
    }


class CatalogueTests(unittest.TestCase):
    def generate(self, source=None):
        source = source or document()
        provenance = {"raw_json_sha256": "fixture-hash", "revision": 7, "version_date": "fixture-day", "version_time": "fixture-time"}
        return catalog.make_catalogue(source, provenance, "Synthetic game", "https://example.invalid/fixture.gz", SCRIPT)

    def reference(self, files, index, name, module="particles", kind="class"):
        item = next(item for item in index["records"] if item["name"] == name and item["module"] == module and item["kind"] == kind)
        return json.loads(files[item["path"]])

    def test_dependency_closure_all_parent_fields_and_first_parent_defaults(self):
        files, index = self.generate()
        self.assertEqual(index["counts"]["classes"], 5)
        self.assertEqual(index["counts"]["enums"], 2)
        wanted = self.reference(files, index, "Wanted")
        self.assertEqual([item["field"]["name"] for item in wanted["fields"]].count("m_Base"), 1)
        self.assertEqual([item["field"]["name"] for item in wanted["fields"]], ["m_Base", "m_Left", "m_Right", "m_Dependency", "m_Mode", "m_Curve"])
        self.assertEqual(wanted["defaults"]["values"]["m_Base"], {"x": 9})
        self.assertNotIn("m_Right", wanted["defaults"]["values"])
        self.assertEqual(wanted["defaults"]["values"]["large"], "18446744073709551615")
        self.assertEqual(wanted["defaults"]["sources"]["m_Left"], {"module": "particles", "name": "Left"})
        self.assertEqual(wanted["declaration"]["metadata"], document()["classes"][3]["metadata"])
        self.assertEqual(wanted["fields"][0]["field"]["metadata"], document()["classes"][0]["fields"][0]["metadata"])
        self.assertEqual(self.reference(files, index, "Provider", "external")["defaults"]["values"]["m_Provider"], "-nan")
        self.assertEqual(self.reference(files, index, "Modes", "external", "enum")["declaration"]["members"][1]["value"], 0)
        atoms = json.loads(files["atomic-types.json"])["types"]
        self.assertEqual({item["name"] for item in atoms}, {"CUtlVector", "OpaqueCurve"})
        self.assertFalse(any(item["name"] == "OpaqueCurve" for item in index["records"]))

    def test_missing_unreadable_and_explicit_empty_defaults_remain_distinct(self):
        source = {"classes": [record("Missing"), record("Unreadable", metadata=defaults("Could not parse KV3 Defaults")), record("Empty", metadata=defaults({})), record("Partial", parents=[{"module": "particles", "name": "Missing"}], metadata=defaults({"value": 1}))], "enums": []}
        files, index = self.generate(source)
        self.assertEqual(self.reference(files, index, "Missing")["defaults"]["status"], "unavailable")
        self.assertEqual(self.reference(files, index, "Unreadable")["defaults"]["issues"][0]["code"], "defaults-unreadable")
        self.assertEqual(self.reference(files, index, "Empty")["defaults"]["status"], "available")
        self.assertEqual(self.reference(files, index, "Partial")["defaults"]["status"], "partial")
        self.assertEqual(self.reference(files, index, "Partial")["defaults"]["values"], {"value": 1})

    def test_collisions_and_unscoped_or_missing_type_references_are_not_guessed(self):
        source = document()
        source["classes"][3]["fields"].extend([field("m_Base"), field("unknown", {"category": "declared_class", "name": "Provider"}), field("missing", {"category": "declared_enum", "module": "external", "name": "Absent"})])
        files, index = self.generate(source)
        wanted = self.reference(files, index, "Wanted")
        self.assertEqual(wanted["field_name_collisions"][0]["name"], "m_Base")
        self.assertEqual(index["counts"]["unresolved_declared_references"], 2)
        self.assertEqual({item["status"] for item in index["unresolved_references"]}, {"missing", "unscoped"})

    def test_invalid_inheritance_fails_and_generated_paths_stay_inside_destination(self):
        for source in [
            {"classes": [record("Loop", parents=[{"module": "particles", "name": "Loop"}])], "enums": []},
            {"classes": [record("Missing", parents=[{"module": "particles", "name": "Absent"}])], "enums": []},
        ]:
            with self.assertRaises(catalog.CatalogError):
                self.generate(source)
        with tempfile.TemporaryDirectory() as directory:
            for relative in ["../escape.json", "/escape.json", "classes/../../escape.json", "classes\\escape.json", "C:/escape.json"]:
                with self.assertRaises(catalog.CatalogError):
                    catalog.safe_path(Path(directory), relative)
        self.assertNotIn("/", catalog.token("Unsafe::Thing<Type/Value>"))

    def test_gzip_hashes_deterministic_generation_integrity_and_portable_cli(self):
        with tempfile.TemporaryDirectory(prefix="portable schema ") as temporary:
            directory = Path(temporary)
            raw = json.dumps(document(), ensure_ascii=False).encode("utf-8")
            packed = gzip.compress(raw, mtime=0)
            filename = directory / "fixture.json.gz"
            filename.write_bytes(packed)
            _, provenance = catalog.load_input(filename)
            self.assertEqual(provenance["input_sha256"], hashlib.sha256(packed).hexdigest())
            self.assertEqual(provenance["raw_json_sha256"], hashlib.sha256(raw).hexdigest())
            destination = directory / "references"
            build = [sys.executable, "-B", str(SCRIPT), "build", "--input", str(filename), "--game", "Fixture game", "--source-url", "https://example.invalid/fixture.gz", "--output", str(destination)]
            built = subprocess.run(build, capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, built.stderr)
            catalogue_text = (destination / "catalogue.md").read_text(encoding="utf-8")
            self.assertIn("## Contents\n\n- [Classes](#classes)\n- [Enums](#enums)\n", catalogue_text)
            self.assertEqual(catalogue_text.count("## Contents"), 1)
            check = subprocess.run(build + ["--check"], capture_output=True, check=False)
            self.assertEqual(check.returncode, 0, check.stderr)
            query = [sys.executable, "-B", str(SCRIPT), "query", "--catalogue", str(destination), "--module", "particles", "--class", "Wanted"]
            result = subprocess.run(query, cwd=temporary, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["records"][0]["identity"]["name"], "Wanted")
            selected = subprocess.run(query + ["--field", "m_Base"], capture_output=True, check=False)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            field_record = json.loads(selected.stdout)["records"][0]
            self.assertEqual(field_record["defaults"]["values"], {"m_Base": {"x": 9}})
            self.assertEqual(field_record["fields"][0]["declared_in"]["name"], "Base")
            self.assertEqual(field_record["fields"][0]["field"]["metadata"], document()["classes"][0]["fields"][0]["metadata"])
            summary = subprocess.run(query + ["--summary"], capture_output=True, check=False)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertEqual(len(json.loads(summary.stdout)["records"][0]["fields"]), 6)
            self.assertNotIn("defaults", json.loads(summary.stdout)["records"][0])
            absent_field = subprocess.run(query + ["--field", "m_Absent"], capture_output=True, check=False)
            self.assertEqual(absent_field.returncode, 2)
            self.assertEqual(absent_field.stdout, b"")
            oversized = subprocess.run(query + ["--max-output-bytes", "1024"], capture_output=True, check=False)
            self.assertEqual(oversized.returncode, 2)
            self.assertEqual(oversized.stdout, b"")
            self.assertIn(b"No fields/defaults were truncated", oversized.stderr)
            index = catalog.verify(destination, SCRIPT)
            record_file = catalog.safe_path(destination, index["records"][0]["path"])
            record_file.write_bytes(record_file.read_bytes() + b" ")
            with self.assertRaisesRegex(catalog.CatalogError, "hash/length mismatch"):
                catalog.verify(destination, SCRIPT)

    def test_combined_native_help_is_portable_exact_and_keeps_separate_provenance(self):
        with tempfile.TemporaryDirectory(prefix="native help isolated ") as temporary:
            directory = Path(temporary)
            filename = directory / "fixture.json"
            filename.write_text(json.dumps(document()), encoding="utf-8")
            destination = directory / "references"
            command = [sys.executable, "-I", "-S", str(SCRIPT)]
            built = subprocess.run(command + ["build", "--input", str(filename), "--game", "Fixture game", "--source-url", "https://example.invalid/fixture", "--output", str(destination)], capture_output=True, check=False)
            self.assertEqual(built.returncode, 0, built.stderr)
            help_file = directory / "native-help.txt"
            help_file.write_text('"lang" { "Tokens" { "Element.Wanted:help" "Synthetic class documentation" "Attribute.Wanted.m_Base:help" "Synthetic contextual help" "Attribute.Base.m_Base:shorthelp" "Synthetic declaring help" } }', encoding="utf-8")
            query = command + ["query", "--catalogue", str(destination), "--module", "particles", "--class", "Wanted", "--field", "m_Base", "--help-file", str(help_file)]
            result = subprocess.run(query, cwd=temporary, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["native_help_provenance"]["sha256"], hashlib.sha256(help_file.read_bytes()).hexdigest())
            self.assertEqual(report["records"][0]["defaults"]["values"], {"m_Base": {"x": 9}})
            help_binding = report["records"][0]["native_help"]["fields"][0]
            self.assertEqual(help_binding["contextual"]["help"]["key"], "Attribute.Wanted.m_Base:help")
            self.assertEqual(help_binding["declaring_class"]["shorthelp"]["key"], "Attribute.Base.m_Base:shorthelp")
            help_file.write_text('"lang" { "Tokens" { "broken"', encoding="utf-8")
            broken = subprocess.run(query, cwd=temporary, capture_output=True, check=False)
            self.assertEqual(broken.returncode, 2)
            self.assertEqual(broken.stdout, b"")
            self.assertNotIn(b"Traceback", broken.stderr)


if __name__ == "__main__":
    unittest.main()
