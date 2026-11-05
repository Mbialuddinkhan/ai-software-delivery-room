#!/usr/bin/env python3
"""Blast-radius tags on a sprint contract, and the human gate they trigger.

Usage:
  python3 blast_radius.py classify .harness/contracts/contract-<sprint>.md [--write]
  python3 blast_radius.py gate-check [--sprint <id>]
  python3 blast_radius.py approve --sprint <id> --who <name> --rationale "<why>"
  python3 blast_radius.py defer   --sprint <id> --who <name> --rationale "<why>"

v4.3 (brief 4.1/4.2). The public claim: verification never skips, it changes
shape — depth is set by the stage's blast radius, DEFINED UP FRONT, not
case-by-case in the moment. This makes the harness match the claim literally.

Every acceptance criterion carries a radius. The contract author declares it
inline — `(radius: high)` at the end of the criterion — or inherits the
default, `medium`. Declarations are checked against a FLOOR, not trusted:
a criterion whose text touches data, auth, money, PII, outbound sends,
deletion or production deploys is high whatever it declares, and declaring
it lower is a blocking error naming the trigger words. Mechanical, so it
cannot be argued with after the fact.

What the radius drives:
  low     mechanical validators + the normal review for the rigor level
  medium  the full stage protocol at the chosen rigor
  high    adversarial review as usual PLUS a cross-family second opinion when
          one is available (second_opinion.py) PLUS the human gate below

The human gate: a ratified contract with any high-radius criterion needs ONE
explicit human approval before the build starts — recorded with its
rationale in docs/decision-log.md (`approve`), or deferred back to
negotiation (`defer`). `gate-check` exits 2 while approval is pending (the
repo's WAITING convention), 0 otherwise. One gate per pipeline, placed by
radius — never one per step, never zero. Low-risk stages never queue.

State lives in `.harness/blast-radius.json`, not in progress.json — the
sprint state machine is untouched. A project with no classification (started
before 4.3) is skipped with a note, never blocked. Zero dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

STATE = Path(".harness/blast-radius.json")
LEVELS = ("low", "medium", "high")
INLINE = re.compile(r"\(\s*radius:\s*(low|medium|high)\s*\)", re.I)

# The floor: any of these in a criterion's text forces high. Word-boundary
# matched; each tuple is (trigger label, regex).
HIGH_TRIGGERS = [
    ("auth", re.compile(r"\b(auth|authenticat\w*|authoriz\w*|login|log[- ]?in|password|session token|api key|credential\w*|secret\w*)\b", re.I)),
    ("money", re.compile(r"\b(payment\w*|billing|charge\w*|refund\w*|invoice\w*|payout\w*|price\s+change|checkout|money|transfer\w*)\b", re.I)),
    ("pii", re.compile(r"\b(PII|personal data|patient\w*|medical|health record\w*|date of birth|passport|SSN|national id)\b", re.I)),
    ("destructive", re.compile(r"\b(delete\w*|drop\s+table|truncate|purge\w*|hard[- ]remove|wipe)\b", re.I)),
    ("migration", re.compile(r"\b(migration\w*|migrate\w*|schema change)\b", re.I)),
    ("production", re.compile(r"\b(production|prod\s+deploy\w*|go[- ]live|release to users)\b", re.I)),
    ("outbound", re.compile(r"\b(outbound|broadcast\w*|mass (email|message|sms)|send\w* (an )?(email|sms|message)s? to (all|every))\b", re.I)),
]


def criteria_of(text: str):
    """Yield (category, number, line) for numbered criteria under ### headings."""
    cat = None
    for line in text.splitlines():
        h = re.match(r"^###\s+(.*?)\s*$", line)
        if h:
            cat = h.group(1)
            continue
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if m and cat:
            yield cat, int(m.group(1)), m.group(2)


def classify_line(body: str):
    declared = None
    m = INLINE.search(body)
    if m:
        declared = m.group(1).lower()
    triggers = [name for name, pat in HIGH_TRIGGERS if pat.search(INLINE.sub("", body))]
    floor = "high" if triggers else "low"
    radius = declared or ("high" if triggers else "medium")
    return declared, triggers, floor, radius


def sprint_of(text: str, path: Path) -> str:
    m = re.search(r"#\s*CONTRACT\s*·\s*(\S+)", text)
    if m:
        return m.group(1)
    m = re.search(r"contract-(.+?)\.md$", path.name)
    return m.group(1) if m else path.stem


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"version": 1, "sprints": {}}


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")


def log_decision(decision, chosen, rationale, who):
    dl = Path(__file__).resolve().parent / "decision_log.py"
    if dl.exists():
        subprocess.run([sys.executable, str(dl), "add", "--decision", decision,
                        "--options", "approve|defer", "--chosen", chosen,
                        "--rationale", rationale, "--who", who,
                        "--source", str(STATE)], capture_output=True, text=True)


