#!/usr/bin/env python3
"""Drive one stage of the ASDR universal triad (plan -> execute -> QA).

Usage:
  python3 stage_status.py <stage-id> --artifact <path> [--max-rounds N]

Every stage in the strategic room and the final gates runs as an independent
triad: a stage-planner writes an acceptance checklist, the specialist executor
produces the artifact, and a SEPARATE stage-qa reviews it. No agent grades its
own work; the QA is the authority. This script tells the orchestrator where a
single stage stands so the loop logic lives on disk, not in the model's memory
(the same discipline as next_action.py for sprints).

State is derived entirely from files:
  plan       .harness/plans/plan-<stage>.md
  artifact   the executor's output (path passed in, e.g. docs/01-product-brief.md)
  qa reports .harness/qa-reports/qa-<stage>-r<n>.md   (one per review round)

Prints ONE instruction as JSON. Circuit breaker: after --max-rounds revise
cycles it returns FORCE-ACCEPT so a stage cannot loop forever.
"""
import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_MAX_ROUNDS = 3


def out(action, agent, stage, round_n, reason, **extra):
    print(json.dumps({
        "action": action, "agent": agent, "stage": stage,
        "round": round_n, "reason": reason, **extra,
    }, indent=2))
    return 0


def qa_verdict(path):
    """Parse verdict: pass|revise from the last fenced block of a QA report."""
    text = Path(path).read_text()
    blocks = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        return None
    m = re.search(r"^\s*verdict\s*:\s*(\S+)", blocks[-1], re.MULTILINE)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--max-rounds", type=int, default=DEFAULT_MAX_ROUNDS)
    ap.add_argument("--no-plan", action="store_true",
                    help="light mode: skip the stage-planner; QA grades the "
                         "artifact against its template and the standard "
                         "(used for low-stakes stages under 'standard' rigor)")
    args = ap.parse_args()

    stage = args.stage
    artifact = Path(args.artifact)
    plan = Path(".harness/plans") / f"plan-{stage}.md"
    qa_glob = sorted(glob.glob(f".harness/qa-reports/qa-{stage}-r*.md"))
    rounds = len(qa_glob)
    rubric = str(plan) if not args.no_plan else "the executor's template and the standard"

    if not args.no_plan and not plan.exists():
        return out("PLAN", "stage-planner", stage, 0,
                   f"No plan for stage '{stage}'. Invoke stage-planner to write "
                   f"{plan} — the acceptance checklist the executor builds to and "
                   "the QA grades against.")

    if not artifact.exists():
        return out("EXECUTE", "<stage-executor>", stage, 1,
                   f"No artifact at {artifact}. Invoke the stage's executor to "
                   f"produce it, building to {rubric}.")

    latest_qa = qa_glob[-1] if qa_glob else None
    if latest_qa is None:
        return out("QA", "stage-qa", stage, 1,
                   f"Artifact exists but has never been reviewed. Invoke stage-qa "
                   f"to grade {artifact} against {rubric} and write "
                   f".harness/qa-reports/qa-{stage}-r1.md.")

    # If the executor revised the artifact after the last review, re-review.
    if artifact.stat().st_mtime > Path(latest_qa).stat().st_mtime:
        return out("QA", "stage-qa", stage, rounds + 1,
                   f"Artifact changed since the last QA review. Invoke stage-qa to "
                   f"re-grade it and write "
                   f".harness/qa-reports/qa-{stage}-r{rounds + 1}.md.")

    verdict = qa_verdict(latest_qa)
    if verdict == "pass":
        return out("DONE", None, stage, rounds,
                   f"Stage '{stage}' passed independent QA. Proceed to the next stage.")
    if verdict == "revise":
        if rounds >= args.max_rounds:
            return out("FORCE-ACCEPT", "stage-qa", stage, rounds,
                       f"Stage '{stage}' hit {args.max_rounds} revise rounds. Invoke "
                       "stage-qa to make the minimal fixes itself and set verdict: pass, "
                       "or escalate to the human. Endless revision is worse than an "
                       "imperfect artifact a later gate can still catch.")
        return out("EXECUTE", "<stage-executor>", stage, rounds + 1,
                   f"QA returned 'revise'. Invoke the executor to address every item in "
                   f"{latest_qa}'s failed_checks, then it will be re-reviewed.")

    return out("FIX-STATE", None, stage, rounds,
               f"Last QA report {latest_qa} has no valid verdict (pass|revise). "
               "Fix its fenced block, then rerun this script.")


if __name__ == "__main__":
    sys.exit(main())
