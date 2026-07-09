#!/usr/bin/env python3
"""Print the next orchestrator action for the ASDR harness.

Usage: python3 next_action.py   (run from the project root)

Reads sprints.json + .harness/progress.json + the active sprint's contract
and prints ONE unambiguous instruction as JSON. The orchestrator loop is:

    run this script -> do exactly what it says -> update state -> repeat

This removes long-horizon sequencing from the model entirely: the state
machine lives here, not in the model's memory.

Reliability note (v2.1): the two circuit breakers below — the attempt cap and
the negotiation-round cap — used to depend on the model faithfully
incrementing counters in progress.json. If the model ever forgot, the
breaker silently never fired and a sprint could loop forever. Those two
counters are now ALSO derived from artifacts on disk that the harness
produces mechanically (eval-report files and trace-log lines) and combined
with the ledger via max(). A missing or stale increment can no longer hide a
runaway sprint or endless negotiation.
"""
import json
import re
import sys
from pathlib import Path

MAX_ATTEMPTS = 5           # per sprint before forced split
MAX_TEARDOWNS_PER_RUN = 2  # same-project teardowns before asking the human
MAX_NEGOTIATION_ROUNDS = 4


def out(next_agent, mode, sprint, attempt, reason, **extra):
    print(json.dumps({
        "next_agent": next_agent, "mode": mode, "sprint": sprint,
        "attempt": attempt, "reason": reason, **extra,
    }, indent=2))
    return 0


def derived_attempt(root, sprint):
    """Attempt number derived from eval-report files on disk.

    A FAIL leaves an eval-report file behind; N failed attempts means N
    report files exist and the next attempt is N+1. This is authoritative
    even if progress.json's `attempt` was never incremented.
    """
    if sprint is None:
        return 0
    reports = root / ".harness" / "eval-reports"
    if not reports.is_dir():
        return 0
    n = len(list(reports.glob(f"eval-report-{sprint}-attempt-*.md")))
    return n + 1


def derived_rounds(root, sprint):
    """Negotiation rounds derived from the trace log.

    The generator logs one `negotiate-<sprint>` line each time it produces or
    revises the contract, so counting those lines yields the true round count
    even if progress.json's `negotiation_rounds` was never incremented.
    """
    if sprint is None:
        return 0
    log = root / ".harness" / "traces" / "log.jsonl"
    if not log.exists():
        return 0
    n = 0
    action = f"negotiate-{sprint}"
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("actor") == "generator" and entry.get("action") == action:
            n += 1
    return n


def main() -> int:
    root = Path.cwd()
    sprints_path = root / "sprints.json"
    progress_path = root / ".harness" / "progress.json"

    if not sprints_path.exists() or sprints_path.read_text().strip() in ("", "[]"):
        return out("planner", "plan", None, 0,
                   "No sprints exist yet. Invoke the planner, then run validate_sprints.py.")

    sprints = json.loads(sprints_path.read_text())
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    ledger_attempt = progress.get("attempt", 0) or 0

    torn_down = [s for s in sprints if s.get("status") == "torn-down"]
    if len(torn_down) >= MAX_TEARDOWNS_PER_RUN:
        return out("HUMAN", "checkpoint", None, ledger_attempt,
                   f"{len(torn_down)} sprints have been torn down. Stop and ask the "
                   "user how to proceed — automatic recovery has failed twice, and a "
                   "third blind retry usually compounds the problem.",
                   torn_down=[s["id"] for s in torn_down])

    active = [s for s in sprints if s.get("status") == "active"]
    if len(active) > 1:
        return out("ORCHESTRATOR", "fix-state", None, ledger_attempt,
                   f"State corrupt: {len(active)} sprints are active; only one may be. "
                   "Set all but the earliest back to pending, then rerun this script.")

    if active:
        sprint = active[0]["id"]
        # Combine the model-maintained ledger with the disk-derived count so a
        # forgotten increment cannot disable the circuit breaker.
        attempt = max(ledger_attempt, derived_attempt(root, sprint), 1)
        contract = root / ".harness" / "contracts" / f"contract-{sprint}.md"
        if attempt > MAX_ATTEMPTS:
            return out("planner", "split", sprint, attempt,
                       f"Attempt count {attempt} exceeds {MAX_ATTEMPTS}. Invoke the "
                       "planner to split this sprint into smaller sprints, mark this "
                       "one torn-down, then rerun this script.")
        if not contract.exists():
            return out("generator", "NEGOTIATE", sprint, attempt,
                       f"No contract exists for {sprint}. Invoke the generator in "
                       f"NEGOTIATE mode to write {contract}.")
        m = re.search(r"^Status:\s*(\S+)", contract.read_text(), re.MULTILINE)
        status = m.group(1) if m else "missing"
        rounds = max(progress.get("negotiation_rounds", 0) or 0,
                     derived_rounds(root, sprint))
        if status == "in-negotiation":
            if rounds >= MAX_NEGOTIATION_ROUNDS:
                return out("evaluator", "FORCE-RATIFY", sprint, attempt,
                           f"Negotiation hit {MAX_NEGOTIATION_ROUNDS} rounds. Invoke the "
                           "evaluator to make final edits itself and set Status: ratified. "
                           "Endless negotiation is worse than an imperfect contract.",
                           negotiation_rounds=rounds)
            return out("evaluator", "NEGOTIATE", sprint, attempt,
                       "Contract awaits review. Invoke the evaluator to ratify it "
                       "(set Status: ratified) or request revision "
                       "(set Status: revision-requested with Revision notes).",
                       negotiation_rounds=rounds)
        if status == "revision-requested":
            return out("generator", "NEGOTIATE", sprint, attempt,
                       "Evaluator requested revisions. Invoke the generator to address "
                       "every item in '## Revision notes', set Status: in-negotiation, "
                       "and increment negotiation_rounds in progress.json.",
                       negotiation_rounds=rounds)
        if status == "ratified":
            report = (root / ".harness" / "eval-reports" /
                      f"eval-report-{sprint}-attempt-{attempt}.md")
            if progress.get("awaiting") == "evaluate":
                return out("evaluator", "EVALUATE", sprint, attempt,
                           f"Build finished for attempt {attempt}. Invoke the "
                           f"evaluator to grade every criterion and write {report}.")
            return out("generator", "BUILD", sprint, attempt,
                       "Contract is ratified. Invoke the generator in BUILD mode, then "
                       "set awaiting=evaluate in progress.json.")
        return out("ORCHESTRATOR", "fix-state", sprint, attempt,
                   f"Contract Status is '{status}' which is not a valid state. Fix the "
                   "Status line to in-negotiation | revision-requested | ratified.")

    pending = [s for s in sprints if s.get("status") == "pending"]
    if pending:
        nxt = pending[0]["id"]
        return out("ORCHESTRATOR", "activate", nxt, 1,
                   f"Mark {nxt} active in sprints.json, set progress.json to "
                   f'{{"phase":"execution","sprint":"{nxt}","attempt":1,'
                   f'"awaiting":null,"negotiation_rounds":0}}, then rerun this script.')

    return out("ORCHESTRATOR", "final-gates", None, 0,
               "All sprints are done. Proceed to final gates: security-compliance, "
               "devops, documentation, release-manager, risk-manager.")


if __name__ == "__main__":
    sys.exit(main())