def cmd_classify(args) -> int:
    path = Path(args.contract)
    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1
    text = re.sub(r"<!--.*?-->", "", path.read_text(), flags=re.DOTALL)
    sprint = sprint_of(text, path)

    rows, errors = [], []
    for cat, n, body in criteria_of(text):
        declared, triggers, floor, radius = classify_line(body)
        if declared and triggers and LEVELS.index(declared) < LEVELS.index("high"):
            errors.append(
                f"ERROR: {cat} #{n}: declared radius '{declared}' but the text "
                f"touches {', '.join(triggers)} — the floor for those is high. "
                "Raise the declaration (or reword the criterion if the trigger "
                "is genuinely absent from the work).")
            radius = "high"
        rows.append({"category": cat, "n": n, "radius": radius,
                     "declared": declared, "triggers": triggers})
    if not rows:
        print("ERROR: no numbered criteria found under '###' categories")
        return 1

    stage_radius = max((r["radius"] for r in rows), key=LEVELS.index)
    high = [r for r in rows if r["radius"] == "high"]
    print(f"{sprint}: {len(rows)} criteria — stage radius {stage_radius} "
          f"({len(high)} high, {sum(1 for r in rows if r['radius'] == 'medium')} medium, "
          f"{sum(1 for r in rows if r['radius'] == 'low')} low)")
    for r in high:
        why = ("declared" if r["declared"] == "high" else
               f"floor: {', '.join(r['triggers'])}")
        print(f"  high: {r['category']} #{r['n']} ({why})")
    for e in errors:
        print(e)

    if args.write and not errors:
        st = load_state()
        st["sprints"][sprint] = {
            "classified": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "contract": str(path), "stage_radius": stage_radius, "criteria": rows,
            "human_gate": ({"required": True, "status": "pending"} if high
                           else {"required": False, "status": "not-needed"}),
        }
        save_state(st)
        print(f"-> {STATE}")
        if high:
            print(f"HUMAN GATE: {sprint} has high-radius criteria — approval "
                  "required before the build starts: "
                  f"blast_radius.py approve --sprint {sprint} --who <name> --rationale \"…\"")
    return 1 if errors else 0


def cmd_gate_check(args) -> int:
    st = load_state()
    if not st["sprints"]:
        print("OK: no blast-radius classification yet (project started before "
              "4.3, or classify was not run) — not blocking")
        return 0
    pending = {s: v for s, v in st["sprints"].items()
               if v["human_gate"]["status"] == "pending"
               and (not args.sprint or s == args.sprint)}
    if args.sprint and args.sprint not in st["sprints"]:
        print(f"OK: {args.sprint} has no classification — not blocking")
        return 0
    if pending:
        print("AWAITING HUMAN — these sprints have high-radius criteria and no "
              "recorded approval:")
        for s, v in sorted(pending.items()):
            highs = [r for r in v["criteria"] if r["radius"] == "high"]
            print(f"  {s} ({v['stage_radius']}): " + "; ".join(
                f"{r['category']} #{r['n']}" for r in highs))
            print(f"    approve: python3 .harness/scripts/blast_radius.py approve "
                  f"--sprint {s} --who <name> --rationale \"<why this risk is accepted>\"")
            print(f"    defer:   python3 .harness/scripts/blast_radius.py defer "
                  f"--sprint {s} --who <name> --rationale \"<what must change first>\"")
        return 2
    print("OK: no pending human gates")
    return 0


def cmd_decide(args, verdict: str) -> int:
    st = load_state()
    v = st["sprints"].get(args.sprint)
    if not v:
        print(f"ERROR: no classification for {args.sprint} — run classify first")
        return 1
    if not args.rationale.strip():
        print("ERROR: --rationale is required; the gate exists to record the why")
        return 1
    v["human_gate"] = {"required": True, "status":
                       "approved" if verdict == "approve" else "deferred",
                       "who": args.who, "rationale": args.rationale,
                       "when": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    save_state(st)
    log_decision(f"Human gate: {args.sprint} (high blast radius)",
                 verdict, args.rationale, args.who)
    if verdict == "approve":
        print(f"OK: {args.sprint} approved by {args.who} — recorded with rationale; "
              "the build may start")
    else:
        print(f"OK: {args.sprint} deferred by {args.who} — send the contract back "
              "to negotiation; the gate stays pending after the next classify")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify")
    c.add_argument("contract")
    c.add_argument("--write", action="store_true")
    g = sub.add_parser("gate-check")
    g.add_argument("--sprint", default=None)
    for name in ("approve", "defer"):
        d = sub.add_parser(name)
        d.add_argument("--sprint", required=True)
        d.add_argument("--who", required=True)
        d.add_argument("--rationale", required=True)
    args = ap.parse_args()
    if args.cmd == "classify":
        return cmd_classify(args)
    if args.cmd == "gate-check":
        return cmd_gate_check(args)
    return cmd_decide(args, args.cmd)


if __name__ == "__main__":
    sys.exit(main())
