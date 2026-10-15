#!/usr/bin/env python3
"""v3.6: project dashboard, questions log and sprint clock.

The dashboard must never show a number the gates would disagree with, never
show a delivery date it cannot back with measured sprints, and must carry
every section the user asked for."""
import datetime as dt
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
sys.path.insert(0, str(S))
import build_dashboard as bd  # noqa: E402

UTC = dt.timezone.utc


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=180)


class TestStatusRule(unittest.TestCase):
    def test_on_track(self):
        state, reasons = bd.classify({}, {"flows": {"PF-01": {"status": "proven", "priority": "must"}}},
                                     {"test_runs": {"status": "passed", "commit_matches_head": True}}, [], [], [])
        self.assertEqual(state, "on track")

    def test_at_risk_rules(self):
        cases = [
            ({}, {"flows": {"PF-01": {"status": "failing", "priority": "must"}}}, {}, [], [], [], "must-have journey"),
            ({}, {}, {"test_runs": {"a11y": {"serious": 1}}}, [], [], [], "accessibility"),
            ({}, {}, {"test_runs": {"metrics": {"m": {"within_budget": False}}}}, [], [], [], "over budget"),
            ({}, {}, {}, [], [{"severity": "High"}], [], "high/critical risk"),
            ({}, {}, {}, [], [], ["PF-02"], "regression"),
            ({"attempt": 4, "sprint": "sprint-02"}, {}, {}, [], [], [], "attempt 4"),
        ]
        for prog, pm, facts, qs, risks, regs, needle in cases:
            state, reasons = bd.classify(prog, pm, facts, qs, risks, regs)
            self.assertEqual(state, "at risk", needle)
            self.assertIn(needle, "; ".join(reasons))

    def test_blocked_beats_at_risk(self):
        state, reasons = bd.classify({"last_eval_result": "teardown"}, {}, {"test_runs": {"status": "failed"}},
                                     [{"status": "open"}], [], [])
        self.assertEqual(state, "blocked")
        self.assertIn("teardown", reasons[0])
        self.assertTrue(any("waiting on you" in r for r in reasons))
        self.assertTrue(any("test run failed" in r for r in reasons))


def times_from(cycles, now, gap=0.0, active_since=None):
    """Sprint stamps: each finished sprint takes cycles[i] hours, with `gap`
    hours of waiting before the next one starts."""
    out, t = {}, now - dt.timedelta(hours=sum(cycles) + gap * len(cycles) + 50)
    for i, h in enumerate(cycles, 1):
        start = t
        done = start + dt.timedelta(hours=h)
        out[f"sprint-{i:02d}"] = {"start": start, "done": done}
        t = done + dt.timedelta(hours=gap)
    return out


