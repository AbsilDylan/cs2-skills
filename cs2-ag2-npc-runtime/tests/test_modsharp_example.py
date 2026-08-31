#!/usr/bin/env python3
"""Structural checks for the bundled ModSharp AG2 example."""

from __future__ import annotations

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "modsharp-ag2-npc-example"
)
GAMEDATA = EXAMPLE / "gamedata" / "modsharp-ag2-npc-example.games.jsonc"


class ModSharpExampleTests(unittest.TestCase):
    def test_gamedata_contains_only_four_native_addresses(self) -> None:
        document = json.loads(GAMEDATA.read_text(encoding="utf-8"))
        self.assertEqual({"Addresses"}, set(document))

        addresses = document["Addresses"]
        self.assertEqual(
            {
                "Ag2NpcExample::Parameters::GetType",
                "Ag2NpcExample::Parameters::SetBool",
                "Ag2NpcExample::Parameters::SetFloat",
                "Ag2NpcExample::Parameters::SetIdentifier",
            },
            set(addresses),
        )
        self.assertTrue(all(entry["library"] == "server" for entry in addresses.values()))

        getter = addresses["Ag2NpcExample::Parameters::GetType"]["linux"]
        self.assertIsInstance(getter, str)
        self.assertGreater(len(getter.split()), 16)

        for name in (
            "SetBool",
            "SetFloat",
            "SetIdentifier",
        ):
            linux = addresses[f"Ag2NpcExample::Parameters::{name}"]["linux"]
            self.assertEqual({"signature", "factory"}, set(linux))
            self.assertGreater(len(linux["signature"].split()), 16)
            self.assertEqual("-303", linux["factory"])

        serialized = json.dumps(document).lower()
        for forbidden in (
            "profiles",
            "modulesha256",
            "elfbuildid",
            "steambuildid",
            "schemaVersion".lower(),
            "rva",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_project_publishes_gamedata_without_embedding_a_profile(self) -> None:
        root = ET.parse(EXAMPLE / "ModSharpAg2NpcExample.csproj").getroot()
        none_items = root.findall(".//None")
        self.assertTrue(
            any(
                item.attrib.get("Update")
                == "gamedata/modsharp-ag2-npc-example.games.jsonc"
                and item.attrib.get("CopyToPublishDirectory") == "PreserveNewest"
                for item in none_items
            )
        )
        self.assertEqual([], root.findall(".//EmbeddedResource"))

    def test_source_uses_modsharp_gamedata_not_a_private_scanner(self) -> None:
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((EXAMPLE / "src").rglob("*.cs"))
        )
        self.assertIn(".Register(GameDataFile)", sources)
        self.assertIn(".Unregister(GameDataFile)", sources)
        self.assertIn("gameData.GetAddress", sources)
        self.assertIn("GetFunctionRange", sources)
        for forbidden in (
            "FindPatternMulti",
            "FindPatternExactly",
            "Ag2SignatureProfile",
            "Ag2NativeModuleIdentity",
        ):
            self.assertNotIn(forbidden, sources)


if __name__ == "__main__":
    unittest.main()
