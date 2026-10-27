#!/usr/bin/env python3
"""Estimate what an ASDR run will cost — agent runs, tokens and hours — per rigor level.

Usage:
  python3 estimate_run.py [--mode build|assess|validate] [--sprints 4] [--services 1]
                          [--ui] [--ai] [--cloud] [--kloc 15]
                          [--rigor lite|standard|paranoid] [--set-budget]
                          [--start discover|design|build|release] [--compare-starts]
                          [--plan economy|balanced|maximum] [--top opus|fable] [--compare-plans]
                          [--price-opus USD --price-sonnet USD --price-haiku USD --price-fable USD]
                          [--runs .harness/agent-runs.jsonl] [--json]

Shown to the user in Phase 0 so they choose the rigor level knowing its cost
(v3.8). Prints one table: lite, standard, paranoid, and what 3.7's standard
would have cost for the same project, so the saving is visible.

Every figure is an ESTIMATE. Per-role token and time defaults come from the
first full /assess run (eShopOnWeb, Oct 2026) where measured, and are labelled
assumptions otherwise. Once a project has logged runs (log_agent_run.py),
roles with 3+ logged runs use their measured averages instead (--runs).

--set-budget writes .harness/budget.json for the chosen --rigor: the estimate
plus 30% headroom. log_agent_run.py warns at 80% and stops at 100%.

v4.0: --plan prices each role on the model the model plan gives it (without
--plan, .harness/models.json is read when it exists, else the balanced plan);
--compare-plans prints economy / balanced / maximum at the chosen rigor.
--start counts only the work from that start point, plus the catch-up: each
skipped stage's documents are converted from the user's own documents (INTAKE
mode, assumed at 60% of writing them) and checked by one critic pass;
--compare-starts prints one row per start point.

No prices are built in (they change); pass --price-<model> in USD per million
tokens (a blended input/output figure) for every model the plan uses to get a
money estimate. Last line: ESTIMATE: {json}.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import model_plan as _mp                     # same folder in the plugin and in .harness/scripts
except ImportError:                              # pragma: no cover - degrade to the frontmatter tiers
    _mp = None

# role: (model tier, tokens per run, minutes per run, source)
ROLES = {
    "product-owner":        ("opus",   190_000, 11, "measured (assess)"),
    "business-analyst":     ("opus",   210_000, 15, "measured (assess)"),
    "product-manager":      ("opus",   180_000, 12, "assumed"),
    "solution-architect":   ("opus",   300_000, 17, "measured (assess)"),
    "ai-architect":         ("opus",   200_000, 12, "assumed"),
    "security-compliance":  ("opus",   230_000, 15, "measured (assess)"),
    "devops":               ("opus",   160_000, 11, "measured (assess)"),
    "critic":               ("opus",   300_000, 18, "measured (assess)"),
    "judge":                ("opus",   210_000, 11, "measured (assess)"),
    "generator":            ("opus",   400_000, 20, "assumed"),
    "evaluator":            ("opus",   250_000, 14, "assumed"),
    "risk-manager":         ("opus",   150_000,  9, "assumed"),
    "stage-planner":        ("sonnet",  50_000,  3, "assumed"),
    "stage-qa":             ("sonnet",  90_000,  5, "assumed"),
    "planner":              ("sonnet",  60_000,  4, "assumed"),
    "product-integrity-qa": ("sonnet", 120_000,  7, "assumed"),
    "documentation":        ("sonnet", 150_000, 10, "assumed"),
    "release-manager":      ("sonnet",  90_000,  6, "assumed"),
    # One persona answer: ~16k tokens, ~17 s, measured with the registered
    # `panelist` agent (Read/Write tools only). The same brief through a
    # general-purpose agent, which carries every tool, cost ~73k (Oct 2026).
    "panelist":             ("sonnet",  16_000, 0.3, "measured (panelist agent, one run)"),
}
LEVELS = ["lite", "standard", "paranoid", "3.7-standard"]
MODEL_NAMES = ["fable", "opus", "sonnet", "haiku"]
STARTS = ["discover", "design", "build", "release"]
INTAKE_FACTOR = 0.6           # converting the user's documents vs writing them from scratch (assumption)


def stages(ui: bool, ai: bool, cloud: bool, services: int):
    d = [("product-brief", "high", "product-owner"), ("business-case", "high", "product-owner"),
         ("roadmap", "med", "product-owner"), ("requirements", "high", "business-analyst"),
         ("use-cases", "high", "business-analyst"), ("features", "high", "product-manager"),
         ("process-flows", "high", "product-manager"), ("test-cases", "high", "business-analyst")]
    # architecture-options needs the user's decision before the rest, so it is its own batch
    a = [("architecture-options", "high", "solution-architect"), ("decision", "-", "user"),
         ("architecture", "high", "solution-architect")]
    if services > 1:
        a.append(("services", "high", "solution-architect"))
    if ui:
        a.append(("design-system", "med", "solution-architect"))
    if ai:
        a.append(("agent-design", "high", "ai-architect"))
    if cloud:
        a.append(("portability", "high", "devops"))
        a.append(("decision", "-", "user"))
    # v4.0: configurable decisions (the user decides), then the per-value test cases
    a += [("handoff", "-", "user"),       # its own invocation, after the portability decision
          ("configuration", "high", "solution-architect"), ("decision", "-", "user"),
          ("setting-tests", "med", "business-analyst")]
    a += [("devops-design", "high", "devops"), ("security-design", "high", "security-compliance")]
    f = [("security-final", "high", "security-compliance"), ("devops-readiness", "high", "devops"),
         ("documentation", "low", "documentation")]
    return d, a, f


def batches(phase):
    """Consecutive stages with the same executor run as ONE agent run in lite and
    standard (v3.8): the product-owner writes brief, business case and roadmap
    together; one stage-qa run reviews the batch."""
    out = []
    for st in phase:
        if out and out[-1][0] == st[2]:
            out[-1][1].append(st)
        else:
            out.append((st[2], [st]))
    return out


def stage_runs(level: str, tier: str) -> dict:
    """Expected runs per stage: executor, stage-planner, stage-qa (revise loops included)."""
    if level == "lite":
        return {"exec": 1.0}
    if level == "standard":
        return {"exec": 1.2, "stage-qa": 1.2} if tier == "high" else {"exec": 1.0}
    if level == "paranoid":
        return {"stage-planner": 1, "exec": 1.3, "stage-qa": 1.3}
    # 3.7 standard: full triad on high stakes, execute + QA on the rest
    return ({"stage-planner": 1, "exec": 1.2, "stage-qa": 1.2} if tier == "high"
            else {"exec": 1.2, "stage-qa": 1.2})


def review_runs(level: str) -> dict:
    """Per phase: critic, judge (3.8: only when the critic finds Critical/High), owner fixes."""
    p_high = 0.7          # share of phases whose critique has a Critical/High finding (assumption)
    if level == "lite":
        return {"critic": 1, "judge": p_high, "fix": 1}
    if level == "standard":
        return {"critic": 1, "judge": p_high * 1.5, "fix": 2}
    return {"critic": 1, "judge": 1.5, "fix": 2}       # paranoid and 3.7: judge every phase + a repair round


def count_build(level: str, a, start: str = "discover") -> dict:
    runs = {}

    def add(role, n):
        if n:
            runs[role] = runs.get(role, 0) + n
    d_st, a_st, f_st = stages(a.ui, a.ai, a.cloud, a.services)
    full = {"discover": [d_st, a_st], "design": [a_st], "build": [], "release": []}[start]
    skipped = {"discover": [], "design": [d_st], "build": [d_st, a_st], "release": [d_st, a_st]}[start]
    if skipped and start != "release":
        for phase in skipped:            # catch-up: one INTAKE run per owner batch, then one critic pass
            for executor, _sts in batches([x for x in phase if x[2] != "user"]):
                add(executor, INTAKE_FACTOR)
        if level != "lite":
            add("critic", 1)
            add("judge", review_runs(level)["judge"] / 1.5 if level == "standard" else review_runs(level)["judge"])
    if start == "release":
        for _, tier, executor in f_st:
            for k, n in stage_runs(level, tier).items():
                add(executor if k == "exec" else k, n)
        add("product-integrity-qa", 1)
        add("risk-manager", 1)
        add("release-manager", 1)
        return runs
    for phase in full:
        if level in ("lite", "standard"):
            for executor, sts in batches(phase):
                if executor == "user":          # a decision the user makes between batches
                    continue
                tier = "high" if any(t == "high" for _, t, _ in sts) else "med"
                for k, n in stage_runs(level, tier).items():
                    add(executor if k == "exec" else k, n)
        else:
            for _, tier, executor in phase:
                if executor == "user":
                    continue
                for k, n in stage_runs(level, tier).items():
                    add(executor if k == "exec" else k, n)
        r = review_runs(level)
        add("critic", r["critic"])
        add("judge", r["judge"])
        add(phase[0][2], r["fix"])           # owner fixes, costed at the phase's first executor
    for _, tier, executor in f_st:
        for k, n in stage_runs(level, tier).items():
            add(executor if k == "exec" else k, n)
    add("planner", 1)
    add("product-integrity-qa", 1 if level == "lite" else 1 + a.sprints)
    attempts = 1.3
    add("generator", a.sprints * (1 + attempts))   # negotiate + build per attempt
    add("evaluator", a.sprints * (1 + attempts))   # ratify + evaluate per attempt
    add("risk-manager", 1)
    add("release-manager", 1)
    return runs


def count_assess(level: str, a) -> dict:
    runs = {"business-analyst": 1, "solution-architect": 2, "security-compliance": 1, "devops": 1,
            "product-owner": 1, "critic": 1}
    if level == "3.7-standard":
        runs["solution-architect"] = 1
        runs.update({"judge": 2})                 # decision + round 2
    elif level == "paranoid":
        runs["judge"] = 2
    else:
        runs["judge"] = 0.9                       # skipped when no Critical/High; round 2 is scripted
    if level != "lite":                           # one revision round by the four owners + product-owner
        for r in ("business-analyst", "solution-architect", "security-compliance", "devops", "product-owner"):
            runs[r] = runs.get(r, 0) + 1
    return runs


def validate_stages():
    return [("idea-seed", "med", "product-owner"), ("desk-evidence", "high", "product-owner"),
            ("panel-stimulus", "med", "product-owner"), ("panel-roster", "med", "business-analyst"),
            ("idea-validation", "high", "product-owner")]


def count_validate(level: str, a) -> dict:
    """The validate skill (v3.9): authoring stages, the panel, critic and decision.
    A MiroFish run is not counted — it spends the user's own LLM account."""
    runs = {}

    def add(role, n):
        if n:
            runs[role] = runs.get(role, 0) + n
    st = validate_stages()
    if level in ("lite", "standard"):
        for executor, sts in batches(st):
            tier = "high" if any(t_ == "high" for _, t_, _ in sts) else "med"
            for k, n in stage_runs(level, tier).items():
                add(executor if k == "exec" else k, n)
    else:
        for _, tier, executor in st:
            for k, n in stage_runs(level, tier).items():
                add(executor if k == "exec" else k, n)
    size = a.panel_size
    add("panelist", size * (1 + a.scenarios) + (size if a.rounds == 2 else 0) + a.followups)
    add("panelist", 0.1 * size)                  # re-asks for invalid or stale answers
    r = review_runs(level)
    add("critic", r["critic"])
    add("judge", r["judge"])
    add("product-owner", r["fix"])
    return runs


