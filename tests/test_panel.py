#!/usr/bin/env python3
"""Tests for the v3.9 synthetic panel (scripts/panel.py).

Deterministic and offline: panelists are simulated by writing their JSON
files directly; the state machine, checks, briefs and aggregation are real.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PY = sys.executable
sys.path.insert(0, str(SCRIPTS))
import validation_questions as vq  # noqa: E402

SEED = """# Validation Seed

## 1. The idea (verbatim)
A $19/month WhatsApp assistant that answers clinic enquiries after hours.

## 3. Segments
| Segment | Role |
|---|---|
| S-01 | small clinic owners |
| S-02 | front-desk managers |

## 6. Hypotheses to test
| Id | Hypothesis | Refuted if |
|---|---|---|
| H-01 | Clinic owners lose bookings to unanswered night messages | fewer than a third mention lost bookings |
"""

DESK = """# Desk Evidence
| Id | Source | Read on | Type | What it shows | Hypothesis |
|---|---|---|---|---|---|
| D-01 | https://example.org/a | 2026-10-01 | forum | "We miss half the WhatsApp messages that come in after 7pm" | H-01 |
| D-02 | https://example.org/b | 2026-10-01 | pricing | Competitor charges $49/month | H-02 |
| D-03 | https://example.org/c | 2026-10-01 | review | "Setup took our receptionist two weeks" | H-03 |
"""

STIM = """**What it is:** A WhatsApp assistant that replies to patient messages after hours.
**Price:** $19 per month per clinic."""


def run(args, cwd):
    p = subprocess.run([PY, *map(str, args)], cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def roster(n=8, **over):
    stances = (["loyal-to-current"] * 3 + ["would-never-buy"] * 2 + ["early-adopter"]
               + ["open"] * (n - 6))
    temps = list(vq.TEMPERAMENT)
    people = []
    for i in range(n):
        people.append({
            "id": f"P{i + 1:02d}", "segment": "S-01" if i % 2 == 0 else "S-02",
            "role": f"role {i}", "context": "8-person clinic, Karachi",
            "job_to_be_done": "keep the diary full", "current_alternative": "manual WhatsApp",
            "budget_authority": "decides", "tech_comfort": "medium",
            "temperament": temps[i % len(temps)], "stance_prior": stances[i],
            "constraints": "tight budget", "grounding": ["D-01"],
            "voice": ["We miss half the WhatsApp messages that come in after 7pm"] if i == 0 else [],
        })
    r = {"personas": people}
    r.update(over)
    return r


def answer(pid, sid, rnd, intent="maybe", cat="price", price="fair", fp=15, changed=None):
    r = {"persona": pid, "scenario": sid, "round": rnd,
         "answers": [f"answer {i}" for i in range(len(vq.DEFAULT_QUESTIONS))],
         "intent": intent, "price_reaction": price, "fair_price": fp,
         "objection_category": cat, "objection": f"{cat} worry number {int(pid[1:]) * 7}",
         "switch_trigger": "a free month", "quote": f"I would rather wait, says voice {int(pid[1:]) * 7}."}
    if rnd == 2:
        r["changed"] = bool(changed)
        r["why"] = "others convinced me" if changed else "same as before"
    return r


class PanelBase(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "docs/validation/panel").mkdir(parents=True)
        (self.d / "docs/validation/seed.md").write_text(SEED)
        (self.d / "docs/validation/desk-evidence.md").write_text(DESK)
        self.p = self.d / "docs/validation/panel"

    def tearDown(self):
        shutil.rmtree(self.d)

    def init(self, *extra):
        code, out, err = run([SCRIPTS / "panel.py", "init", *extra], self.d)
        self.assertEqual(code, 0, out + err)

    def nxt(self, *extra):
        code, out, err = run([SCRIPTS / "panel.py", "next", *extra], self.d)
        self.assertEqual(code, 0, out + err)
        return json.loads(out)

    def write(self, rel, obj):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)

    def answer_tasks(self, res, fn):
        for t in res["tasks"]:
            self.write(t["output"], fn(t))


class TestPanelFlow(PanelBase):
    def test_full_flow_two_rounds_scenario_followups(self):
        self.init("--size", "8", "--followups", "2")
        self.assertEqual(self.nxt()["action"], "WRITE-STIMULUS")
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.write("docs/validation/panel/stimulus-SC-01.md", STIM.replace("$19", "$29"))
        self.write("docs/validation/panel/scenarios.json", {"scenarios": [
            {"id": "base", "stimulus": "docs/validation/panel/stimulus.md", "label": "as is"},
            {"id": "SC-01", "stimulus": "docs/validation/panel/stimulus-SC-01.md", "label": "$29"}]})
        res = self.nxt()
        self.assertEqual(res["action"], "WRITE-ROSTER")
        # the business-analyst reads a seed copy without the hypotheses
        sfr = (self.p / "seed-for-roster.md").read_text()
        self.assertNotIn("H-01", sfr)
        self.assertIn("S-02", sfr)
        self.write("docs/validation/panel/roster.json", roster(8))
        res = self.nxt()
        self.assertEqual(res["action"], "RESPOND")
        self.assertEqual(len(res["tasks"]), 16)          # 8 personas x 2 scenarios
        brief = Path(self.d / res["tasks"][0]["input"]).read_text()
        self.assertNotIn("H-01", brief)
        self.assertNotIn("lose bookings", brief)
        self.assertIn("$19", brief)
        self.assertIn("We miss half", (self.p / "inputs/base-r1-P01.md").read_text())
        # base: 2 yes, 3 maybe, 3 no; SC-01 ($29): everyone one step more negative
        base_int = ["yes", "yes", "maybe", "maybe", "maybe", "no", "no", "no"]
        down = {"yes": "maybe", "maybe": "no", "no": "no"}
        cats = ["price", "trust-privacy", "price", "switching-cost", "complexity",
                "price", "not-my-problem", "price"]

        def r1(t):
            i = int(t["persona"][1:]) - 1
            it = base_int[i] if t["scenario"] == "base" else down[base_int[i]]
            return answer(t["persona"], t["scenario"], 1, it, cats[i],
                          "would-not-pay" if it == "no" else "fair", 10 + i)
        self.answer_tasks(res, r1)
        res = self.nxt()
        self.assertEqual(res["action"], "REVISE")
        digest = (self.p / "digest.md").read_text()
        self.assertEqual(digest.count("\n- "), 8)
        self.assertNotRegex(digest, r"\bP\d{2}\b")                 # no persona ids
        self.assertNotRegex(digest.lower(), r"\b(yes|maybe|no)\b")  # no intents or tallies
        r2brief = Path(self.d / res["tasks"][0]["input"]).read_text()
        self.assertIn('"round": 1', r2brief)             # memory: own earlier answer
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 2,
                                                base_int[int(t["persona"][1:]) - 1],
                                                cats[int(t["persona"][1:]) - 1],
                                                changed=t["persona"] == "P03"))
        res = self.nxt()
        self.assertEqual(res["action"], "FOLLOWUP")
        sel = json.loads((self.p / "followups/selection.json").read_text())
        self.assertEqual([s["intent"] for s in sel], ["no", "no"])
        self.assertEqual(len({s["objection_category"] for s in sel}), 2)  # diverse objections
        fbrief = Path(self.d / res["tasks"][0]["input"]).read_text()
        self.assertIn(sel[0]["objection"], fbrief)
        self.answer_tasks(res, lambda t: {"persona": t["persona"],
                                          "answers": ["a"] * len(vq.FOLLOWUP_PROBES),
                                          "root_cause": "cash flow", "would_try_if": "free month"})
        res = self.nxt()
        self.assertEqual(res["action"], "DONE", res)
        facts = json.loads((self.d / ".harness/validation.json").read_text())["panel"]
        self.assertEqual(facts["status"], "complete")
        self.assertEqual(facts["scenarios"]["base"]["r1"]["intent"], {"yes": 2, "maybe": 3, "no": 3})
        self.assertEqual(facts["scenarios"]["base"]["intent_changed"], 0)
        self.assertEqual(facts["scenarios"]["base"]["changed_declared"], 1)
        d = facts["deltas"]["SC-01"]
        self.assertEqual(d["same_persona_shift"], {"more_positive": 0, "same": 3, "more_negative": 5})
        self.assertEqual(d["yes_share_pp"], -25.0)
        self.assertEqual(facts["scenarios"]["base"]["r1"]["fair_price"]["median"], 13.5)
        self.assertFalse(facts["flags"]["implausible_positivity"])
        self.assertFalse(facts["flags"]["herding"])
        self.assertEqual(facts["flags"]["thin_segments"], [])
        self.assertEqual(facts["followups"]["count"], 2)

    def test_flags_positivity_herding_homogeneous(self):
        self.init("--size", "8", "--followups", "0")
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.write("docs/validation/panel/roster.json", roster(8))
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1, "yes", "price"))
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 2,
                                                "no" if t["persona"] in ("P01", "P02", "P03") else "yes",
                                                "price", changed=True))
        res = self.nxt()
        self.assertEqual(res["action"], "DONE", res)
        self.assertEqual(set(res["flags_raised"]),
                         {"implausible_positivity", "herding", "homogeneous"})

    def test_invalid_answer_comes_back_as_a_fix(self):
        self.init("--size", "8", "--rounds", "1", "--followups", "0")
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.write("docs/validation/panel/roster.json", roster(8))
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        bad = answer("P02", "base", 1)
        bad["intent"] = "yes|maybe|no"
        self.write("docs/validation/panel/responses/base/r1-P02.json", bad)
        res = self.nxt()
        self.assertEqual(res["action"], "RESPOND")
        self.assertEqual([t["persona"] for t in res["tasks"]], ["P02"])
        self.assertTrue(any("intent" in e for e in res["tasks"][0]["fix"]))

    def test_desk_evidence_comes_first(self):
        self.init()
        (self.d / "docs/validation/desk-evidence.md").unlink()
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.assertEqual(self.nxt()["action"], "WAIT-DESK")


class TestRosterAndStimulusChecks(PanelBase):
    def setUp(self):
        super().setUp()
        self.init("--size", "8")
        self.write("docs/validation/panel/stimulus.md", STIM)

    def errors(self, r):
        self.write("docs/validation/panel/roster.json", r)
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-ROSTER", res)
        return " | ".join(res["errors"])

    def test_quotas(self):
        r = roster(8)
        for p in r["personas"]:
            p["stance_prior"] = "early-adopter"
        e = self.errors(r)
        self.assertIn("loyal-to-current", e)
        self.assertIn("would-never-buy", e)
        self.assertIn("early-adopter", e)

    def test_size_segments_duplicates(self):
        r = roster(8)
        r["personas"] = r["personas"][:6]
        self.assertIn("8–30", self.errors(r))
        r = roster(8)
        for p in r["personas"]:
            p["segment"] = "S-01"
        self.assertIn("S-02 has no persona", self.errors(r))
        r = roster(8)
        r["personas"][1].update(segment="S-01", role="role 0",
                                temperament=r["personas"][0]["temperament"])
        self.assertIn("same segment, role and temperament", self.errors(r))

    def test_grounding_and_fabricated_quotes(self):
        r = roster(8)
        r["personas"][0]["grounding"] = ["D-99"]
        r["personas"][1]["voice"] = ["A quote nobody ever said"]
        e = self.errors(r)
        self.assertIn("D-99", e)
        self.assertIn("not found verbatim", e)

    def test_hypothesis_leak_in_roster_and_stimulus(self):
        r = roster(8)
        r["personas"][0]["constraints"] = "Worried, see H-01"
        self.assertIn("hypothesis id", self.errors(r))
        self.write("docs/validation/panel/stimulus.md",
                   STIM + "\nClinic owners lose bookings to unanswered night messages.")
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-STIMULUS")
        self.assertIn("hypothesis wording", " ".join(res["errors"]))

    def test_too_many_scenarios(self):
        self.write("docs/validation/panel/scenarios.json", {"scenarios": [
            {"id": "base", "stimulus": "docs/validation/panel/stimulus.md"}] + [
            {"id": f"SC-0{i}", "stimulus": "docs/validation/panel/stimulus.md"} for i in range(1, 5)]})
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-STIMULUS")
        self.assertIn("at most 4", " ".join(res["errors"]))


class TestLessonsFromTheFirstRealRun(PanelBase):
    """Each test pins a problem the first real panel run (8 personas, two
    scenarios, real Claude panelists) exposed."""

    def start(self, rounds="1", scen=False, r=None):
        self.init("--size", "8", "--rounds", rounds, "--followups", "0")
        self.write("docs/validation/panel/stimulus.md", STIM)
        if scen:
            self.write("docs/validation/panel/stimulus-SC-01.md", STIM.replace("$19", "$49"))
            self.write("docs/validation/panel/scenarios.json", {"scenarios": [
                {"id": "base", "stimulus": "docs/validation/panel/stimulus.md", "label": "$19"},
                {"id": "SC-01", "stimulus": "docs/validation/panel/stimulus-SC-01.md",
                 "label": "$49"}]})
        self.write("docs/validation/panel/roster.json", r or roster(8))

    def bump(self, rel):
        p = self.d / rel
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))

    def test_price_and_changed_written_as_text_are_accepted(self):
        # Panelists wrote "19" instead of 19; a re-do costs a whole agent call.
        import panel
        self.assertEqual(panel.coerce_price("19"), 19)
        self.assertEqual(panel.coerce_price("$19/month"), 19)
        self.assertEqual(panel.coerce_price("US$ 1,200 per year"), 1200)
        self.assertEqual(panel.coerce_price("12.50"), 12.5)
        self.assertIsNone(panel.coerce_price("null"))
        self.assertEqual(panel.coerce_price("two hundred"), "invalid")
        self.start(rounds="2")
        res = self.nxt()
        self.answer_tasks(res, lambda t: {**answer(t["persona"], "base", 1), "fair_price": "$19"})
        res = self.nxt()
        self.assertEqual(res["action"], "REVISE", res)
        self.answer_tasks(res, lambda t: {**answer(t["persona"], "base", 2), "changed": "false"})
        res = self.nxt()
        self.assertEqual(res["action"], "DONE", res)
        facts = json.loads((self.d / ".harness/validation.json").read_text())
        self.assertEqual(facts["panel"]["scenarios"]["base"]["r1"]["fair_price"]["median"], 19)

    def test_a_card_that_states_an_attitude_is_rejected(self):
        # The roster told P02 it "will not let software talk to patients"; the
        # panel then "found" that objection.
        r = roster(8)
        r["personas"][1]["constraints"] = "will not let software talk to patients"
        r["personas"][3]["constraints"] = "a cheap self-serve tool reads as not enterprise-ready"
        self.start(r=r)
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-ROSTER", res)
        errs = " | ".join(res["errors"])
        self.assertIn("P02: 'constraints' states an attitude", errs)
        self.assertIn("P04: 'constraints' states an attitude", errs)
        self.assertEqual(len(res["errors"]), 2)

    def test_answers_to_an_old_card_are_asked_again(self):
        # Editing the roster left answers to the old cards in place.
        self.start()
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        r = roster(8)
        r["personas"][2]["constraints"] = "one shared front-desk PC"
        self.write("docs/validation/panel/roster.json", r)
        self.bump("docs/validation/panel/roster.json")
        res = self.nxt()
        self.assertEqual(res["action"], "RESPOND", res)
        self.assertEqual([t["persona"] for t in res["tasks"]], ["P03"])
        self.assertTrue(res["tasks"][0]["fix"][0].startswith("stale"))

    def test_rewriting_an_identical_roster_keeps_every_answer(self):
        self.start()
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        self.write("docs/validation/panel/roster.json", roster(8))
        self.bump("docs/validation/panel/roster.json")
        self.assertEqual(self.nxt()["action"], "DONE")

    def test_echo_static_round_and_noise(self):
        r = roster(8)
        for p in r["personas"][:3]:
            p["constraints"] = ("organisation-approved tools only; replies must count toward "
                                "the tracked response metric in the patient portal")
        self.start(rounds="2", scen=True, r=r)
        echo = ("It is not organisation-approved and its replies would not count toward "
                "the tracked response metric in our patient portal")

        def r1(t):
            a = answer(t["persona"], t["scenario"], 1, "maybe", "trust-privacy")
            if t["persona"] in ("P01", "P02", "P03"):
                a.update(objection=echo, objection_category="missing-capability")
            if t["scenario"] == "SC-01" and t["persona"] == "P04":
                a["intent"] = "no"          # one persona moves: within noise at n=8
            return a
        res = self.nxt()
        self.answer_tasks(res, r1)
        res = self.nxt()
        self.answer_tasks(res, lambda t: {**json.loads((self.d / t["output"].replace("r2-", "r1-"))
                                                        .read_text()), "round": 2,
                                          "changed": False, "why": "same"})
        res = self.nxt()
        self.assertEqual(res["action"], "DONE", res)
        self.assertIn("static_round2", res["flags_raised"])
        self.assertIn("echo_heavy", res["flags_raised"])
        panel = json.loads((self.d / ".harness/validation.json").read_text())["panel"]
        self.assertEqual(panel["echo"]["personas"], ["P01", "P02", "P03"])
        self.assertTrue(panel["deltas"]["SC-01"]["within_noise"])


class TestReviewFindings(PanelBase):
    """Pins the independent review of 3.9.0."""
    start = TestLessonsFromTheFirstRealRun.start
    bump = TestLessonsFromTheFirstRealRun.bump

    def test_wrong_json_shape_is_a_fix_not_a_crash(self):
        self.start()
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        self.write("docs/validation/panel/responses/base/r1-P02.json", "[1, 2]")
        res = self.nxt()
        self.assertEqual(res["action"], "RESPOND", res)
        self.assertIn("expected a JSON object", res["tasks"][0]["fix"][0])

    def test_round_two_digest_leaves_out_your_own_objection(self):
        self.start(rounds="2")
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        res = self.nxt()
        self.assertEqual(res["action"], "REVISE")
        brief = (self.d / "docs/validation/panel/inputs/base-r2-P03.md").read_text()
        others = brief.split("What other people said", 1)[1].split("## Questions", 1)[0]
        self.assertNotIn("price worry number 21", others)      # P03's own objection
        self.assertIn("price worry number 14", others)          # P02's

    def test_results_go_stale_when_the_panel_is_reopened(self):
        self.start()
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1))
        self.assertEqual(self.nxt()["action"], "DONE")
        facts = lambda: json.loads((self.d / ".harness/validation.json").read_text())["panel"]  # noqa: E731
        self.assertEqual(facts()["status"], "complete")
        r = roster(8)
        r["personas"][0]["constraints"] = "two receptionists on shifts"
        self.write("docs/validation/panel/roster.json", r)
        self.bump("docs/validation/panel/roster.json")
        self.assertEqual(self.nxt()["action"], "RESPOND")
        self.assertEqual(facts()["status"], "stale")

    def test_panel_words_never_block_the_panel(self):
        # A panelist writing "H2" (a half-year) or echoing the hypothesis is
        # data, not a leak; only what the team wrote is checked.
        self.start(rounds="2")
        res = self.nxt()
        self.answer_tasks(res, lambda t: {**answer(t["persona"], "base", 1),
                                          "objection": "Clinic owners lose bookings to "
                                          "unanswered night messages; ask me again in H2"})
        res = self.nxt()
        self.assertEqual(res["action"], "REVISE", res)

    def test_scenarios_of_the_wrong_shape_are_a_fix(self):
        self.init("--size", "8")
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.write("docs/validation/panel/scenarios.json", {"scenarios": ["base"]})
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-STIMULUS", res)
        self.assertIn("list of {id, stimulus, label}", " ".join(res["errors"]))

    def test_roster_must_match_the_initialised_size(self):
        self.init("--size", "10")
        self.write("docs/validation/panel/stimulus.md", STIM)
        self.write("docs/validation/panel/roster.json", roster(8))
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-ROSTER")
        self.assertIn("--size 10", " ".join(res["errors"]))

    def test_roster_builder_never_sees_hypotheses_and_quotes_must_be_real(self):
        desk = DESK.replace("| Hypothesis |", "| Hypothesis |") + (
            "\n## Gaps\n\nNo source says \"owners would pay for this tomorrow\".\n")
        self.write("docs/validation/desk-evidence.md", desk)
        r = roster(8)
        r["personas"][1]["voice"] = ["owners would pay for this tomorrow"]
        self.start(r=r)
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-ROSTER")
        self.assertIn("voice quote not found", " ".join(res["errors"]))
        shown = (self.d / "docs/validation/panel/desk-for-roster.md").read_text()
        self.assertNotIn("H-0", shown)
        self.assertNotIn("Gaps", shown)
        self.assertIn("We miss half the WhatsApp messages", shown)

    def test_stimulus_with_template_comment_or_hypothesis_id_is_refused(self):
        self.init("--size", "8")
        self.write("docs/validation/panel/stimulus.md", STIM + "\n<!-- guidance -->\nSee H1.")
        res = self.nxt()
        self.assertEqual(res["action"], "FIX-STIMULUS")
        joined = " ".join(res["errors"])
        self.assertIn("guidance comment", joined)
        self.assertIn("hypothesis id", joined)

    def test_fair_price_is_labelled_not_wtp(self):
        import panel
        self.assertEqual(panel.coerce_price("€1.200"), 1200)
        self.start()
        res = self.nxt()
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1,
                                                price="would-not-pay" if t["persona"] == "P01"
                                                else "fair", fp=None if t["persona"] == "P01" else 20))
        self.assertEqual(self.nxt()["action"], "DONE")
        fp = json.loads((self.d / ".harness/validation.json").read_text())["panel"][
            "scenarios"]["base"]["r1"]["fair_price"]
        self.assertEqual(fp["would_pay_nothing"], 1)
        self.assertIn("not willingness to pay", fp["note"])


class TestCompareAndWalkthrough(PanelBase):
    def complete_panel(self, d, pid, yes_ids):
        run([SCRIPTS / "panel.py", "init", "--dir", d, "--panel-id", pid, "--size", "8",
             "--rounds", "1", "--followups", "0"], self.d)
        self.write(f"{d}/stimulus.md", STIM)
        self.write(f"{d}/roster.json", roster(8))
        res = self.nxt("--dir", d)
        self.answer_tasks(res, lambda t: answer(t["persona"], "base", 1,
                                                "yes" if t["persona"] in yes_ids else "no",
                                                "price" if t["persona"] < "P05" else "complexity"))
        self.assertEqual(self.nxt("--dir", d)["action"], "DONE")

    def test_compare_two_panels(self):
        self.complete_panel("docs/validation/panel", "panel", {"P01", "P02"})
        self.complete_panel("docs/validation/panel-2", "panel-2", {"P01", "P02", "P03", "P04"})
        code, out, err = run([SCRIPTS / "panel.py", "compare", "docs/validation/panel",
                              "docs/validation/panel-2"], self.d)
        self.assertEqual(code, 0, out + err)
        facts = json.loads((self.d / ".harness/validation.json").read_text())
        self.assertEqual(facts["panel_variance"]["yes_share_abs_diff_pp"], 25.0)
        self.assertIn("panel", facts)
        self.assertIn("panel-2", facts)

    def test_walkthrough(self):
        self.complete_panel("docs/validation/panel", "panel", {"P01"})
        self.write("docs/02d-process-flows.md", "# Flows\n## PF-00 lifecycle\n## PF-01 Book\n## PF-02 Pay\n")
        code, out, _ = run([SCRIPTS / "panel.py", "walkthrough-next", "--sample", "4"], self.d)
        res = json.loads(out)
        self.assertEqual(res["action"], "WALKTHROUGH")
        self.assertEqual(len(res["tasks"]), 4)
        segs = {roster(8)["personas"][int(t["persona"][1:]) - 1]["segment"] for t in res["tasks"]}
        self.assertEqual(segs, {"S-01", "S-02"})
        for t in res["tasks"]:
            self.write(t["output"], {"persona": t["persona"], "flows": [
                {"flow_id": "PF-01", "steps": [
                    {"step": "Pick a slot", "ok": False, "friction": "too many taps",
                     "severity": "high", "would_abandon": t["persona"] == "P01"}]},
                {"flow_id": "PF-02", "steps": [
                    {"step": "Pay", "ok": True, "friction": None, "severity": None,
                     "would_abandon": False}]}]})
        code, out, _ = run([SCRIPTS / "panel.py", "walkthrough-next", "--sample", "4"], self.d)
        self.assertEqual(json.loads(out)["action"], "DONE")
        w = json.loads((self.d / ".harness/validation.json").read_text())["walkthrough"]
        self.assertEqual(w["flows"]["PF-01"]["personas_abandoning"], 1)
        self.assertEqual(w["flows"]["PF-01"]["worst_steps"][0]["friction"], 4)
        self.assertIn("PF-01", (self.p / "walkthrough-summary.md").read_text())

    def test_walkthrough_skips_without_panel(self):
        # No `init`: the discover/asdr skills call this in projects that never ran validate.
        code, out, err = run([SCRIPTS / "panel.py", "walkthrough-next"], self.d)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["action"], "SKIP")
        self.init()
        code, out, _ = run([SCRIPTS / "panel.py", "walkthrough-next"], self.d)
        self.assertEqual(json.loads(out)["action"], "SKIP")

    def test_walkthrough_flows_that_name_a_hypothesis_are_held_back(self):
        self.complete_panel("docs/validation/panel", "panel", {"P01"})
        self.write("docs/02d-process-flows.md", "# Flows\n## PF-01 Book (tests H-01)\n")
        code, out, _ = run([SCRIPTS / "panel.py", "walkthrough-next", "--sample", "2"], self.d)
        res = json.loads(out)
        self.assertEqual(res["action"], "FIX-LEAK", res)
        self.assertIn("H-01", " ".join(res["errors"]))

    def test_compare_refuses_one_panel_twice(self):
        self.complete_panel("docs/validation/panel", "panel", {"P01"})
        code, out, _ = run([SCRIPTS / "panel.py", "compare", "docs/validation/panel",
                            "docs/validation/panel"], self.d)
        self.assertEqual(code, 1)
        self.complete_panel("docs/validation/panel-2", "panel", {"P01"})
        code, out, _ = run([SCRIPTS / "panel.py", "compare", "docs/validation/panel",
                            "docs/validation/panel-2"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("own --panel-id", out)


class TestSharedVocabulary(unittest.TestCase):
    def test_mirofish_and_panel_ask_the_same_questions(self):
        src = (SCRIPTS / "mirofish_validate.py").read_text()
        self.assertTrue("vq.DEFAULT_QUESTIONS" in src, "mirofish_validate must use the shared questions")
        self.assertFalse("DEFAULT_QUESTIONS = [" in src, "no private copy of the questions")

    def test_strip_and_leaks(self):
        text, removed = vq.strip_sections(SEED)
        self.assertNotIn("H-01", text)
        self.assertEqual(removed, ["6. Hypotheses to test"])
        self.assertTrue(vq.leaks("we think clinic owners lose bookings to unanswered night messages", SEED))
        self.assertFalse(vq.leaks("A WhatsApp assistant for clinics", SEED))


if __name__ == "__main__":
    unittest.main()