class TestForecast(unittest.TestCase):
    now = dt.datetime(2026, 10, 15, 12, 0, tzinfo=UTC)

    def sprints(self, done, pending):
        return ([{"id": f"sprint-{i:02d}", "status": "done"} for i in range(1, done + 1)]
                + [{"id": f"sprint-{i:02d}", "status": "pending"} for i in range(done + 1, done + pending + 1)])

    def test_no_date_with_fewer_than_two_measured_sprints(self):
        fc = bd.forecast(self.sprints(1, 3), times_from([10], self.now), self.now)
        self.assertFalse(fc["available"])
        self.assertIn("1 more finished sprint", fc["need"][0])
        fc = bd.forecast(self.sprints(0, 3), {}, self.now)
        self.assertFalse(fc["available"])

    def test_expected_date_and_standard_deviation(self):
        # cycles finish-to-finish: 10, 14, 12 → mean 12, sample SD 2; 2 sprints left
        tm = {"sprint-01": {"start": self.now - dt.timedelta(hours=40), "done": self.now - dt.timedelta(hours=30)},
              "sprint-02": {"start": self.now - dt.timedelta(hours=28), "done": self.now - dt.timedelta(hours=16)},
              "sprint-03": {"start": self.now - dt.timedelta(hours=14), "done": self.now - dt.timedelta(hours=4)}}
        # cycle 1 = 10 (start→done), cycle 2 = 30-16 = 14, cycle 3 = 16-4 = 12
        fc = bd.forecast(self.sprints(3, 2), tm, self.now)
        self.assertTrue(fc["available"])
        self.assertEqual([round(x, 6) for x in fc["durs"]], [10, 14, 12])
        self.assertAlmostEqual(fc["mean_h"], 12.0)
        self.assertAlmostEqual(fc["sd_sprint_h"], 2.0)
        # 2 left × 12 h − 4 h already elapsed since the last finish = 20 h
        self.assertAlmostEqual(fc["expected_h"], 20.0)
        self.assertEqual(fc["expected"], self.now + dt.timedelta(hours=20))
        # prediction-interval SD = s·√(k + k²/n) = 2·√(2 + 4/3)
        self.assertAlmostEqual(fc["sd_h"], 2.0 * (2 + 4 / 3) ** 0.5)
        self.assertAlmostEqual(fc["t"], 4.303)                       # Student-t, 2 df
        self.assertEqual(fc["confidence"], "medium")
        lo, hi = fc["r95"]
        self.assertAlmostEqual((hi - fc["expected"]).total_seconds() / 3600, 4.303 * fc["sd_h"], places=4)
        self.assertEqual(len(fc["per_sprint"]), 2)
        self.assertLess(fc["per_sprint"][0][2], fc["per_sprint"][1][2])  # later sprints are less certain

    def test_cycle_time_includes_waiting_between_sprints(self):
        busy = bd.forecast(self.sprints(3, 1), times_from([10, 10, 10], self.now, gap=0), self.now)
        waiting = bd.forecast(self.sprints(3, 1), times_from([10, 10, 10], self.now, gap=6), self.now)
        self.assertGreater(waiting["mean_h"], busy["mean_h"])

    def test_t_table(self):
        self.assertEqual(bd.t95(1), 12.706)
        self.assertEqual(bd.t95(11), 2.228)       # conservative: next-lower df
        self.assertEqual(bd.t95(40), 1.96)

    def test_first_done_stamp_wins(self):
        clock = [{"ts": "2026-10-10T00:00:00+00:00", "event": "start", "sprint": "sprint-01"},
                 {"ts": "2026-10-10T08:00:00+00:00", "event": "done", "sprint": "sprint-01"},
                 {"ts": "2026-10-11T08:00:00+00:00", "event": "done", "sprint": "sprint-01"}]
        t = bd.sprint_times(clock, [])
        self.assertEqual(t["sprint-01"]["done"].hour, 8)
        self.assertEqual(t["sprint-01"]["done"].day, 10)

    def test_trace_fallback(self):
        traces = [{"ts": "2026-10-10T00:00:00+00:00", "actor": "generator", "action": "negotiate-sprint-01", "result": "r1"},
                  {"ts": "2026-10-10T09:00:00+00:00", "actor": "evaluator", "action": "evaluate-sprint-01", "result": "verdict=pass"}]
        t = bd.sprint_times([], traces)
        self.assertEqual((t["sprint-01"]["done"] - t["sprint-01"]["start"]).total_seconds(), 9 * 3600)

    def test_history_logged_only_when_inputs_change(self):
        d = Path(tempfile.mkdtemp())
        try:
            path = d / "fh.jsonl"
            fc = {"available": True, "n": 3, "pending": 2, "expected": self.now, "sd_h": 4.0}
            bd.record_forecast(fc, path)
            bd.record_forecast(fc, path)
            self.assertEqual(len(path.read_text().splitlines()), 1)
            bd.record_forecast({**fc, "n": 4, "pending": 1}, path)
            self.assertEqual(len(path.read_text().splitlines()), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-dash-"))
        h = self.d / ".harness"
        (h / "traces").mkdir(parents=True)
        (self.d / "docs").mkdir()
        now = dt.datetime.now(UTC)
        ts = lambda hrs: (now - dt.timedelta(hours=hrs)).isoformat(timespec="seconds")
        (self.d / "sprints.json").write_text(json.dumps([
            {"id": "sprint-01", "goal": "Sign in", "status": "done", "flows": ["PF-01"]},
            {"id": "sprint-02", "goal": "Daily work", "status": "done", "flows": ["PF-02"]},
            {"id": "sprint-03", "goal": "Admin", "status": "active", "flows": ["PF-03"]},
            {"id": "sprint-04", "goal": "Export", "status": "pending", "flows": ["PF-04"]}]))
        (h / "sprint-clock.jsonl").write_text("\n".join(json.dumps(x) for x in [
            {"ts": ts(40), "event": "start", "sprint": "sprint-01"}, {"ts": ts(30), "event": "done", "sprint": "sprint-01"},
            {"ts": ts(28), "event": "start", "sprint": "sprint-02"}, {"ts": ts(16), "event": "done", "sprint": "sprint-02"},
            {"ts": ts(3), "event": "start", "sprint": "sprint-03"}]) + "\n")
        (h / "progress.json").write_text(json.dumps({"phase": "execution", "sprint": "sprint-03"}))
        (h / "product-map.json").write_text(json.dumps({
            "flows": {"PF-01": {"status": "proven", "priority": "must", "title": "First sign-in"},
                      "PF-02": {"status": "proven", "priority": "must", "title": "Daily work"},
                      "PF-03": {"status": "pending", "priority": "must", "title": "Admin"},
                      "PF-04": {"status": "pending", "priority": "should", "title": "Export"}},
            "features": {"F-01": {"name": "Sign-in", "priority": "must", "flows": ["PF-01"]},
                         "F-02": {"name": "Admin settings", "priority": "must", "flows": ["PF-03"]},
                         "F-03": {"name": "Export", "priority": "should", "flows": ["PF-04"]},
                         "F-04": {"name": "Sign-out", "priority": "must", "flows": ["PF-02", "PF-03"]}},
            "counts": {"items": 10, "items_executed": 6}}))
        (h / "dashboard.json").write_text(json.dumps({
            "project": "Demo",
            "environments": [{"name": "Local", "url": "http://localhost:3000"},
                             {"name": "Test", "url": "<https://test.example.com>"},
                             {"name": "Staging", "url": "https://staging.asdr-test.invalid", "test_roles": ["member"]}],
            "links": [{"label": "CI", "url": "https://ci.asdr-test.invalid"}]}))
        with (h / "questions.jsonl").open("w") as f:
            for q in [{"id": "Q-01", "question": "Shared board?", "answer": None, "status": "open"},
                      {"id": "Q-02", "question": "CSV columns?", "answer": "id,title", "status": "answered", "changed": ["docs/02-requirements.md"]},
                      {"id": "Q-01", "question": "Shared board?", "answer": "Yes, one per team", "status": "answered"}]:
                f.write(json.dumps({"ts": ts(1), **q}) + "\n")
        (self.d / "docs/01-product-brief.md").write_text("# brief\n")
        (self.d / "docs/notes.md").write_text("# notes\n")
        (self.d / "docs/09-risk-register.md").write_text(
            "| ID | Risk | Severity | Likelihood | Owner | Mitigation | Status |\n|---|---|---|---|---|---|---|\n"
            "| R-1 | Data loss | High | Low | devops | backups | Open |\n| R-2 | Old risk | Low | Low | x | y | Closed |\n")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)


