#!/usr/bin/env python3
"""Initialize the AI Software Delivery Room harness in the current project.

Usage: python3 init_asdr.py --source <plugin-root>

<plugin-root> is the directory containing the plugin's scripts/ and
templates/ folders (two levels above any skill's base directory).

This is Phase 0 as a single command. It:
  1. creates the harness directory tree
  2. copies the plugin's scripts and templates into .harness/ so every later
     step uses stable project-local paths (no plugin path math after this)
  3. seeds progress.json, sprints.json, and CLAUDE.md if missing
Idempotent: safe to rerun; never overwrites existing project files.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

DIRS = [
    ".harness/contracts",
    ".harness/eval-reports",
    ".harness/traces",
    ".harness/tests",
    ".harness/scripts",
    ".harness/templates",
    ".harness/plans",       # stage-planner acceptance checklists (triad)
    ".harness/qa-reports",  # stage-qa review reports (triad)
    "docs",
    "evals",
]

PROGRESS_SEED = {
    "phase": "strategic",
    "sprint": None,
    "attempt": 0,
    "awaiting": None,
    "negotiation_rounds": 0,
    "last_eval_result": None,
    # Universal-triad rigor dial: paranoid | standard | lite
    #   paranoid = full plan->execute->QA on every stage
    #   standard = full triad on high-stakes stages, light execute->QA elsewhere
    #   lite     = no per-stage triad (v2.1 behavior: batched critic + judge)
    "rigor": "standard",
    "last_updated": None,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True,
                        help="Plugin root containing scripts/ and templates/")
    args = parser.parse_args()
    source = Path(args.source).resolve()
    root = Path.cwd()

    if not (source / "scripts").is_dir() or not (source / "templates").is_dir():
        print(f"ERROR: {source} does not contain scripts/ and templates/ — "
              "pass the plugin root (two levels above the skill directory).")
        return 1

    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    for sub in ("scripts", "templates"):
        for f in (source / sub).iterdir():
            if f.is_file():
                shutil.copy2(f, root / ".harness" / sub / f.name)

    progress = root / ".harness" / "progress.json"
    if not progress.exists():
        progress.write_text(json.dumps(PROGRESS_SEED, indent=2) + "\n")

    sprints = root / "sprints.json"
    if not sprints.exists():
        sprints.write_text("[]\n")

    claude_md = root / "CLAUDE.md"
    template = root / ".harness" / "templates" / "CLAUDE-template.md"
    if not claude_md.exists() and template.exists():
        claude_md.write_text(template.read_text())

    print("ASDR harness initialized.")
    print("State files: sprints.json, .harness/progress.json, CLAUDE.md")
    print("Validators:  .harness/scripts/  Templates: .harness/templates/")
    print("Rigor dial:  progress.json -> \"rigor\" (paranoid | standard | lite)")
    print("Next: python3 .harness/scripts/next_action.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
