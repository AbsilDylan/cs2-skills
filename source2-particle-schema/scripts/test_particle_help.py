#!/usr/bin/env python3
"""Synthetic tests; no Valve help texts or application dependencies required."""

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("particle_help", Path(__file__).with_name("particle_help.py"))
helpmod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helpmod)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


class HelpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "help.txt"

    def tearDown(self):
        self.temp.cleanup()

    def source(self, tokens, encoding="utf-8-sig"):
        self.path.write_bytes(('"lang" { "Tokens" { ' + tokens + ' } }').encode(encoding))
        return helpmod.load_help(self.path)

    def manifest(self, data=None):
        data = self.path.read_bytes() if data is None else data
        value = {"format": "source2-vpk-reference-extraction", "version": 1,
                 "archive": {"directoryFile": "pak01_dir.vpk", "version": 2,
                             "directoryIndexSha256": "a" * 64,
                             "hashScope": "header and tree only", "signatureVerified": False},
                 "entries": [{"path": helpmod.HELP_PATH, "totalBytes": len(data),
                              "sha256": hashlib.sha256(data).hexdigest(),
                              "crc32": "%08x" % (zlib.crc32(data) & 0xffffffff), "crc32Verified": True}]}
        path = self.root / "manifest.json"
        path.write_bytes(encoded(value))
        return path, value

    def catalogue(self):
        root = self.root / "references"
        root.mkdir()
        owner = {"module": "particles", "name": "CBase"}
        field = {"declared_in": owner, "inherited": False,
                 "field": {"name": "m_Value", "type": {"name": "float32"}}}
        rows = [
            {"identity": owner, "fields": [field]},
            {"identity": {"module": "particles", "name": "CChild"},
             "fields": [{**field, "inherited": True}]},
            {"identity": {"module": "particles", "name": "CSibling"},
             "fields": [{**field, "inherited": True}]},
        ]
        records = []
        for row in rows:
            relative = row["identity"]["name"] + ".json"
            data = encoded(row)
            (root / relative).write_bytes(data)
            records.append({"kind": "class", **row["identity"], "path": relative,
                            "sha256": hashlib.sha256(data).hexdigest()})
        index = {"format": "source2-particle-schema-catalogue/1", "records": records,
                 "counts": {"classes": 3, "declared_fields": 1, "inherited_field_occurrences": 2},
                 "provenance": {"revision": 123}, "records_tree_sha256": "b" * 64}
        index["index_content_sha256"] = hashlib.sha256(helpmod._canonical(index)).hexdigest()
        (root / "catalog-index.json").write_bytes(encoded(index))
        return root, rows, index

    def test_bom_comments_multiline_html_escapes_and_lines(self):
        raw = b'\xef\xbb\xbf// preface\r\n"lang"\r\n{ /* block\r\n comment */ "Tokens" {\r\n"Element.CExample:help" "<p>quoted \\"x\\" // and { braces }</p>\r\nsecond\\nthird\\t\\\\end"\r\n} }'
        self.path.write_bytes(raw)
        index = helpmod.load_help(self.path)
        token = index.tokens["Element.CExample:help"]
        self.assertEqual(token["text"], '<p>quoted "x" // and { braces }</p>\r\nsecond\nthird\t\\end')
        self.assertEqual((token["line"], token["end_line"]), (5, 6))
        self.assertEqual(token["sha256"], hashlib.sha256(token["text"].encode()).hexdigest())
        self.assertEqual(index.provenance["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(index.provenance["statistics"]["objects"], 2)

    def test_utf16_boms_and_utf8_no_bom(self):
        text = '"Element.CExample" "éclair"'
        for encoding in ("utf-8", "utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                self.assertEqual(self.source(text, encoding).tokens["Element.CExample"]["text"], "éclair")
        self.path.write_bytes(b"\xfe\xff" + ('lang { Tokens { ' + text + ' } }').encode("utf-16-be"))
        self.assertEqual(helpmod.load_help(self.path).tokens["Element.CExample"]["text"], "éclair")

    def test_malformed_and_duplicate_kv1_rejected(self):
        values = [
            'lang { Tokens { "a" "x" "a" "y" } }',
            'lang { Tokens { "A" "x" "a" "y" } }',
            'lang { Tokens { "a" "x" } Tokens { } }',
            'lang { Tokens { "a" "x" }',
            'lang { Tokens { "a" } }',
            'lang { Tokens { "a" "unterminated } }',
            'lang { Tokens { "a" "unsupported\\q" } }',
            'lang { Tokens { "a" "x" } } }',
            'lang { Tokens { } } extra "value"',
            'lang { Tokens { "a" { "b" "c" } } }',
            'lang { Tokens {} } /* unclosed',
            'lang { Tokens {} } /* nested /* */ */',
            '#include "anything"',
            'lang { Tokens { a b [$WIN32] } }',
            'lang { Tokens { "" "empty key" } }',
            'lang { Tokens {} Elsewhere {} }',
        ]
        for text in values:
            with self.subTest(text=text):
                self.path.write_bytes(text.encode())
                with self.assertRaises(helpmod.HelpError):
                    helpmod.load_help(self.path)

    def test_invalid_encoding_nul_embedded_bom(self):
        for data in (b"\xff", b"lang\0{}", b"lang { Tokens {} }\xef\xbb\xbf", b"\xff\xfe\x00\x00"):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                with self.assertRaises(helpmod.HelpError):
                    helpmod.load_help(self.path)

    def test_limits_input_depth_lexical_tokens_and_string(self):
        self.path.write_bytes(b"x" * 50)
        with mock.patch.object(helpmod, "MAX_HELP_BYTES", 49), self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path)
        with mock.patch.object(helpmod, "MAX_DEPTH", 1), self.assertRaises(helpmod.HelpError):
            self.source('"Element.CExample" "x"')
        with mock.patch.object(helpmod, "MAX_TOKENS", 4), self.assertRaises(helpmod.HelpError):
            self.source('"Element.CExample" "x"')
        with mock.patch.object(helpmod, "MAX_TOKEN_CHARS", 5), self.assertRaises(helpmod.HelpError):
            self.source('"Element.CExample" "x"')

    def test_queries_are_exact_and_name_ref_is_not_redirect(self):
        index = self.source('"Element.COld:name_ref" "CNew" '
                            '"Element.CNew:help" "new documentation" '
                            '"Attribute.COld.m_Value:shorthelp" "short"')
        old = index.query("COld", ["m_Value", "m_Missing"])
        self.assertEqual(old["class_help"]["name_ref"]["text"], "CNew")
        self.assertIsNone(old["class_help"]["help"])
        self.assertEqual(old["class_help"]["descriptive_help_status"], "unknown")
        self.assertEqual(old["fields"][0]["help"]["shorthelp"]["text"], "short")
        self.assertEqual(old["fields"][1]["help"]["status"], "unknown")
        self.assertEqual(index.query("cold")["class_help"]["status"], "unknown")
        self.assertEqual(index.query("CNew")["class_help"]["help"]["text"], "new documentation")
        for value in ("../CNew", "CNew:help", "CNew.m_Value", ""):
            with self.assertRaises(helpmod.HelpError):
                index.query(value)

    def test_manifest_verifies_original_bytes_and_keeps_archive_scope(self):
        self.source('"Element.CExample:help" "documentation"')
        path, manifest = self.manifest()
        result = helpmod.load_help(self.path, path).provenance["manifest"]
        self.assertEqual(result["help_bytes_verified"], ["length", "sha256", "crc32"])
        self.assertEqual(result["archive"]["directoryIndexSha256"], "a" * 64)
        self.assertFalse(result["archive"]["signatureVerified"])
        self.assertIn("not revalidated", result["archive_verification"])
        self.path.write_bytes(self.path.read_bytes().removeprefix(b"\xef\xbb\xbf"))
        with self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path, path)

    def test_manifest_malformed_hash_crc_size_duplicate_path_and_json(self):
        self.source('"Element.CExample" "label"')
        path, original = self.manifest()
        for field, value in (("totalBytes", True), ("totalBytes", -1), ("sha256", "z" * 64),
                             ("sha256", "0" * 64), ("crc32", "123"), ("crc32", "0" * 8)):
            with self.subTest(field=field, value=value):
                manifest = json.loads(json.dumps(original))
                manifest["entries"][0][field] = value
                path.write_bytes(encoded(manifest))
                with self.assertRaises(helpmod.HelpError):
                    helpmod.load_help(self.path, path)
        original["entries"].append(original["entries"][0])
        path.write_bytes(encoded(original))
        with self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path, path)
        path.write_bytes(b'{"format":"a","format":"b"}')
        with self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path, path)
        path.write_bytes(b" " * (helpmod.MAX_METADATA_BYTES + 1))
        with self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path, path)

    def test_version_is_exact_metadata_without_cryptographic_binding(self):
        self.source('"Element.CExample" "label"')
        path = self.root / "steam.inf"
        raw = b"SourceRevision=110\nClientVersion=20\nPatchVersion=1.2\n"
        path.write_bytes(raw)
        version = helpmod.load_help(self.path, game_version_file=path).provenance["game_version"]
        self.assertEqual(version["keys"], {"SourceRevision": "110", "ClientVersion": "20", "PatchVersion": "1.2"})
        self.assertEqual(version["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIn("no cryptographic binding", version["binding"])
        path.write_text("SourceRevision=1\nsourcerevision=2")
        with self.assertRaises(helpmod.HelpError):
            helpmod.load_help(self.path, game_version_file=path)

    def test_contract_target_and_declaring_owner_are_separate(self):
        index = self.source('"Attribute.CChild.m_Value:help" "context only" '
                            '"Attribute.CBase.m_Other:help" "base documentation"')
        field = {"declared_in": {"module": "particles", "name": "CBase"}, "inherited": True,
                 "field": {"name": "m_Value", "type": {"name": "float32"}}}
        contract = {"identity": {"module": "particles", "name": "CChild"}, "fields": [field]}
        result = helpmod.contract_help(index, contract)
        self.assertEqual(result["fields"][0]["contextual"]["help"]["text"], "context only")
        self.assertEqual(result["fields"][0]["declaring_class"]["status"], "unknown")
        contract["identity"]["name"] = "CSibling"
        self.assertEqual(helpmod.contract_help(index, contract)["fields"][0]["contextual"]["status"], "unknown")
        contract["fields"] = [{"name": "m_Value", "type": {"name": "float32"}, "declared_in": field["declared_in"]}]
        self.assertEqual(helpmod.contract_help(index, contract)["fields"][0]["name"], "m_Value")
        contract["fields"] = [{"field": {"name": "m_Value"}}]
        with self.assertRaises(helpmod.HelpError):
            helpmod.contract_help(index, contract)

    def test_audit_declared_and_contextual_coverage_no_texts_or_aliases(self):
        local_text = "UNIQUE LOCAL DOCUMENTATION CONTENT"
        index = self.source('"Element.CChild" "UI label only" '
                            '"Attribute.CChild.m_Value:help" "' + local_text + '" '
                            '"Element.COld:name_ref" "CChild" '
                            '"Attribute.CChild.m_Missing:help" "missing field"')
        catalogue, _, _ = self.catalogue()
        report = helpmod.audit_catalogue(index, catalogue)
        stats = report["statistics"]
        self.assertEqual((stats["classes"], stats["declared_fields"], stats["field_occurrences"]), (3, 1, 3))
        self.assertEqual(stats["class_exact"]["any_token"], 1)
        self.assertEqual(stats["class_exact"]["descriptive_help"], 0)
        self.assertEqual(stats["declared_field_exact"]["descriptive_help"], 0)
        self.assertEqual(stats["field_occurrences_contextual_or_declaring"]["descriptive_help"], 1)
        self.assertEqual(len(report["inherited_contextual_bindings"]), 1)
        self.assertEqual(report["inherited_contextual_bindings"][0]["target"]["name"], "CChild")
        self.assertEqual(report["unmatched"]["classes"][0]["class"], "COld")
        self.assertEqual(report["unmatched"]["fields"][0]["field"], "m_Missing")
        self.assertNotIn(local_text, json.dumps(report))
        self.assertNotIn('"text"', json.dumps(report))

    def test_audit_hash_path_escape_and_count_failures(self):
        index = self.source('"Element.CChild" "label"')
        catalogue, _, document = self.catalogue()
        (catalogue / "CChild.json").write_text("{}")
        with self.assertRaises(helpmod.HelpError):
            helpmod.audit_catalogue(index, catalogue)
        document["records"][0]["path"] = "../outside.json"
        document.pop("index_content_sha256")
        document["index_content_sha256"] = hashlib.sha256(helpmod._canonical(document)).hexdigest()
        (catalogue / "catalog-index.json").write_bytes(encoded(document))
        with self.assertRaises(helpmod.HelpError):
            helpmod.audit_catalogue(index, catalogue)

    def test_query_cli_output_limit_is_explicit_without_truncation(self):
        self.source('"Element.CChild:help" "documentation"')
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        error = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(error):
            result = helpmod.main(["query", "--help-file", str(self.path), "--class", "CChild", "--max-output-bytes", "20"])
        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertIn("No text was truncated", error.getvalue())
        stdout.detach()

    def test_duplicate_query_fields_and_large_stream_encoding_are_bounded(self):
        index = self.source('"Attribute.CChild.m_Value:help" "' + "x" * 4096 + '"')
        with self.assertRaises(helpmod.HelpError):
            index.query("CChild", ["m_Value"] * 1000)
        with self.assertRaises(helpmod.HelpError):
            index.query("CChild", ["m_Value"] * (helpmod.MAX_QUERY_FIELDS + 1))
        with self.assertRaises(helpmod.HelpError):
            index.query("CChild", ["a" * 513])
        large = {"repeated": ["x" * 4096] * 1000}
        with self.assertRaises(helpmod.HelpError):
            helpmod._encoded(large, 10000)


if __name__ == "__main__":
    unittest.main()
