#!/usr/bin/env python3
"""v3.4 end-to-end chain: validate_product_map.py and flow-based sprints.

The TaskBoard sample's discovery docs are the fixture: they must pass, and
each deliberate break below must produce the error that names the gap."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
SAMPLE_DOCS = REPO / "examples" / "sample-app" / "docs"
DOCS = ["02-requirements.md", "02b-use-cases.md", "02c-features.md", "02d-process-flows.md", "02e-test-cases.md"]


def run(args, cwd):
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, timeout=60)


class Fixture:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="asdr-pm-"))
        (self.dir / "docs").mkdir()
        for f in DOCS:
            shutil.copy(SAMPLE_DOCS / f, self.dir / "docs" / f)

    def edit(self, name, old, new, count=1):
        p = self.dir / "docs" / name
        s = p.read_text()
        assert old in s, (name, old)
        p.write_text(s.replace(old, new, count))

    def check(self, *extra):
        return run([str(S / "validate_product_map.py"), *extra], self.dir)

    def results(self, statuses: dict, coverage="ideal"):
        """Write a run_tests.py summary where each TC id has the given status.

        coverage: "ideal" = every test case marked exactly what its documents
        say it proves (see ideal_markers); None = no markers; or a by_tc dict."""
        run_dir = self.dir / ".harness/test-results/r1"
        run_dir.mkdir(parents=True)
        cases = [{"name": f"[{tid}] case", "status": st} for tid, st in statuses.items()]
        summary = {"run_id": "r1", "commit": None, "suites": [{"name": "pw", "cases": cases}]}
        if coverage == "ideal":
            coverage = ideal_markers(self.dir / "docs")
        if coverage is not None:
            summary["coverage"] = {"by_tc": coverage, "metrics": [], "untagged_markers": 0}
        (run_dir / "summary.json").write_text(json.dumps(summary))
        (self.dir / ".harness/test-results/latest.json").write_text(json.dumps({"path": str(run_dir)}))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def ideal_markers(docs: Path) -> dict:
    """What a well-instrumented suite marks: a journey marks every step of its
    flow (flowStep), an exception test its exception path, and every test the
    items on its Covers line (covers)."""
    flows_md = (docs / "02d-process-flows.md").read_text()
    out = {}
    for tid, body in re.findall(r"^### (TC-\d+).*?\n(.*?)(?=^### |\Z)",
                                (docs / "02e-test-cases.md").read_text(), re.MULTILINE | re.DOTALL):
        flow = (re.search(r"^- Flow: (PF-\d+(?:\.E\d+)?)", body, re.MULTILINE) or [None, None])[1]
        kind = (re.search(r"^- Type: (\w+)", body, re.MULTILINE) or [None, ""])[1]
        cov = re.search(r"^- Covers: (.*)$", body, re.MULTILINE)
        items = re.findall(r"[A-Z]+-\d+(?:\.[AE]?\d+)?", cov.group(1)) if cov else []
        if flow and kind == "journey":
            items += re.findall(rf"^\| ({re.escape(flow)}\.\d+) \|", flows_md, re.MULTILINE)
        elif flow and ".E" in flow:
            items.append(flow)
        out[tid] = sorted(set(items))
    return out


def all_tcs():
    return re.findall(r"^### (TC-\d+)", (SAMPLE_DOCS / "02e-test-cases.md").read_text(), re.MULTILINE)


class TestProductMap(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_sample_chain_is_whole(self):
        r = self.f.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("5 flows", r.stdout)
        self.assertIn("81/81 testable items named by a test case", r.stdout)
        m = json.loads((self.f.dir / ".harness/product-map.json").read_text())
        self.assertEqual(m["counts"]["requirements_tested"], m["counts"]["requirements"])
        self.assertEqual(m["flows"]["PF-02"]["journey_tests"], ["TC-03"])
        md = (self.f.dir / "docs/product-map.md").read_text()
        self.assertIn("```mermaid", md)
        self.assertIn("| PF-02 · Daily work on the board |", md)

    def test_use_case_on_no_flow(self):
        self.f.edit("02d-process-flows.md", "| PF-04.2 | Team member | Clicks Export CSV | Downloads tasks.csv with every task | UC-05 |",
                    "| PF-04.2 | Team member | Clicks Export CSV | Downloads tasks.csv with every task | UC-04 |")
        r = self.f.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("UC-05 (Export tasks) is not on any process flow", r.stdout)

    def test_unreachable_flow_and_lifecycle_gap(self):
        self.f.edit("02d-process-flows.md", "- Preceded by: PF-02\n- Followed by: none", "- Preceded by: PF-09\n- Followed by: none")
        self.f.edit("02d-process-flows.md", '  PF02 --> PF04["PF-04 · Weekly round-up and export"]', "")
        r = self.f.check()
        self.assertIn("PF-04: Preceded/Followed by PF-09, which is not a flow", r.stdout)
        self.assertIn("PF-04 is missing from the PF-00 lifecycle diagram", r.stdout)

    def test_flow_without_journey_test_and_untested_exception(self):
        self.f.edit("02e-test-cases.md", "- Type: journey\n- Flow: PF-03", "- Type: functional\n- Flow: PF-03")
        self.f.edit("02e-test-cases.md", "- Flow: PF-02.E1", "- Flow: PF-02")
        r = self.f.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("PF-03 has no journey test case", r.stdout)
        self.assertIn("PF-02.E1 (The title is empty or only spaces) has no test case", r.stdout)

    def test_must_feature_off_every_flow(self):
        self.f.edit("02c-features.md", "| F-08 | Sign-out with saved board | Team member, Team admin | Must | MVP | PF-02 |",
                    "| F-08 | Sign-out with saved board | Team member, Team admin | Must | MVP | PF-04 |")
        self.f.edit("02d-process-flows.md", "- Features: F-02, F-03, F-04, F-08", "- Features: F-02, F-03, F-04")
        self.f.edit("02d-process-flows.md", "| UC-08 | F-08 |", "| UC-08 | — |")
        r = self.f.check()
        self.assertIn("F-08 (Sign-out with saved board) is Must but no process flow uses it", r.stdout)

    def test_must_flow_needs_an_exception_path(self):
        self.f.edit("02d-process-flows.md", "| PF-03.E1 | PF-03.1 | The person signed in as a Team member | No Settings link; the settings page is not shown | ends |\n", "")
        r = self.f.check()
        self.assertIn("PF-03 is Must but documents no exception path", r.stdout)

    def test_gate_requires_passing_results_for_must_cases(self):
        r = self.f.check("--gate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no test results", r.stdout)
        statuses = {t: "passed" for t in all_tcs()}
        self.f.results(statuses)
        r = self.f.check("--gate")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("5 flows (5 proven)", r.stdout)
        self.assertIn("81 reached by a passing test", r.stdout)
        shutil.rmtree(self.f.dir / ".harness/test-results")
        statuses["TC-03"] = "failed"
        del statuses["TC-05"]
        self.f.results(statuses)
        r = self.f.check("--gate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("TC-03 (Member works through the day and comes back) FAILED", r.stdout)
        self.assertIn("TC-05 is Must but has no passing result", r.stdout)
        m = json.loads((self.f.dir / ".harness/product-map.json").read_text())
        self.assertEqual(m["flows"]["PF-02"]["status"], "failing")
        self.assertFalse(m["flows"]["PF-03"]["journey_passing"])

    def test_pytest_style_ids_match(self):
        sys.path.insert(0, str(S))
        import validate_product_map as v
        self.assertEqual(v.tc_refs("test_tc_14_quick_add"), ["TC-14"])
        self.assertEqual(v.tc_refs("Board [TC-03] adds and [TC-04]"), ["TC-03", "TC-04"])
        self.assertEqual(v.tc_refs("etc_12"), [])
        self.assertEqual(v.ids("Followed by: PF-02. See PF-01.3 and PF-01.E1", "PF"), ["PF-02"])


class TestFlowBasedSprints(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "docs").mkdir()
        shutil.copy(SAMPLE_DOCS / "02d-process-flows.md", self.d / "docs")

    def tearDown(self):
        shutil.rmtree(self.d)

    def sprints(self, data):
        (self.d / "sprints.json").write_text(json.dumps(data))
        return run([str(S / "validate_sprints.py")], self.d)

    def test_every_must_flow_is_delivered(self):
        sp = [{"id": "sprint-01", "goal": "A new member can sign in and add a first task.", "status": "pending", "flows": ["PF-01"]},
              {"id": "sprint-02", "goal": "Members can work through the day.", "status": "pending", "flows": ["PF-02"]}]
        r = self.sprints(sp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("['PF-03'] are not delivered", r.stdout)
        sp.append({"id": "sprint-03", "goal": "An admin can set up the team.", "status": "pending", "flows": ["PF-03", "PF-04"]})
        self.assertEqual(self.sprints(sp).returncode, 0)

    def test_flows_required_once_flows_doc_exists(self):
        r = self.sprints([{"id": "sprint-01", "goal": "A member can sign in.", "status": "pending"}])
        self.assertIn("no 'flows' list", r.stdout)
        r = self.sprints([{"id": "sprint-01", "goal": "A member can sign in.", "status": "pending", "flows": ["PF-77"]}])
        self.assertIn("flow PF-77 is not in", r.stdout)

    def test_legacy_projects_without_flows_still_validate(self):
        os.remove(self.d / "docs/02d-process-flows.md")
        r = self.sprints([{"id": "sprint-01", "goal": "A member can sign in.", "status": "pending"}])
        self.assertEqual(r.returncode, 0, r.stdout)


class TestAgentsAndSkills(unittest.TestCase):
    def test_product_manager_agent(self):
        text = (REPO / "agents/product-manager.md").read_text()
        fm = text.split("---")[1]
        self.assertIn("name: product-manager", fm)
        self.assertIn("02c-features.md", text)
        self.assertIn("02d-process-flows.md", text)
        self.assertEqual(len(list((REPO / "agents").glob("*.md"))), 18)

    def test_skill_references_exist(self):
        skill = (REPO / "skills/asdr/SKILL.md").read_text()
        for ref in set(re.findall(r"references/[a-z-]+\.md", skill)):
            self.assertTrue((REPO / "skills/asdr" / ref).is_file(), ref)
        fm = (REPO / "skills/asdr/references/file-map.md").read_text()
        for stage in ("features", "process-flows", "test-cases"):
            self.assertIn(f"`{stage}`", fm)


if __name__ == "__main__":
    unittest.main()
