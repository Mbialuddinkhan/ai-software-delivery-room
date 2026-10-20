#!/usr/bin/env python3
"""Record what one agent run cost, and warn when the project budget runs out.

Usage:
  python3 log_agent_run.py --agent critic --phase discovery [--stage product-brief]
                           [--tokens 305547 --tool-uses 72 --ms 1085298 | --usage "<usage block>"]
                           [--model opus] [--result ok|partial|failed] [--note "…"]
                           [--out .harness/agent-runs.jsonl] [--budget .harness/budget.json]

The orchestrator calls this after EVERY agent run (v3.8). The Agent tool's
result ends with a usage block (subagent_tokens, tool_uses, duration_ms):
pass it whole with --usage, or the numbers one by one.

Appends one line to .harness/agent-runs.jsonl, which run_metrics.py and the
dashboard read (tokens and time by role, phase and model). Then compares the
running total with .harness/budget.json (written by estimate_run.py when the
user picks a rigor level) and prints:

  BUDGET: {"tokens_used": …, "tokens_budget": …, "pct": …, "state": "ok|warn|over"}

warn at 80% (configurable), over at 100%. Over budget is not an error — the
orchestrator stops and asks the user whether to continue. Exit 0 always: a
logging problem must never stop the build.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path


def parse_usage(text: str) -> dict:
    out = {}
    for key, name in (("subagent_tokens", "tokens"), ("total_tokens", "tokens"),
                      ("tool_uses", "tool_uses"), ("duration_ms", "ms")):
        m = re.search(rf"{key}\s*[:=]\s*(\d+)", text or "")
        if m and name not in out:
            out[name] = int(m.group(1))
    return out


def totals(path: Path) -> dict:
    t = {"runs": 0, "tokens": 0, "seconds": 0.0}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return t
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        t["runs"] += 1
        t["tokens"] += int(r.get("tokens") or 0)
        t["seconds"] += float(r.get("seconds") or 0)
    return t


def budget_state(used: dict, budget: dict) -> dict:
    tb = int(budget.get("tokens") or 0)
    hb = float(budget.get("hours") or 0)
    warn_at = float(budget.get("warn_at") or 0.8)
    pct_t = used["tokens"] / tb if tb else 0.0
    pct_h = (used["seconds"] / 3600) / hb if hb else 0.0
    pct = max(pct_t, pct_h)
    state = "over" if pct >= 1 else "warn" if pct >= warn_at else "ok"
    return {"tokens_used": used["tokens"], "tokens_budget": tb or None,
            "hours_used": round(used["seconds"] / 3600, 2), "hours_budget": hb or None,
            "runs": used["runs"], "pct": round(pct * 100, 1), "state": state if (tb or hb) else "no-budget"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Log one agent run and check the budget.")
    ap.add_argument("--agent", required=True)
    ap.add_argument("--phase", default="")
    ap.add_argument("--stage", default="")
    ap.add_argument("--tokens", type=int)
    ap.add_argument("--tool-uses", type=int)
    ap.add_argument("--ms", type=int)
    ap.add_argument("--usage", default="", help="the usage block from the Agent tool's result, pasted whole")
    ap.add_argument("--model", default="")
    ap.add_argument("--result", default="ok", choices=["ok", "partial", "failed"])
    ap.add_argument("--note", default="")
    ap.add_argument("--out", default=".harness/agent-runs.jsonl")
    ap.add_argument("--budget", default=".harness/budget.json")
    args = ap.parse_args()

    u = parse_usage(args.usage)
    tokens = args.tokens if args.tokens is not None else u.get("tokens")
    ms = args.ms if args.ms is not None else u.get("ms")
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "agent": args.agent.split(":")[-1], "phase": args.phase, "stage": args.stage,
           "tokens": tokens or 0, "tool_uses": args.tool_uses if args.tool_uses is not None else u.get("tool_uses"),
           "seconds": round((ms or 0) / 1000, 1), "model": args.model, "result": args.result}
    if args.note:
        rec["note"] = args.note
    if not tokens:
        print("WARN: no token count given — pass --usage with the Agent result's usage block")
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as ex:
        print(f"WARN: could not write {out}: {ex}")
        return 0
    try:
        budget = json.loads(Path(args.budget).read_text())
    except (OSError, ValueError):
        budget = {}
    st = budget_state(totals(out), budget)
    if st["state"] == "warn":
        print(f"WARN: {st['pct']}% of the budget used ({st['tokens_used']:,} tokens, {st['hours_used']} h) — tell the user")
    elif st["state"] == "over":
        print(f"OVER BUDGET: {st['pct']}% used ({st['tokens_used']:,} tokens, {st['hours_used']} h) — "
              "stop and ask the user whether to continue, lower the rigor, or cut scope")
    print("BUDGET: " + json.dumps(st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
