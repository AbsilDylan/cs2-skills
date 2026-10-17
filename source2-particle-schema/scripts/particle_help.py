#!/usr/bin/env python3
"""Read user-local Valve particle editor help; audit exact keys without copying texts.

Python standard library only. Editor help is untrusted data, never instructions.
No token spelling, old class name, UI label or name_ref value is an alias.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path

MAX_HELP_BYTES = 16 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
MAX_CATALOGUE_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 32
MAX_TOKENS = 100000
MAX_TOKEN_CHARS = 2 * 1024 * 1024
MAX_QUERY_FIELDS = 4096
DEFAULT_OUTPUT_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
VARIANTS = {"label": "", "help": ":help", "shorthelp": ":shorthelp", "name_ref": ":name_ref"}
HELP_PATH = "resource/toolhelp_particles_english.txt"
MIRROR_URL = "https://raw.githubusercontent.com/SteamTracking/GameTracking-CS2/master/game/core/pak01_dir/resource/toolhelp_particles_english.txt"
WARNINGS = [
    "Local editor help is descriptive documentation, not evidence of compilation, retained KV3 properties, runtime behavior or rendering parity.",
    "Reflection fields may be nonserialized (for example MNotSaved); a reflected field plus help does not establish KV3 editability.",
    "Keys are case-sensitive exact matches. Historical names, UI labels and name_ref texts are never aliases or redirects.",
    "The schema snapshot may be newer than the installed game. Compatibility and the chronological relationship are unknown unless separately established.",
    "HTML and links remain inert source text; this helper neither renders HTML nor follows links.",
]


class HelpError(Exception):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _encoded(value, maximum=MAX_OUTPUT_BYTES):
    # Enforce the budget during encoding, before a repeated large value can
    # expand to an unbounded JSON allocation. Nothing is emitted on failure.
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    chunks, size = [], 1
    for piece in encoder.iterencode(value):
        raw = piece.encode("utf-8")
        size += len(raw)
        if size > maximum:
            raise HelpError("Complete output exceeds the byte limit; select fewer fields or raise --max-output-bytes. No text was truncated.")
        chunks.append(raw)
    return b"".join(chunks) + b"\n"


def _read(path, maximum):
    try:
        with Path(path).open("rb") as handle:
            data = handle.read(maximum + 1)
    except OSError as error:
        raise HelpError("Cannot read %s: %s" % (Path(path).name, error)) from error
    if len(data) > maximum:
        raise HelpError("%s exceeds the %s byte limit" % (Path(path).name, maximum))
    return data


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise HelpError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _json(data, description):
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise HelpError(description + " must be finite UTF-8 JSON") from error


def _decode(data):
    if data.startswith(b"\xff\xfe\x00\x00") or data.startswith(b"\x00\x00\xfe\xff"):
        raise HelpError("UTF-32 help is unsupported; use UTF-8 or BOM-marked UTF-16")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        text = data.decode(encoding)
    except UnicodeError as error:
        raise HelpError("Help must be UTF-8 or BOM-marked UTF-16") from error
    if "\0" in text or "\ufeff" in text:
        raise HelpError("Unexpected NUL or embedded BOM in help")
    return text, encoding


class _Lexer:
    def __init__(self, text):
        self.text, self.pos, self.line, self.count = text, 0, 1, 0

    def _advance(self):
        char = self.text[self.pos]
        self.pos += 1
        if char == "\n" or (char == "\r" and (self.pos == len(self.text) or self.text[self.pos] != "\n")):
            self.line += 1
        return char

    def next(self):
        text = self.text
        while self.pos < len(text):
            if text[self.pos].isspace():
                self._advance()
            elif text.startswith("//", self.pos):
                while self.pos < len(text) and text[self.pos] not in "\r\n":
                    self._advance()
            elif text.startswith("/*", self.pos):
                start = self.line
                self._advance()
                self._advance()
                while not text.startswith("*/", self.pos):
                    if self.pos >= len(text):
                        raise HelpError("Unterminated block comment at line %s" % start)
                    if text.startswith("/*", self.pos):
                        raise HelpError("Nested block comment at line %s" % self.line)
                    self._advance()
                self._advance()
                self._advance()
            else:
                break
        if self.pos == len(text):
            return ("eof", "", self.line, self.line)
        self.count += 1
        if self.count > MAX_TOKENS:
            raise HelpError("KV1 lexical token limit exceeded")
        start = self.line
        char = self._advance()
        if char in "{}":
            return (char, char, start, self.line)
        value = []
        if char == '"':
            while True:
                if self.pos == len(text):
                    raise HelpError("Unterminated quoted string at line %s" % start)
                char = self._advance()
                if char == '"':
                    break
                if char == "\\":
                    if self.pos == len(text):
                        raise HelpError("Unterminated escape at line %s" % self.line)
                    escaped = self._advance()
                    translations = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
                    if escaped not in translations:
                        raise HelpError("Unsupported escape at line %s" % self.line)
                    char = translations[escaped]
                value.append(char)
                if len(value) > MAX_TOKEN_CHARS:
                    raise HelpError("KV1 string limit exceeded")
        else:
            value.append(char)
            while self.pos < len(text) and not text[self.pos].isspace() and text[self.pos] not in '{}"':
                if text.startswith(("//", "/*"), self.pos):
                    break
                value.append(self._advance())
                if len(value) > MAX_TOKEN_CHARS:
                    raise HelpError("KV1 string limit exceeded")
            if value[0] in "#[":
                raise HelpError("KV1 directives and conditions are unsupported at line %s" % start)
        return ("string", "".join(value), start, self.line)


def _parse(text):
    lexer = _Lexer(text)
    object_count = 0

    def entries(depth, closing):
        nonlocal object_count
        if depth > MAX_DEPTH:
            raise HelpError("KV1 nesting exceeds %s" % MAX_DEPTH)
        result, folded = {}, set()
        while True:
            key = lexer.next()
            if key[0] == "eof":
                if closing:
                    raise HelpError("Missing closing brace at end of help")
                return result
            if key[0] == "}":
                if not closing:
                    raise HelpError("Unexpected closing brace at line %s" % key[2])
                return result
            if key[0] != "string" or not key[1]:
                raise HelpError("Expected nonempty KV1 key at line %s" % key[2])
            if key[1].casefold() in folded:
                raise HelpError("Duplicate KV1 key (case-insensitive): %s at line %s" % (key[1], key[2]))
            folded.add(key[1].casefold())
            value = lexer.next()
            if value[0] == "{":
                object_count += 1
                node = entries(depth + 1, True)
                end = lexer.line
            elif value[0] == "string":
                node, end = value[1], value[3]
            else:
                raise HelpError("Expected KV1 value for %s at line %s" % (key[1], value[2]))
            result[key[1]] = {"value": node, "line": key[2], "end_line": end}

    result = entries(0, False)
    return result, {"lexical_tokens": lexer.count, "objects": object_count, "source_lines": lexer.line}


def _variant_key(key):
    for variant, suffix in VARIANTS.items():
        if suffix and key.endswith(suffix):
            return key[:-len(suffix)], variant
    return key, "label"


def _identity_key(key):
    base, variant = _variant_key(key)
    parts = base.split(".")
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
        return None
    if len(parts) == 2 and parts[0] == "Element":
        return ("class", parts[1], None, variant)
    if len(parts) == 3 and parts[0] == "Attribute":
        return ("field", parts[1], parts[2], variant)
    return None


def _verify_manifest(path, data):
    raw = _read(path, MAX_METADATA_BYTES)
    manifest = _json(raw, "Extraction manifest")
    if not isinstance(manifest, dict) or manifest.get("format") != "source2-vpk-reference-extraction" or manifest.get("version") != 1:
        raise HelpError("Unsupported extraction manifest format")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise HelpError("Extraction manifest entries must be objects")
    candidates = [entry for entry in entries if entry.get("path") == HELP_PATH]
    if len(candidates) != 1:
        raise HelpError("Extraction manifest must contain exactly one " + HELP_PATH)
    entry = candidates[0]
    size, sha, crc = entry.get("totalBytes"), entry.get("sha256"), entry.get("crc32")
    if type(size) is not int or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha) or not isinstance(crc, str) or not re.fullmatch(r"[0-9a-fA-F]{8}", crc):
        raise HelpError("Manifest help entry requires totalBytes, SHA-256 and CRC32")
    actual_crc = "%08x" % (zlib.crc32(data) & 0xffffffff)
    if size != len(data) or sha.lower() != _digest(data) or crc.lower() != actual_crc:
        raise HelpError("Help bytes do not match manifest length/SHA-256/CRC32")
    archive = manifest.get("archive")
    if not isinstance(archive, dict):
        raise HelpError("Extraction manifest archive metadata must be an object")
    archive_keys = ("directoryFile", "version", "directoryFileBytes", "directoryIndexBytes", "directoryIndexSha256", "hashScope", "entryCount", "signatureVerified")
    entry_keys = ("path", "crc32", "archiveIndex", "offset", "archiveBytes", "preloadBytes", "totalBytes", "sha256", "crc32Verified")
    return {"name": Path(path).name, "bytes": len(raw), "sha256": _digest(raw),
            "help_bytes_verified": ["length", "sha256", "crc32"],
            "entry": {key: entry[key] for key in entry_keys if key in entry},
            "archive": {key: archive[key] for key in archive_keys if key in archive},
            "archive_verification": "manifest metadata only; archive/tree/signature not revalidated by this helper"}


def _game_version(path):
    raw = _read(path, MAX_METADATA_BYTES)
    text, encoding = _decode(raw)
    values, folded = {}, set()
    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith(("//", "#", ";")):
            continue
        if "=" not in line:
            raise HelpError("Malformed game version key/value at line %s" % line_number)
        key, value = (piece.strip() for piece in line.split("=", 1))
        if not key or key.casefold() in folded:
            raise HelpError("Empty or duplicate game version key at line %s" % line_number)
        folded.add(key.casefold())
        values[key] = value
    return {"name": Path(path).name, "bytes": len(raw), "sha256": _digest(raw), "encoding": encoding,
            "keys": values, "binding": "user-supplied version metadata; no cryptographic binding to the help, VPK or schema snapshot"}


class HelpIndex:
    def __init__(self, tokens, provenance):
        self.tokens = tokens
        self.provenance = provenance

    def _binding(self, base):
        result = {"base_key": base, "match": "exact", "status": "unknown", "unknown_keys": []}
        for variant, suffix in VARIANTS.items():
            key = base + suffix
            if key in self.tokens:
                result[variant] = {"key": key, **copy.deepcopy(self.tokens[key])}
                result["status"] = "found"
            else:
                result[variant] = None
                result["unknown_keys"].append(key)
        result["descriptive_help_status"] = "found" if result["help"] is not None or result["shorthelp"] is not None else "unknown"
        return result

    def query(self, class_name, field_names=None):
        _check_name(class_name, "class")
        names = [] if field_names is None else list(field_names)
        if len(names) > MAX_QUERY_FIELDS:
            raise HelpError("Too many requested fields")
        for name in names:
            _check_name(name, "field")
        if len(set(names)) != len(names):
            raise HelpError("Repeated exact field requests are unsupported")
        return {"format": "source2-particle-local-help-query/1", "class": class_name,
                "evidence": "local editor documentation; no behavior, aliases or KV3 editability established",
                "class_help": self._binding("Element." + class_name),
                "fields": [{"name": name, "help": self._binding("Attribute.%s.%s" % (class_name, name))} for name in names]}


def _check_name(value, kind):
    if not isinstance(value, str) or len(value) > 512 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise HelpError("Expected exact reflected %s identifier" % kind)


def load_help(help_file, manifest_file=None, game_version_file=None):
    """Load a bounded local file. Optional extraction metadata must match its bytes."""
    data = _read(help_file, MAX_HELP_BYTES)
    text, encoding = _decode(data)
    document, stats = _parse(text)
    if set(document) != {"lang"} or not isinstance(document["lang"]["value"], dict):
        raise HelpError("Expected one lang KV1 object")
    language = document["lang"]["value"]
    if "Tokens" not in language or not isinstance(language["Tokens"]["value"], dict):
        raise HelpError("Expected lang/Tokens KV1 object")
    if any(isinstance(value["value"], dict) for key, value in language.items() if key != "Tokens"):
        raise HelpError("Unexpected additional object beside lang/Tokens")
    tokens = {}
    for key, value in language["Tokens"]["value"].items():
        if not isinstance(value["value"], str):
            raise HelpError("Help token must have a scalar text: " + key)
        tokens[key] = {"text": value["value"], "line": value["line"], "end_line": value["end_line"], "sha256": _digest(value["value"].encode("utf-8"))}
    variants = dict.fromkeys(VARIANTS, 0)
    families = {"Element": 0, "Attribute": 0, "other": 0}
    for key in tokens:
        identity = _identity_key(key)
        if identity is None:
            families["other"] += 1
        else:
            variants[identity[3]] += 1
            families["Element" if identity[0] == "class" else "Attribute"] += 1
    provenance = {"format": "source2-particle-local-help-provenance/1", "file_name": Path(help_file).name,
                  "bytes": len(data), "sha256": _digest(data), "crc32": "%08x" % (zlib.crc32(data) & 0xffffffff),
                  "encoding": encoding, "statistics": {**stats, "tokens": len(tokens), "variants": variants, "families": families},
                  "helper": {"script": "scripts/particle_help.py", "sha256": _digest(_read(Path(__file__), MAX_HELP_BYTES)),
                             "dependencies": "Python 3 standard library only"},
                  "public_mirror_reference": {"url": MIRROR_URL, "status": "reference URL only; not fetched or asserted equal to local bytes"},
                  "manifest": _verify_manifest(manifest_file, data) if manifest_file else None,
                  "game_version": _game_version(game_version_file) if game_version_file else None,
                  "installed_game_schema_compatibility": "unknown", "warnings": WARNINGS[:]}
    return HelpIndex(tokens, provenance)


def contract_help(help_index, contract_dict):
    """Bind schema full/field/summary records, keeping target and owner separate.

    Only supplied known fields and declared_in identities are used. No type or
    inheritance is guessed, and contextual help is never propagated to siblings.
    """
    if not isinstance(contract_dict, dict) or not isinstance(contract_dict.get("identity"), dict):
        raise HelpError("Expected a schema class/field contract with identity")
    target = contract_dict["identity"].get("name")
    _check_name(target, "class")
    fields = contract_dict.get("fields")
    if not isinstance(fields, list) or len(fields) > MAX_QUERY_FIELDS:
        raise HelpError("Schema contract must contain a known fields array")
    result = help_index.query(target)
    result["identity"] = copy.deepcopy(contract_dict["identity"])
    result["fields"] = []
    for entry in fields:
        if not isinstance(entry, dict) or not isinstance(entry.get("declared_in"), dict):
            raise HelpError("Known field lacks explicit declared_in identity")
        field = entry.get("field", entry)
        if not isinstance(field, dict):
            raise HelpError("Invalid schema field record")
        name, owner = field.get("name"), entry["declared_in"].get("name")
        _check_name(name, "field")
        _check_name(owner, "class")
        result["fields"].append({"name": name, "declared_in": copy.deepcopy(entry["declared_in"]),
                                 "contextual": help_index._binding("Attribute.%s.%s" % (target, name)),
                                 "declaring_class": help_index._binding("Attribute.%s.%s" % (owner, name))})
    result["binding_policy"] = "Contextual exact target and explicit declaring class are separate; neither supplies aliases or behavior proof."
    return result


def _safe_path(root, relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative or "\0" in relative:
        raise HelpError("Invalid catalogue path")
    if any(part in ("", ".", "..") for part in relative.split("/")):
        raise HelpError("Catalogue reference path escapes its directory")
    path = root.joinpath(*relative.split("/")).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise HelpError("Catalogue reference path escapes its directory") from error
    return path


def _coverage(tokens, base):
    keys = [base + suffix for suffix in VARIANTS.values() if base + suffix in tokens]
    return {"token_keys": keys, "any_token": bool(keys), "label": base in tokens,
            "help": base + ":help" in tokens, "shorthelp": base + ":shorthelp" in tokens,
            "name_ref": base + ":name_ref" in tokens,
            "descriptive_help": base + ":help" in tokens or base + ":shorthelp" in tokens}


def _coverage_totals(rows):
    return {key: sum(bool(row[key]) for row in rows) for key in ("any_token", "label", "help", "shorthelp", "name_ref", "descriptive_help")}


def audit_catalogue(help_index, catalogue):
    """Return keys, identities, counts and hashes only; never Valve help texts."""
    root = Path(catalogue)
    index_raw = _read(root / "catalog-index.json", MAX_CATALOGUE_BYTES)
    index = _json(index_raw, "Catalogue index")
    if not isinstance(index, dict) or index.get("format") != "source2-particle-schema-catalogue/1":
        raise HelpError("Unsupported schema catalogue")
    unsigned = {key: value for key, value in index.items() if key != "index_content_sha256"}
    if _digest(_canonical(unsigned)) != index.get("index_content_sha256"):
        raise HelpError("Catalogue index content digest mismatch")
    records = index.get("records")
    if not isinstance(records, list) or len(records) > MAX_TOKENS:
        raise HelpError("Invalid catalogue records array")
    classes, names, declared, occurrences, contextual_bindings = [], set(), set(), [], []
    used_owners, used_fields = set(), set()
    total_bytes = len(index_raw)
    for record in records:
        if not isinstance(record, dict):
            raise HelpError("Invalid catalogue record")
        if record.get("kind") != "class":
            continue
        name, module = record.get("name"), record.get("module")
        _check_name(name, "class")
        if not isinstance(module, str) or not module:
            raise HelpError("Class module is missing")
        identity = (module, name)
        if identity in names:
            raise HelpError("Duplicate catalogue class identity")
        names.add(identity)
        raw = _read(_safe_path(root, record.get("path")), MAX_CATALOGUE_BYTES)
        total_bytes += len(raw)
        if total_bytes > MAX_CATALOGUE_BYTES:
            raise HelpError("Catalogue aggregate input limit exceeded")
        if _digest(raw) != record.get("sha256"):
            raise HelpError("Catalogue class digest mismatch: " + name)
        contract = _json(raw, "Class reference")
        if not isinstance(contract, dict) or contract.get("identity") != {"module": module, "name": name} or not isinstance(contract.get("fields"), list):
            raise HelpError("Catalogue class identity/fields mismatch: " + name)
        classes.append({"id": module + "/" + name, "module": module, "class": name, **_coverage(help_index.tokens, "Element." + name)})
        seen = set()
        for entry in contract["fields"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("field"), dict) or not isinstance(entry.get("declared_in"), dict):
                raise HelpError("Invalid catalogue field identity")
            field_name = entry["field"].get("name")
            owner = entry["declared_in"].get("name")
            owner_module = entry["declared_in"].get("module")
            _check_name(field_name, "field")
            _check_name(owner, "class")
            if not isinstance(owner_module, str) or not owner_module:
                raise HelpError("Invalid field declaring module")
            field_id = (owner_module, owner, field_name)
            used_owners.add((owner_module, owner))
            used_fields.add(field_id)
            if field_id in seen:
                raise HelpError("Duplicate catalogue field occurrence")
            seen.add(field_id)
            own = _coverage(help_index.tokens, "Attribute.%s.%s" % (owner, field_name))
            direct = _coverage(help_index.tokens, "Attribute.%s.%s" % (name, field_name))
            occurrences.append({"inherited": identity != (owner_module, owner), "direct": direct, "declaring": own})
            if identity == (owner_module, owner):
                declared.add(field_id)
            elif direct["any_token"]:
                contextual_bindings.append({"target": {"module": module, "name": name}, "field": field_name,
                                            "declared_in": {"module": owner_module, "name": owner},
                                            "contextual_token_keys": direct["token_keys"], "declaring_token_keys": own["token_keys"]})
    fields = [{"id": module + "/" + name + "/" + field, "module": module, "class": name, "field": field,
               **_coverage(help_index.tokens, "Attribute.%s.%s" % (name, field))} for module, name, field in sorted(declared)]
    expected_counts = index.get("counts", {})
    if not isinstance(expected_counts, dict) or expected_counts.get("classes") != len(classes) or expected_counts.get("declared_fields") != len(fields):
        raise HelpError("Catalogue declared class/field counts mismatch")
    if expected_counts.get("inherited_field_occurrences") != sum(row["inherited"] for row in occurrences):
        raise HelpError("Catalogue inherited field occurrence count mismatch")
    if not used_owners.issubset(names):
        raise HelpError("Catalogue field declaring class is absent")
    if not used_fields.issubset(declared):
        raise HelpError("Catalogue inherited field declaration is absent")
    class_names = {name for _, name in names}
    valid_context_pairs = {(row["class"], row["field"]) for row in fields}
    valid_context_pairs.update((row["target"]["name"], row["field"]) for row in contextual_bindings)
    unmatched_classes, unmatched_fields, other = {}, {}, []
    matched = []
    for key in sorted(help_index.tokens):
        parsed = _identity_key(key)
        if parsed is None:
            other.append(key)
            continue
        kind, name, field, _ = parsed
        if name not in class_names:
            unmatched_classes.setdefault(name, []).append(key)
        elif kind == "field" and (name, field) not in valid_context_pairs:
            unmatched_fields.setdefault((name, field), []).append(key)
        else:
            matched.append(key)
    return {"format": "source2-particle-local-help-coverage/1", "provenance": copy.deepcopy(help_index.provenance),
            "method": copy.deepcopy(help_index.provenance["helper"]), "help_text_included": False,
            "catalogue": {"index_sha256": _digest(index_raw), "index_content_sha256": index["index_content_sha256"],
                          "records_tree_sha256": index.get("records_tree_sha256"), "source": index.get("provenance"),
                          "verification": "index content and every class reference SHA-256 verified; enums outside help audit scope"},
            "statistics": {"classes": len(classes), "declared_fields": len(fields), "field_occurrences": len(occurrences),
                           "inherited_field_occurrences": sum(row["inherited"] for row in occurrences),
                           "class_exact": _coverage_totals(classes), "declared_field_exact": _coverage_totals(fields),
                           "field_occurrences_contextual_exact": _coverage_totals([row["direct"] for row in occurrences]),
                           "field_occurrences_declaring_exact": _coverage_totals([row["declaring"] for row in occurrences]),
                           "field_occurrences_contextual_or_declaring": {key: sum(row["direct"][key] or row["declaring"][key] for row in occurrences) for key in ("any_token", "descriptive_help", "help", "shorthelp")},
                           "matched_tokens": len(matched), "unmatched_class_names": len(unmatched_classes),
                           "unmatched_class_tokens": sum(map(len, unmatched_classes.values())),
                           "unmatched_class_field_pairs": len(unmatched_fields), "unmatched_class_field_tokens": sum(map(len, unmatched_fields.values()))},
            "class_coverage": classes, "declared_field_coverage": fields,
            "gaps": {"classes_without_any_token": [row["id"] for row in classes if not row["any_token"]],
                     "classes_without_descriptive_help": [row["id"] for row in classes if not row["descriptive_help"]],
                     "declared_fields_without_any_token": [row["id"] for row in fields if not row["any_token"]],
                     "declared_fields_without_descriptive_help": [row["id"] for row in fields if not row["descriptive_help"]]},
            "inherited_contextual_bindings": contextual_bindings, "matched_token_keys": matched,
            "unmatched": {"classes": [{"class": name, "token_keys": keys} for name, keys in sorted(unmatched_classes.items())],
                          "fields": [{"class": name, "field": field, "token_keys": keys} for (name, field), keys in sorted(unmatched_fields.items())],
                          "other_keys": other},
            "coverage_policy": "Element exact class keys; declared fields use their declaring owner. Inherited occurrences keep contextual target and declaring owner separate, with union counts explicitly labeled. Labels/name_ref do not count as descriptive help; no aliases.",
            "warnings": WARNINGS[:]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("query", "audit"):
        sub = commands.add_parser(name)
        sub.add_argument("--help-file", required=True, type=Path)
        sub.add_argument("--manifest", type=Path)
        sub.add_argument("--game-version-file", type=Path)
        sub.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_BYTES,
                         help="Query stdout limit; audit report limit is always 4 MiB")
        if name == "query":
            sub.add_argument("--class", dest="class_name", required=True)
            sub.add_argument("--field", dest="fields", action="append", default=[])
        else:
            sub.add_argument("--catalogue", required=True, type=Path)
            sub.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.max_output_bytes <= MAX_OUTPUT_BYTES:
            raise HelpError("--max-output-bytes must be between 1 and 4194304")
        index = load_help(args.help_file, args.manifest, args.game_version_file)
        if args.command == "query":
            value = {**index.query(args.class_name, args.fields), "provenance": index.provenance}
            raw = _encoded(value, args.max_output_bytes)
            sys.stdout.buffer.write(raw)
        else:
            report = audit_catalogue(index, args.catalogue)
            raw = _encoded(report)
            if len(raw) > MAX_OUTPUT_BYTES:
                raise HelpError("Coverage report exceeds the 4 MiB limit")
            inputs = {args.help_file.resolve(), (args.catalogue / "catalog-index.json").resolve()}
            inputs.update(path.resolve() for path in (args.manifest, args.game_version_file) if path is not None)
            catalogue_index = _json(_read(args.catalogue / "catalog-index.json", MAX_CATALOGUE_BYTES), "Catalogue index")
            for item in catalogue_index.get("records", []):
                if item.get("kind") == "class":
                    inputs.add(_safe_path(args.catalogue, item.get("path")))
            if args.output.resolve() in inputs:
                raise HelpError("Audit output must not replace an input file")
            args.output.write_bytes(raw)
            sys.stdout.buffer.write(_encoded({"output": str(args.output), "bytes": len(raw), "sha256": _digest(raw), "statistics": report["statistics"]}))
        return 0
    except (HelpError, OSError, RecursionError) as error:
        print("particle_help: " + str(error)[:1000], file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
