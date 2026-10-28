#!/usr/bin/env python3
"""Initialize the AI Software Delivery Room harness in the current project.

Usage: python3 init_asdr.py --source <plugin-root>

<plugin-root> is the directory containing the plugin's scripts/ and
templates/ folders (two levels above any skill's base directory).

This is Phase 0 as a single command. It:
  1. creates the harness directory tree
  2. copies the plugin's scripts and templates (including template folders
     such as templates/e2e/) into .harness/ so every later step uses stable
     project-local paths (no plugin path math after this)
  3. seeds progress.json, sprints.json, publish.json and CLAUDE.md if missing
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
    ".harness/packs",       # generated per-task context packs (v3.2)
    ".harness/test-results",  # run_tests.py run folders (v3.4)
    ".harness/manual",        # manual-tour screenshots + manifests (v3.4)
    "docs",
    "docs/manuals",           # manual.json + built manuals per version (v3.4)
    "evals",
    "deploy/agents",      # T3 agent runtime manifests (v3.3)
]

PROGRESS_SEED = {
    "phase": "strategic",
    "sprint": None,
    "attempt": 0,
    "awaiting": None,
    "negotiation_rounds": 0,
    "last_eval_result": None,
    # Commit the active sprint started from; emit_facts.py diffs against it
    # (v3.2.1). Set by the orchestrator when a sprint is activated.
    "sprint_base_ref": None,
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
            elif f.is_dir() and not f.name.startswith(("__", ".")):
                # template folders such as templates/e2e/{playwright,cypress,selenium}
                shutil.copytree(f, root / ".harness" / sub / f.name, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Where test reports and manuals are published. Private by default: the
    # repo, CI artifacts and a private claude.ai page. GitHub Pages is public
    # and stays off unless the user turns it on for this project (v3.4).
    publish = root / ".harness" / "publish.json"
    if not publish.exists():
        publish.write_text(json.dumps({"repo": True, "ci_artifacts": True,
                                       "claude_artifact": True, "github_pages": False},
                                      indent=2) + "\n")

    # Dashboard inputs (v3.6): where the project runs and lives, and the log of
    # every question asked and answered. Never holds credentials.
    dash = root / ".harness" / "dashboard.json"
    tmpl = root / ".harness" / "templates" / "dashboard.json"
    if not dash.exists() and tmpl.exists():
        cfg = json.loads(tmpl.read_text())
        cfg["project"] = root.name
        dash.write_text(json.dumps(cfg, indent=2) + "\n")
    q = root / ".harness" / "questions.jsonl"
    if not q.exists():
        q.write_text("")

    # Test cloud (v3.8): where ASDR may deploy temporary test environments,
    # chosen by the user in Phase 0. Starts as "none"; never holds credentials.
    cloud = root / ".harness" / "cloud.json"
    ctmpl = root / ".harness" / "templates" / "cloud.json"
    if not cloud.exists() and ctmpl.exists():
        c = json.loads(ctmpl.read_text())
        c.setdefault("tags", {})["project"] = root.name
        cloud.write_text(json.dumps(c, indent=2) + "\n")

    progress = root / ".harness" / "progress.json"
    # Which ASDR started this project (v4.1): known only for a project initialised
    # fresh by 4.1 or later; an older project is stamped "unknown" (null) once.
    origin = root / ".harness" / "origin.json"
    if not origin.exists():
        try:
            ver = json.loads((source / ".claude-plugin" / "plugin.json").read_text()).get("version")
        except (OSError, ValueError, AttributeError):
            ver = None
        fresh = not progress.exists()
        origin.write_text(json.dumps({"asdr_version": ver if fresh else None,
                                      "note": "initialised fresh" if fresh else
                                      "project existed before 4.1; the version that started it is unknown"},
                                     indent=2) + "\n")
    if not progress.exists():
        progress.write_text(json.dumps(PROGRESS_SEED, indent=2) + "\n")

    sprints = root / "sprints.json"
    if not sprints.exists():
        sprints.write_text("[]\n")

    # Product-integrity traceability matrix (seeded empty; the
    # product-integrity-qa agent fills it after discovery).
    trace = root / ".harness" / "traceability.json"
    if not trace.exists():
        trace.write_text(json.dumps({
            "version": 1, "last_updated": None,
            "outcomes": [], "use_cases": [], "requirements": [],
        }, indent=2) + "\n")

    claude_md = root / "CLAUDE.md"
    template = root / ".harness" / "templates" / "CLAUDE-template.md"
    if not claude_md.exists() and template.exists():
        claude_md.write_text(template.read_text())

    print("ASDR harness initialized.")
    print("State files: sprints.json, .harness/progress.json, CLAUDE.md")
    print("Validators:  .harness/scripts/  Templates: .harness/templates/")
    print("Rigor dial:  progress.json -> \"rigor\" (paranoid | standard | lite)")
    print()
    print("Context discipline (v3.2) — run these before dispatching any agent:")
    print("  python3 .harness/scripts/emit_facts.py --base <ref> --test-cmd '<cmd>'")
    print("  python3 .harness/scripts/build_graph.py")
    print("  python3 .harness/scripts/build_digest.py")
    print("  python3 .harness/scripts/make_context_pack.py --sprint <id> --role <role>")
    print("Browser tests (v3.4): copy .harness/templates/e2e/test-config.json to")
    print("  .harness/test-config.json, then: python3 .harness/scripts/run_tests.py [--live]")
    print("Cost (v3.8): python3 .harness/scripts/estimate_run.py --sprints <n> [--ui] [--ai] [--services <n>] "
          "--rigor <level> --set-budget; log every agent run with log_agent_run.py")
    print("Test cloud (v3.8): set .harness/cloud.json → test_cloud (aws | azure | gcp | none), then "
          "python3 .harness/scripts/cloud_preflight.py")
    print("Dashboard (v3.6): fill .harness/dashboard.json (environments, repos, links), then")
    print("  python3 .harness/scripts/build_dashboard.py   → docs/dashboard/ (HTML + PDF)")
    print("Where to start (v4.0): python3 .harness/scripts/entry_point.py recommend --prompt \"<request>\"; "
          "then entry_point.py choose <start>")
    print("Model plan (v4.0): python3 .harness/scripts/model_plan.py set --plan economy|balanced|maximum "
          "[--top fable]; pass model_plan.py get <role> on every agent call")
    print("Settings (v4.0): docs/03f-configuration.md, checked by validate_configurability.py")
    print("Next: python3 .harness/scripts/next_action.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
