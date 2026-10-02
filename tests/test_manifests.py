#!/usr/bin/env python3
"""Manifest constraints that no CLI validator enforces for us.

Cowork refuses a .plugin whose plugin.json description exceeds 500
characters ("Plugin description must be at most 500 characters"), while
`claude plugin validate` passes it — so the cap lives here.
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAX_DESC = 500


class TestManifests(unittest.TestCase):
    def setUp(self):
        self.plugin = json.loads((REPO / ".claude-plugin/plugin.json").read_text())
        self.market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())

    def test_descriptions_fit_cowork_limit(self):
        self.assertLessEqual(len(self.plugin["description"]), MAX_DESC, "plugin.json")
        self.assertLessEqual(len(self.market.get("description", "")), MAX_DESC, "marketplace.json")
        for e in self.market["plugins"]:
            self.assertLessEqual(len(e.get("description", "")), MAX_DESC, e["name"])

    def test_versions_agree(self):
        v = self.plugin["version"]
        self.assertRegex(v, r"^\d+\.\d+\.\d+$")
        for f in sorted((REPO / "skills").glob("*/SKILL.md")):
            fm = f.read_text().split("---")[1]
            self.assertIn(f'version: "{v}"', fm, f"{f} is not at {v}")
        asdr = next(e for e in self.market["plugins"] if e["name"] == self.plugin["name"])
        self.assertNotIn("version", asdr, "ASDR marketplace entry must not carry a version")

    def test_no_hooks_shipped(self):
        self.assertNotIn("hooks", self.plugin)
        self.assertFalse((REPO / "hooks").exists())


if __name__ == "__main__":
    unittest.main()
