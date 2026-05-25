#!/usr/bin/env python3
"""Initialize AI Software Delivery Room harness in the current repo."""
from pathlib import Path
import json

root = Path.cwd()
(root / ".harness" / "traces").mkdir(parents=True, exist_ok=True)
(root / "docs").mkdir(exist_ok=True)
(root / "evals").mkdir(exist_ok=True)

progress = root / ".harness" / "progress.json"
if not progress.exists():
    progress.write_text(json.dumps({
        "phase": "init",
        "sprint": None,
        "attempt": 0,
        "awaiting": None,
        "last_eval_result": None,
        "last_updated": None
    }, indent=2) + "\n")

sprints = root / "sprints.json"
if not sprints.exists():
    sprints.write_text("[]\n")

print("AI Software Delivery Room harness initialized.")
print("Next: run /asdr \"<your software idea>\" in Claude Code.")
