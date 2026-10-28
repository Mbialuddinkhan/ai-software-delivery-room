#!/usr/bin/env python3
"""v4.1: resuming a run that began on an earlier ASDR (found on the first real
4.0 trial, a Dataistan build paused at sprint 2): the documents later versions
added are offered, gate-read ones first; the settings gate skips a register the
user did not write; the estimate counts what is left; the dashboard explains
late-start and resumed-run gaps instead of calling them missing."""
import argparse
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
import estimate_run as er  # noqa: E402


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last(stdout, tag):
    return json.loads([x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1][len(tag) + 2:])


OLD_RUN_DOCS = ["docs/01-product-brief.md", "docs/02-requirements.md", "docs/02b-use-cases.md",
                "docs/03-architecture.md", "docs/05-security.md"]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-v41-"))
        (self.d / ".harness").mkdir()
        (self.d / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def touch(self, rel, text="x\n"):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def old_run(self):
        """A run that began before 3.5: no feature list, flows, test cases, options or settings."""
        for d in OLD_RUN_DOCS:
            self.touch(d, "# doc\ncontent\n")
        self.touch("docs/decision-discovery.md", "verdict: go\n")
        self.touch("docs/decision-architecture.md", "verdict: go\n")
        self.touch(".harness/progress.json", json.dumps({"phase": "execution", "sprint": "sprint-02",
                                                         "awaiting": "evaluate", "rigor": "standard"}))
        self.touch("sprints.json", json.dumps({"sprints": [{"id": f"sprint-0{i}", "status": s} for i, s in
                                                           enumerate(["done", "active"] + ["pending"] * 5, 1)]}))

    def choose_resume(self):
        r = run([str(S / "entry_point.py"), "choose", "resume", "--prompt", "continue building"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, json.loads((self.d / ".harness/entry.json").read_text())


class TestResumeGaps(Tmp):
    def test_resume_is_recommended_and_lists_gaps_gate_read_first(self):
        self.old_run()
        r = run([str(S / "entry_point.py"), "recommend", "--prompt", "continue building", "--json"], self.d)
        self.assertEqual(last(r.stdout, "ENTRY")["recommended"], "resume")
        r, entry = self.choose_resume()
        gaps = entry["legacy_gaps"]
        paths = [g["path"] for g in gaps]
        for p in ("docs/02c-features.md", "docs/02d-process-flows.md", "docs/02e-test-cases.md",
                  "docs/03f-configuration.md", "docs/03c-architecture-options.md"):
            self.assertIn(p, paths)
        kinds = {g["path"]: g["kind"] for g in gaps}
        gate = sorted(p for p, k in kinds.items() if k == "gate")
        self.assertEqual(gate, ["docs/02c-features.md", "docs/02d-process-flows.md", "docs/02e-test-cases.md"])
        self.assertEqual(kinds["docs/03f-configuration.md"], "optional")
        self.assertEqual([g["introduced"] for g in gaps if g["path"] == "docs/02c-features.md"], ["3.4"])
        self.assertEqual(kinds["docs/03c-architecture-options.md"], "optional")
        self.assertEqual(kinds["docs/06-devops.md"], "missing", "a core document older than the run is not optional")
        order = [g["kind"] for g in gaps]
        self.assertEqual(order, sorted(order, key=["gate", "missing", "optional"].index), "gate first, optional last")
        self.assertEqual(entry["began_before"], "4.0")
        self.assertEqual(entry["catch_up"], [], "a resume never forces a catch-up")
        self.assertIn("[before release] feature list", r.stdout)
        self.assertIn("[missing] deployment plan", r.stdout)
        self.assertIn("[optional] configurable decisions", r.stdout)
        self.assertIn("added in ASDR 4.0", r.stdout)
        self.assertIn("skips the settings check", r.stdout)
        for p in OLD_RUN_DOCS:
            self.assertNotIn(p, paths)

    def test_core_documents_the_gate_reads_are_never_optional(self):
        self.old_run()
        (self.d / "docs/02b-use-cases.md").unlink()        # a run from before 3.1
        _r, entry = self.choose_resume()
        kinds = {g["path"]: g["kind"] for g in entry["legacy_gaps"]}
        self.assertEqual(kinds["docs/02b-use-cases.md"], "gate")

    def test_a_4_0_run_resumed_has_no_legacy_gaps_and_keeps_its_start(self):
        self.old_run()
        self.touch(".harness/entry.json", json.dumps({"start": "build", "skipped": ["validate", "discover", "design"]}))
        r, entry = self.choose_resume()
        self.assertEqual(entry["legacy_gaps"], [])
        self.assertNotIn("began_before", entry)
        self.assertEqual(entry["resumed_from"]["start"], "build")
        self.assertNotIn("began before", r.stdout)
        g = run([str(S / "validate_configurability.py"), "--gate"], self.d)
        self.assertEqual(g.returncode, 1, "a 4.0 run cannot skip the settings gate by resuming: " + g.stdout)

    def test_resuming_twice_keeps_the_legacy_status(self):
        self.old_run()
        self.choose_resume()
        _r, entry = self.choose_resume()
        self.assertEqual(entry["began_before"], "4.0")
        self.assertTrue(entry["legacy_gaps"])

    def test_a_4_0_resume_record_leaves_the_origin_to_the_user(self):
        self.old_run()
        self.touch(".harness/entry.json", json.dumps({"start": "resume", "catch_up": []}))   # written by 4.0.x
        r, entry = self.choose_resume()
        self.assertTrue(entry["origin_unknown"])
        self.assertNotIn("began_before", entry)
        self.assertIn("cannot tell whether this run began before 4.0", r.stdout)
        g = run([str(S / "validate_configurability.py"), "--gate"], self.d)
        self.assertEqual(g.returncode, 1, "unknown origin: every check applies")
        r = run([str(S / "entry_point.py"), "choose", "resume", "--began-before", "4.0"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        entry = json.loads((self.d / ".harness/entry.json").read_text())
        self.assertEqual(entry["began_before"], "4.0")
        self.assertNotIn("origin_unknown", entry)
        self.assertEqual(run([str(S / "validate_configurability.py"), "--gate"], self.d).returncode, 0)

    def test_an_origin_stamp_decides(self):
        self.old_run()
        self.touch(".harness/origin.json", json.dumps({"asdr_version": "4.1.0"}))   # e.g. started with /discover
        _r, entry = self.choose_resume()
        self.assertEqual(entry["legacy_gaps"], [])
        self.assertNotIn("began_before", entry)
        self.touch(".harness/origin.json", json.dumps({"asdr_version": None}))
        (self.d / ".harness/entry.json").unlink()
        _r, entry = self.choose_resume()
        self.assertEqual(entry["began_before"], "4.0", "an unknown stamp falls back to the record (none: pre-4.0)")

    def test_init_stamps_the_origin_once(self):
        fresh = self.d / "fresh"
        fresh.mkdir()
        run([str(S / "init_asdr.py"), "--source", str(REPO)], fresh)
        v = json.loads((REPO / ".claude-plugin/plugin.json").read_text())["version"]
        self.assertEqual(json.loads((fresh / ".harness/origin.json").read_text())["asdr_version"], v)
        self.old_run()                                          # an existing project, first seen by 4.1
        run([str(S / "init_asdr.py"), "--source", str(REPO)], self.d)
        o = json.loads((self.d / ".harness/origin.json").read_text())
        self.assertIsNone(o["asdr_version"])
        (self.d / ".harness/origin.json").write_text(json.dumps({"asdr_version": "9.9.9"}))
        run([str(S / "init_asdr.py"), "--source", str(REPO)], self.d)
        self.assertEqual(json.loads((self.d / ".harness/origin.json").read_text())["asdr_version"], "9.9.9")

    def test_a_current_run_has_no_gaps(self):
        self.old_run()
        for p, _n, _o in __import__("entry_point").required("build", {"cloud"}):
            self.touch(p, "# doc\ncontent\n")
        r, entry = self.choose_resume()
        self.assertEqual(entry["legacy_gaps"], [])
        self.assertNotIn("earlier ASDR", r.stdout)

    def test_other_starts_record_no_gaps(self):
        r = run([str(S / "entry_point.py"), "choose", "discover"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("legacy_gaps", json.loads((self.d / ".harness/entry.json").read_text()))


class TestSettingsGateOnResume(Tmp):
    def gate(self):
        return run([str(S / "validate_configurability.py"), "--gate"], self.d)

    def test_resumed_pre_4_run_is_skipped_even_with_a_model_plan(self):
        self.old_run()
        self.choose_resume()
        run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        r = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SKIP", r.stdout)
        self.assertIn("resumed under 4.0", r.stdout)
        self.assertTrue(last(r.stdout, "CONFIG")["skipped"])

    def test_a_4_0_design_without_the_register_still_fails(self):
        self.touch(".harness/entry.json", json.dumps({"start": "build", "legacy_gaps": []}))
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ERROR", r.stdout)

    def test_resume_without_the_register_in_its_gaps_still_fails(self):
        self.touch(".harness/entry.json", json.dumps({"start": "resume", "legacy_gaps": [
            {"path": "docs/02c-features.md", "gate": True}]}))
        self.assertEqual(self.gate().returncode, 1)

    def test_a_written_register_is_checked_normally(self):
        self.old_run()
        self.choose_resume()
        self.touch("docs/03f-configuration.md", "# Configuration\n\nno sections\n")
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("SKIP", r.stdout)

    def test_garbage_entry_file_does_not_crash(self):
        for bad in ("[1, 2]", json.dumps({"start": "resume", "began_before": "4.0", "legacy_gaps": 5}),
                    json.dumps({"start": "resume", "began_before": "4.0", "legacy_gaps": [1, "x", None]})):
            self.touch(".harness/entry.json", bad)
            r = self.gate()
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_a_hand_made_resume_record_without_began_before_does_not_skip(self):
        self.touch(".harness/entry.json", json.dumps({"start": "resume", "legacy_gaps": [
            {"path": "docs/03f-configuration.md", "kind": "optional"}]}))
        self.assertEqual(self.gate().returncode, 1)


class TestEstimates(Tmp):
    def est(self, *args):
        r = run([str(S / "estimate_run.py"), *args], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, last(r.stdout, "ESTIMATE")

    def test_resume_counts_the_sprints_left(self):
        self.old_run()
        r, est = self.est("--start", "resume", "--ai")
        self.assertIn("6 sprints left, 1 service, AI, resuming an earlier run (from sprints.json)", r.stdout)
        r4, est4 = self.est("--start", "resume", "--ai", "--sprints", "4")
        self.assertIn("4 sprints", r4.stdout)
        self.assertGreater(est["levels"]["standard"]["agent_runs"], est4["levels"]["standard"]["agent_runs"])

    def test_resume_counts_the_gate_read_catch_up_only_when_missing(self):
        self.old_run()
        _, missing = self.est("--start", "resume", "--sprints", "3")
        for p in ("docs/02c-features.md", "docs/02d-process-flows.md", "docs/02e-test-cases.md"):
            self.touch(p)
        _, present = self.est("--start", "resume", "--sprints", "3")
        self.assertGreater(missing["levels"]["standard"]["agent_runs"], present["levels"]["standard"]["agent_runs"])

    def test_torn_down_sprints_are_not_left_and_an_empty_plan_is_unknown(self):
        self.touch("sprints.json", json.dumps({"sprints": [{"id": "s1", "status": "done"}, {"id": "s2", "status": "torn-down"},
                                                           {"id": "s3", "status": "done"}, {"id": "s4", "status": "active"}]}))
        r, _ = self.est("--start", "resume")
        self.assertIn("1 sprint left,", r.stdout)
        self.touch("sprints.json", json.dumps({"sprints": []}))
        r, _ = self.est("--start", "resume")
        self.assertIn("4 sprints left", r.stdout)
        self.assertNotIn("from sprints.json", r.stdout)

    def test_resume_without_a_sprint_file_defaults_to_four(self):
        r, _ = self.est("--start", "resume")
        self.assertIn("4 sprints", r.stdout)
        self.assertNotIn("from sprints.json", r.stdout)

    def test_release_start_counts_its_catch_up(self):
        a = argparse.Namespace(ui=True, ai=False, cloud=False, services=1, sprints=4)
        runs = er.count_build("standard", a, "release")
        for role in ("product-owner", "business-analyst", "product-manager", "solution-architect", "critic"):
            self.assertIn(role, runs, f"release start should convert {role}'s documents")
        self.assertIn("risk-manager", runs)
        self.assertNotIn("generator", runs, "a release start builds nothing")


class TestDashboardExplainsGaps(Tmp):
    def dash(self, client=False):
        args = [str(S / "build_dashboard.py"), "--no-pdf"]
        env = None
        if client:
            brand = self.d / "brand.json"
            brand.write_text(json.dumps({"monogram": "BK", "lockup": "Test"}))
            args += ["--audience", "client", "--brand", str(brand)]
            env = {"HOME": str(self.d)}
        r = run(args, self.d, env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return (self.d / ("docs/dashboard/client/index.html" if client else "docs/dashboard/index.html")).read_text()

    def row(self, html, path):
        i = html.index(f'<span class="mono">{path}</span>')
        return html[i:html.index("</tr>", i)]

    def test_late_start_decisions_are_covered_by_the_intake_review(self):
        for d in OLD_RUN_DOCS:
            self.touch(d)
        self.touch(".harness/progress.json", json.dumps({"phase": "planning"}))
        self.assertEqual(run([str(S / "entry_point.py"), "choose", "build"], self.d).returncode, 0)
        html = self.dash()
        self.assertIn("due: the intake review", self.row(html, "docs/decision-discovery.md"))
        self.touch("docs/decision-intake.md", "verdict: go\n")
        html = self.dash()
        self.assertIn("covered by the intake review · go", self.row(html, "docs/decision-discovery.md"))
        self.assertIn("covered by the intake review · go", self.row(html, "docs/decision-architecture.md"))
        self.assertIn("decision-intake.md: go", html)

    def test_resumed_run_gaps_are_not_called_missing(self):
        self.old_run()
        self.choose_resume()
        html = self.dash()
        self.assertIn("not in this run yet · needed before release", self.row(html, "docs/02e-test-cases.md"))
        self.assertIn("not in this run (added in ASDR 4.0)", self.row(html, "docs/03f-configuration.md"))
        self.assertNotIn(">missing<", self.row(html, "docs/03f-configuration.md"))
        self.assertIn(">missing<", self.row(html, "docs/06-devops.md"), "a real gap is still called missing")

    def test_a_resumed_late_start_keeps_its_intake_cover(self):
        for d in OLD_RUN_DOCS:
            self.touch(d)
        self.touch(".harness/progress.json", json.dumps({"phase": "execution", "sprint": "sprint-01"}))
        self.assertEqual(run([str(S / "entry_point.py"), "choose", "build"], self.d).returncode, 0)
        self.touch("docs/decision-intake.md", "verdict: go\n")
        self.choose_resume()
        html = self.dash()
        self.assertIn("covered by the intake review · go", self.row(html, "docs/decision-discovery.md"))

    def test_an_intake_review_older_than_the_documents_does_not_cover_them(self):
        for d in OLD_RUN_DOCS:
            self.touch(d)
        self.touch(".harness/progress.json", json.dumps({"phase": "strategic"}))
        run([str(S / "entry_point.py"), "choose", "build"], self.d)
        intake = self.touch("docs/decision-intake.md", "verdict: go\n")
        old = intake.stat().st_mtime - 100
        os.utime(intake, (old, old))
        html = self.dash()
        self.assertIn("due: documents changed after the intake review", self.row(html, "docs/decision-discovery.md"))
        # once the catch-up is over, later edits (setting tests, scope changes) have their own gates
        self.touch(".harness/progress.json", json.dumps({"phase": "execution", "sprint": "sprint-01"}))
        html = self.dash()
        self.assertIn("covered by the intake review · go", self.row(html, "docs/decision-discovery.md"))


class TestSkillWiring(unittest.TestCase):
    def test_resume_protocol_and_estimate_are_documented(self):
        t = " ".join((REPO / "skills/asdr/SKILL.md").read_text().split())
        self.assertIn("legacy_gaps", t)
        self.assertIn("--start resume", t)
        self.assertIn("skips the settings check", t)


if __name__ == "__main__":
    unittest.main()