class TestDashboardBuild(Fixture):
    def test_every_section_and_rule(self):
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = (self.d / "docs/dashboard/index.html").read_text()
        for sid in ("glance", "phases", "forecast", "roadmap", "features", "speed", "quality", "risks",
                    "decisions", "documents", "environments", "repos", "activity", "effort"):
            self.assertIn(f'id="{sid}"', h, sid)
        self.assertIn("Expected delivery", h)                 # 2 measured cycles → a date
        self.assertIn("1 standard deviation", h)
        self.assertIn("AT RISK", h)                           # open high risk, Q-01 superseded → not blocked
        self.assertNotIn("Waiting on you</h3><div class=\"q open\"", h)
        self.assertIn("Yes, one per team", h)
        self.assertIn("R-1", h)
        self.assertNotIn("Old risk", h)                       # closed risks are not shown
        self.assertIn("in progress", h)                       # F-02 sits on the active sprint
        self.assertIn("verified", h)                          # F-01's journey is proven
        self.assertIn("planned", h)                           # F-03's sprint has not started
        self.assertIn("staging.asdr-test.invalid", h)
        self.assertNotIn("test.example.com", h)               # unfilled template rows are skipped
        self.assertIn("local only", h)
        self.assertIn("docs/notes.md", h)                     # every other document is listed
        self.assertIn("missing", h)                           # discovery docs absent after discovery ended
        self.assertTrue((self.d / ".harness/forecast-history.jsonl").is_file())
        self.assertTrue((self.d / ".harness/dashboard-snapshot.json").is_file())

    def test_regression_is_detected_on_the_next_build(self):
        run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        pm = json.loads((self.d / ".harness/product-map.json").read_text())
        pm["flows"]["PF-01"]["status"] = "failing"
        (self.d / ".harness/product-map.json").write_text(json.dumps(pm))
        run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        h = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("regression: PF-01", h)

    def test_no_date_before_two_sprints(self):
        (self.d / ".harness/sprint-clock.jsonl").write_text("")
        run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        h = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("No delivery date yet", h)
        self.assertIn("after 2 sprints", h)


