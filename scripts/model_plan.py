#!/usr/bin/env python3
"""Which model each ASDR role runs on: the model plan (v4.0).

Usage:
  python3 model_plan.py set --plan economy|balanced|maximum [--top opus|fable] [--file .harness/models.json]
  python3 model_plan.py get <role> [--file .harness/models.json]
  python3 model_plan.py unavailable <model> [--file .harness/models.json]
  python3 model_plan.py show [--file .harness/models.json] [--json]

Every role runs on its own model, whatever model the main conversation uses;
the orchestrator passes `model: <get role>` on EVERY agent invocation. The main
conversation itself stays on the model the user selected — ASDR cannot change
that, so the cheapest setup is a Sonnet main session with this plan.

Plans (tiers: top = the strongest model, standard = Sonnet, light = Haiku):
  balanced  the 3.8/3.9 defaults: judgement and authoring roles on top,
            checklist roles and the panel on Sonnet (same as agent frontmatter)
  economy   only the roles that can stop a bad release stay on top (critic,
            judge, evaluator, risk-manager, security-compliance); authors on
            Sonnet; the panel and the release notes on Haiku
  maximum   every role on top
--top fable makes "top" mean Fable instead of Opus (for when the user picked
Fable and wants the judgement roles to follow).

If an agent call fails because the account or organisation does not allow a
model, run `unavailable <model>`: `get` then returns the next model in the
fallback chain (fable -> opus -> sonnet; haiku -> sonnet; opus -> sonnet;
sonnet -> opus), then any other model still available, and the change is
recorded. With no plan file, `get` answers with the balanced plan — or the
maximum plan when .harness/progress.json says rigor `paranoid`. Last line:
MODEL: {json}.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROLES = ["product-owner", "business-analyst", "product-manager", "solution-architect", "ai-architect",
         "security-compliance", "devops", "critic", "judge", "generator", "evaluator", "risk-manager",
         "stage-planner", "stage-qa", "planner", "product-integrity-qa", "documentation", "release-manager",
         "panelist"]
GATEKEEPERS = ["critic", "judge", "evaluator", "risk-manager", "security-compliance"]
CHECKLIST = ["stage-planner", "stage-qa", "planner", "product-integrity-qa", "documentation", "release-manager",
             "panelist"]
PLANS = {
    "balanced": {"top": [r for r in ROLES if r not in CHECKLIST], "standard": CHECKLIST, "light": []},
    "economy": {"top": GATEKEEPERS,
                "standard": [r for r in ROLES if r not in GATEKEEPERS + ["panelist", "release-manager"]],
                "light": ["panelist", "release-manager"]},
    "maximum": {"top": list(ROLES), "standard": [], "light": []},
}
PLAIN = {
    "balanced": "Today's setup: judgement and authoring roles on the strongest model, checklist roles and the "
                "simulated panel on Sonnet.",
    "economy": "Only the roles that can stop a bad release (critic, judge, tester, risk manager, security) stay "
               "on the strongest model; authors move to Sonnet; the panel and release notes to Haiku.",
    "maximum": "Every role on the strongest model. Highest cost; for client work with money, personal or "
               "regulated data.",
}
FALLBACK = {"fable": ["opus", "sonnet"], "opus": ["sonnet"], "haiku": ["sonnet"], "sonnet": ["opus"]}
MODELS = ["fable", "opus", "sonnet", "haiku"]
PREFERENCE = ["opus", "sonnet", "fable", "haiku"]      # last resort, strongest affordable first


def mapping(plan: str, top: str = "opus") -> dict:
    p = PLANS[plan]
    out = {}
    for tier, model in (("top", top), ("standard", "sonnet"), ("light", "haiku")):
        for r in p[tier]:
            out[r] = model
    return out


def default_plan(path: Path) -> str:
    try:
        prog = json.loads((path.parent / "progress.json").read_text())
        if isinstance(prog, dict) and prog.get("rigor") == "paranoid":
            return "maximum"
    except (OSError, ValueError):
        pass
    return "balanced"


def clean(d: dict) -> dict:
    """Tolerate a hand-edited file: wrong types are replaced, unknown models ignored."""
    plan = d.get("plan") if d.get("plan") in PLANS else "balanced"
    top = d.get("top") if d.get("top") in ("opus", "fable") else "opus"
    un = d.get("unavailable")
    un = [m for m in un if m in MODELS] if isinstance(un, list) else []
    mp_ = d.get("map")
    base = mapping(plan, top)
    if isinstance(mp_, dict):
        base.update({r: m for r, m in mp_.items() if r in ROLES and m in MODELS})
    return {**d, "plan": plan, "top": top, "unavailable": sorted(set(un)), "map": base}


def load(path: Path) -> dict:
    try:
        d = json.loads(path.read_text())
        if isinstance(d, dict) and d.get("plan") in PLANS:
            return clean(d)
    except (OSError, ValueError):
        pass
    plan = default_plan(path)
    return {"plan": plan, "top": "opus", "map": mapping(plan), "unavailable": [], "source": "default"}


def resolve(model: str, unavailable: list) -> str:
    if model not in unavailable:
        return model
    for m in FALLBACK.get(model, []) + PREFERENCE:
        if m not in unavailable:
            return m
    return model                      # every model marked unavailable: let the call fail loudly


def role_model(role: str, data: dict) -> str:
    data = clean(data) if not isinstance(data.get("map"), dict) or not isinstance(data.get("unavailable", []), list) else data
    m = (data.get("map") or {}).get(role)
    if m not in MODELS:
        m = mapping(data.get("plan", "balanced") if data.get("plan") in PLANS else "balanced",
                    data.get("top", "opus")).get(role, "sonnet")
    return resolve(m, [x for x in (data.get("unavailable") or []) if x in MODELS])


def table(data: dict) -> str:
    rows = ["| Role | Model |", "|---|---|"]
    for r in ROLES:
        rows.append(f"| {r} | {role_model(r, data)} |")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Choose and read the per-role model plan.")
    ap.add_argument("cmd", choices=["set", "get", "unavailable", "show"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--plan", choices=list(PLANS), help="default: maximum under paranoid rigor, else balanced")
    ap.add_argument("--top", choices=["opus", "fable"], default="opus")
    ap.add_argument("--file", default=".harness/models.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    path = Path(a.file)

    if a.cmd == "set":
        old = load(path)
        a.plan = a.plan or default_plan(path)
        data = {"plan": a.plan, "top": a.top, "map": mapping(a.plan, a.top),
                "unavailable": old.get("unavailable") or [], "about": PLAIN[a.plan],
                "set_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError as ex:
            print(f"WARN: could not write {path}: {ex}")
        if not a.json:
            print(f"Model plan: {a.plan} (top = {a.top}). {PLAIN[a.plan]}\n")
            print(table(data))
        counts = {}
        for r in ROLES:
            m = role_model(r, data)
            counts[m] = counts.get(m, 0) + 1
        print("MODEL: " + json.dumps({"cmd": "set", "plan": a.plan, "top": a.top, "roles_by_model": counts}))
        return 0

    data = load(path)
    if a.cmd == "get":
        if a.arg not in ROLES:
            print(f"ERROR: unknown role {a.arg!r}; roles: {', '.join(ROLES)}")
            return 1
        m = role_model(a.arg, data)
        print(m)
        print("MODEL: " + json.dumps({"cmd": "get", "role": a.arg, "model": m, "plan": data.get("plan")}))
        return 0

    if a.cmd == "unavailable":
        if a.arg not in MODELS:
            print(f"ERROR: unknown model {a.arg!r}; models: {', '.join(MODELS)}")
            return 1
        un = sorted(set((data.get("unavailable") or []) + [a.arg]))
        data["unavailable"] = un
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n")
        except OSError as ex:
            print(f"WARN: could not write {path}: {ex}")
        moved = {r: role_model(r, data) for r in ROLES if (data.get("map") or {}).get(r) == a.arg}
        print(f"Recorded: {a.arg} is not available here. "
              + (f"{len(moved)} role(s) now run on {', '.join(sorted(set(moved.values())))}." if moved else "No role used it."))
        print("MODEL: " + json.dumps({"cmd": "unavailable", "model": a.arg, "unavailable": un, "moved": moved}))
        return 0

    if not a.json:
        print(f"Model plan: {data.get('plan')} (top = {data.get('top')})"
              + (f"; unavailable: {', '.join(data['unavailable'])}" if data.get("unavailable") else "") + "\n")
        print(table(data))
    print("MODEL: " + json.dumps({"cmd": "show", "plan": data.get("plan"), "top": data.get("top"),
                                 "map": {r: role_model(r, data) for r in ROLES},
                                 "unavailable": data.get("unavailable") or []}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
