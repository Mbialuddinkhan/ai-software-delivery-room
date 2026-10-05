#!/usr/bin/env python3
"""Summarise how an ASDR run went — what each sprint and stage cost, from files.

Usage:
  python3 run_metrics.py [--out .harness/metrics.json] [--md docs/run-metrics.md]

Reads only what earlier steps left on disk, so it works mid-run or after:
  .harness/traces/log.jsonl            agent invocations (actor, action)
  .harness/eval-reports/eval-report-<sprint>-attempt-<n>.md   evaluations + verdicts
  .harness/qa-reports/qa-<stage>-r<n>.md                       triad review rounds
  .harness/packs/*.md                   context-pack sizes (≈ tokens = chars / 4)
  .harness/test-results/history.jsonl   browser test runs (run_tests.py)
  .harness/progress.json, sprints.json  where the run is now

Use it to answer "where did the time go": a sprint with 3 attempts and 4
negotiation rounds, a stage QA'd 3 times, or a context pack near its budget
is where the next run should change something. Missing inputs give zeros,
never an error.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

H = Path(".harness")


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def jsonl(p: Path) -> list:
    rows = []
    if p.is_file():
        for line in p.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def verdict_of(text: str) -> str | None:
    m = re.search(r"^\s*verdict:\s*([a-z-]+)", text, re.MULTILINE | re.IGNORECASE)
    return m.group(1).lower() if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarise an ASDR run from its files.")
    ap.add_argument("--out", default=str(H / "metrics.json"))
    ap.add_argument("--md", default="docs/run-metrics.md")
    args = ap.parse_args()

    traces = jsonl(H / "traces" / "log.jsonl")
    by_actor = collections.Counter(t.get("actor") for t in traces)
    progress = read_json(H / "progress.json", {})
    sprints_doc = read_json(Path("sprints.json"), [])
    sprints_list = sprints_doc.get("sprints", []) if isinstance(sprints_doc, dict) else sprints_doc

    sprints = []
    ids = [s.get("id") for s in sprints_list if isinstance(s, dict)]
    for f in sorted((H / "eval-reports").glob("eval-report-*-attempt-*.md")) if (H / "eval-reports").is_dir() else []:
        m = re.match(r"eval-report-(.+)-attempt-(\d+)\.md", f.name)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    for sid in ids:
        reports = sorted((H / "eval-reports").glob(f"eval-report-{sid}-attempt-*.md")) if (H / "eval-reports").is_dir() else []
        verdicts = [verdict_of(r.read_text(errors="ignore")) for r in reports]
        rounds = sum(1 for t in traces if t.get("actor") == "generator" and t.get("action") == f"negotiate-{sid}")
        status = next((s.get("status") for s in sprints_list if isinstance(s, dict) and s.get("id") == sid), None)
        sprints.append({"id": sid, "status": status, "attempts": len(reports),
                        "verdicts": verdicts, "negotiation_rounds": rounds,
                        "generator_runs": sum(1 for t in traces if t.get("actor") == "generator" and sid in str(t.get("action"))),
                        "evaluator_runs": sum(1 for t in traces if t.get("actor") == "evaluator" and sid in str(t.get("action")))})

    stages = collections.defaultdict(int)
    for f in (H / "qa-reports").glob("qa-*-r*.md") if (H / "qa-reports").is_dir() else []:
        m = re.match(r"qa-(.+)-r(\d+)\.md", f.name)
        if m:
            stages[m.group(1)] = max(stages[m.group(1)], int(m.group(2)))

    packs = []
    for f in sorted((H / "packs").glob("*.md")) if (H / "packs").is_dir() else []:
        chars = len(f.read_text(errors="ignore"))
        packs.append({"pack": f.name, "chars": chars, "approx_tokens": chars // 4})

    runs = jsonl(H / "test-results" / "history.jsonl")
    tests = {
        "runs": len(runs),
        "passed_runs": sum(1 for r in runs if r.get("status") == "passed"),
        "last": runs[-1] if runs else None,
    }

    metrics = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "phase": progress.get("phase"),
        "active_sprint": progress.get("sprint"),
        "rigor": progress.get("rigor"),
        "agent_invocations": dict(by_actor.most_common()),
        "agent_invocations_total": len(traces),
        "sprints": sprints,
        "sprint_attempts_total": sum(s["attempts"] for s in sprints),
        "negotiation_rounds_total": sum(s["negotiation_rounds"] for s in sprints),
        "stage_qa_rounds": dict(sorted(stages.items())),
        "packs": packs,
        "pack_tokens_max": max((p["approx_tokens"] for p in packs), default=0),
        "tests": tests,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2))

    lines = ["# Run metrics", "",
             f"Generated {metrics['generated_at']} by run_metrics.py from the files in `.harness/`. "
             "Do not hand-edit; rerun the script.", "",
             f"- Phase: **{metrics['phase'] or '—'}**, active sprint: **{metrics['active_sprint'] or '—'}**, rigor: {metrics['rigor'] or '—'}",
             f"- Agent invocations: {metrics['agent_invocations_total']}"
             + (" (" + ", ".join(f"{k} {v}" for k, v in by_actor.most_common(6)) + ")" if by_actor else ""),
             f"- Sprint evaluations: {metrics['sprint_attempts_total']} · contract negotiation rounds: {metrics['negotiation_rounds_total']}",
             f"- Browser test runs: {tests['runs']} ({tests['passed_runs']} passed)"
             + (f"; last: {tests['last'].get('status')} {tests['last'].get('passed', 0)}/{tests['last'].get('tests', 0)} at {tests['last'].get('commit')}"
                if tests["last"] else ""), ""]
    if sprints:
        lines += ["## Sprints", "", "| Sprint | Status | Evaluations | Verdicts | Negotiation rounds |",
                  "|---|---|---|---|---|"]
        lines += [f"| {s['id']} | {s['status'] or '—'} | {s['attempts']} | {', '.join(v or '?' for v in s['verdicts']) or '—'} | {s['negotiation_rounds']} |"
                  for s in sprints]
        lines.append("")
    if stages:
        lines += ["## Stage reviews", "", "| Stage | QA rounds |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(stages.items())]
        lines.append("")
    if packs:
        lines += ["## Context packs", "", "| Pack | ≈ tokens |", "|---|---|"]
        lines += [f"| {p['pack']} | {p['approx_tokens']:,} |" for p in packs]
        lines.append("")
    md = Path(args.md)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines) + "\n")
    print(f"OK: {out} and {md} — {len(sprints)} sprints, {sum(stages.values())} QA rounds, "
          f"{len(packs)} packs, {tests['runs']} test runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