class TestClientView(Fixture):
    """--audience client: same facts and status rule, nothing internal, in the consultant's brand."""

    def build_client(self, *extra):
        home = self.d / "home"
        home.mkdir(exist_ok=True)
        cfg = json.loads((self.d / ".harness/dashboard.json").read_text())
        cfg["client"] = {"name": "Acme Logistics", "reference": "BK-2026-014", "hide_risks": ["R-9"]}
        cfg["environments"].append({"name": "Internal sandbox", "url": "https://sandbox.asdr-test.invalid", "client": False})
        cfg["links"].append({"label": "UAT form", "url": "https://forms.asdr-test.invalid/uat", "client": True})
        (self.d / ".harness/dashboard.json").write_text(json.dumps(cfg))
        with (self.d / ".harness/questions.jsonl").open("a") as f:
            f.write(json.dumps({"id": "Q-10", "question": "Which date format do your reports use?", "answer": None,
                                "status": "open", "client": True}) + "\n")
            f.write(json.dumps({"id": "Q-11", "question": "Internal: switch the ORM?", "answer": "No",
                                "status": "answered"}) + "\n")
        with (self.d / "docs/09-risk-register.md").open("a") as f:
            f.write("| R-9 | Margin on fixed price | High | Low | Bilal | track hours | Open |\n"
                    "| R-3 | Vendor API limits | Medium | Low | solution-architect | cache | Open |\n")
        brand = self.d / "brand.json"
        brand.write_text(json.dumps({"monogram": "BK", "lockup": "Bilal Uddin Khan", "footer": "BILALKHAN.CONSULTING · CONFIDENTIAL"}))
        r = run([str(S / "build_dashboard.py"), "--audience", "client", "--no-pdf", "--brand", str(brand), *extra], self.d,
                env={"HOME": str(home)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, (self.d / "docs/dashboard/client/index.html").read_text()

    def test_client_report_content(self):
        r, h = self.build_client()
        for i, title in enumerate(["Summary", "Phases", "Delivery forecast", "Roadmap", "Features", "Quality", "Risks",
                                   "Decisions and what we need from you", "Deliverables", "Environments and links"], 1):
            self.assertIn(f'<span class="no">{i:02d} ·</span>{title}</h2>', h)
        self.assertIn("Prepared for Acme Logistics", h)
        self.assertIn("BK-2026-014", h)
        self.assertIn(">BK<", h)
        self.assertIn("BILALKHAN.CONSULTING · CONFIDENTIAL", h)
        self.assertEqual(h.count('class="callout"'), 1)                  # one callout: the delivery estimate
        self.assertIn("Expected delivery · estimate", h)
        self.assertIn("Which date format do your reports use?", h)       # client question shown
        self.assertIn("staging.asdr-test.invalid", h)
        self.assertIn("forms.asdr-test.invalid/uat", h)
        self.assertIn("Delivery team", h)                                # agent owner → delivery team
        self.assertIn("read it before you send it", r.stdout)

    def test_nothing_internal_leaks(self):
        _, h = self.build_client()
        for leak in ("Internal: switch the ORM", "localhost", "sandbox.asdr-test.invalid", "ci.asdr-test.invalid",
                     "Margin on fixed price", "solution-architect", "ASDR effort", "Recent activity", "Local path",
                     ".harness", "evaluator", "attempt"):
            self.assertNotIn(leak, h, leak)

    def test_status_matches_the_private_view(self):
        _, h = self.build_client()
        run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        private = (self.d / "docs/dashboard/index.html").read_text()
        state = re.search(r'pill state \w+">([A-Z ]+)<', private).group(1).lower()
        self.assertIn(f'class="r ', h)
        self.assertIn(f'>{state}</span>', h)
        self.assertIn("decision(s) waiting on you", h)

    def test_classify_full_same_state_client_wording(self):
        qs = [{"status": "open"}, {"status": "open", "client": True}]
        pm = {"flows": {"PF-01": {"status": "failing", "priority": "must", "title": "First sign-in"}}}
        state, private, client = bd.classify_full({"attempt": 5, "sprint": "sprint-02"}, pm, {}, qs, [], [])
        self.assertEqual(state, "blocked")
        self.assertEqual(len(private), len(client))
        joined = "; ".join(client)
        self.assertIn("1 decision(s) waiting on you", joined)
        self.assertIn("waiting on an internal decision", joined)
        self.assertIn("First sign-in", joined)
        self.assertNotIn("sprint-02", joined)
        self.assertNotIn("PF-01", joined)


class TestLogAndClock(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-log-"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_log_question(self):
        run([str(S / "log_question.py"), "--q", "Which provider?", "--phase", "arch"], self.d)
        run([str(S / "log_question.py"), "--q", "Which provider?", "--a", "Stripe", "--id", "Q-01",
             "--changed", "docs/03-architecture.md, docs/05-security.md"], self.d)
        run([str(S / "log_question.py"), "--q", "Date format?", "--client"], self.d)
        rows = [json.loads(x) for x in (self.d / ".harness/questions.jsonl").read_text().splitlines()]
        self.assertEqual(rows[0]["status"], "open")
        self.assertEqual(rows[0]["id"], "Q-01")
        self.assertEqual(rows[1]["status"], "answered")
        self.assertEqual(rows[1]["changed"], ["docs/03-architecture.md", "docs/05-security.md"])
        self.assertNotIn("client", rows[1])
        self.assertTrue(rows[2]["client"])

    def test_sprint_clock(self):
        self.assertEqual(run([str(S / "sprint_clock.py"), "start", "sprint-03"], self.d).returncode, 0)
        self.assertEqual(run([str(S / "sprint_clock.py"), "start", "sprint-3"], self.d).returncode, 1)
        self.assertEqual(run([str(S / "sprint_clock.py"), "finish", "sprint-03"], self.d).returncode, 1)
        rows = (self.d / ".harness/sprint-clock.jsonl").read_text().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["event"], "start")

    def test_sprints_json_stays_user_visible(self):
        """Timing lives in the clock file because validate_sprints.py forbids extra fields."""
        (self.d / "sprints.json").write_text(json.dumps([{"id": "sprint-01", "goal": "A visitor signs in and sees the board",
                                                          "status": "active", "flows": [], "started_at": "x"}]))
        r = run([str(S / "validate_sprints.py")], self.d)
        self.assertIn("only id, goal, status, flows are allowed", r.stdout)


class TestWiring(unittest.TestCase):
    def test_init_seeds_dashboard_inputs(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-init-"))
        try:
            r = run([str(S / "init_asdr.py"), "--source", str(REPO)], d)
            self.assertEqual(r.returncode, 0, r.stdout)
            cfg = json.loads((d / ".harness/dashboard.json").read_text())
            self.assertEqual(cfg["project"], d.name)
            self.assertTrue((d / ".harness/questions.jsonl").is_file())
            self.assertTrue((d / ".harness/templates/assess/findings.json").is_file())
            self.assertNotIn("password", json.dumps(cfg).lower().replace("never put passwords", ""))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_orchestrator_and_evaluator_call_the_dashboard_tools(self):
        asdr = (REPO / "skills/asdr/SKILL.md").read_text()
        for needle in ("log_question.py", "sprint_clock.py start", "build_dashboard.py", "/asdr status"):
            self.assertIn(needle, asdr)
        self.assertIn("sprint_clock.py done", (REPO / "agents/evaluator.md").read_text())
        for sk in ("discover", "architect", "riskgate", "release", "assess"):
            self.assertIn("build_dashboard.py", (REPO / "skills" / sk / "SKILL.md").read_text(), sk)


if __name__ == "__main__":
    unittest.main()
