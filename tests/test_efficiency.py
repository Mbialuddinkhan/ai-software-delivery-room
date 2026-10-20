#!/usr/bin/env python3
"""v3.8 efficiency: measure every agent run, estimate before choosing rigor,
run cheap roles on Sonnet, skip the judge when nothing is serious, script the
second round, and give /assess reviewers a starting list of files."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
sys.path.insert(0, str(S))
import estimate_run as er  # noqa: E402
import log_agent_run as lar  # noqa: E402

USAGE = "<usage>subagent_tokens: 300000\ntool_uses: 72\nduration_ms: 1080000</usage>"


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last(stdout, tag):
    return json.loads([x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1][len(tag) + 2:])


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-eff-"))
        (self.d / ".harness").mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)


class TestAgentRunLog(Tmp):
    def test_usage_block_parsed_and_logged(self):
        self.assertEqual(lar.parse_usage(USAGE), {"tokens": 300000, "tool_uses": 72, "ms": 1080000})
        r = run([str(S / "log_agent_run.py"), "--agent", "ai-software-delivery-room:critic", "--phase", "discovery",
                 "--model", "opus", "--usage", USAGE], self.d)
        self.assertEqual(r.returncode, 0)
        rec = json.loads((self.d / ".harness/agent-runs.jsonl").read_text())
        self.assertEqual((rec["agent"], rec["tokens"], rec["seconds"], rec["model"]), ("critic", 300000, 1080.0, "opus"))
        self.assertEqual(last(r.stdout, "BUDGET")["state"], "no-budget")

    def test_budget_warn_and_over(self):
        (self.d / ".harness/budget.json").write_text(json.dumps({"tokens": 1_000_000, "hours": 0, "warn_at": 0.8}))
        states = []
        for _ in range(4):
            r = run([str(S / "log_agent_run.py"), "--agent", "critic", "--tokens", "300000"], self.d)
            states.append(last(r.stdout, "BUDGET")["state"])
            self.assertEqual(r.returncode, 0)             # never blocks: the orchestrator asks the user
        self.assertEqual(states, ["ok", "ok", "warn", "over"])
        self.assertIn("OVER BUDGET", r.stdout)

    def test_missing_tokens_warns(self):
        r = run([str(S / "log_agent_run.py"), "--agent", "critic"], self.d)
        self.assertIn("no token count", r.stdout)


class TestEstimate(Tmp):
    def est(self, *args):
        r = run([str(S / "estimate_run.py"), *args], self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, last(r.stdout, "ESTIMATE")["levels"]

    def test_levels_order_and_saving_against_37(self):
        _, lv = self.est("--sprints", "4", "--ui")
        self.assertLess(lv["lite"]["tokens"], lv["standard"]["tokens"])
        self.assertLess(lv["standard"]["tokens"], lv["3.7-standard"]["tokens"])
        self.assertLess(lv["standard"]["agent_runs"], 0.75 * lv["3.7-standard"]["agent_runs"])   # batching
        self.assertGreater(lv["paranoid"]["tokens"], lv["standard"]["tokens"])
        self.assertGreater(lv["standard"]["tokens_sonnet"], 0)

    def test_microservices_and_cloud_cost_more(self):
        _, mono = self.est("--sprints", "4")
        _, micro = self.est("--sprints", "4", "--services", "5", "--cloud")
        self.assertGreater(micro["standard"]["tokens"], mono["standard"]["tokens"])

    def test_set_budget_and_prices(self):
        r, lv = self.est("--sprints", "3", "--rigor", "lite", "--set-budget", "--price-opus", "10", "--price-sonnet", "2")
        b = json.loads((self.d / ".harness/budget.json").read_text())
        self.assertEqual(b["rigor"], "lite")
        self.assertEqual(b["tokens"], int(lv["lite"]["tokens"] * 1.3))
        self.assertIn("usd", lv["lite"])
        self.assertIn("(chosen)", r.stdout)

    def test_calibrates_from_logged_runs(self):
        with (self.d / ".harness/agent-runs.jsonl").open("w") as f:
            for _ in range(3):
                f.write(json.dumps({"agent": "critic", "tokens": 50_000, "seconds": 120}) + "\n")
        t = er.role_table(self.d / ".harness/agent-runs.jsonl")
        self.assertEqual(t["critic"][1], 50_000)
        self.assertTrue(t["critic"][3].startswith("measured here"))

    def test_assess_mode_scales_with_size(self):
        _, small = self.est("--mode", "assess", "--kloc", "10")
        _, big = self.est("--mode", "assess", "--kloc", "80")
        self.assertGreater(big["standard"]["tokens"], small["standard"]["tokens"])
        self.assertLess(small["lite"]["agent_runs"], small["standard"]["agent_runs"])

    def test_model_tiers_match_agent_frontmatter(self):
        sonnet = set()
        for f in (REPO / "agents").glob("*.md"):
            m = re.search(r"^model:\s*(\S+)", f.read_text(), re.M).group(1)
            self.assertIn(f.stem, er.ROLES, f.stem)
            self.assertEqual(m, er.ROLES[f.stem][0], f.stem)
            if m == "sonnet":
                sonnet.add(f.stem)
        self.assertEqual(sonnet, {"stage-planner", "stage-qa", "product-integrity-qa", "documentation",
                                  "release-manager", "planner"})
        for judgement in ("critic", "judge", "security-compliance", "solution-architect", "generator", "evaluator"):
            self.assertEqual(er.ROLES[judgement][0], "opus")


CRIT = """# Critique · discovery

