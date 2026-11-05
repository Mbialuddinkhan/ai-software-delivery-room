#!/usr/bin/env python3
"""v4.3: blast-radius gating and the cross-family second opinion.
Per the repo charter, every new check gets a true-positive test and a test
showing it does not block a valid input."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable

CLEAN = """# CONTRACT · sprint-01 · theming
Status: ratified
## Sprint goal
Pick a theme.
## Acceptance criteria
### Happy path
1. An admin can choose light or dark and the choice persists. (radius: low)
2. The theme applies without a page reload.
"""

MONEY_LOW = """# CONTRACT · sprint-02 · refunds
Status: ratified
## Sprint goal
Refunds.
## Acceptance criteria
### Happy path
1. A customer can request a refund and the charge is reversed. (radius: low)
"""


def run(argv, cwd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([PY] + argv, capture_output=True, text=True,
                          cwd=str(cwd), env=e)


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        (self.d / ".harness" / "contracts").mkdir(parents=True)
        (self.d / "docs").mkdir()

    def tearDown(self):
        self._td.cleanup()

    def contract(self, text, sprint="sprint-01"):
        p = self.d / ".harness" / "contracts" / f"contract-{sprint}.md"
        p.write_text(text)
        return p


class TestBlastRadius(Tmp):
    def test_under_declaration_below_floor_errors(self):
        p = self.contract(MONEY_LOW, "sprint-02")
        r = run([str(SCRIPTS / "blast_radius.py"), "classify", str(p)], self.d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("floor", r.stdout)

    def test_clean_contract_passes_and_queues_no_gate(self):
        p = self.contract(CLEAN)
        r = run([str(SCRIPTS / "blast_radius.py"), "classify", str(p), "--write"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        g = run([str(SCRIPTS / "blast_radius.py"), "gate-check"], self.d)
        self.assertEqual(g.returncode, 0, g.stdout)
        st = json.loads((self.d / ".harness" / "blast-radius.json").read_text())
        self.assertEqual(st["sprints"]["sprint-01"]["human_gate"]["status"], "not-needed")

    def test_high_radius_waits_then_approval_clears_and_logs(self):
        p = self.contract(MONEY_LOW.replace("(radius: low)", "(radius: high)"),
                          "sprint-02")
        run([str(SCRIPTS / "blast_radius.py"), "classify", str(p), "--write"], self.d)
        g = run([str(SCRIPTS / "blast_radius.py"), "gate-check"], self.d)
        self.assertEqual(g.returncode, 2, g.stdout)  # AWAITING HUMAN
        bad = run([str(SCRIPTS / "blast_radius.py"), "approve", "--sprint",
                   "sprint-02", "--who", "t", "--rationale", "  "], self.d)
        self.assertEqual(bad.returncode, 1)  # rationale required
        ok = run([str(SCRIPTS / "blast_radius.py"), "approve", "--sprint",
                  "sprint-02", "--who", "t", "--rationale", "test mode only"], self.d)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        g2 = run([str(SCRIPTS / "blast_radius.py"), "gate-check"], self.d)
        self.assertEqual(g2.returncode, 0)
        self.assertIn("Human gate", (self.d / "docs" / "decision-log.md").read_text())

    def test_legacy_project_without_classification_not_blocked(self):
        r = run([str(SCRIPTS / "blast_radius.py"), "gate-check"], self.d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("not blocking", r.stdout)


class TestSecondOpinion(Tmp):
    def setUp(self):
        super().setUp()
        (self.d / "artifact.md").write_text("refund route lacks a signature check\n")
        self.bin = self.d / "bin"
        self.bin.mkdir()

    def fake_cli(self, name, body):
        p = self.bin / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

    def path_env(self, with_fakes):
        base = os.environ.get("PATH", "")
        return {"PATH": (f"{self.bin}:{base}" if with_fakes else "/usr/bin:/bin")}

    def test_single_provider_warning_when_no_cli(self):
        r = run([str(SCRIPTS / "second_opinion.py"), "--artifact", "artifact.md",
                 "--stage", "s1"], self.d, env=self.path_env(False))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SINGLE_PROVIDER", r.stdout)
        warn = (self.d / ".harness" / "run-warnings.jsonl").read_text()
        self.assertIn("SINGLE_PROVIDER", warn)
        self.assertIn("Unavailable",
                      (self.d / ".harness" / "second-opinions" / "so-s1.md").read_text())

    def test_opinion_captured_from_fake_gemini(self):
        self.fake_cli("gemini", "#!/bin/sh\necho 'Finding 1: unsigned refund route.'\n"
                                "echo 'SECOND-OPINION: concerns'\n")
        r = run([str(SCRIPTS / "second_opinion.py"), "--artifact", "artifact.md",
                 "--stage", "s1"], self.d, env=self.path_env(True))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = (self.d / ".harness" / "second-opinions" / "so-s1.md").read_text()
        self.assertIn("**gemini**", out)
        self.assertIn("Verdict line: **concerns**", out)
        self.assertIn("ADVISORY EVIDENCE", out)

    def test_failing_cli_degrades_never_gates(self):
        self.fake_cli("gemini", "#!/bin/sh\nexit 7\n")
        r = run([str(SCRIPTS / "second_opinion.py"), "--artifact", "artifact.md",
                 "--stage", "s2"], self.d, env=self.path_env(True))
        self.assertEqual(r.returncode, 0)
        self.assertIn("UNAVAILABLE", r.stdout)


if __name__ == "__main__":
    unittest.main()
