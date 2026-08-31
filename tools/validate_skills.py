#!/usr/bin/env python3
"""Validate the portable skill packages and repository distribution metadata."""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
OPENAI_FIELDS = {"display_name", "short_description", "default_prompt"}
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
FORBIDDEN_FILE_SUFFIXES = {
    ".dll",
    ".dylib",
    ".exe",
    ".pdb",
    ".so",
    ".vpk",
}


def fail(errors: list[str], scope: Path | str, message: str) -> None:
    if isinstance(scope, Path):
        try:
            label = scope.relative_to(ROOT).as_posix()
        except ValueError:
            label = str(scope)
    else:
        label = scope
    errors.append(f"{label}: {message}")


def decode_scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid double-quoted scalar: {exc}") from exc
        if not isinstance(decoded, str):
            raise ValueError("expected a string scalar")
        return decoded
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_frontmatter(path: Path, errors: list[str]) -> tuple[dict[str, str], list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(errors, path, f"cannot read UTF-8 text: {exc}")
        return {}, []

    if not lines or lines[0] != "---":
        fail(errors, path, "must start with YAML frontmatter delimiter ---")
        return {}, lines

    try:
        closing = lines.index("---", 1)
    except ValueError:
        fail(errors, path, "frontmatter has no closing --- delimiter")
        return {}, lines

    fields: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        if line[:1].isspace() or ":" not in line:
            fail(errors, path, f"unsupported frontmatter syntax on line {number}")
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if key in fields:
            fail(errors, path, f"duplicate frontmatter key {key!r}")
            continue
        if key == "description" and not (
            raw.strip().startswith('"') and raw.strip().endswith('"')
        ):
            fail(errors, path, "description must be a double-quoted YAML string")
            continue
        try:
            fields[key] = decode_scalar(raw)
        except ValueError as exc:
            fail(errors, path, f"invalid {key!r} value: {exc}")

    return fields, lines[closing + 1 :]


def local_link_target(raw: str) -> str | None:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    if not target or target.startswith("#") or URL_RE.match(target):
        return None
    return unquote(target.split("#", 1)[0])


def markdown_heading_anchors(path: Path) -> set[str]:
    """Approximate GitHub/CommonMark heading IDs for local fragment checks."""
    anchors: set[str] = set()
    counts: Counter[str] = Counter()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        heading = re.sub(r"<[^>]+>", "", match.group(1))
        heading = re.sub(r"[`*_~]", "", heading).lower()
        base = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        base = re.sub(r"\s+", "-", base.strip())
        index = counts[base]
        counts[base] += 1
        anchors.add(base if index == 0 else f"{base}-{index}")
    return anchors


def validate_markdown_links(
    markdown_root: Path,
    containment_root: Path,
    errors: list[str],
) -> None:
    root = containment_root.resolve()
    markdown_files = (
        [markdown_root]
        if markdown_root.is_file()
        else sorted(markdown_root.rglob("*.md"))
    )
    for markdown in markdown_files:
        text = markdown.read_text(encoding="utf-8")
        for raw in MARKDOWN_LINK_RE.findall(text):
            normalized = raw.strip()
            if normalized.startswith("<") and ">" in normalized:
                normalized = normalized[1 : normalized.index(">")]
            else:
                normalized = normalized.split(maxsplit=1)[0]
            if URL_RE.match(normalized):
                continue
            local_path, separator, fragment = normalized.partition("#")
            target = local_link_target(raw)
            if target is None and not (separator and not local_path):
                continue
            resolved = markdown.resolve() if not local_path else (markdown.parent / unquote(local_path)).resolve()
            if resolved != root and root not in resolved.parents:
                fail(errors, markdown, f"local link escapes the skill: {local_path}")
            elif not resolved.exists():
                fail(errors, markdown, f"missing local link target: {local_path}")
            elif separator and fragment and resolved.suffix.lower() == ".md":
                anchor = unquote(fragment).lower()
                if anchor not in markdown_heading_anchors(resolved):
                    fail(errors, markdown, f"missing Markdown anchor: {normalized}")


def validate_openai_yaml(skill_dir: Path, skill_name: str, errors: list[str]) -> None:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        fail(errors, skill_dir, "missing agents/openai.yaml")
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        fail(errors, path, f"cannot read UTF-8 YAML: {exc}")
        return

    fields: dict[str, str] = {}
    saw_interface = False
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line:
            fail(errors, path, f"tabs are not allowed on line {number}")
            continue
        if line == "interface:":
            if saw_interface:
                fail(errors, path, "duplicate interface mapping")
            saw_interface = True
            continue
        if not saw_interface:
            fail(errors, path, f"interface: must be the first mapping (line {number})")
            continue
        if not line.startswith("  ") or line.startswith("   ") or ":" not in line:
            fail(errors, path, f"unsupported YAML structure on line {number}")
            continue
        key, raw = line.strip().split(":", 1)
        if key not in OPENAI_FIELDS:
            fail(errors, path, f"unsupported interface field {key!r}")
            continue
        if key in fields:
            fail(errors, path, f"duplicate interface.{key}")
            continue
        if not (raw.strip().startswith('"') and raw.strip().endswith('"')):
            fail(errors, path, f"interface.{key} must be a double-quoted string")
            continue
        try:
            fields[key] = decode_scalar(raw)
        except ValueError as exc:
            fail(errors, path, f"invalid interface.{key}: {exc}")

    if not saw_interface:
        fail(errors, path, "missing interface mapping")
    for missing in sorted(OPENAI_FIELDS - fields.keys()):
        fail(errors, path, f"missing interface.{missing}")

    for key, value in fields.items():
        if not value.strip():
            fail(errors, path, f"interface.{key} must not be empty")

    short = fields.get("short_description", "")
    if short and not 25 <= len(short) <= 64:
        fail(errors, path, "interface.short_description must be 25-64 characters")

    prompt = fields.get("default_prompt", "")
    if prompt and f"${skill_name}" not in prompt:
        fail(errors, path, f"interface.default_prompt must mention ${skill_name}")


def validate_bundled_code(skill_dir: Path, errors: list[str]) -> None:
    for script in sorted((skill_dir / "scripts").glob("*.py")):
        try:
            source = script.read_text(encoding="utf-8")
            ast.parse(source, filename=str(script))
        except (OSError, UnicodeError, SyntaxError) as exc:
            fail(errors, script, f"invalid Python source: {exc}")
            continue
        if not source.startswith("#!/usr/bin/env python3"):
            fail(errors, script, "Python entry/helper must declare python3 shebang")

    for test in sorted((skill_dir / "tests").glob("test_*.py")):
        try:
            ast.parse(test.read_text(encoding="utf-8"), filename=str(test))
        except (OSError, UnicodeError, SyntaxError) as exc:
            fail(errors, test, f"invalid Python test source: {exc}")

    for example in sorted((skill_dir / "examples").glob("*.json")):
        try:
            json.loads(example.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            fail(errors, example, f"invalid JSON example: {exc}")


def validate_skill(skill_dir: Path, errors: list[str]) -> str | None:
    skill_file = skill_dir / "SKILL.md"
    fields, body = parse_frontmatter(skill_file, errors)

    unexpected = set(fields) - {"name", "description"}
    if unexpected:
        fail(errors, skill_file, f"unsupported frontmatter keys: {sorted(unexpected)}")

    name = fields.get("name", "")
    description = fields.get("description", "")
    if not name:
        fail(errors, skill_file, "missing name")
    elif name != skill_dir.name:
        fail(errors, skill_file, f"name {name!r} must match directory {skill_dir.name!r}")
    elif len(name) > 64 or not NAME_RE.fullmatch(name):
        fail(errors, skill_file, "name must be <=64 lowercase letters/digits/hyphens")

    if not description.strip():
        fail(errors, skill_file, "missing description")
    elif len(description) > 200:
        fail(
            errors,
            skill_file,
            f"description is {len(description)} characters; cross-surface limit is 200",
        )

    total_lines = len(skill_file.read_text(encoding="utf-8").splitlines())
    if total_lines > 500:
        fail(errors, skill_file, f"main skill is {total_lines} lines; split below 500")

    if not any(line.startswith("# ") for line in body):
        fail(errors, skill_file, "body must contain a level-one title")

    references_dir = skill_dir / "references"
    if references_dir.is_dir():
        main_text = skill_file.read_text(encoding="utf-8")
        for reference in sorted(references_dir.glob("*.md")):
            if reference.name not in main_text:
                fail(errors, reference, "reference is not linked directly from SKILL.md")
            lines = reference.read_text(encoding="utf-8").splitlines()
            if len(lines) > 100 and "## Contents" not in lines:
                fail(errors, reference, "references over 100 lines need a Contents section")

    validate_markdown_links(skill_dir, skill_dir, errors)
    validate_bundled_code(skill_dir, errors)
    if name:
        validate_openai_yaml(skill_dir, name, errors)
    return name or None


def validate_marketplace(skill_names: set[str], errors: list[str]) -> None:
    path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(errors, path, "missing Claude marketplace")
        return
    except (json.JSONDecodeError, UnicodeError) as exc:
        fail(errors, path, f"invalid UTF-8 JSON: {exc}")
        return

    if not isinstance(catalog, dict):
        fail(errors, path, "root must be an object")
        return
    if not NAME_RE.fullmatch(str(catalog.get("name", ""))):
        fail(errors, path, "marketplace name must be kebab-case")
    owner = catalog.get("owner")
    if not isinstance(owner, dict) or not str(owner.get("name", "")).strip():
        fail(errors, path, "owner.name is required")

    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        fail(errors, path, "plugins must be a non-empty array")
        return

    declared: list[str] = []
    for index, plugin in enumerate(plugins):
        scope = f"marketplace.plugins[{index}]"
        if not isinstance(plugin, dict):
            fail(errors, scope, "entry must be an object")
            continue
        name = str(plugin.get("name", ""))
        if not NAME_RE.fullmatch(name):
            fail(errors, scope, "plugin name must be kebab-case")
        source = plugin.get("source")
        if not isinstance(source, str) or not source.startswith("./"):
            fail(errors, scope, "source must be a repository-relative ./ path")
            continue
        source_root = (ROOT / source).resolve()
        if source_root != ROOT.resolve() and ROOT.resolve() not in source_root.parents:
            fail(errors, scope, "source escapes the repository")
            continue
        skills = plugin.get("skills")
        if isinstance(skills, str):
            skills = [skills]
        if not isinstance(skills, list) or not skills:
            fail(errors, scope, "skills must be a non-empty string or array")
            continue
        if plugin.get("strict") is not False:
            fail(errors, scope, "strict must be false when no plugin.json is used")
        for skill_path in skills:
            if not isinstance(skill_path, str) or not skill_path.startswith("./"):
                fail(errors, scope, "each skills path must start with ./")
                continue
            resolved = (source_root / skill_path).resolve()
            if not (resolved / "SKILL.md").is_file():
                fail(errors, scope, f"skills path has no SKILL.md: {skill_path}")
                continue
            skill_fields, _ = parse_frontmatter(resolved / "SKILL.md", errors)
            if skill_fields.get("name"):
                declared.append(skill_fields["name"])

    duplicates = sorted(name for name, count in Counter(declared).items() if count > 1)
    if duplicates:
        fail(errors, path, f"skills declared more than once: {duplicates}")
    if set(declared) != skill_names:
        fail(
            errors,
            path,
            f"declared skills {sorted(set(declared))} != repository skills {sorted(skill_names)}",
        )


def validate_routing_cases(skill_names: set[str], errors: list[str]) -> None:
    path = ROOT / "evals" / "routing-cases.json"
    try:
        cases = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(errors, path, "missing routing case corpus")
        return
    except (json.JSONDecodeError, UnicodeError) as exc:
        fail(errors, path, f"invalid UTF-8 JSON: {exc}")
        return

    if not isinstance(cases, list) or not cases:
        fail(errors, path, "root must be a non-empty array")
        return

    ids: set[str] = set()
    coverage: Counter[str] = Counter()
    for index, case in enumerate(cases):
        scope = f"evals.routing-cases[{index}]"
        if not isinstance(case, dict):
            fail(errors, scope, "case must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not NAME_RE.fullmatch(case_id):
            fail(errors, scope, "id must be unique kebab-case")
        elif case_id in ids:
            fail(errors, scope, f"duplicate id {case_id}")
        else:
            ids.add(case_id)
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            fail(errors, scope, "prompt must be a non-empty string")
        expected = case.get("expected_skills")
        rejected = case.get("not_expected_skills")
        if not isinstance(expected, list):
            fail(errors, scope, "expected_skills must be an array")
            continue
        if not isinstance(rejected, list):
            fail(errors, scope, "not_expected_skills must be an array")
            continue
        if any(not isinstance(value, str) for value in expected + rejected):
            fail(errors, scope, "skill entries must be strings")
            continue
        if len(expected) != len(set(expected)) or len(rejected) != len(set(rejected)):
            fail(errors, scope, "skill arrays must not contain duplicates")
        unknown = (set(expected) | set(rejected)) - skill_names
        if unknown:
            fail(errors, scope, f"unknown skills: {sorted(unknown)}")
        overlap = set(expected) & set(rejected)
        if overlap:
            fail(errors, scope, f"skills both expected and rejected: {sorted(overlap)}")
        missing = skill_names - (set(expected) | set(rejected))
        if missing:
            fail(errors, scope, f"classification is not exhaustive; missing: {sorted(missing)}")
        coverage.update(expected)

    for skill in sorted(skill_names):
        if coverage[skill] < 3:
            fail(errors, path, f"{skill} needs at least three positive routing cases")


def validate_repository_safety(errors: list[str]) -> None:
    for directory in ROOT.rglob("__pycache__"):
        if directory.is_dir() and ".git" not in directory.parts:
            fail(errors, directory, "Python bytecode cache must not be packaged")
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        name = path.name.lower()
        if path.suffix.lower() in {".pyc", ".pyo"}:
            fail(errors, path, "Python bytecode must not be packaged")
        if name.endswith("_c") or path.suffix.lower() in FORBIDDEN_FILE_SUFFIXES:
            fail(errors, path, "compiled/native asset is not allowed in this public skill repo")
        if path.is_symlink():
            resolved = path.resolve()
            if resolved != ROOT.resolve() and ROOT.resolve() not in resolved.parents:
                fail(errors, path, "symlink escapes the repository")


def main() -> int:
    errors: list[str] = []
    skill_dirs = sorted(
        path for path in ROOT.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()
    )
    if not skill_dirs:
        fail(errors, "repository", "no top-level skills found")

    skill_names = {
        name for skill_dir in skill_dirs if (name := validate_skill(skill_dir, errors))
    }
    validate_marketplace(skill_names, errors)
    validate_routing_cases(skill_names, errors)
    validate_markdown_links(ROOT / "README.md", ROOT, errors)
    validate_repository_safety(errors)

    if errors:
        print("Validation failed:", file=sys.stderr)
        for error in errors:
            print(f" - {error}", file=sys.stderr)
        return 1

    print(
        f"Validated {len(skill_names)} skills, Claude marketplace metadata, "
        "routing-fixture schema, and repository safety."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
