from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from animgraph2_manifest import ManifestError, load_manifest, validate_manifest  # noqa: E402


EXAMPLE = SKILL_ROOT / "examples" / "animgraph2-project.example.json"


class ManifestPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_declares_multiple_private_roots_and_blocked_artifacts(self) -> None:
        _, manifest = load_manifest(EXAMPLE)
        self.assertEqual(2, len(manifest["project"]["namespaces"]))
        self.assertEqual(
            "blocked", manifest["project"]["artifact_policy"]["status"]
        )

    def test_legacy_single_namespace_is_canonicalized(self) -> None:
        candidate = copy.deepcopy(self.raw)
        namespace = candidate["project"].pop("namespaces")[0]
        candidate["project"]["namespace"] = namespace
        manifest = validate_manifest(candidate)
        self.assertEqual([namespace], manifest["project"]["namespaces"])
        self.assertNotIn("namespace", manifest["project"])

    def test_resources_may_span_declared_private_roots(self) -> None:
        candidate = copy.deepcopy(self.raw)
        graph = "animation/example/example_item/viewmodel.vnmgraph"
        candidate["compile_resources"].append(graph)
        manifest = validate_manifest(candidate)
        self.assertIn(graph, manifest["compile_resources"])

    def test_undeclared_or_global_roots_fail_closed(self) -> None:
        both = copy.deepcopy(self.raw)
        both["project"]["namespace"] = both["project"]["namespaces"][0]
        with self.assertRaisesRegex(ManifestError, "namespace or namespaces"):
            validate_manifest(both)

        global_root = copy.deepcopy(self.raw)
        global_root["project"]["namespaces"] = ["animation/graphs/viewmodel"]
        with self.assertRaisesRegex(ManifestError, "Valve global"):
            validate_manifest(global_root)

    def test_artifact_policy_and_packaged_dependencies_require_basis(self) -> None:
        missing_basis = copy.deepcopy(self.raw)
        missing_basis["project"]["artifact_policy"] = {"status": "allowed"}
        with self.assertRaisesRegex(ManifestError, "artifact_policy.basis"):
            validate_manifest(missing_basis)

        missing_template_basis = copy.deepcopy(self.raw)
        missing_template_basis["project"]["artifact_policy"] = {
            "status": "allowed",
            "basis": "project-owned outputs",
        }
        with self.assertRaisesRegex(ManifestError, "template_derivative_basis"):
            validate_manifest(missing_template_basis)

        packaged_stock = copy.deepcopy(self.raw)
        packaged_stock["stock_dependencies"][0]["package"] = True
        with self.assertRaisesRegex(ManifestError, "redistribution_basis"):
            validate_manifest(packaged_stock)


if __name__ == "__main__":
    unittest.main()
