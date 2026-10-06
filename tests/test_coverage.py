#!/usr/bin/env python3
"""v3.5.1: coverage of every testable item, runtime markers and cross-role rules.

The TaskBoard sample's documents are the fixture. Coverage is per project: the
validator enumerates whatever FR / NFR / AC / BR / EC / use-case flows /
features / flow steps the documents define, so every check below edits the
documents and expects the gap to be named."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_product_map import Fixture, all_tcs, ideal_markers  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
sys.path.insert(0, str(S))
import validate_product_map as v  # noqa: E402


class TestItems(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def model(self):
        return json.loads((self.f.dir / ".harness/product-map.json").read_text())

    def test_every_kind_is_enumerated_from_the_documents(self):
        r = self.f.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        c = self.model()["coverage"]
        self.assertEqual({k: x["total"] for k, x in c.items()},
                         {"FR": 11, "NFR": 2, "AC": 22, "BR": 2, "EC": 2, "UC": 8, "UC-ALT": 5,
                          "F": 8, "STEP": 17, "EXC": 4})
        self.assertTrue(all(x["declared"] == x["total"] for x in c.values()))
        items = self.model()["items"]
        # two labels on one bullet ("E1: …; A1: …") are two items
        self.assertIn("UC-07.E1", items)
        self.assertIn("UC-07.A1", items)
        self.assertEqual(items["AC-03.2"]["kind"], "AC")
        md = (self.f.dir / "docs/product-map.md").read_text()
        self.assertIn("## Coverage of every testable item", md)
        self.assertIn("| AC-03.2 |", md)

    def test_a_new_item_without_a_test_case_is_a_gap(self):
        self.f.edit("02-requirements.md", "- BR-02:", "- BR-03: Archived tasks are read-only.\n- BR-02:")
        r = self.f.check()
        self.assertEqual(r.returncode, 0, r.stdout)                       # warning while building
        self.assertIn("BR-03 (business rule: Archived tasks are read-only.) is not named by any test case", r.stdout)
        r = self.f.check("--require-coverage")
        self.assertEqual(r.returncode, 1)                                 # error at the end of discovery
        self.assertIn("ERROR: BR-03", r.stdout)

    def test_new_acceptance_criterion_and_use_case_flow(self):
        self.f.edit("02-requirements.md", "- AC-03.2:", "- AC-03.3: Ticking twice quickly leaves one change.\n- AC-03.2:")
        self.f.edit("02b-use-cases.md", "E1: deleting is not allowed", "E2: the task is already gone → nothing happens; E1: deleting is not allowed")
        r = self.f.check("--require-coverage")
        self.assertEqual(r.returncode, 1)
        self.assertIn("AC-03.3", r.stdout)
        self.assertIn("UC-07.E2", r.stdout)

    def test_covers_must_name_defined_items(self):
        self.f.edit("02e-test-cases.md", "- Covers: AC-03.2, FR-03", "- Covers: AC-03.9, FR-03")
        r = self.f.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("TC-24 covers AC-03.9, which no document defines", r.stdout)

    def test_cross_role_needs_a_step_for_the_affected_role(self):
        self.f.edit("02c-features.md", "| Team member |\n", "| Guest |\n")
        r = self.f.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("changes what Guest can do, but no flow has a Guest step", r.stdout)

    def test_a_switch_needs_on_and_off_tests_from_the_affected_side(self):
        # TC-23 (member, deleting off) becomes an admin test: only the "on" side is left
        p = self.f.dir / "docs/02e-test-cases.md"
        s = p.read_text()
        start = s.index("### TC-23")
        end = s.index("### ", start + 4)
        p.write_text(s[:start] + s[start:end].replace("- Persona: Team member", "- Persona: Team admin") + s[end:])
        r = self.f.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("F-07 (", r.stdout)
        self.assertIn("with it on and with it off — needs 2 test case(s) with Persona Team member covering F-07, found 1",
                      r.stdout)
        self.assertEqual(self.f.check("--require-coverage").returncode, 1)

    def test_item_helpers(self):
        self.assertEqual(v.kind_of("AC-03.2"), "AC")
        self.assertEqual(v.kind_of("UC-07.E1"), "UC-ALT")
        self.assertEqual(v.kind_of("PF-02.E1"), "EXC")
        self.assertEqual(v.kind_of("PF-02.3"), "STEP")
        self.assertEqual(v.items_in("AC-01.1, BR-02 and UC-07.A1; F-07"), ["AC-01.1", "BR-02", "UC-07.A1", "F-07"])
        self.assertEqual(v.ids("UC-07 and UC-07.E1", "UC"), ["UC-07"])


class TestRuntimeMarkers(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.passed = {t: "passed" for t in all_tcs()}

    def tearDown(self):
        self.f.close()

    def gate(self, coverage):
        self.f.results(self.passed, coverage=coverage)
        return self.f.check("--gate")

    def test_ideal_markers_pass_the_gate(self):
        r = self.gate("ideal")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("81 reached by a passing test", r.stdout)
        md = (self.f.dir / "docs/product-map.md").read_text()
        self.assertIn("✅ tested", md)
        self.assertNotIn("not reached", md)

    def test_no_markers_fail_the_gate(self):
        r = self.gate(None)
        self.assertEqual(r.returncode, 1)
        self.assertIn("the test run recorded no coverage markers", r.stdout)

    def test_a_must_step_nobody_reached(self):
        m = ideal_markers(self.f.dir / "docs")
        m["TC-03"].remove("PF-02.3")
        r = self.gate(m)
        self.assertEqual(r.returncode, 1)
        self.assertIn("PF-02.3 was never reached by a passing test", r.stdout)

    def test_a_covers_item_its_test_never_marked(self):
        m = ideal_markers(self.f.dir / "docs")
        m["TC-24"].remove("AC-03.2")
        r = self.gate(m)
        self.assertEqual(r.returncode, 1)
        self.assertIn("TC-24 says it covers AC-03.2, but its test never marked it", r.stdout)
        self.assertIn("AC-03.2", r.stdout.split("no passing test reached:")[1])

    def test_markers_of_a_failing_test_do_not_count(self):
        self.passed["TC-24"] = "failed"
        r = self.gate("ideal")
        self.assertEqual(r.returncode, 1)
        self.assertIn("TC-24", r.stdout)
        self.assertIn("2 testable item(s) no passing test reached: FR-03, AC-03.2", r.stdout)

    def test_a_step_marker_reaches_its_use_case_and_feature(self):
        m = {"TC-03": ["PF-02.1"]}
        self.f.results(self.passed, coverage=m)
        self.f.check("--results", "latest")
        items = json.loads((self.f.dir / ".harness/product-map.json").read_text())["items"]
        self.assertEqual(items["UC-02"]["executed_by"], ["TC-03"])
        self.assertEqual(items["F-02"]["executed_by"], ["TC-03"])
        self.assertEqual(items["AC-02.1"]["executed_by"], [])


class TestRunTestsMarkers(unittest.TestCase):
    """run_tests.py collects the markers every framework writes, and they reach facts and the report."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-cov-"))
        (self.d / ".harness").mkdir()
        lines = [
            {"framework": "playwright", "test": "[TC-03] journey", "tc": ["TC-03"], "kind": "step", "items": ["PF-02.1"]},
            {"framework": "playwright", "test": "[TC-03] journey", "tc": ["TC-03"], "kind": "covers", "items": ["AC-02.3"]},
            {"framework": "playwright", "test": "[TC-03] journey", "tc": ["TC-03"], "kind": "step", "items": ["PF-02.1"]},
            {"framework": "playwright", "test": "perf", "tc": ["TC-25"], "kind": "metric",
             "name": "board-render-500", "value": 1200, "unit": "ms", "budget": 1000},
            {"framework": "playwright", "test": "no id", "tc": [], "kind": "covers", "items": ["AC-01.1"]},
        ]
        cy = [{"framework": "cypress", "test": "[TC-23] off", "tc": ["TC-23"], "kind": "covers", "items": ["AC-07.2", "BR-02"]}]
        (self.d / "suite.py").write_text(
            "import os, json, pathlib\n"
            "r = pathlib.Path(os.environ['ASDR_RESULTS_DIR'])\n"
            "(r/'junit').mkdir(parents=True, exist_ok=True); (r/'coverage').mkdir(exist_ok=True)\n"
            f"(r/'coverage'/'playwright.jsonl').write_text({json.dumps(chr(10).join(json.dumps(x) for x in lines))})\n"
            f"(r/'coverage'/'cypress.jsonl').write_text({json.dumps(chr(10).join(json.dumps(x) for x in cy))})\n"
            "(r/'junit'/'s.xml').write_text('<testsuite><testcase name=\"[TC-03] journey\" classname=\"c\"/></testsuite>')\n")
        cfg = {"schema": 1, "product": "Demo", "app": {},
               "suites": [{"name": "s", "framework": "playwright", "cmd": f"{sys.executable} suite.py",
                           "junit": ["junit/s.xml"]}]}
        (self.d / ".harness/test-config.json").write_text(json.dumps(cfg))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_py(self, *args):
        e = dict(os.environ)
        e.pop("ASDR_COMMIT", None)
        return subprocess.run([sys.executable, *args], cwd=self.d, capture_output=True, text=True, env=e, timeout=120)

    def test_markers_to_summary_facts_and_report(self):
        r = self.run_py(str(S / "run_tests.py"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("coverage markers: 4 distinct items marked by 2 test cases, 1 measurements", r.stdout)
        p = json.loads((self.d / ".harness/test-results/latest.json").read_text())["path"]
        cov = json.loads((Path(p) / "summary.json").read_text())["coverage"]
        self.assertEqual(cov["by_tc"], {"TC-03": ["AC-02.3", "PF-02.1"], "TC-23": ["AC-07.2", "BR-02"]})
        self.assertEqual(cov["untagged_markers"], 1)
        self.assertEqual(cov["metrics"][0]["within_budget"], False)
        self.run_py(str(S / "emit_facts.py"), "--no-tests", "--out", ".harness/facts.json")
        f = json.loads((self.d / ".harness/facts.json").read_text())
        self.assertEqual(f["test_runs"]["metrics"]["board-render-500"],
                         {"value": 1200, "unit": "ms", "budget": 1000, "within_budget": False})
        self.run_py(str(S / "publish_test_report.py"), "--label", "x")
        html = (self.d / "docs/test-reports/x/index.html").read_text()
        self.assertIn("<h2>Measurements</h2>", html)
        self.assertIn("over budget", html)


class TestCoverHelpers(unittest.TestCase):
    def test_helpers_write_the_same_record_shape(self):
        for f, needles in {
            "templates/e2e/playwright/asdr-cover.ts": ["export async function flowStep", "export function covers",
                                                       "export function metric", "playwright.jsonl"],
            "templates/e2e/cypress/asdr-cover.js": ["'flowStep'", "'covers'", "'metric'", "asdrCover"],
            "templates/e2e/cypress/asdr-cover-plugin.js": ["asdrCover", "cypress.jsonl"],
            "templates/e2e/selenium/asdr_cover.py": ["def flow_step", "def covers", "def metric", "selenium.jsonl"],
        }.items():
            text = (REPO / f).read_text()
            for n in needles:
                self.assertIn(n, text, f"{f}: {n}")

    def test_selenium_helper_records_markers(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-sel-"))
        try:
            code = ("import os, sys; sys.path.insert(0, %r)\n"
                    "os.environ['PYTEST_CURRENT_TEST'] = 'e2e/test_board.py::test_tc_16_done (call)'\n"
                    "from asdr_cover import flow_step, covers, metric\n"
                    "flow_step('PF-02.3'); covers('AC-03.1', 'AC-04.2'); metric('t', 5, 'ms', 10)\n"
                    % str(REPO / "templates/e2e/selenium"))
            e = dict(os.environ, ASDR_RESULTS_DIR=str(d))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=e, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            recs = [json.loads(x) for x in (d / "coverage/selenium.jsonl").read_text().splitlines()]
            self.assertEqual([x["kind"] for x in recs], ["step", "covers", "metric"])
            self.assertEqual(recs[0]["tc"], ["TC-16"])
            self.assertEqual(recs[1]["items"], ["AC-03.1", "AC-04.2"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
