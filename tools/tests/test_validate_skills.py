from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "validate_skills.py"
SPEC = importlib.util.spec_from_file_location("validate_skills", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class OpenAIMetadataTests(unittest.TestCase):
    def write_skill(self, root: Path, yaml_text: str) -> Path:
        skill = root / "example-skill"
        (skill / "agents").mkdir(parents=True)
        (skill / "agents" / "openai.yaml").write_text(yaml_text, encoding="utf-8")
        return skill

    def test_accepts_exact_interface_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skill = self.write_skill(
                Path(temp),
                "interface:\n"
                '  display_name: "Example Skill"\n'
                '  short_description: "Perform one deterministic example workflow"\n'
                '  default_prompt: "Use $example-skill to solve this task."\n',
            )
            errors: list[str] = []
            VALIDATOR.validate_openai_yaml(skill, "example-skill", errors)
            self.assertEqual([], errors)

    def test_rejects_nested_or_unknown_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skill = self.write_skill(
                Path(temp),
                "interface:\n"
                '  display_name: "Example Skill"\n'
                '  short_description: "Perform one deterministic example workflow"\n'
                '  default_prompt: "Use $example-skill to solve this task."\n'
                "  policy:\n"
                '    hidden: "value"\n',
            )
            errors: list[str] = []
            VALIDATOR.validate_openai_yaml(skill, "example-skill", errors)
            self.assertTrue(any("unsupported" in error for error in errors))


class FrontmatterTests(unittest.TestCase):
    def test_rejects_unquoted_description_with_yaml_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skill_file = Path(temp) / "SKILL.md"
            skill_file.write_text(
                "---\nname: example-skill\n"
                "description: Diagnose things: safely\n---\n# Example\n",
                encoding="utf-8",
            )
            errors: list[str] = []
            VALIDATOR.parse_frontmatter(skill_file, errors)
            self.assertTrue(any("double-quoted" in error for error in errors))


class MarkdownLinkTests(unittest.TestCase):
    def test_single_root_readme_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            readme = root / "README.md"
            readme.write_text("[missing](does-not-exist.md)\n", encoding="utf-8")
            errors: list[str] = []
            VALIDATOR.validate_markdown_links(readme, root, errors)
            self.assertEqual(1, len(errors))
            self.assertIn("missing local link target", errors[0])


class RoutingFixtureTests(unittest.TestCase):
    def test_empty_expected_list_is_valid_when_classification_is_exhaustive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evals").mkdir()
            skills = {"skill-one", "skill-two", "skill-three"}
            cases = []
            for index in range(3):
                for skill in sorted(skills):
                    cases.append(
                        {
                            "id": f"{skill}-positive-{index}",
                            "prompt": f"Use {skill}",
                            "expected_skills": [skill],
                            "not_expected_skills": sorted(skills - {skill}),
                        }
                    )
            cases.append(
                {
                    "id": "intentionally-ambiguous",
                    "prompt": "Not enough context",
                    "expected_skills": [],
                    "not_expected_skills": sorted(skills),
                }
            )
            (root / "evals" / "routing-cases.json").write_text(
                json.dumps(cases), encoding="utf-8"
            )

            original_root = VALIDATOR.ROOT
            VALIDATOR.ROOT = root
            try:
                errors: list[str] = []
                VALIDATOR.validate_routing_cases(skills, errors)
            finally:
                VALIDATOR.ROOT = original_root
            self.assertEqual([], errors)


class RepositorySafetyTests(unittest.TestCase):
    def test_rejects_python_bytecode_and_cache_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "skill" / "scripts" / "__pycache__"
            cache.mkdir(parents=True)
            (cache / "tool.cpython-312.pyc").write_bytes(b"bytecode")

            original_root = VALIDATOR.ROOT
            VALIDATOR.ROOT = root
            try:
                errors: list[str] = []
                VALIDATOR.validate_repository_safety(errors)
            finally:
                VALIDATOR.ROOT = original_root

            self.assertTrue(any("cache" in error for error in errors))
            self.assertTrue(any("bytecode" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
