#!/usr/bin/env python3
"""Stamp sprint start / finish times for the delivery forecast.

Usage:
  python3 sprint_clock.py start <sprint-id>       # when a sprint is activated
  python3 sprint_clock.py done <sprint-id>        # when the evaluator passes it
  python3 sprint_clock.py torn-down <sprint-id>   # when it is torn down and re-planned

Appends one line to .harness/sprint-clock.jsonl. sprints.json stays limited to
user-visible fields (validate_sprints.py enforces that), so timing lives here.
build_dashboard.py turns these stamps into an expected delivery date with a
standard deviation. Append-only and best-effort: never blocks the run.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVENTS = {"start", "done", "torn-down"}


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in EVENTS or not re.match(r"^sprint-\d{2}$", sys.argv[2]):
        print("usage: sprint_clock.py start|done|torn-down sprint-NN")
        return 1
    path = Path(".harness/sprint-clock.jsonl")
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": sys.argv[1], "sprint": sys.argv[2]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(line) + "\n")
        print(f"clock: {line['sprint']} {line['event']} {line['ts']}")
    except OSError as e:
        print(f"WARN: could not write {path}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
