#!/usr/bin/env python3
"""v4.0: choose where a run starts (with the catch-up a late start needs), a per-role
model plan, and configurable decisions decided by the user and tested per value."""
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
import model_plan as mp  # noqa: E402
import entry_point as ep  # noqa: E402


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last(stdout, tag):
    return json.loads([x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1][len(tag) + 2:])


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-v4-"))
        (self.d / ".harness").mkdir()
        (self.d / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def touch(self, rel, text="x\n"):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def recommend(self, prompt=""):
        r = run([str(S / "entry_point.py"), "recommend", "--prompt", prompt, "--json"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return last(r.stdout, "ENTRY")


# ---------------------------------------------------------------- where to start
class TestEntryPoint(Tmp):
    def test_new_idea_starts_at_discovery(self):
        res = self.recommend("Build me a booking app for dentists")
        self.assertEqual(res["recommended"], "discover")
        self.assertEqual(res["options"][0]["start"], "discover")
        self.assertTrue(any("optional" in r.lower() for r in res["reasons"]))

    def test_unproven_idea_starts_at_validation(self):
        res = self.recommend("Is this worth building? Not sure people would pay for an invoice tracker")
        self.assertEqual(res["recommended"], "validate")

    def test_users_requirements_document_starts_at_design_with_catch_up(self):
        self.touch("docs/Invoice-PRD.md", "# PRD\n")
        res = self.recommend("design the system")
        self.assertEqual(res["recommended"], "design")
        design = next(o for o in res["options"] if o["start"] == "design")
        self.assertEqual([m["path"] for m in design["catch_up"]],
                         [p for p, *_ in ep.DISCOVERY] + ["docs/decision-intake.md"])
        self.assertIn("validate_product_map.py --require-coverage", design["validators"])
        self.assertEqual([k["stage"] for k in design["skips"]], ["validate", "discover"])

    def test_requirements_and_architecture_documents_start_at_build(self):
        self.touch("docs/requirements-spec.md")
        self.touch("Architecture-notes.md")
        res = self.recommend("we have the spec, build it")
        self.assertEqual(res["recommended"], "build")
        build = next(o for o in res["options"] if o["start"] == "build")
        paths = [m["path"] for m in build["catch_up"]]
        for p in ("docs/02e-test-cases.md", "docs/03c-architecture-options.md", "docs/03f-configuration.md",
                  "docs/03d-portability.md", "docs/05-security.md", "docs/06-devops.md", "docs/decision-intake.md"):
            self.assertIn(p, paths)
        # written by the continue step (Phase 1 steps 11-13), so never a catch-up item
        self.assertNotIn("docs/00-blueprint-summary.md", paths)

    def test_existing_code_without_documents_starts_at_assess(self):
        for i in range(12):
            self.touch(f"src/m{i}.py", "x = 1\n")
        self.touch("package.json", "{}")
        res = self.recommend("is this ready to ship?")
        self.assertEqual(res["recommended"], "assess")
        self.assertTrue(any("release gate" in r for r in res["reasons"]))
        rel = next(o for o in res["options"] if o["start"] == "release")
        self.assertEqual(rel["fit"], "not advised")

    def test_code_in_docs_folder_is_not_counted(self):
        for i in range(15):
            self.touch(f"docs/examples/s{i}.py", "x = 1\n")
        self.assertFalse(self.recommend("build me a crm")["existing_code"])

    def test_earlier_run_resumes(self):
        (self.d / ".harness/progress.json").write_text(json.dumps({"phase": "execution", "sprint": "sprint-02"}))
        res = self.recommend("carry on")
        self.assertEqual(res["recommended"], "resume")
        self.assertEqual(res["options"][0]["start"], "resume")

    def test_complete_documents_start_at_build_then_release(self):
        for d in ep.DISCOVERY + ep.DESIGN:
            self.touch(d[0])
        self.touch("docs/decision-discovery.md")
        self.touch("docs/decision-architecture.md")
        self.assertEqual(self.recommend("")["recommended"], "build")
        (self.d / "sprints.json").write_text(json.dumps([{"id": "s1", "status": "done"},
                                                         {"id": "s2", "status": "torn-down"}]))
        self.assertEqual(self.recommend("")["recommended"], "release")

    def test_ui_product_needs_a_design_system_in_the_build_catch_up(self):
        self.touch("docs/PRD.md")
        self.touch("docs/architecture.md")
        res = self.recommend("a web app dashboard for clinics, build it")
        build = next(o for o in res["options"] if o["start"] == "build")
        self.assertIn("docs/03b-design-system.md", [m["path"] for m in build["catch_up"]])
        self.assertNotIn("docs/04-agent-design.md", [m["path"] for m in build["catch_up"]])

    def test_choose_records_and_catchup_tracks_progress(self):
        self.touch("docs/Invoice-PRD.md")
        r = run([str(S / "entry_point.py"), "choose", "build", "--by", "Bilal", "--prompt", "build"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        rec = json.loads((self.d / ".harness/entry.json").read_text())
        self.assertEqual((rec["start"], rec["recommended"], rec["followed_recommendation"], rec["chosen_by"]),
                         ("build", "design", False, "Bilal"))
        self.assertIn("ASDR recommended Design", r.stdout)
        r = run([str(S / "entry_point.py"), "catchup"], self.d)
        self.assertEqual(r.returncode, 2)
        self.assertIn("MISSING: product brief", r.stdout)
        for path, _n, _o in ep.required("build", {"cloud"}):
            self.touch(path)
        r = run([str(S / "entry_point.py"), "catchup"], self.d)
        self.assertEqual(r.returncode, 2)
        self.assertEqual([m["path"] for m in last(r.stdout, "ENTRY")["missing"]], ["docs/decision-intake.md"])
        self.touch("docs/decision-intake.md", "verdict: go\n")
        r = run([str(S / "entry_point.py"), "catchup"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(last(r.stdout, "ENTRY")["ok"])

    def test_phase_one_run_is_not_a_resume(self):
        (self.d / ".harness/progress.json").write_text(json.dumps({"phase": "strategic", "sprint": None}))
        for p, *_ in ep.DISCOVERY:
            self.touch(p)
        self.touch("docs/decision-discovery.md")
        res = self.recommend("carry on")
        self.assertEqual(res["recommended"], "design")       # not "resume": next_action would skip design
        self.assertNotIn("resume", [o["start"] for o in res["options"]])

    def test_unreviewed_documents_get_a_review_in_the_catch_up(self):
        for p, *_ in ep.DISCOVERY:
            self.touch(p)
        self.touch("docs/critique-discovery.md")              # interrupted before the decision
        res = self.recommend("")
        self.assertEqual(res["recommended"], "design")
        design = next(o for o in res["options"] if o["start"] == "design")
        self.assertEqual([(m["path"], m["owner"]) for m in design["catch_up"]],
                         [("docs/decision-intake.md", "critic")])

    def test_symlinks_are_not_followed(self):
        outside = Path(tempfile.mkdtemp(prefix="asdr-out-"))
        try:
            for i in range(30):
                (outside / f"m{i}.py").write_text("x=1\n")
            (self.d / "src").mkdir()
            os.symlink(outside, self.d / "src" / "linked")
            self.touch("docs/PRD.md")
            res = self.recommend("")
            self.assertFalse(res["existing_code"])
            self.assertEqual(res["recommended"], "design")
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_a_manifest_alone_is_not_an_existing_system(self):
        self.touch("package.json", "{}")
        self.touch("requirements.txt", "requests\n")
        self.touch("index.js", "1")
        res = self.recommend("build me a crm")
        self.assertFalse(res["existing_code"])
        self.assertEqual(res["user_docs"]["discovery"], [])     # pip requirements are not a requirements document
        self.assertEqual(res["recommended"], "discover")

    def test_catchup_rereads_what_the_product_needs(self):
        self.touch("docs/PRD.md")
        self.touch("docs/architecture.md")
        run([str(S / "entry_point.py"), "choose", "build", "--prompt", "build it now"], self.d)
        self.touch("docs/02-requirements.md", "Admins use a dashboard; an AI assistant drafts replies.\n")
        r = run([str(S / "entry_point.py"), "catchup"], self.d)
        paths = [m["path"] for m in last(r.stdout, "ENTRY")["missing"]]
        self.assertIn("docs/03b-design-system.md", paths)
        self.assertIn("docs/04-agent-design.md", paths)

    def test_microservices_need_services_and_local_only_needs_no_portability(self):
        self.touch("docs/PRD.md")
        (self.d / ".harness/architecture.json").write_text(json.dumps({"style": "microservices"}))
        r = run([str(S / "entry_point.py"), "choose", "build", "--local-only"], self.d)
        paths = [m["path"] for m in last(r.stdout, "ENTRY")["catch_up"]]
        self.assertIn("docs/03e-services.md", paths)
        self.assertNotIn("docs/03d-portability.md", paths)

    def test_release_cannot_catch_up_a_build(self):
        r = run([str(S / "entry_point.py"), "choose", "release"], self.d)
        miss = last(r.stdout, "ENTRY")["catch_up"]
        self.assertEqual(miss[-1]["owner"], "build")
        self.assertIn("not a catch-up: build first", r.stdout)

    def test_a_review_written_before_the_documents_does_not_count(self):
        for p, *_ in ep.DISCOVERY:
            self.touch(p)
        self.touch("docs/decision-intake.md", "verdict: go\n")
        old = (self.d / "docs/decision-intake.md").stat().st_mtime - 100
        os.utime(self.d / "docs/decision-intake.md", (old, old))
        for d in ep.DESIGN:
            if len(d) == 3:
                self.touch(d[0])
        self.touch("docs/03d-portability.md")
        r = run([str(S / "entry_point.py"), "choose", "build"], self.d)
        paths = [m["path"] for m in last(r.stdout, "ENTRY")["catch_up"]]
        self.assertEqual(paths, ["docs/decision-intake.md"])     # discovery docs are newer than the review too
        os.utime(self.d / "docs/decision-intake.md", None)        # a review written after everything counts
        self.assertEqual(run([str(S / "entry_point.py"), "catchup"], self.d).returncode, 0)

    def test_no_go_is_not_done(self):
        for p, *_ in ep.DISCOVERY:
            self.touch(p)
        self.touch("docs/decision-discovery.md", "```\nverdict: no-go\n```\n")
        res = self.recommend("")
        self.assertEqual(res["recommended"], "discover")
        self.assertTrue(any("no-go" in r for r in res["reasons"]))

    def test_catchup_without_a_choice_fails(self):
        r = run([str(S / "entry_point.py"), "catchup"], self.d)
        self.assertEqual(r.returncode, 1)

    def test_early_starts_need_no_catch_up(self):
        for st in ("validate", "discover", "assess"):
            r = run([str(S / "entry_point.py"), "choose", st], self.d)
            self.assertEqual(last(r.stdout, "ENTRY")["catch_up"], [], st)


# ---------------------------------------------------------------- model plan
class TestModelPlan(Tmp):
    def frontmatter_models(self):
        out = {}
        for f in (REPO / "agents").glob("*.md"):
            m = re.search(r"^model:\s*(\S+)", f.read_text(), re.MULTILINE)
            out[f.stem] = m.group(1) if m else "inherit"
        return out

    def test_roles_match_the_agents(self):
        self.assertEqual(sorted(mp.ROLES), sorted(self.frontmatter_models()))

    def test_balanced_equals_frontmatter(self):
        self.assertEqual(mp.mapping("balanced"), self.frontmatter_models())

    def get(self, role):
        r = run([str(S / "model_plan.py"), "get", role], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        return r.stdout.splitlines()[0]

    def test_default_is_balanced(self):
        self.assertEqual(self.get("stage-qa"), "sonnet")
        self.assertEqual(self.get("critic"), "opus")

    def test_economy_keeps_gatekeepers_on_top(self):
        r = run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        self.assertEqual(r.returncode, 0)
        for g in ("critic", "judge", "evaluator", "risk-manager", "security-compliance"):
            self.assertEqual(self.get(g), "opus", g)
        self.assertEqual(self.get("generator"), "sonnet")
        self.assertEqual(self.get("panelist"), "haiku")
        self.assertEqual(last(r.stdout, "MODEL")["roles_by_model"], {"opus": 5, "sonnet": 12, "haiku": 2})

    def test_top_can_follow_fable(self):
        run([str(S / "model_plan.py"), "set", "--plan", "maximum", "--top", "fable"], self.d)
        self.assertEqual(self.get("judge"), "fable")
        self.assertEqual(self.get("stage-qa"), "fable")

    def test_unavailable_models_fall_back(self):
        run([str(S / "model_plan.py"), "set", "--plan", "economy", "--top", "fable"], self.d)
        r = run([str(S / "model_plan.py"), "unavailable", "haiku"], self.d)
        self.assertEqual(last(r.stdout, "MODEL")["moved"], {"panelist": "sonnet", "release-manager": "sonnet"})
        run([str(S / "model_plan.py"), "unavailable", "fable"], self.d)
        self.assertEqual(self.get("critic"), "opus")
        # a new plan keeps what is known to be unavailable
        run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        self.assertEqual(self.get("panelist"), "sonnet")

    def test_fallback_never_returns_an_unavailable_model_while_another_exists(self):
        run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        run([str(S / "model_plan.py"), "unavailable", "haiku"], self.d)
        run([str(S / "model_plan.py"), "unavailable", "sonnet"], self.d)
        self.assertEqual(self.get("panelist"), "opus")
        data = {"plan": "economy", "top": "fable", "map": mp.mapping("economy", "fable"), "unavailable": ["opus", "sonnet"]}
        self.assertEqual(mp.role_model("stage-qa", data), "fable")
        data["unavailable"] = list(mp.MODELS)
        self.assertIn(mp.role_model("stage-qa", data), mp.MODELS)   # nothing left: the call fails loudly

    def test_a_hand_edited_file_does_not_break_it(self):
        (self.d / ".harness/models.json").write_text(json.dumps(
            {"plan": "economy", "unavailable": "opus", "map": ["x"]}))
        self.assertEqual(self.get("critic"), "opus")
        self.assertEqual(run([str(S / "model_plan.py"), "unavailable", "haiku"], self.d).returncode, 0)
        (self.d / ".harness/models.json").write_text(json.dumps({"plan": "balanced", "map": {"critic": "gpt-9"}}))
        self.assertEqual(self.get("critic"), "opus")

    def test_paranoid_without_a_plan_uses_maximum(self):
        (self.d / ".harness/progress.json").write_text(json.dumps({"rigor": "paranoid"}))
        self.assertEqual(self.get("stage-qa"), "opus")

    def test_set_without_a_plan_follows_the_rigor(self):
        (self.d / ".harness/progress.json").write_text(json.dumps({"rigor": "paranoid"}))
        r = run([str(S / "model_plan.py"), "set"], self.d)
        self.assertEqual(last(r.stdout, "MODEL")["plan"], "maximum")

    def test_unknown_role_or_model_is_an_error(self):
        self.assertEqual(run([str(S / "model_plan.py"), "get", "intern"], self.d).returncode, 1)
        self.assertEqual(run([str(S / "model_plan.py"), "unavailable", "gpt"], self.d).returncode, 1)


# ---------------------------------------------------------------- estimator
class TestEstimatorV4(Tmp):
    PRICES = ["--price-opus", "6.4", "--price-sonnet", "3.2", "--price-haiku", "0.16", "--price-fable", "10"]

    def est(self, *args):
        r = run([str(S / "estimate_run.py"), "--sprints", "4", "--ui", "--runs", "none.jsonl", *self.PRICES, *args], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return last(r.stdout, "ESTIMATE"), r.stdout

    def test_plans_order_by_cost(self):
        e, out = self.est("--compare-plans")
        p = e["plans"]
        self.assertLess(p["economy"]["usd"], p["balanced"]["usd"])
        self.assertLess(p["balanced"]["usd"], p["maximum"]["usd"])
        self.assertGreater(p["economy"]["tokens_haiku"], 0)
        self.assertEqual(p["maximum"]["tokens_sonnet"], 0)
        self.assertIn("| Plan |", out)

    def test_later_starts_cost_less_but_not_nothing(self):
        e, out = self.est("--compare-starts")
        t = [e["starts"][s]["tokens"] for s in ("discover", "design", "build", "release")]
        self.assertEqual(t, sorted(t, reverse=True))
        self.assertGreater(e["starts"]["release"]["agent_runs"], 0)
        self.assertIn("| Start |", out)

    def test_catch_up_is_counted(self):
        e, _ = self.est("--start", "design", "--rigor", "standard")
        full, _ = self.est("--rigor", "standard")
        # converting discovery costs less than writing it, but it is not free
        self.assertLess(e["levels"]["standard"]["tokens"], full["levels"]["standard"]["tokens"])
        a = type("A", (), {"ui": True, "ai": False, "cloud": False, "services": 1, "sprints": 4})()
        import estimate_run as er
        runs = er.count_build("standard", a, "design")
        self.assertAlmostEqual(runs["product-owner"], er.INTAKE_FACTOR)
        self.assertGreaterEqual(runs["critic"], 2)          # the catch-up critic pass + the design phase

    def test_plan_file_is_read(self):
        run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        e, _ = self.est()
        self.assertGreater(e["levels"]["standard"]["tokens_haiku"], 0)

    def test_no_money_without_a_price_for_every_model_used(self):
        r = run([str(S / "estimate_run.py"), "--plan", "economy", "--price-opus", "6", "--price-sonnet", "3",
                 "--runs", "none.jsonl"], self.d)
        self.assertNotIn("usd", last(r.stdout, "ESTIMATE")["levels"]["standard"])

    def test_budget_records_the_start(self):
        self.est("--start", "build", "--set-budget")
        self.assertEqual(json.loads((self.d / ".harness/budget.json").read_text())["start"], "build")


# ---------------------------------------------------------------- configurable decisions
DOC = """# Configurable decisions — Demo

## 02 · Decision register

| ID | Decision | Options | Type recommended | Extra cost to build all options | Splits the data model? | Why | Decided by | Decision |
|---|---|---|---|---|---|---|---|---|
| DEC-01 | Who approves a refund | fixed limit; per-customer limit | configure | 8% | no | changes often | Bilal, 2026-10-27 | configure |
| DEC-02 | Database | PostgreSQL; managed cloud database | prepare | 60% | no | costly to build both | Bilal, 2026-10-27 | prepare |
| DEC-03 | Tenancy | shared schema; schema per tenant | decide-once | 80% | yes | one-way door | Bilal, 2026-10-27 | decide-once |

## 03 · Settings (decisions decided as configure)

| ID | Decision | Setting key | Default | Allowed values | Who can change it | Takes effect | Owner | Review by | Tests |
|---|---|---|---|---|---|---|---|---|---|
| CFG-01 | DEC-01 | refunds.approval_limit | 100 | 50, 100, 250 | Admin | immediately | Product owner | 2027-03-31 | TC-14, TC-15, TC-16 |

## 04 · Prepared options (decisions decided as prepare)

| Decision | Built now | Prepared for | Connection point | Estimated cost to switch later |
|---|---|---|---|---|
| DEC-02 | PostgreSQL | a managed cloud database | the repository interface in src/data | 3–5 days |

## 05 · Settings that interact

| Settings | How they interact | Test approach |
|---|---|---|
"""


class TestConfigurability(Tmp):
    def setUp(self):
        super().setUp()
        self.touch("docs/02e-test-cases.md", "TC-14 a\nTC-15 b\nTC-16 c\nTC-17 d\n")

    def check(self, doc, *extra):
        self.touch("docs/03f-configuration.md", doc)
        r = run([str(S / "validate_configurability.py"), "--today", "2026-11-01", *extra], self.d)
        return r.returncode, r.stdout

    def test_decided_document_passes_and_is_recorded(self):
        code, out = self.check(DOC)
        self.assertEqual(code, 0, out)
        j = json.loads((self.d / ".harness/configuration.json").read_text())
        self.assertEqual(j["by_type"], {"configure": 1, "prepare": 1, "decide-once": 1})
        self.assertEqual(j["setting_list"][0]["tests"], ["TC-14", "TC-15", "TC-16"])

    def test_waits_for_the_user(self):
        code, out = self.check(DOC.replace("| Bilal, 2026-10-27 | decide-once |", "| | |"))
        self.assertEqual(code, 2, out)
        self.assertEqual(last(out, "CONFIG")["pending"], ["DEC-03"])

    def test_recommendation_must_follow_the_rule(self):
        code, out = self.check(DOC.replace("| configure | 8% | no |", "| configure | 25% | no |"))
        self.assertEqual(code, 1)
        self.assertIn("adds 25%", out)
        code, out = self.check(DOC.replace("| configure | 8% | no |", "| configure | 8% | yes |"))
        self.assertEqual(code, 1)
        self.assertIn("splits the data model", out)

    def test_user_may_override_and_it_is_recorded(self):
        doc = DOC.replace("| prepare | 60% | no | costly to build both | Bilal, 2026-10-27 | prepare |",
                          "| prepare | 60% | no | costly to build both | Bilal, 2026-10-27 | configure |")
        doc = re.sub(r"\| DEC-02 \| PostgreSQL .*\n", "", doc)
        doc = doc.replace("## 04", "| CFG-02 | DEC-02 | db.engine | postgres | postgres, managed | Ops | next deploy | CTO | 2027-01-31 | TC-14, TC-17 |\n\n## 04")
        code, out = self.check(doc)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: DEC-02: configure chosen against the rule", out)

    def test_setting_errors(self):
        code, out = self.check(DOC.replace("| 100 | 50, 100, 250 |", "| 500 | 50, 100, 250 |"))
        self.assertIn("default '500' is not one of the allowed values", out)
        code, out = self.check(DOC.replace("TC-14, TC-15, TC-16 |", "TC-14, TC-15 |"))
        self.assertIn("2 test case(s) for 3 value(s)", out)
        code, out = self.check(DOC.replace("TC-16 |", "TC-99 |"))
        self.assertIn("TC-99 is not in", out)
        code, out = self.check(DOC.replace("| 2027-03-31 |", "| soon |"))
        self.assertIn("review by must be a date", out)
        self.assertEqual(code, 1)

    def test_range_needs_minimum_maximum_and_default(self):
        doc = DOC.replace("| 100 | 50, 100, 250 |", "| 100 | 10..500 |").replace("TC-14, TC-15, TC-16", "TC-14, TC-15")
        code, out = self.check(doc)
        self.assertIn("2 test case(s) for 3 value(s) to test", out)
        code, _ = self.check(doc.replace("TC-14, TC-15", "TC-14, TC-15, TC-16"))
        self.assertEqual(code, 0)

    def test_every_configure_and_prepare_decision_is_complete(self):
        code, out = self.check(re.sub(r"\| CFG-01 .*\n", "", DOC))
        self.assertIn("DEC-01: decided as configure but has no setting", out)
        code, out = self.check(re.sub(r"\| DEC-02 \| PostgreSQL .*\n", "", DOC))
        self.assertIn("DEC-02: decided as prepare but section 04", out)
        code, out = self.check(DOC.replace("| DEC-02 | PostgreSQL |", "| DEC-03 | PostgreSQL |"))
        self.assertIn("section 04: DEC-03 was decided as decide-once", out)

    def test_template_placeholders_fail(self):
        code, out = self.check((REPO / "templates/configuration.md").read_text())
        self.assertEqual(code, 1)
        self.assertIn("template placeholders", out)

    def test_gate_review_dates_and_passing_tests(self):
        (self.d / ".harness/product-map.json").write_text(json.dumps(
            {"test_cases": {"TC-14": {"state": "passed"}, "TC-15": {"state": "passed"}, "TC-16": {"state": "failed"}}}))
        code, out = self.check(DOC, "--gate")
        self.assertEqual(code, 1)
        self.assertIn("CFG-01: test case(s) not passing in the latest results: TC-16", out)
        (self.d / ".harness/product-map.json").write_text(json.dumps(
            {"test_cases": {t: {"state": "passed"} for t in ("TC-14", "TC-15", "TC-16")}}))
        self.assertEqual(self.check(DOC, "--gate")[0], 0)
        code, out = self.check(DOC.replace("2027-03-31", "2026-10-01"), "--gate")
        self.assertEqual(code, 1)
        self.assertIn("review date 2026-10-01 has passed", out)
        code, out = self.check(DOC.replace("2027-03-31", "2026-10-01"))      # before release: a warning only
        self.assertEqual(code, 0)
        self.assertIn("WARN: CFG-01: review date", out)

    def test_many_settings_and_combinations_are_warned(self):
        rows = "".join(f"| CFG-{i:02d} | DEC-01 | k{i} | a | a, b, c | Admin | now | PO | 2027-03-31 | TC-14, TC-15, TC-16 |\n"
                       for i in range(2, 15))
        doc = DOC.replace("\n\n## 04", "\n" + rows + "\n## 04")
        code, out = self.check(doc)
        self.assertEqual(code, 0, out)
        self.assertIn("14 settings", out)
        self.assertIn("combinations of setting values", out)

    def test_tests_come_after_the_decision(self):
        doc = DOC.replace("TC-14, TC-15, TC-16 |", " |")
        code, out = self.check(doc)
        self.assertEqual(code, 2, out)                     # waiting for the business-analyst, not an error
        self.assertIn("WAITING: CFG-01", out)
        code, out = self.check(doc, "--require-tests")
        self.assertEqual(code, 1)
        self.assertIn("ERROR: CFG-01: 0 test case(s)", out)

    def test_pending_is_a_pending_decision(self):
        code, out = self.check(DOC.replace("| Bilal, 2026-10-27 | decide-once |", "| | pending |"))
        self.assertEqual(code, 2, out)

    def test_gate_without_a_document_skips_and_with_pending_fails(self):
        r = run([str(S / "validate_configurability.py"), "--gate"], self.d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("SKIP:", r.stdout)
        (self.d / ".harness/product-map.json").write_text(json.dumps(
            {"test_cases": {t: {"state": "passed"} for t in ("TC-14", "TC-15", "TC-16")}}))
        code, out = self.check(DOC.replace("| Bilal, 2026-10-27 | decide-once |", "| | |"), "--gate")
        self.assertEqual(code, 1)
        self.assertIn("DEC-03: still undecided at the release gate", out)

    def test_error_paths(self):
        cases = [
            (DOC.replace("| DEC-03 |", "| D3 |"), "decision id 'D3'"),
            (DOC.replace("| DEC-03 |", "| DEC-01 |"), "DEC-01: listed twice"),
            (DOC.replace("| shared schema; schema per tenant |", "| shared schema |"), "needs at least two options"),
            (DOC.replace("| decide-once | 80% |", "| maybe | 80% |"), "type recommended must be"),
            (DOC.replace("| 80% | yes |", "| 80% | perhaps |"), "must be yes or no"),
            (DOC.replace("| one-way door | Bilal, 2026-10-27 |", "| one-way door | |"), "'Decided by' is empty"),
            (DOC.replace("| CFG-01 |", "| S1 |"), "setting id 'S1'"),
            (DOC.replace("| CFG-01 | DEC-01 |", "| CFG-01 | DEC-07 |"), "'DEC-07' is not in the register"),
            (DOC.replace("| Product owner | 2027", "| | 2027"), "CFG-01: owner is empty"),
            (DOC.replace("| 100 | 50, 100, 250 |", "| 900 | 10..500 |"), "outside the range"),
            (DOC.replace("| DEC-02 | PostgreSQL |", "| DEC-08 | PostgreSQL |"), "names 'DEC-08'"),
            (DOC + "| CFG-09 | x | pairwise |\n", "section 05 names CFG-09"),
            (DOC.replace("## 03", "| CFG-01 | DEC-01 | k | 50 | 50, 100 | Admin | now | PO | 2027-03-31 | TC-14, TC-15 |\n\n## 03")
             .replace("## 03 · Settings (decisions decided as configure)\n\n| ID |", "## 03 · Settings\n\n| ID |"), None),
            ("# just a title\n", "no decision register"),
        ]
        for doc, needle in cases:
            code, out = self.check(doc)
            if needle:
                self.assertIn(needle, out, needle)
                self.assertEqual(code, 1, needle)
        dup = DOC.replace("\n\n## 04", "\n| CFG-01 | DEC-01 | k2 | 50 | 50, 100 | Admin | now | PO | 2027-03-31 | TC-14, TC-15 |\n\n## 04")
        code, out = self.check(dup)
        self.assertIn("CFG-01: listed twice", out)

    def test_gate_skips_only_projects_designed_before_4_0(self):
        (self.d / ".harness/entry.json").write_text(json.dumps({"start": "discover"}))
        r = run([str(S / "validate_configurability.py"), "--gate"], self.d)
        self.assertEqual(r.returncode, 1)                  # a 4.0 run that skipped step 6c
        self.assertIn("not found", r.stdout)

    def test_escaped_pipes_stay_in_one_cell(self):
        code, out = self.check(DOC.replace("| Who approves a refund |", "| Who approves a refund \\| credit |"))
        self.assertEqual(code, 0, out)

    def test_percent_is_read_from_the_percentage(self):
        code, out = self.check(DOC.replace("| configure | 8% |", "| configure | ~8% (2 of 25 days) |"))
        self.assertEqual(code, 0, out)

    def test_missing_test_case_file(self):
        (self.d / "docs/02e-test-cases.md").unlink()
        code, out = self.check(DOC)
        self.assertEqual(code, 0, out)
        self.assertIn("WARN: docs/02e-test-cases.md not found", out)
        code, out = self.check(DOC, "--require-tests")
        self.assertEqual(code, 1)

    def test_bad_inputs_do_not_crash(self):
        (self.d / ".harness/product-map.json").write_text("[1, 2]")
        code, out = self.check(DOC, "--gate")
        self.assertEqual(code, 1)
        self.assertIn("has no test_cases", out)
        self.touch("docs/03f-configuration.md", DOC)
        r = run([str(S / "validate_configurability.py"), "--today", "tomorrow"], self.d)
        self.assertEqual(r.returncode, 2)                  # argparse's usage error, not a traceback
        self.assertNotIn("Traceback", r.stderr)

    def test_dashboard_survives_malformed_files_and_tells_the_client(self):
        (self.d / ".harness/models.json").write_text("[1]")
        (self.d / ".harness/configuration.json").write_text(json.dumps({"setting_list": [1, {"review_by": 5}]}))
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.check(DOC.replace("2027-03-31", "2026-10-01"))
        self.assertTrue((self.d / ".harness/configuration.json").exists())
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        html = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("past their review date: CFG-01", html)
        self.assertNotIn("no blocking or risk rule triggered", html.split("past their review date")[0][-400:])
        brand = self.d / "brand.json"
        brand.write_text(json.dumps({"monogram": "BK", "lockup": "Test"}))
        r = run([str(S / "build_dashboard.py"), "--audience", "client", "--no-pdf", "--brand", str(brand)], self.d,
                env={"HOME": str(self.d)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        client = (self.d / "docs/dashboard/client/index.html").read_text()
        self.assertIn("a product setting is past its agreed review date", client.lower())
        self.assertNotIn("no blocking or risk rule triggered", client.lower())

    def test_dashboard_shows_settings_and_flags_an_overdue_review(self):
        self.check(DOC.replace("2027-03-31", "2026-10-01"))
        run([str(S / "model_plan.py"), "set", "--plan", "economy"], self.d)
        run([str(S / "entry_point.py"), "choose", "discover"], self.d)
        r = run([str(S / "build_dashboard.py"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        html = (self.d / "docs/dashboard/index.html").read_text()
        self.assertIn("Run set-up and settings", html)
        self.assertIn("refunds.approval_limit", html)
        self.assertIn("model plan economy", html)
        self.assertIn("started at Discovery", html)
        self.assertIn("past their review date: CFG-01", html)


# ---------------------------------------------------------------- the skills say it
class TestSkillsWiring(unittest.TestCase):
    def test_asdr_skill_has_the_three_steps(self):
        s = (REPO / "skills/asdr/SKILL.md").read_text()
        for needle in ("5a. **Where to start (v4.0).**", "entry_point.py choose", "Starting late: the catch-up",
                       "model_plan.py set --plan", "model_plan.py get <agent>", "6c. **solution-architect (configurable",
                       "validate_configurability.py --gate"):
            self.assertIn(needle, s)
        self.assertNotIn('pass `model:\n  "opus"` on every agent invocation', s)

    def test_every_skill_passes_the_plan_model(self):
        for f in (REPO / "skills").glob("*/SKILL.md"):
            s = f.read_text()
            self.assertIn("model_plan.py get", s, f)
            self.assertNotIn("--model <opus|sonnet>", s, f)

    def test_file_map_and_agents(self):
        fm = (REPO / "skills/asdr/references/file-map.md").read_text()
        self.assertIn("`docs/03f-configuration.md`", fm)
        self.assertIn("| `configuration` | solution-architect |", fm)
        for role in ("product-owner", "business-analyst", "product-manager", "solution-architect",
                     "security-compliance", "devops"):
            self.assertIn("## INTAKE mode (a late start, v4.0)", (REPO / f"agents/{role}.md").read_text(), role)
        for role in ("generator", "evaluator", "critic", "risk-manager", "documentation"):
            self.assertIn("(v4.0)", (REPO / f"agents/{role}.md").read_text(), role)


if __name__ == "__main__":
    unittest.main()
