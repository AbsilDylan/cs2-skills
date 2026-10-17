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
