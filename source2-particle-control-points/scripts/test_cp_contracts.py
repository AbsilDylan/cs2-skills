#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("cp_contracts.py")
spec = importlib.util.spec_from_file_location("cp_contracts", SCRIPT)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class NativeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogue = cp.load_catalogue()

    def field(self, name, field, module="particles"):
        return cp.query(self.catalogue, module, name, "class", field)

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)["result"]

    def test_list_respects_explicit_module_and_name_filters(self):
        result = self.cli("--list", "--module", "animationsystem", "--limit", "500")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["records"][0]["name"], "ParticleAttachment_t")
        self.assertTrue(all(record["module"] == "animationsystem" for record in result["records"]))
        empty = self.cli("--list", "--module", "animationsystem", "--contains", "ControlPoint")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["records"], [])

    def test_list_without_module_still_discovers_dependencies_across_modules(self):
        result = self.cli("--list", "--limit", "500")
        self.assertEqual(result["total"], len(self.catalogue["records"]))
        self.assertEqual(result["returned"], result["total"])
        self.assertGreater(len({record["module"] for record in result["records"]}), 1)

    def test_cli_exact_lookup_still_defaults_to_particles(self):
        result = self.cli("--class", "C_OP_DistanceBetweenCPsToCP", "--field", "m_nStartCP")
        self.assertEqual(result["identity"]["module"], "particles")
        self.assertEqual(result["defaults"]["value"], 0)

    def test_native_distance_has_start_and_output_component_fields(self):
        self.assertEqual(self.field("C_OP_DistanceBetweenCPsToCP", "m_nStartCP")["defaults"]["value"], 0)
        self.assertEqual(self.field("C_OP_DistanceBetweenCPsToCP", "m_nOutputCPField")["fields"][0]["type"]["name"], "int32")

    def test_native_orientation_is_qangle_and_source_defaults_remain_partial(self):
        field = self.field("C_OP_SetControlPointOrientation", "m_vecRotation")
        self.assertEqual(field["fields"][0]["type"]["name"], "QAngle")
        self.assertEqual(field["defaults"]["status"], "partial")
        self.assertEqual(field["defaults"]["value"], [0, 0, 0])

    def test_similar_child_fields_have_different_native_types(self):
        a = self.field("C_OP_SetChildControlPoints", "m_nFirstSourcePoint")["fields"][0]["type"]["name"]
        b = self.field("C_OP_SetParentControlPointsToChildCP", "m_nFirstSourcePoint")["fields"][0]["type"]["name"]
        self.assertEqual(a, "CParticleCollectionFloatInput")
        self.assertEqual(b, "int32")

    def test_driver_default_is_not_the_most_observed_attachment_value(self):
        self.assertEqual(self.field("ParticleControlPointDriver_t", "m_iAttachType")["defaults"]["value"], "PATTACH_ABSORIGIN_FOLLOW")
        self.assertEqual(self.field("CPathParameters", "m_nMidControlPointNumber")["defaults"]["value"], -1)

    def test_absent_native_field_is_not_synthesized(self):
        with self.assertRaisesRegex(ValueError, "No declared field"):
            self.field("C_OP_SetSingleControlPointPosition", "m_bUseWorldLocation")

    def test_skill_folder_works_when_copied_to_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "copied-cp-skill"
            shutil.copytree(SCRIPT.parent.parent, target)
            result = subprocess.run([sys.executable, str(target / "scripts/cp_contracts.py"),
                                     "--class", "C_OP_DistanceBetweenCPsToCP", "--field", "m_nStartCP"],
                                    cwd=directory, capture_output=True, text=True, check=True)
            value = json.loads(result.stdout)
            self.assertEqual(value["result"]["defaults"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