## Findings

### F-01 · Retention missing

- Severity: {s1}
- Where: docs/02-requirements.md "Data is kept"
- Problem: no period
- Required fix: Add NFR-09 with a retention period.

### F-02 · Wording

- Severity: Low
- Where: docs/01-product-brief.md "users"
- Problem: vague
- Required fix: Name the role.

## Summary block

```yaml
findings_total: 2
critical: 0
high: {high}
medium: {med}
low: 1
shortfall_justified: true
```
"""


class TestDecide(Tmp):
    def decide(self, s1="Medium", high=0, med=1, rigor="standard"):
        (self.d / "crit.md").write_text(CRIT.format(s1=s1, high=high, med=med))
        return run([str(S / "decide.py"), "crit.md", "--out", "docs/decision-discovery.md", "--phase", "discovery",
                    "--rigor", rigor], self.d)

    def test_no_high_writes_a_valid_decision(self):
        r = self.decide()
        self.assertEqual(r.returncode, 0, r.stdout)
        d = last(r.stdout, "DECISION")
        self.assertEqual((d["verdict"], d["required_changes"], d["assumptions"]), ("go", ["F-01"], ["F-02"]))
        v = run([str(S / "validate_verdict.py"), "docs/decision-discovery.md", "--type", "decision"], self.d)
        self.assertEqual(v.returncode, 0, v.stdout)
        self.assertIn("Add NFR-09", (self.d / "docs/decision-discovery.md").read_text())

    def test_high_needs_the_judge(self):
        r = self.decide(s1="High", high=1, med=0)
        self.assertEqual(r.returncode, 2)
        self.assertIn("JUDGE: required", r.stdout)
        self.assertFalse((self.d / "docs/decision-discovery.md").exists())

    def test_paranoid_and_inconsistent_need_the_judge(self):
        self.assertEqual(self.decide(rigor="paranoid").returncode, 2)
        self.assertEqual(self.decide(med=3).returncode, 2)        # summary disagrees with the findings


DEC = """# Decision · assessment

## Required changes before proceeding

- **RC-01** · `docs/a.json` · fix a
- **RC-02** · `docs/b.md` · fix b
- **RC-03** · no file named here

## Verdict block