def role_table(runs_file: Path) -> dict:
    t = {k: list(v) for k, v in ROLES.items()}
    try:
        lines = runs_file.read_text().splitlines()
    except OSError:
        return t
    seen = {}
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("tokens"):
            seen.setdefault(r.get("agent"), []).append((r["tokens"], (r.get("seconds") or 0) / 60))
    for role, xs in seen.items():
        if role in t and len(xs) >= 3:
            t[role][1] = int(statistics.mean(x[0] for x in xs))
            t[role][2] = round(statistics.mean(x[1] for x in xs), 1) or t[role][2]
            t[role][3] = f"measured here ({len(xs)} runs)"
    return t


def plan_models(a) -> dict:
    """role -> model under the chosen plan: --plan, else .harness/models.json, else the frontmatter tiers."""
    if _mp is None:
        return {r: v[0] for r, v in ROLES.items()}
    if getattr(a, "plan", None):
        return {r: _mp.role_model(r, {"plan": a.plan, "top": a.top, "map": _mp.mapping(a.plan, a.top)})
                for r in ROLES}
    data = _mp.load(Path(getattr(a, "models", ".harness/models.json")))
    return {r: _mp.role_model(r, data) for r in ROLES}


def cost(runs: dict, table: dict, a, mode: str, models: "dict | None" = None) -> dict:
    scale = max(0.6, (a.kloc / 15) ** 0.6) if mode == "assess" else 1.0
    svc = 1 + 0.15 * (a.services - 1)
    models = models or {r: v[0] for r, v in table.items()}
    tok = {m: 0.0 for m in MODEL_NAMES}
    minutes = 0.0
    for role, n in runs.items():
        _tier, t, m, _ = table[role]
        model = models.get(role, _tier)
        f = scale if role in ("business-analyst", "solution-architect", "security-compliance", "devops", "critic") else 1.0
        if role in ("generator", "evaluator"):
            f *= svc
        tok[model] = tok.get(model, 0.0) + n * t * f
        minutes += n * m * f
    if mode == "assess":
        minutes *= 0.75                          # reviewers and the revision round run in parallel
    out = {"agent_runs": round(sum(runs.values()), 1), "tokens": int(sum(tok.values())),
           "hours": round(minutes / 60, 1)}
    for mname in MODEL_NAMES:
        out[f"tokens_{mname}"] = int(tok.get(mname, 0))
    prices = {mname: getattr(a, f"price_{mname}", None) for mname in MODEL_NAMES}
    used = [mname for mname in MODEL_NAMES if tok.get(mname)]
    if used and all(prices[mname] is not None for mname in used):
        out["usd"] = round(sum(tok[mname] / 1e6 * prices[mname] for mname in used), 2)
    return out


