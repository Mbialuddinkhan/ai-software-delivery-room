#!/usr/bin/env python3
"""Append one trace line to .harness/traces/log.jsonl.

Usage: python3 trace.py <actor> <action> <result>
Example: python3 trace.py evaluator evaluate-sprint-02 "verdict=fail attempt=2"

The trace log is what makes a crashed or interrupted run resumable and
auditable — every agent invocation leaves exactly one line here.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: trace.py <actor> <action> <result>")
        return 1
    path = Path(".harness/traces/log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": sys.argv[1],
        "action": sys.argv[2],
        "result": " ".join(sys.argv[3:]),
    }
    with path.open("a") as f:
        f.write(json.dumps(line) + "\n")
    print("traced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
