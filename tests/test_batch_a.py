#!/usr/bin/env python3
"""v4.2 Batch A: secrets gate, decision log, cost report, founder profile,
and the seeded-defect eval suite's runner mechanics."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
EVALS = ROOT / "evals"
PY = sys.executable


def run(argv, cwd):
    return subprocess.run([PY] + argv, capture_output=True, text=True, cwd=str(cwd))


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.d = Path(self._td.name)
        (self.d / "docs").mkdir()
        (self.d / ".harness").mkdir()

    def tearDown(self):
        self._td.cleanup()


class TestSecretsGate(Tmp):
    def seed(self, text):
        (self.d / "docs" / "evidence.md").write_text(text)

    def test_catches_aws_key_and_url_credentials(self):
        self.seed("key AKIAIOSFODNN7EXAMPLE and postgres://u:Hunter22Hunter@db/x\n")
        r = run([str(SCRIPTS / "check_secrets.py"), "docs", "--gate"], self.d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("SECRET", r.stdout)

    def test_output_is_redacted(self):
        self.seed('password = "Hunter22Hunter"\n')
        r = run([str(SCRIPTS / "check_secrets.py"), "docs", "--gate"], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Hunter22Hunter", r.stdout + r.stderr)

    def test_placeholders_do_not_fire(self):
        self.seed('api_key = "<YOUR_KEY>"\npassword = "changeme-please"\n')
        r = run([str(SCRIPTS / "check_secrets.py"), "docs", "--gate"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_allowlist_and_report_only_mode(self):
        self.seed('token = "WinterProd2026xyz"\n')
        r = run([str(SCRIPTS / "check_secrets.py"), "docs"], self.d)  # no --gate
        self.assertEqual(r.returncode, 0)
        (self.d / ".harness" / "secrets-allowlist.txt").write_text("WinterProd2026xyz\n")
        r = run([str(SCRIPTS / "check_secrets.py"), "docs", "--gate"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("allowed", r.stdout)


class TestDecisionLog(Tmp):
    def test_add_and_collect_are_idempotent(self):
        (self.d / ".harness" / "entry.json").write_text('{"start":"build","reason":"docs exist"}')
        (self.d / ".harness" / "models.json").write_text('{"plan":"economy"}')
        (self.d / ".harness" / "progress.json").write_text('{"rigor":"lite"}')
        run([str(SCRIPTS / "decision_log.py"), "add", "--decision", "Rigor",
             "--chosen", "lite", "--options", "lite|standard|paranoid",
             "--rationale", "demo", "--source", "test"], self.d)
        run([str(SCRIPTS / "decision_log.py"), "collect"], self.d)
        r2 = run([str(SCRIPTS / "decision_log.py"), "collect"], self.d)
        self.assertIn("added 0 new", r2.stdout)
        rows = [l for l in (self.d / "docs" / "decision-log.md").read_text().splitlines()
                if l.startswith("|")]
        self.assertEqual(len(rows), 2 + 4)  # header + separator + 4 unique decisions

    def test_duplicate_add_is_skipped(self):
        for _ in range(2):
            run([str(SCRIPTS / "decision_log.py"), "add", "--decision", "X",
                 "--chosen", "a", "--source", "s"], self.d)
        rows = [l for l in (self.d / "docs" / "decision-log.md").read_text().splitlines()
                if l.startswith("|")]
        self.assertEqual(len(rows), 3)


class TestCostReport(Tmp):
    def write_runs(self):
        lines = [
            {"agent": "generator", "phase": "execution", "stage": "s1",
             "tokens": 500000, "seconds": 600, "model": "sonnet", "result": "ok"},
            {"agent": "evaluator", "phase": "execution", "stage": "s1",
             "tokens": 300000, "seconds": 400, "model": "opus", "result": "ok"},
        ]
        (self.d / ".harness" / "agent-runs.jsonl").write_text(
            "\n".join(json.dumps(x) for x in lines) + "\n")

    def test_totals_and_usd(self):
        self.write_runs()
        r = run([str(SCRIPTS / "cost_report.py"), "--price-opus", "30",
                 "--price-sonnet", "6"], self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((self.d / ".harness" / "cost-report.json").read_text())
        self.assertEqual(data["totals"]["tokens"], 800000)
        self.assertAlmostEqual(data["totals"]["usd"], 0.5 * 6 + 0.3 * 30, places=2)
        self.assertTrue(data["totals"]["usd_complete"])

    def test_unpriced_model_is_flagged_not_zeroed(self):
        self.write_runs()
        r = run([str(SCRIPTS / "cost_report.py"), "--price-opus", "30"], self.d)
        self.assertEqual(r.returncode, 0)
        md = (self.d / "docs" / "cost-report.md").read_text()
        self.assertIn("Incomplete pricing", md)

    def test_no_runs_is_not_an_error(self):
        r = run([str(SCRIPTS / "cost_report.py")], self.d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to report", r.stdout)


class TestFounderProfile(Tmp):
    def test_founder_sets_rigor_and_profile_and_logs(self):
        r = run([str(SCRIPTS / "set_profile.py"), "founder",
                 "--rationale", "one committed buyer"], self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        prof = json.loads((self.d / ".harness" / "profile.json").read_text())
        self.assertEqual(prof["profile"], "founder")
        prog = json.loads((self.d / ".harness" / "progress.json").read_text())
        self.assertEqual(prog["rigor"], "lite")
        self.assertIn("founder", (self.d / "docs" / "decision-log.md").read_text())
        self.assertIn("stay ON", r.stdout)  # the gates-stay-on message

    def test_show_without_profile(self):
        r = run([str(SCRIPTS / "set_profile.py"), "show"], self.d)
        self.assertIn("enterprise", r.stdout)


class TestSeededSuite(unittest.TestCase):
    def test_mechanical_cases_all_caught_and_control_quiet(self):
        r = subprocess.run([PY, str(EVALS / "run_seeded.py")],
                           capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        results = json.loads((EVALS / "results.json").read_text())
        mech = results["mechanical"]
        self.assertGreaterEqual(mech["total"], 11)
        self.assertEqual(mech["caught"], mech["total"],
                         [c for c in mech["cases"] if not c["caught"]])

    def test_gate_passes_against_baseline(self):
        r = subprocess.run([PY, str(EVALS / "run_seeded.py"), "--gate"],
                           capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_agent_layer_prints_not_yet_measured_without_records(self):
        if (EVALS / "agent-results.jsonl").exists() and \
                (EVALS / "agent-results.jsonl").read_text().strip():
            self.skipTest("live agent records exist")
        table = (EVALS / "CATCH-RATES.md").read_text()
        self.assertIn("not yet measured", table)


if __name__ == "__main__":
    unittest.main()