def count(level: str, a, start: str = "discover") -> dict:
    if a.mode == "build":
        return count_build(level, a, start)
    return count_assess(level, a) if a.mode == "assess" else count_validate(level, a)


def main() -> int:
    ap = argparse.ArgumentParser(description="Estimate agent runs, tokens and hours per rigor level.")
    ap.add_argument("--mode", choices=["build", "assess", "validate"], default="build")
    ap.add_argument("--panel-size", type=int, default=12, help="validate: personas (8-30)")
    ap.add_argument("--scenarios", type=int, default=0, help="validate: what-if scenarios (0-3)")
    ap.add_argument("--rounds", type=int, choices=[1, 2], default=2, help="validate: panel rounds")
    ap.add_argument("--followups", type=int, default=3, help="validate: follow-up interviews")
    ap.add_argument("--sprints", type=int, default=4)
    ap.add_argument("--services", type=int, default=1, help="1 = monolith; >1 = microservices")
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--cloud", action="store_true", help="a portability / cloud stage is needed")
    ap.add_argument("--kloc", type=float, default=15, help="assess: thousands of lines in the system")
    ap.add_argument("--rigor", choices=["lite", "standard", "paranoid"], default="standard")
    ap.add_argument("--start", choices=STARTS, default="discover", help="build: where the run starts (v4.0)")
    ap.add_argument("--compare-starts", action="store_true", help="build: one row per start point")
    ap.add_argument("--plan", choices=["economy", "balanced", "maximum"], help="model plan (v4.0)")
    ap.add_argument("--top", choices=["opus", "fable"], default="opus")
    ap.add_argument("--models", default=".harness/models.json")
    ap.add_argument("--compare-plans", action="store_true", help="one row per model plan at the chosen rigor")
    ap.add_argument("--set-budget", action="store_true")
    ap.add_argument("--budget-file", default=".harness/budget.json")
    for mname in MODEL_NAMES:
        ap.add_argument(f"--price-{mname}", type=float, help=f"USD per million tokens on {mname} (blended)")
    ap.add_argument("--runs", default=".harness/agent-runs.jsonl")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    table = role_table(Path(a.runs))
    models = plan_models(a)
    res = {lv: cost(count(lv, a, a.start), table, a, a.mode, models) for lv in LEVELS}
    base = res["3.7-standard"]["tokens"] or 1
    plans = {}
    if a.compare_plans and _mp is not None:
        for pl in ("economy", "balanced", "maximum"):
            m = {r: _mp.role_model(r, {"plan": pl, "top": a.top, "map": _mp.mapping(pl, a.top)}) for r in ROLES}
            plans[pl] = cost(count(a.rigor, a, a.start), table, a, a.mode, m)
    starts = {}
    if a.compare_starts and a.mode == "build":
        for st in STARTS:
            starts[st] = cost(count(a.rigor, a, st), table, a, a.mode, models)
    if not a.json:
        shape = (f"{a.sprints} sprints, {a.services} service{'s' if a.services != 1 else ''}"
                 + (", UI" if a.ui else "") + (", AI" if a.ai else "") + (", cloud" if a.cloud else "")
                 + (f", starting at {a.start}" if a.start != "discover" else "")
                 if a.mode == "build" else f"assessment of about {a.kloc:g}k lines"
                 if a.mode == "assess" else
                 f"idea validation: a {a.panel_size}-person panel, {a.scenarios} scenario(s), "
                 f"{a.rounds} round(s), {a.followups} follow-up(s); MiroFish not counted")
        print(f"Estimate for {shape} — all figures are estimates.\n")
        hdr = "| Rigor | Agent runs | Tokens | on Opus/Fable | on Sonnet | on Haiku | Hours | vs 3.7 standard |"
        if "usd" in res["standard"]:
            hdr = hdr + " USD |"
        print(hdr)
        print("|" + "---|" * (hdr.count("|") - 1))
        for lv in LEVELS:
            r = res[lv]
            row = (f"| {lv}{' (chosen)' if lv == a.rigor else ''} | {r['agent_runs']:g} | {r['tokens'] / 1e6:.1f}M | "
                   f"{(r['tokens_opus'] + r['tokens_fable']) / 1e6:.1f}M | {r['tokens_sonnet'] / 1e6:.1f}M | "
                   f"{r['tokens_haiku'] / 1e6:.1f}M | {r['hours']:g} | {round(100 * r['tokens'] / base)}% |")
            if "usd" in r:
                row = row + f" {r['usd']:,.0f} |"
            print(row)
        if plans:
            print(f"\nModel plans at {a.rigor} rigor (top = {a.top}):\n")
            print("| Plan | Tokens on Opus/Fable | on Sonnet | on Haiku |" + (" USD |" if "usd" in plans["balanced"] else ""))
            print("|---|---|---|---|" + ("---|" if "usd" in plans["balanced"] else ""))
            for pl, r in plans.items():
                print(f"| {pl} | {(r['tokens_opus'] + r['tokens_fable']) / 1e6:.1f}M | {r['tokens_sonnet'] / 1e6:.1f}M | "
                      f"{r['tokens_haiku'] / 1e6:.1f}M |" + (f" {r['usd']:,.0f} |" if "usd" in r else ""))
        if starts:
            print(f"\nStart points at {a.rigor} rigor (catch-up included):\n")
            print("| Start | Agent runs | Tokens | Hours |" + (" USD |" if "usd" in starts["discover"] else ""))
            print("|---|---|---|---|" + ("---|" if "usd" in starts["discover"] else ""))
            for st, r in starts.items():
                print(f"| {st} | {r['agent_runs']:g} | {r['tokens'] / 1e6:.1f}M | {r['hours']:g} |"
                      + (f" {r['usd']:,.0f} |" if "usd" in r else ""))
        measured = [k for k, v in table.items() if v[3].startswith("measured here")]
        print("\nPer-role defaults: measured on the first /assess run where marked, otherwise assumed"
              + (f"; measured in this project: {', '.join(measured)}" if measured else "") + ".")
    if a.set_budget:
        r = res[a.rigor]
        b = {"rigor": a.rigor, "start": a.start, "tokens": int(r["tokens"] * 1.3), "hours": round(r["hours"] * 1.3, 1),
             "warn_at": 0.8, "basis": "estimate_run.py + 30% headroom"}
        if "usd" in r:
            b["usd"] = round(r["usd"] * 1.3, 2)
        try:
            Path(a.budget_file).parent.mkdir(parents=True, exist_ok=True)
            Path(a.budget_file).write_text(json.dumps(b, indent=2) + "\n")
            print(f"\nBudget written to {a.budget_file}: {b['tokens'] / 1e6:.1f}M tokens, {b['hours']} h.")
        except OSError as ex:
            print(f"WARN: could not write the budget: {ex}")
    out = {"mode": a.mode, "chosen": a.rigor, "start": a.start, "levels": res}
    if plans:
        out["plans"] = plans
    if starts:
        out["starts"] = starts
    print("ESTIMATE: " + json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
