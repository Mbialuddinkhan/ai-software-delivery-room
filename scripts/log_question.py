#!/usr/bin/env python3
"""Append one question-and-answer to .harness/questions.jsonl.

Usage:
  python3 log_question.py --q "<question asked>" --a "<the user's answer>" \
      [--phase <phase>] [--asked-by <agent/role>] [--changed docs/02-requirements.md,sprints.json] \
      [--status answered|open] [--id Q-07]

Every time the orchestrator asks the user a decision question and gets an
answer, it logs it here. The dashboard reads this file to show the decision
trail: what was asked, what the user decided, when, and which documents the
answer changed. An unanswered question (status=open, no --a) shows on the
dashboard as "waiting on you".

Why a log and not just chat: answers made in chat are lost between sessions.
This file is the durable record a future session (or the user, weeks later)
reads to know why the project is shaped the way it is. One line per Q&A;
never hand-edited in a way that rewrites history — to revise an answer, append
a new line that supersedes it (same --id).

Append-only and best-effort: a failed write prints a warning and exits 0 so it
never blocks the run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Log a question and the user's answer for the dashboard.")
    ap.add_argument("--q", required=True, help="the question asked")
    ap.add_argument("--a", default=None, help="the user's answer; omit for an open question")
    ap.add_argument("--phase", default=None, help="phase/stage the question came up in")
    ap.add_argument("--asked-by", default=None, help="which agent or skill asked")
    ap.add_argument("--changed", default="", help="comma-separated paths the answer changed")
    ap.add_argument("--status", choices=["answered", "open"], default=None)
    ap.add_argument("--id", dest="qid", default=None, help="stable id, e.g. Q-07; a repeat supersedes the earlier line")
    ap.add_argument("--out", default=".harness/questions.jsonl")
    args = ap.parse_args()

    path = Path(args.out)
    status = args.status or ("answered" if args.a else "open")
    qid = args.qid
    if not qid:
        existing = 0
        if path.is_file():
            existing = sum(1 for _ in path.read_text(errors="ignore").splitlines() if _.strip())
        qid = f"Q-{existing + 1:02d}"
    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "id": qid,
        "phase": args.phase,
        "asked_by": args.asked_by,
        "question": args.q,
        "answer": args.a,
        "status": status,
        "changed": [p.strip() for p in args.changed.split(",") if p.strip()],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(line) + "\n")
        print(f"logged {qid} ({status})")
    except OSError as e:
        print(f"WARN: could not write {path}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
