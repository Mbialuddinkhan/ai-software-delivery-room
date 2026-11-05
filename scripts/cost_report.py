#!/usr/bin/env python3
"""Turn the run log into a cost report a proposal or an invoice can cite.

Usage:
  python3 cost_report.py [--runs .harness/agent-runs.jsonl]
        [--price-opus USD --price-sonnet USD --price-haiku USD --price-fable USD]
        [--prices .harness/prices.json]
        [--client "Acme"] [--project "ClientProof Voice OS"]
        [--md docs/cost-report.md] [--json .harness/cost-report.json]

v4.2 (brief 3.4). `log_agent_run.py` (3.8) already stamps every agent run with
tokens, seconds and the model actually used; `estimate_run.py` prices runs
BEFORE they happen. This closes the loop AFTER: measured spend by stage, role
and model, attributable to a client — so the payback and savings charts in a
proposal cite real run costs, not estimates.

Prices follow estimate_run.py's stance: none are built in (they change).
Pass --price-<model> in USD per million tokens (blended in/out), or keep them
in .harness/prices.json: {"opus": 30, "sonnet": 6, "haiku": 1, "fable": 40}.
With no prices the report still shows tokens, runs and hours; USD columns
appear only for priced models, and unpriced models are listed so the gap is
visible rather than silently zero.

Reads only what is on disk; missing files give an empty report, never an error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

MODEL_NAMES = ("opus", "sonnet", "haiku", "fable")


def norm_model(name: str) -> str:
    n = (name or "").lower()
    for m in MODEL_NAMES:
        if m in n:
            return m
    return n or "unknown"


def load_runs(path: Path):
    runs = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return runs
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        runs.append({
            "agent": r.get("agent") or "unknown",
            "phase": r.get("phase") or "",
            "stage": r.get("stage") or "",
            "tokens": int(r.get("tokens") or 0),
            "seconds": float(r.get("seconds") or 0),
            "model": norm_model(r.get("model", "")),
            "result": r.get("result", "ok"),
            "ts": r.get("ts", ""),
        })
    return runs


def group(runs, key):
    g = defaultdict(lambda: {"runs": 0, "tokens": 0, "seconds": 0.0,
                             "by_model": defaultdict(int)})
    for r in runs:
        k = r[key] or "(none)"
        g[k]["runs"] += 1
        g[k]["tokens"] += r["tokens"]
        g[k]["seconds"] += r["seconds"]
        g[k]["by_model"][r["model"]] += r["tokens"]
    return g


def usd(tokens_by_model, prices):
    total, priced_all = 0.0, True
    for m, tok in tokens_by_model.items():
        if m in prices:
            total += tok / 1e6 * prices[m]
        elif tok:
            priced_all = False
    return (round(total, 2), priced_all)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=".harness/agent-runs.jsonl")
    for m in MODEL_NAMES:
        ap.add_argument(f"--price-{m}", type=float, help=f"USD per million tokens on {m} (blended)")
    ap.add_argument("--prices", default=".harness/prices.json")
    ap.add_argument("--client", default="")
    ap.add_argument("--project", default=Path.cwd().name)
    ap.add_argument("--md", default="docs/cost-report.md")
    ap.add_argument("--json", dest="json_out", default=".harness/cost-report.json")
    args = ap.parse_args()

    prices = {}
    try:
        stored = json.loads(Path(args.prices).read_text())
        prices.update({norm_model(k): float(v) for k, v in stored.items()})
    except (OSError, ValueError):
        pass
    for m in MODEL_NAMES:
        v = getattr(args, f"price_{m}")
        if v is not None:
            prices[m] = v

    runs = load_runs(Path(args.runs))
    if not runs:
        print(f"OK: no runs logged yet in {args.runs} — nothing to report")
        return 0

    tok_by_model = defaultdict(int)
    for r in runs:
        tok_by_model[r["model"]] += r["tokens"]
    total_usd, fully_priced = usd(tok_by_model, prices)
    totals = {"runs": len(runs), "tokens": sum(r["tokens"] for r in runs),
              "hours": round(sum(r["seconds"] for r in runs) / 3600, 2),
              "by_model": dict(tok_by_model)}
    if prices:
        totals["usd"] = total_usd
        totals["usd_complete"] = fully_priced

    out = {"client": args.client, "project": args.project,
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "prices_usd_per_mtok": prices, "totals": totals,
           "by_phase": {}, "by_stage": {}, "by_agent": {}}

    L = [f"# Cost report — {args.project}" + (f" (client: {args.client})" if args.client else ""),
         "", f"_Generated {out['generated']} by cost_report.py from measured run "
         f"stamps in `{args.runs}` — these are actual costs, not estimates._", ""]
    L.append(f"**Totals:** {totals['runs']} agent runs · {totals['tokens']:,} tokens · "
             f"{totals['hours']} h" + (f" · **${totals['usd']:,.2f}**" if "usd" in totals else ""))
    if prices and not fully_priced:
        unpriced = sorted(m for m, t in tok_by_model.items() if t and m not in prices)
        L.append(f"\n> Incomplete pricing: no price given for {', '.join(unpriced)} — "
                 "the USD total excludes those tokens.")
    if not prices:
        L.append("\n> No prices supplied (`--price-<model>` or `.harness/prices.json`), "
                 "so this report shows usage without USD.")

    for key, title in (("phase", "By phase"), ("stage", "By stage"), ("agent", "By role")):
        g = group(runs, key)
        out[f"by_{key}"] = {}
        L += ["", f"## {title}", "",
              "| " + title.split()[1].capitalize() + " | Runs | Tokens | Hours |"
              + (" USD |" if prices else ""),
              "|---|---|---|---|" + ("---|" if prices else "")]
        for k in sorted(g, key=lambda x: -g[x]["tokens"]):
            v = g[k]
            row_usd, _ = usd(v["by_model"], prices)
            rec = {"runs": v["runs"], "tokens": v["tokens"],
                   "hours": round(v["seconds"] / 3600, 2),
                   "by_model": dict(v["by_model"])}
            if prices:
                rec["usd"] = row_usd
            out[f"by_{key}"][k] = rec
            L.append(f"| {k} | {v['runs']} | {v['tokens']:,} | {rec['hours']} |"
                     + (f" {row_usd:,.2f} |" if prices else ""))

    L += ["", "## By model", "", "| Model | Tokens |" + (" USD/Mtok | USD |" if prices else ""),
          "|---|---|" + ("---|---|" if prices else "")]
    for m in sorted(tok_by_model, key=lambda x: -tok_by_model[x]):
        line = f"| {m} | {tok_by_model[m]:,} |"
        if prices:
            p = prices.get(m)
            line += (f" {p:,.2f} | {tok_by_model[m]/1e6*p:,.2f} |" if p is not None
                     else " — | (unpriced) |")
        L.append(line)

    md = Path(args.md)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(L) + "\n")
    jp = Path(args.json_out)
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    print(f"OK: {totals['runs']} runs, {totals['tokens']:,} tokens"
          + (f", ${totals['usd']:,.2f}" if "usd" in totals else "")
          + f" -> {md} and {jp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
