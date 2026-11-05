#!/usr/bin/env python3
"""One decision log for every gate a human passed, with the rationale.

Usage:
  python3 decision_log.py add --decision "Architecture option" --chosen "B (modular monolith)"
         [--options "A|B|C"] [--rationale "cheapest to run at this scale"]
         [--who user] [--source docs/decision-architecture.md] [--out docs/decision-log.md]
  python3 decision_log.py collect [--out docs/decision-log.md]

v4.2 (brief 4.3). The run already records decisions in half a dozen shapes —
phase decision docs, `.harness/entry.json` (start point), `.harness/models.json`
(model plan), the DEC-xx configuration register, the rigor in progress.json.
What was missing is ONE table a client or a future maintainer reads top to
bottom, each row carrying the rationale — and a weekly look at whether the
decisions held.

`add` appends one row (the orchestrator calls it at every user gate: rigor
pick, start point, architecture option, portability, contract ratification,
configuration decisions, release go). `collect` backfills from the artifacts
above; it is idempotent — a row's key is (decision, chosen, source), so
re-running collect never duplicates.

The client status report and the dashboard read this file. Exit 0 always on
`collect` (missing artifacts are normal mid-run); `add` exits 2 when required
fields are missing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HEADER = """# Decision log

Every gate a human passed in this project — what was decided, what the
options were, why, by whom. Written by `decision_log.py` (add at each gate,
`collect` to backfill). Reviewed weekly: a decision that did not hold gets a
new row superseding it, never an edit.

| When (UTC) | Decision | Options seen | Chosen | Rationale | Who | Source |
|---|---|---|---|---|---|---|
"""


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def split_row(line: str):
    """Split a markdown table row on pipes that are NOT escaped as \\|."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def existing_keys(out: Path):
    keys = set()
    if out.exists():
        for line in out.read_text(errors="ignore").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = split_row(line)
            if len(cells) >= 7 and cells[0] not in ("When (UTC)", "---"):
                keys.add((cells[1], cells[3], cells[6]))
    return keys


def append_rows(out: Path, rows):
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        out.write_text(HEADER)
    have = existing_keys(out)
    added = 0
    with out.open("a") as f:
        for r in rows:
            key = (esc(r["decision"]), esc(r["chosen"]), esc(r.get("source", "")))
            if key in have:
                continue
            f.write("| {ts} | {d} | {o} | {c} | {r} | {w} | {s} |\n".format(
                ts=r.get("ts") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
                d=esc(r["decision"]), o=esc(r.get("options", "")), c=esc(r["chosen"]),
                r=esc(r.get("rationale", "")) or "(not recorded)",
                w=esc(r.get("who", "user")), s=esc(r.get("source", ""))))
            have.add(key)
            added += 1
    return added


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def collect_rows():
    rows = []
    # Start point (4.0 entry_point.py)
    e = read_json(".harness/entry.json")
    if e and e.get("start"):
        rows.append({"decision": "Where the run starts", "chosen": str(e["start"]),
                     "options": "validate|discover|design|build|release|assess|resume",
                     "rationale": str(e.get("reason", "") or e.get("why", "")),
                     "source": ".harness/entry.json"})
    # Model plan (4.0)
    m = read_json(".harness/models.json")
    if m and m.get("plan"):
        rows.append({"decision": "Model plan", "chosen": str(m["plan"]) +
                     (" (top=fable)" if m.get("top") == "fable" else ""),
                     "options": "economy|balanced|maximum",
                     "rationale": "picked with the cost estimate at Phase 0",
                     "source": ".harness/models.json"})
    # Rigor
    p = read_json(".harness/progress.json")
    if p and p.get("rigor"):
        rows.append({"decision": "Rigor", "chosen": str(p["rigor"]),
                     "options": "lite|standard|paranoid",
                     "rationale": "picked with the cost estimate at Phase 0",
                     "source": ".harness/progress.json"})
    # Profile (4.2 founder mode)
    pr = read_json(".harness/profile.json")
    if pr and pr.get("profile"):
        rows.append({"decision": "Delivery profile", "chosen": str(pr["profile"]),
                     "options": "founder|enterprise",
                     "rationale": str(pr.get("rationale", "")),
                     "source": ".harness/profile.json"})
    # Phase decisions (go/no-go verdict blocks)
    for doc in sorted(Path("docs").glob("decision-*.md")) if Path("docs").is_dir() else []:
        text = doc.read_text(errors="ignore")
        m2 = re.search(r"^verdict:\s*(\S+)", text, re.M)
        if m2:
            phase = doc.stem.replace("decision-", "")
            why = ""
            r2 = re.search(r"(?:##\s*(?:Reasons|Why|Rationale)\s*\n)(.{10,300}?)(?:\n#|\n\n)", text, re.S)
            if r2:
                why = re.sub(r"\s+", " ", r2.group(1))[:200]
            rows.append({"decision": f"Phase gate: {phase}", "chosen": m2.group(1),
                         "options": "go|no-go", "rationale": why,
                         "who": "judge (user-ratified)", "source": str(doc)})
    # Configuration register DEC-xx (4.0, docs/03f)
    cfg = Path("docs/03f-configuration.md")
    if cfg.exists():
        for m3 in re.finditer(r"^\|\s*(DEC-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|",
                              cfg.read_text(errors="ignore"), re.M):
            dec_id, what, _opts, _rec, decided = (m3.group(i).strip() for i in range(1, 6))
            if decided and decided.lower() not in ("pending", "decision", "---", ""):
                rows.append({"decision": f"{dec_id}: {what}"[:80], "chosen": decided,
                             "options": _opts[:80], "rationale": "see configuration register",
                             "source": "docs/03f-configuration.md"})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--decision", required=True)
    a.add_argument("--chosen", required=True)
    a.add_argument("--options", default="")
    a.add_argument("--rationale", default="")
    a.add_argument("--who", default="user")
    a.add_argument("--source", default="")
    a.add_argument("--out", default="docs/decision-log.md")
    c = sub.add_parser("collect")
    c.add_argument("--out", default="docs/decision-log.md")
    args = ap.parse_args()

    out = Path(args.out)
    if args.cmd == "add":
        if not args.rationale:
            print("NOTE: no --rationale given — the log is only as useful as its why")
        n = append_rows(out, [vars(args)])
        print(f"OK: {'added 1 row' if n else 'already logged (no duplicate written)'} -> {out}")
        return 0
    rows = collect_rows()
    n = append_rows(out, rows)
    print(f"OK: collect found {len(rows)} decision(s), added {n} new -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
