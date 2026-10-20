#!/usr/bin/env python3
"""Corpus-level integrity and regression checks, without game or network access."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_observations import EXTREMA_CORRECTION, audit, numeric_example
from query_observations import (
    CLASS_SCHEMA, DEFAULT_REFERENCES, INDEX_SCHEMA,
    INCOMPLETE_EXTREMA_GENERATOR_SHA256, query,
)


class ObservationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.refs = Path(self.temp.name)
        self.relative = "observations/cs2/example.json"
        self.record_path = self.refs / self.relative
        self.record_path.parent.mkdir(parents=True)
        self.witness = "particles/example.vpcf_c"
        self.record = {"schema": CLASS_SCHEMA, "game": "cs2", "steamBuildId": "123",
                       "classObservation": {"class": "C_OP_Example", "stage": "m_Operators",
                       "instances": 1, "witnesses": [self.witness], "fields": {
                           "m_nControlPoint": {"occurrences": 2, "kinds": {"scalar": 2},
                                              "examples": [{"$bigint": "0"}],
                                              "witness": self.witness}}}}
        self.index = {"schema": INDEX_SCHEMA, "summary": {"uniqueClassesAcrossGames": 1},
                      "games": [{"game": "cs2", "identity": {"steamBuildId": "123"},
                      "coverage": {"classStagePairs": 1, "uniqueClasses": 1, "classFieldPaths": 1},
                      "classFiles": {}, "witnesses": {self.witness: {
                          "bytes": 20, "sha256": "a" * 64, "crc32": "0x12345678"}}}]}
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        raw = json.dumps(self.record).encode()
        self.record_path.write_bytes(raw)
        self.index["games"][0]["classFiles"]["m_Operators:C_OP_Example"] = {
            "path": self.relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        (self.refs / "native-vpk-observations.json").write_text(json.dumps(self.index))

    def field(self):
        return self.record["classObservation"]["fields"]["m_nControlPoint"]

    def test_historical_bigint_omission_is_detected(self):
        self.field().update(observedMin=2, observedMax=17)
        self.save()
        result = audit(self.refs)
        self.assertFalse(result["metadataValid"])
        self.assertTrue(any("outside reported extrema" in issue["message"] for issue in result["issues"]))

    def test_large_integer_comparison_keeps_precision(self):
        self.assertEqual(numeric_example({"$bigint": "18446744073709551615"}), 18446744073709551615)
        self.assertIsNone(numeric_example(True))

    def test_corrected_snapshot_rejects_even_plausible_extrema(self):
        self.index["metadataCorrections"] = [{"id": EXTREMA_CORRECTION}]
        self.field().update(observedMin=0, observedMax=17)
        self.save()
        self.assertTrue(any("Withdrawn numeric extrema" in issue["message"] for issue in audit(self.refs)["issues"]))

    def test_missing_witness_and_bad_occurrence_counts_are_detected(self):
        self.field().update(witness="particles/missing.vpcf_c", occurrences=3)
        self.save()
        messages = [issue["message"] for issue in audit(self.refs)["issues"]]
        self.assertTrue(any("absent from" in message for message in messages))
        self.assertTrue(any("kind counts" in message for message in messages))

    def test_coverage_and_build_mismatches_are_detected(self):
        self.index["games"][0]["coverage"]["classFieldPaths"] = 7
        self.record["steamBuildId"] = "999"
        self.save()
        self.assertEqual(audit(self.refs)["issueCount"], 2)

    def test_unindexed_observation_is_detected(self):
        (self.record_path.parent / "stray.json").write_text("{}")
        self.assertFalse(audit(self.refs)["metadataValid"])

    def test_query_surfaces_correction_and_unknown_numeric_extrema(self):
        self.index["metadataCorrections"] = [{"id": EXTREMA_CORRECTION,
                                              "numericExtremaStatus": "withdrawn-incomplete"}]
        self.save()
        result = query(self.refs, "cs2", class_name="C_OP_Example", field="m_nControlPoint")
        self.assertEqual(result["metadataCorrections"][0]["numericExtremaStatus"], "withdrawn-incomplete")
        self.assertNotIn("observedMin", result["results"][0]["field"]["observation"])
        self.assertEqual(result["results"][0]["field"]["observation"]["examples"], [{"$bigint": "0"}])

    def test_query_suppresses_extrema_in_an_uncorrected_historical_snapshot(self):
        self.index["method"] = {"scriptSha256": INCOMPLETE_EXTREMA_GENERATOR_SHA256}
        self.field().update(observedMin=2, observedMax=17)
        self.save()
        result = query(self.refs, "cs2", class_name="C_OP_Example", field="m_nControlPoint")
        observation = result["results"][0]["field"]["observation"]
        self.assertNotIn("observedMin", observation)
        self.assertNotIn("observedMax", observation)
        self.assertEqual(observation["examples"], [{"$bigint": "0"}])
        self.assertIn("unavailable", result["numericExtremaStatus"])

    def test_all_bundled_records_match_their_index_and_witnesses(self):
        result = audit(DEFAULT_REFERENCES)
        self.assertTrue(result["metadataValid"], result["issues"][:5])
        self.assertTrue(result["numericExtremaWithdrawn"])
        self.assertFalse(result["payloadsVerified"])
        self.assertFalse(result["runtimeBehaviorVerified"])


if __name__ == "__main__":
    unittest.main()
