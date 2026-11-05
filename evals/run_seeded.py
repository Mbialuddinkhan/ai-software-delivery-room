#!/usr/bin/env python3
"""Seeded-defect eval suite: measure what the harness actually catches.

Usage:
  python3 evals/run_seeded.py                 run mechanical checks, write results + table
  python3 evals/run_seeded.py --gate          also exit 1 on any regression vs baseline
  python3 evals/run_seeded.py --update-baseline
  python3 evals/run_seeded.py --live          print the reviewer tasks for agent-layer cases
  python3 evals/run_seeded.py record --case SD-A2 --role security-compliance \
          --caught yes [--model opus] [--family claude] [--notes "found in round 1"]
  python3 evals/run_seeded.py --release v4.2.0   append the escape line for a release

v4.2 (brief 8.1/8.2). "Independent check at every stage" is a claim; this
suite is the measurement. Each case under evals/cases/ is an artifact with a
KNOWN defect seeded in it, plus the check that should catch it.

Two layers, reported separately and never mixed:
  mechanical — the validators and gates (preflight_contract, validate_critique,
    validate_verdict, validate_traceability, check_secrets). Run here, in CI,
    every time. A case is CAUGHT when its check exits non-zero AND, when
    `must_match` is set, the output matches it.
  agent — the reviewer roles (critic, evaluator, security-compliance, …).
    Running them costs real tokens, so they are run inside a Claude session
    (`--live` prints the tasks) and the outcome is recorded with `record`.
    The table shows catch rate per role and per model family; "not yet
    measured" is printed honestly instead of a guessed number.

Escape rate per release (8.2): `--release vX.Y.Z` appends one line to
evals/escape-log.md. The release gate runs `--gate`: a defect that WAS caught
at the baseline and is not caught now is a regression and blocks the tag.
Zero dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
ROOT = EVALS.parent
CASES = EVALS / "cases"
RESULTS = EVALS / "results.json"
BASELINE = EVALS / "baseline.json"
AGENT_LOG = EVALS / "agent-results.jsonl"
TABLE = EVALS / "CATCH-RATES.md"
ESCAPE_LOG = EVALS / "escape-log.md"


def load_cases():
    cases = []
    for cj in sorted(CASES.glob("*/case.json")):
        try:
            c = json.loads(cj.read_text())
            c["_dir"] = cj.parent
            cases.append(c)
        except ValueError as ex:
            print(f"ERROR: {cj} is not valid JSON: {ex}")
    return cases


def run_mechanical(case):
    check = case.get("check") or {}
    argv = [a.replace("{SCRIPTS}", str(ROOT / "scripts")).replace("{CASE}", str(case["_dir"]))
            for a in check.get("argv", [])]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120,
                           cwd=str(case["_dir"]))
    except Exception as ex:  # noqa: BLE001 — a crash means the defect was not caught cleanly
        return {"caught": False, "detail": f"check failed to run: {ex}"}
    out = (r.stdout or "") + (r.stderr or "")
    nonzero = r.returncode != 0
    matched = bool(re.search(check["must_match"], out)) if check.get("must_match") else True
    if case.get("control"):
        # Negative control: a CLEAN artifact. "Caught" here means the check
        # correctly stayed quiet — exit 0. A control that fires is a false
        # positive, which is its own kind of escape.
        return {"caught": r.returncode == 0,
                "detail": f"exit={r.returncode} (control: 0 = no false positive)"}
    caught = nonzero and matched
    detail = f"exit={r.returncode}"
    if check.get("must_match"):
        detail += f", match[{check['must_match']}]={'yes' if matched else 'NO'}"
    return {"caught": caught, "detail": detail}


def agent_records():
    """Latest record wins per (case, role, family)."""
    recs = {}
    if AGENT_LOG.exists():
        for line in AGENT_LOG.read_text().splitlines():
            try:
                r = json.loads(line)
                recs[(r["case"], r["role"], r.get("family", "claude"))] = r
            except (ValueError, KeyError):
                continue
    return recs


def build_results(cases):
    mech, agent = [], []
    recs = agent_records()
    for c in cases:
        if c.get("layer") == "agent":
            entry = {"id": c["id"], "defect": c["defect"],
                     "roles": {}}
            for role in c.get("reviewer_roles", []):
                found = {f: r for (cid, rr, f), r in recs.items()
                         if cid == c["id"] and rr == role}
                entry["roles"][role] = (
                    {f: {"caught": r["caught"], "model": r.get("model", "")}
                     for f, r in found.items()} or None)
            agent.append(entry)
        else:
            res = run_mechanical(c)
            mech.append({"id": c["id"], "defect": c["defect"],
                         "caught": res["caught"], "detail": res["detail"]})
    caught = sum(1 for m in mech if m["caught"])
    results = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mechanical": {"total": len(mech), "caught": caught,
                       "rate": round(caught / len(mech), 3) if mech else None,
                       "cases": mech},
        "agent": {"cases": agent,
                  "recorded": sum(1 for a in agent for v in a["roles"].values() if v)},
    }
    return results


def write_table(results):
    L = ["# Catch rates — seeded-defect eval suite",
         "", f"_Generated {results['generated']} by `evals/run_seeded.py`. "
         "Every row is a KNOWN defect seeded into a sample artifact; "
         "'caught' means the named layer flagged it with no hints._", "",
         "## Mechanical layer (validators and gates — runs in CI)", "",
         "| Case | Seeded defect | Caught |", "|---|---|---|"]
    for m in results["mechanical"]["cases"]:
        L.append(f"| {m['id']} | {m['defect']} | {'yes' if m['caught'] else '**ESCAPED**'} |")
    r = results["mechanical"]
    L.append(f"\n**Mechanical catch rate: {r['caught']}/{r['total']}"
             + (f" ({r['rate']:.0%})**" if r["rate"] is not None else "**"))
    L += ["", "## Agent layer (reviewer roles — run live, recorded per release)", "",
          "| Case | Seeded defect | Role | Result by model family |", "|---|---|---|---|"]
    for a in results["agent"]["cases"]:
        for role, fams in a["roles"].items():
            if fams:
                cell = "; ".join(f"{f}: {'caught' if v['caught'] else '**ESCAPED**'}"
                                 + (f" ({v['model']})" if v.get("model") else "")
                                 for f, v in sorted(fams.items()))
            else:
                cell = "not yet measured"
            L.append(f"| {a['id']} | {a['defect']} | {role} | {cell} |")
    L += ["", "_An ESCAPED row is a to-do, not a secret: the next release either "
          "fixes the check or documents why the defect class is out of scope. "
          "A caught→escaped change against `baseline.json` blocks the tag "
          "(`--gate`)._"]
    TABLE.write_text("\n".join(L) + "\n")


def regressions(results):
    try:
        base = json.loads(BASELINE.read_text())
    except (OSError, ValueError):
        return None  # no baseline yet — nothing can regress
    was = {c["id"]: c["caught"] for c in base.get("mechanical", {}).get("cases", [])}
    return [m["id"] for m in results["mechanical"]["cases"]
            if was.get(m["id"]) is True and not m["caught"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["run", "record"], default="run")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--release", default=None)
    ap.add_argument("--case"); ap.add_argument("--role")
    ap.add_argument("--caught", choices=["yes", "no"])
    ap.add_argument("--model", default=""); ap.add_argument("--family", default="claude")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    if args.cmd == "record":
        if not (args.case and args.role and args.caught):
            print("ERROR: record needs --case, --role and --caught yes|no")
            return 1
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "case": args.case, "role": args.role, "family": args.family,
               "model": args.model, "caught": args.caught == "yes", "notes": args.notes}
        with AGENT_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"OK: recorded {args.case}/{args.role}/{args.family} caught={args.caught}")
        # fall through to rebuild the table with the new record

    cases = load_cases()
    if not cases:
        print("ERROR: no cases under evals/cases/")
        return 1

    if args.live:
        print("Agent-layer tasks — run each INSIDE a Claude session, then `record` the outcome.")
        print("Give the reviewer ONLY the files listed; never name the defect.\n")
        for c in cases:
            if c.get("layer") == "agent":
                files = ", ".join(str(c["_dir"] / f) for f in c.get("files", []))
                for role in c.get("reviewer_roles", []):
                    print(f"- {c['id']} -> invoke the {role} agent on: {files}")
                    print(f"    then: python3 evals/run_seeded.py record --case {c['id']} "
                          f"--role {role} --caught yes|no --model <model> --family <family>")
        return 0

    results = build_results(cases)
    RESULTS.write_text(json.dumps(results, indent=2) + "\n")
    write_table(results)
    r = results["mechanical"]
    print(f"mechanical: {r['caught']}/{r['total']} caught"
          + (f" ({r['rate']:.0%})" if r["rate"] is not None else ""))
    for m in r["cases"]:
        print(f"  {'CAUGHT ' if m['caught'] else 'ESCAPED'} {m['id']}: {m['defect']} [{m['detail']}]")
    print(f"agent-layer records: {results['agent']['recorded']} "
          f"(run with --live inside Claude to measure; record with `record`)")
    print(f"-> {RESULTS}\n-> {TABLE}")

    if args.update_baseline:
        BASELINE.write_text(json.dumps(results, indent=2) + "\n")
        print(f"-> baseline updated: {BASELINE}")

    if args.release:
        escaped = [m["id"] for m in r["cases"] if not m["caught"]]
        line = (f"| {args.release} | {dt.date.today()} | {r['caught']}/{r['total']} | "
                f"{results['agent']['recorded']} | "
                f"{', '.join(escaped) if escaped else 'none'} |")
        if not ESCAPE_LOG.exists():
            ESCAPE_LOG.write_text(
                "# Escape log — per release\n\n"
                "| Release | Date | Mechanical caught | Agent records | Escaped |\n"
                "|---|---|---|---|---|\n")
        with ESCAPE_LOG.open("a") as f:
            f.write(line + "\n")
        print(f"-> escape log: {ESCAPE_LOG}")

    if args.gate:
        reg = regressions(results)
        if reg is None:
            print("GATE: no baseline.json yet — run --update-baseline once; not blocking")
        elif reg:
            print(f"GATE: REGRESSION — previously caught, now escaped: {', '.join(reg)}")
            return 1
        else:
            print("GATE: no regressions vs baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
