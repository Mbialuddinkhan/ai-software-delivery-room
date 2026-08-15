#!/usr/bin/env python3
"""Regenerate .harness/state-digest.md — one page of authoritative state.

Usage:
  python3 build_digest.py [--max-chars 4000]

Agents currently re-read progress.json, sprints.json, every eval report and the
traceability matrix to answer "where are we?". This derives that once, cheaply,
into a page a context pack can inline.

Machine-generated only. Nothing here is an agent's prose summary — every line
is read from a state file, so a wrong digest is a script bug (findable) rather
than a hallucination (silent, and copied into every downstream brief).
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(p, default=None):
    q = Path(p)
    if not q.exists():
        return default
    try:
        return json.loads(q.read_text())
    except ValueError:
        return default


def verdict_of(report):
    blocks = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```",
                        Path(report).read_text(errors="ignore"), re.DOTALL)
    if not blocks:
        return None
    m = re.search(r"^\s*verdict\s*:\s*(\S+)", blocks[-1], re.M)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".harness/state-digest.md")
    ap.add_argument("--max-chars", type=int, default=4000)
    args = ap.parse_args()

    progress = load(".harness/progress.json", {}) or {}
    sprints = load("sprints.json", []) or []
    matrix = load(".harness/traceability.json", {}) or {}
    facts = load(".harness/facts.json", None)

    L = ["# Project state digest",
         f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
         "by build_digest.py — do not edit by hand._", ""]

    L.append(f"- Phase: **{progress.get('phase', '?')}**  ·  "
             f"Sprint: **{progress.get('sprint') or '—'}**  ·  "
             f"Attempt: **{progress.get('attempt', 0)}**  ·  "
             f"Rigor: **{progress.get('rigor', 'standard')}**")
    if progress.get("awaiting"):
        L.append(f"- Awaiting: **{progress['awaiting']}**")
    if facts:
        c = facts.get("census", {}) or {}
        t = facts.get("tests") or {}
        L.append(f"- Facts: commit `{facts.get('commit')}` · "
                 f"files {c.get('total', '?')} "
                 f"(unit {c.get('unit', '?')} / int {c.get('integration', '?')} "
                 f"/ e2e {c.get('e2e', '?')}) · "
                 f"tests passed={t.get('passed', '?')} failed={t.get('failed', '?')}")
    else:
        L.append("- Facts: **missing** — run `emit_facts.py`; numeric claims are "
                 "not gradeable until it exists")
    L.append("")

    if sprints:
        L.append("## Sprints")
        for s in sprints:
            L.append(f"- `{s.get('id')}` **{s.get('status')}** — {s.get('goal', '')}")
        L.append("")

    evals = sorted(Path(".harness/eval-reports").glob("eval-report-*.md")) \
        if Path(".harness/eval-reports").is_dir() else []
    if evals:
        L.append("## Latest verdicts")
        seen = {}
        for r in evals:
            m = re.match(r"eval-report-(.+)-attempt-(\d+)\.md", r.name)
            if m:
                seen[m.group(1)] = r  # sorted, so last wins
        for sprint, r in sorted(seen.items()):
            L.append(f"- `{sprint}` → **{verdict_of(r) or '?'}** ({r.name})")
        L.append("")

    reqs = matrix.get("requirements", []) or []
    if reqs:
        by = {}
        for r in reqs:
            by[r.get("status", "?")] = by.get(r.get("status", "?"), 0) + 1
        L.append("## Traceability")
        L.append("- " + " · ".join(f"{k}: {v}" for k, v in sorted(by.items())))
        bad = [r["req_id"] for r in reqs
               if r.get("status") in ("drifted", "broken")]
        if bad:
            L.append(f"- **Needs attention:** {', '.join(bad)}")
        L.append("")

    carry = []
    for p in list(Path(".harness/contracts").glob("*.md")) if \
            Path(".harness/contracts").is_dir() else []:
        for line in p.read_text(errors="ignore").splitlines():
            if "CARRY-FORWARD:" in line or "SHIPS-OPEN:" in line:
                carry.append(line.strip())
    if carry:
        L.append("## Open carry-forwards")
        L.extend(f"- {c}" for c in sorted(set(carry))[:20])
        L.append("")

    text = "\n".join(L)
    if len(text) > args.max_chars:
        text = text[:args.max_chars].rsplit("\n", 1)[0] + \
            "\n\n_(truncated to fit the digest budget)_\n"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text if text.endswith("\n") else text + "\n")
    print(f"OK: wrote {out} ({len(text)} chars, budget {args.max_chars})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