```yaml
verdict: no-go
required_changes: [RC-01, RC-02, RC-03]
reason: round 1
```
"""


class TestRequiredChanges(Tmp):
    def setUp(self):
        super().setUp()
        (self.d / "docs").mkdir()
        for f in ("a.json", "b.md"):
            (self.d / "docs" / f).write_text("before")
        time.sleep(0.05)
        (self.d / "docs/decision.md").write_text(DEC)
        time.sleep(0.05)
        (self.d / "docs/a.json").write_text("after")              # RC-01 applied, RC-02 not

    def test_reports_open_changes(self):
        r = run([str(S / "check_required_changes.py"), "docs/decision.md"], self.d)
        self.assertEqual(r.returncode, 1)
        res = last(r.stdout, "ROUND2")
        self.assertEqual(res["open"], ["RC-02"])
        self.assertIn("RC-03: no file named", r.stdout)

    def test_write_needs_spot_checks_then_appends_a_valid_verdict(self):
        (self.d / "docs/b.md").write_text("after")
        r = run([str(S / "check_required_changes.py"), "docs/decision.md", "--write"], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs --spot-checked", r.stdout)
        r = run([str(S / "check_required_changes.py"), "docs/decision.md", "--write", "--spot-checked", "RC-01",
                 "--gate", f"{sys.executable} -c pass"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        text = (self.d / "docs/decision.md").read_text()
        self.assertIn("## Round 2 (scripted check)", text)
        v = run([str(S / "validate_verdict.py"), "docs/decision.md", "--type", "decision"], self.d)
        self.assertEqual(v.returncode, 0, v.stdout)
        self.assertIn("verdict=go", v.stdout)

    def test_failing_gate_is_no_go(self):
        (self.d / "docs/b.md").write_text("after")
        r = run([str(S / "check_required_changes.py"), "docs/decision.md", "--gate",
                 f"{sys.executable} -c \"raise SystemExit(1)\""], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(last(r.stdout, "ROUND2")["gate"])

    def test_since_overrides_the_decision_time(self):
        r = run([str(S / "check_required_changes.py"), "docs/decision.md", "--since", "2000-01-01T00:00:00Z"], self.d)
        self.assertEqual(last(r.stdout, "ROUND2")["open"], [])


class TestAssessScope(Tmp):
    def test_lists_per_area_with_core_files(self):
        src = self.d / "source"
        for rel, body in {
            "src/Program.cs": "var app = builder.Build();",
            "src/Web/Controllers/OrderController.cs": "[Authorize] class OrderController { status checkout order }",
            "src/Identity/LoginService.cs": "password token jwt authenticate",
            "src/Data/Migrations/2020_Init.Designer.cs": "password token jwt authenticate migration",
            ".github/workflows/ci.yml": "jobs: build",
            "infra/main.bicep": "resource sql",
            "Directory.Packages.props": "<Project/>",
            "tests/OrderTests.cs": "checkout order status",
        }.items():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_text(body)
        ev = self.d / "ev"
        ev.mkdir()
        (ev / "semgrep.json").write_text(json.dumps({"results": [{"path": "src/Identity/LoginService.cs"}]}))
        r = run([str(S / "assess_scope.py"), "--target", str(src), "--evidence", str(ev)], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        sec = (ev / "scope-security.txt").read_text().splitlines()[2:]
        ops = (ev / "scope-operations.txt").read_text().splitlines()[2:]
        self.assertIn("src/Program.cs", sec[:6])                     # core file in every list
        self.assertIn(".github/workflows/ci.yml", ops)
        gen = "src/Data/Migrations/2020_Init.Designer.cs"          # generated code: demoted or dropped
        self.assertTrue(gen not in sec or sec.index("src/Identity/LoginService.cs") < sec.index(gen))
        self.assertIn("src/Identity/LoginService.cs", sec[:8])
        proc = (ev / "scope-process.txt").read_text().splitlines()[2:]
        self.assertLess(proc.index("src/Web/Controllers/OrderController.cs"), proc.index("tests/OrderTests.cs"))


class TestCostOnDashboardAndMetrics(Tmp):
    def test_metrics_and_dashboard(self):
        (self.d / ".harness/budget.json").write_text(json.dumps({"tokens": 500_000, "rigor": "lite"}))
        for a in ("critic", "judge"):
            run([str(S / "log_agent_run.py"), "--agent", a, "--phase", "discovery", "--usage", USAGE], self.d)
        r = run([str(S / "run_metrics.py")], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = json.loads((self.d / ".harness/metrics.json").read_text())
        self.assertEqual(m["cost"]["tokens"], 600_000)
        self.assertEqual(m["cost"]["budget"]["pct"], 120.0)
        self.assertIn("## Cost", (self.d / "docs/run-metrics.md").read_text())
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("Tokens by role", h)
        self.assertIn("over the lite token budget", h)
        self.assertIn("AT RISK", h)


class TestEfficiencyWiring(unittest.TestCase):
    def test_skills_use_the_new_tools(self):
        asdr = (REPO / "skills/asdr/SKILL.md").read_text()
        for needle in ("estimate_run.py", "log_agent_run.py", "decide.py", "check_required_changes.py",
                       "Batches (lite and standard", 'model: "opus"', "--set-budget"):
            self.assertIn(needle, asdr)
        assess = (REPO / "skills/assess/SKILL.md").read_text()
        for needle in ("assess_scope.py", "decide.py", "check_required_changes.py", "estimate_run.py --mode assess"):
            self.assertIn(needle, assess)
        self.assertIn("decide.py", (REPO / "agents/judge.md").read_text())


if __name__ == "__main__":
    unittest.main()
