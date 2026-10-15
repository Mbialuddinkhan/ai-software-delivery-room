#!/usr/bin/env python3
"""v3.7: parity with the old system.

When ASDR takes over an existing system, the behaviours the client keeps must
still behave the same in the new build. These tests pin the comparison rules:
what counts as the same, what may differ, which captures count, and that the
release gate cannot pass on a stale, missing or self-referential comparison."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
sys.path.insert(0, str(S))
import compare_parity as cp  # noqa: E402
import build_dashboard as bd  # noqa: E402

DOC = """# Parity

| ID | Behaviour to keep | From (as-is) | Compare | Ignore | Decision |
|---|---|---|---|---|---|
| PAR-01 | Member sees the counter and order | AF-02 | ui-text | whitespace | keep |
| PAR-02 | CSV export rows | AF-07 | file | exported_at, order | keep |
| PAR-03 | Anyone can pick admin | T-02 | ui-text | | change — approved by Jane Doe (client PO), 2026-10-15, email "Roles" |
| PAR-04 | Old print view | AF-09 | ui-text | | drop — approved by Jane Doe, 2026-10-15, workshop notes |
"""


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=120)


def last_json(stdout, tag):
    line = [x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1]
    return json.loads(line[len(tag) + 2:])


def summary(run_id, url, caps, failed=(), role=None, commit="abc1234"):
    """A run_tests.py summary: one passing test per test case in caps, except `failed`."""
    tcs = sorted({c["tc"] for c in caps} | set(failed))
    cases = [{"name": f"[{t}] test", "classname": "", "status": "failed" if t in failed else "passed"} for t in tcs]
    return {"run_id": run_id, "commit": commit, "finished_at": "2026-10-15T07:00:00+00:00", "parity_role": role,
            "environment": {"base_url": url},
            "suites": [{"name": "playwright", "cases": cases}],
            "coverage": {"by_tc": {}, "metrics": [], "untagged_markers": 0,
                         "parity": [{"id": c["id"], "label": c.get("label", ""), "value": c["value"], "tc": [c["tc"]],
                                     "test": f"[{c['tc']}] test", "framework": "playwright"} for c in caps]}}


class TestNormalise(unittest.TestCase):
    def test_ignore_rules(self):
        n = cp.normalise
        self.assertEqual(n({"a": 1, "meta": {"exported_at": "x", "b": 2}}, ["exported_at"]), {"a": 1, "meta": {"b": 2}})
        self.assertEqual(n("Saved 2026-10-15T07:01:02Z at 9:15 AM", ["timestamps"]), "Saved <ts> at <ts>")
        self.assertEqual(n("id 123e4567-e89b-12d3-a456-426614174000", ["uuids"]), "id <uuid>")
        self.assertEqual(n([3, 1, 2], ["order"]), [1, 2, 3])
        self.assertEqual(n("b\na", ["order"]), "a\nb")
        self.assertEqual(n("  1 open ·\n 1 done ", ["whitespace"]), "1 open · 1 done")
        self.assertEqual(n("Open", ["case"]), "open")
        self.assertEqual(n([{"task_id": 7, "title": "x"}], ["numbers-in-ids"]), [{"task_id": "<id>", "title": "x"}])
        self.assertEqual(n({"a": [1, 2]}, []), {"a": [1, 2]})               # no rules → untouched
        self.assertNotEqual(cp.canon(n([2, 1], [])), cp.canon(n([1, 2], [])))  # order matters unless ignored


class TestDoc(unittest.TestCase):
    def test_decisions_and_approvals(self):
        d = Path(tempfile.mkdtemp())
        try:
            f = d / "p.md"
            f.write_text(DOC + "| PAR-05 | Fees | BR-1 | data | | change |\n"
                               "| PAR-06 | Tax | BR-2 | data | | change — <approved by …> |\n")
            warns = []
            doc = cp.read_doc(f, warns)
            self.assertEqual(doc["PAR-01"]["decision"], "keep")
            self.assertEqual(doc["PAR-02"]["ignore"], ["exported_at", "order"])
            self.assertEqual(doc["PAR-03"]["decision"], "change")
            self.assertIn("Jane Doe", doc["PAR-03"]["approval"])
            self.assertEqual(doc["PAR-04"]["decision"], "drop")
            self.assertEqual(doc["PAR-05"]["decision"], "keep")        # a change nobody approved is a keep
            self.assertEqual(doc["PAR-06"]["decision"], "keep")        # a placeholder is not an approval
            self.assertEqual(len(warns), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestCompare(unittest.TestCase):
    OLD = [{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open ·  1 done", "tasks": ["A", "B"]}},
           {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A", "exported_at": "1"}, {"t": "B"}]},
           {"id": "PAR-03", "tc": "TC-92", "value": "role picker"}]

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-par-"))
        (self.d / "docs").mkdir()
        (self.d / "docs/02f-parity.md").write_text(DOC)
        self.write("old", summary("r-old", "http://old:8080", self.OLD, role="old"))
        rt = self.d / ".harness/test-results"
        (rt / "parity-baseline.json").write_text(json.dumps({"path": str(rt / "old")}))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, name, s):
        rd = self.d / ".harness/test-results" / name
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "summary.json").write_text(json.dumps(s))
        if name != "old":
            (self.d / ".harness/test-results/latest.json").write_text(json.dumps({"path": str(rd)}))

    def new(self, caps, **kw):
        self.write("new", summary("r-new", kw.pop("url", "http://new:8080"), caps, **kw))

    def compare(self, *extra):
        r = run([str(S / "compare_parity.py"), *extra], self.d)
        out = json.loads((self.d / ".harness/parity.json").read_text()) if (self.d / ".harness/parity.json").is_file() else {}
        return r, out

    def test_same_after_ignore_rules(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "B"}, {"t": "A", "exported_at": "2"}]},
                  {"id": "PAR-03", "tc": "TC-92", "value": "assigned by an administrator"}])
        r, out = self.compare()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(out["all_kept_match"])
        st = {k: v["status"] for k, v in out["items"].items()}
        self.assertEqual(st, {"PAR-01": "same", "PAR-02": "same", "PAR-03": "changed", "PAR-04": "dropped"})
        rep = (self.d / "docs/parity-report.md").read_text()
        self.assertIn("2/2 kept behaviours match", rep)
        self.assertIn("approved by Jane Doe", rep)

    def test_a_kept_behaviour_that_differs_fails_with_a_diff(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 to do · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A"}, {"t": "B"}]},
                  {"id": "PAR-03", "tc": "TC-92", "value": "x"}])
        r, out = self.compare()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out["items"]["PAR-01"]["status"], "differs")
        self.assertIn('-  "counter": "1 open', out["items"]["PAR-01"]["diff"].replace(' "counter"', '  "counter"'))
        self.assertIn("1 to do", (self.d / "docs/parity-report.md").read_text())
        self.assertFalse(out["all_kept_match"])

    def test_captures_from_failing_tests_do_not_count(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A"}, {"t": "B"}]}],
                 failed=("TC-90",))
        r, out = self.compare()
        self.assertEqual(out["items"]["PAR-01"]["status"], "not captured")
        self.assertIn("TC-90, which did not pass", r.stdout)
        self.assertEqual(r.returncode, 0)                      # a warning while building …
        r, _ = self.compare("--gate")
        self.assertEqual(r.returncode, 1)                      # … an error at the gate

    def test_unstable_capture(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": "a"}, {"id": "PAR-01", "tc": "TC-93", "value": "b"},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A"}, {"t": "B"}]}])
        r, out = self.compare()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out["items"]["PAR-01"]["status"], "unstable")
        self.assertIn("not deterministic", r.stdout)

    def test_missing_label_differs(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "admin", "value": [{"t": "A"}, {"t": "B"}]}])
        r, out = self.compare()
        self.assertEqual(out["items"]["PAR-02"]["status"], "differs")
        self.assertIn("missing in the new build", out["items"]["PAR-02"]["diff"])

    def test_change_that_was_not_built_is_flagged(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A"}, {"t": "B"}]},
                  {"id": "PAR-03", "tc": "TC-92", "value": "role picker"}])
        r, out = self.compare()
        self.assertEqual(out["items"]["PAR-03"]["status"], "change not seen")
        self.assertIn("was the change built?", r.stdout)

    def test_comparing_a_system_with_itself_is_refused(self):
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open ·  1 done", "tasks": ["A", "B"]}}],
                 url="http://old:8080")
        r, _ = self.compare()
        self.assertEqual(r.returncode, 1)
        self.assertIn("compares a system with itself", r.stdout)

    def test_gate_needs_a_real_old_system_baseline_and_current_commit(self):
        self.write("old", summary("r-old", "http://old:8080", self.OLD, role=None))
        self.new([{"id": "PAR-01", "tc": "TC-90", "value": {"counter": "1 open · 1 done", "tasks": ["A", "B"]}},
                  {"id": "PAR-02", "tc": "TC-91", "label": "member", "value": [{"t": "A"}, {"t": "B"}]}])
        r, _ = self.compare()
        self.assertEqual(r.returncode, 0)
        self.assertIn("not recorded with --parity old", r.stdout)
        r, _ = self.compare("--gate")
        self.assertEqual(r.returncode, 1)

    def test_no_baseline(self):
        (self.d / ".harness/test-results/parity-baseline.json").unlink()
        self.new([])
        r, _ = self.compare()
        self.assertEqual(r.returncode, 1)
        self.assertIn("--parity old", r.stdout)

    def test_no_parity_doc_is_a_no_op(self):
        (self.d / "docs/02f-parity.md").unlink()
        r, _ = self.compare("--gate")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(last_json(r.stdout, "PARITY")["items"], 0)


class TestRunTestsParity(unittest.TestCase):
    """run_tests.py collects parity captures and keeps the old-system run out of 'latest'."""

    def test_collect_and_baseline_pointer(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-rtp-"))
        try:
            rd = d / "run1"
            (rd / "junit").mkdir(parents=True)
            (rd / "coverage").mkdir()
            (rd / "junit/playwright.xml").write_text(
                '<testsuites><testsuite name="s"><testcase name="[TC-90] board" classname="x" time="1"/>'
                '</testsuite></testsuites>')
            (rd / "coverage/playwright.jsonl").write_text(json.dumps(
                {"framework": "playwright", "test": "[TC-90] board", "tc": ["TC-90"], "kind": "parity",
                 "items": ["PAR-01"], "id": "PAR-01", "label": "", "value": {"counter": "1 open"}}) + "\n")
            (d / "cfg.json").write_text(json.dumps({"app": {"url": "http://old:8080"},
                                                    "suites": [{"name": "playwright", "framework": "playwright",
                                                                "cmd": "true", "junit": ["junit/playwright.xml"]}]}))
            r = run([str(S / "run_tests.py"), "--config", "cfg.json", "--collect-only", str(rd), "--parity", "old"], d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            s = json.loads((rd / "summary.json").read_text())
            self.assertEqual(s["parity_role"], "old")
            self.assertEqual(s["coverage"]["parity"][0]["value"], {"counter": "1 open"})
            self.assertEqual(s["coverage"]["by_tc"]["TC-90"], ["PAR-01"])          # a capture also marks coverage
            res = d / ".harness/test-results"
            base = json.loads((res / "parity-baseline.json").read_text())
            self.assertEqual(base["base_url"], "http://old:8080")
            self.assertEqual(base["captures"], 1)
            self.assertFalse((res / "latest.json").exists())                        # never "latest"
            r = run([str(S / "run_tests.py"), "--config", "cfg.json", "--collect-only", str(rd),
                     "--base-url", "http://new:9090"], d)
            self.assertTrue((res / "latest.json").exists())
            self.assertEqual(json.loads((rd / "summary.json").read_text())["environment"]["base_url"], "http://new:9090")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestGateAndWiring(unittest.TestCase):
    def test_product_map_counts_parity_items_and_gate_needs_a_comparison(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-pm-"))
        try:
            shutil.copytree(REPO / "examples/sample-app/docs", d / "docs",
                            ignore=shutil.ignore_patterns("assess", "manuals", "test-reports", "product-map.md"))
            (d / "docs/02f-parity.md").write_text(DOC)
            r = run([str(S / "validate_product_map.py"), "--no-write"], d)
            self.assertIn("PAR-01 (parity items (behaviour kept from the old system)", r.stdout)
            self.assertNotIn("PAR-04 (", r.stdout)                                  # dropped: nothing to test
            r = run([str(S / "validate_product_map.py"), "--no-write", "--gate"], d)
            self.assertIn("no comparison with the old system", r.stdout)
            (d / ".harness").mkdir(exist_ok=True)
            (d / ".harness/parity.json").write_text(json.dumps({"errors": 1, "all_kept_match": False, "new": {},
                                                                  "counts": {"same": 1, "keep": 2, "differs": 1}}))
            r = run([str(S / "validate_product_map.py"), "--no-write", "--gate"], d)
            self.assertIn("parity with the old system fails: 1/2", r.stdout)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_facts(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-pf-"))
        try:
            (d / "docs").mkdir()
            (d / "docs/02f-parity.md").write_text(DOC)
            (d / ".harness").mkdir()
            (d / ".harness/parity.json").write_text(json.dumps(
                {"all_kept_match": True, "errors": 0, "counts": {"same": 2, "keep": 2}, "new": {"run_id": "n"},
                 "old": {"run_id": "o"}, "items": {"PAR-01": {"status": "same", "decision": "keep"}}}))
            r = run([str(S / "emit_facts.py"), "--no-tests"], d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            f = json.loads((d / ".harness/facts.json").read_text())
            self.assertTrue(f["parity"]["all_kept_match"])
            self.assertEqual(f["parity"]["items"]["PAR-01"]["status"], "same")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_dashboard_status(self):
        par = {"counts": {"differs": 1, "same": 1, "keep": 2}, "items": {"PAR-01": {"status": "differs"}}}
        state, reasons = bd.classify({}, {}, {}, [], [], [], par)
        self.assertEqual(state, "at risk")
        self.assertIn("differ from the old system: PAR-01", "; ".join(reasons))
        self.assertEqual(bd.classify({}, {}, {}, [], [], [], {"counts": {"differs": 0}})[0], "on track")

    def test_helpers_and_docs(self):
        self.assertIn("export function parity", (REPO / "templates/e2e/playwright/asdr-cover.ts").read_text())
        self.assertIn("'parity'", (REPO / "templates/e2e/cypress/asdr-cover.js").read_text())
        self.assertIn("def parity", (REPO / "templates/e2e/selenium/asdr_cover.py").read_text())
        tpl = (REPO / "templates/parity.md").read_text()
        self.assertIn("| ID | Behaviour to keep | From (as-is) | Compare | Ignore | Decision |", tpl)
        self.assertIn("--parity old --base-url", (REPO / "skills/assess/SKILL.md").read_text())
        self.assertIn("compare_parity.py --gate", (REPO / "agents/risk-manager.md").read_text())
        self.assertIn("compare_parity.py", (REPO / "agents/evaluator.md").read_text())
        self.assertIn("02f-parity.md", (REPO / "agents/business-analyst.md").read_text())
        self.assertIn("parity(", (REPO / "agents/generator.md").read_text())
        self.assertIn("Changes from the old", (REPO / "agents/release-manager.md").read_text())


if __name__ == "__main__":
    unittest.main()
