#!/usr/bin/env python3
"""Synthetic portable-query tests: no game install or third-party package required."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from query_observations import CLASS_SCHEMA, INDEX_SCHEMA, MAX_FILE_BYTES, QueryError, encode_report, query


class ObservationQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.refs = self.root / "references"
        self.refs.mkdir()
        self.relative = "observations/cs2/example.json"
        self.path = self.refs / self.relative
        self.path.parent.mkdir(parents=True)
        self.document = {
            "schema": CLASS_SCHEMA, "game": "cs2", "classObservation": {
                "class": "C_OP_Example", "stage": "m_Renderers", "instances": 3,
                "witnesses": ["particles/original.vpcf_c"],
                "fields": {"m_flAlpha": {"occurrences": 2, "kinds": {"scalar": 2},
                                          "examples": [0.5], "witness": "particles/original.vpcf_c",
                                          "observedMin": 0.1, "observedMax": 0.5},
                           "m_vecTexturesInput[].m_hTexture": {"occurrences": 1, "kinds": {"resource": 1},
                                                              "examples": ["materials/fx/original.vtex"],
                                                              "witness": "particles/original.vpcf_c"}},
            },
        }
        raw = json.dumps(self.document).encode()
        self.path.write_bytes(raw)
        self.index = {
            "schema": INDEX_SCHEMA, "observedOn": "2026-10-15", "games": [{
                "game": "cs2", "identity": {"steamBuildId": "123"}, "coverage": {"decoded": 3},
                "classFiles": {"m_Renderers:C_OP_Example": {"path": self.relative, "bytes": len(raw),
                                                          "sha256": hashlib.sha256(raw).hexdigest()}},
                "witnesses": {"particles/original.vpcf_c": {"bytes": 123, "sha256": "a" * 64, "crc32": "0x12345678"}},
            }],
        }
        self.write_index()

    def tearDown(self):
        self.temp.cleanup()

    def write_index(self):
        (self.refs / "native-vpk-observations.json").write_text(json.dumps(self.index), encoding="utf-8")

    def descriptor(self):
        return self.index["games"][0]["classFiles"]["m_Renderers:C_OP_Example"]

    def test_default_class_query_is_verified_summary_not_field_dump(self):
        result = query(self.refs, "cs2", class_name="C_OP_Example", limit=1)
        row = result["results"][0]
        self.assertTrue(result["classFilesVerified"])
        self.assertEqual(row["fieldCount"], 2)
        self.assertEqual(row["fieldNames"], ["m_flAlpha"])
        self.assertTrue(row["fieldNamesTruncated"])
        self.assertNotIn("fields", row)
        self.assertTrue(row["classFile"]["verified"])
        self.assertEqual(row["witnesses"]["particles/original.vpcf_c"]["sha256"], "a" * 64)

    def test_exact_field_preserves_observation_and_payload_provenance(self):
        result = query(self.refs, "cs2", class_name="C_OP_Example", stage="m_Renderers", field="m_vecTexturesInput[].m_hTexture")
        row = result["results"][0]
        self.assertEqual(row["field"]["observation"]["examples"], ["materials/fx/original.vtex"])
        self.assertEqual(row["witnesses"]["particles/original.vpcf_c"]["crc32"], "0x12345678")
        self.assertIn("compiled-asset-observation", encode_report(result))

    def test_search_is_bounded_index_only_and_declares_no_class_file_verification(self):
        self.path.unlink()
        result = query(self.refs, "cs2", search="EXAMPLE", limit=1)
        self.assertEqual(result["matchedClasses"], 1)
        self.assertFalse(result["classFilesVerified"])
        self.assertNotIn("fields", result["results"][0])
        self.assertEqual(query(self.refs, "cs2", search="not-observed")["matchedClasses"], 0)

    def test_tampered_same_size_class_payload_is_rejected(self):
        data = self.path.read_bytes().replace(b"0.5", b"0.7")
        self.path.write_bytes(data)
        with self.assertRaisesRegex(QueryError, "SHA-256 mismatch"):
            query(self.refs, "cs2", class_name="C_OP_Example")

    def test_mismatched_size_is_rejected(self):
        self.descriptor()["bytes"] += 1
        self.write_index()
        with self.assertRaisesRegex(QueryError, "size or SHA-256 mismatch"):
            query(self.refs, "cs2", class_name="C_OP_Example")

    def test_paths_cannot_escape_references(self):
        for name in ("../outside.json", "/outside.json", "observations/../../outside.json", "C:/outside.json", "observations\\example.json", "observations/\0example.json"):
            with self.subTest(name=name):
                self.descriptor()["path"] = name
                self.write_index()
                with self.assertRaisesRegex(QueryError, "Unsafe class-file path"):
                    query(self.refs, "cs2", class_name="C_OP_Example")

    def test_metadata_file_bound_applies_before_opening_descriptor_target(self):
        self.descriptor()["bytes"] = MAX_FILE_BYTES + 1
        self.write_index()
        with self.assertRaisesRegex(QueryError, "4 MiB"):
            query(self.refs, "cs2", class_name="C_OP_Example")

    def test_wrong_class_identity_is_rejected_even_with_correct_content_hash(self):
        self.document["classObservation"]["class"] = "C_OP_Other"
        raw = json.dumps(self.document).encode()
        self.path.write_bytes(raw)
        self.descriptor().update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.write_index()
        with self.assertRaisesRegex(QueryError, "does not match"):
            query(self.refs, "cs2", class_name="C_OP_Example")

    def test_missing_class_or_field_is_explicit(self):
        with self.assertRaisesRegex(QueryError, "not observed"):
            query(self.refs, "cs2", class_name="C_OP_Other")
        with self.assertRaisesRegex(QueryError, "field not observed"):
            query(self.refs, "cs2", class_name="C_OP_Example", field="m_Absent")

    def test_oversized_output_errors_instead_of_truncating_json(self):
        with self.assertRaisesRegex(QueryError, "128 KiB"):
            encode_report({"text": "é" * (128 * 1024)})


if __name__ == "__main__":
    unittest.main()
