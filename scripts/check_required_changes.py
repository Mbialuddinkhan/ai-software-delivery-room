#!/usr/bin/env python3
"""Second-round check of a decision's required changes — a script, not a judge run.

Usage:
  python3 check_required_changes.py <decision.md> [--gate "<command>"]
                                    [--write --spot-checked RC-01,RC-05]

v3.8 (efficiency). In the first full /assess run the judge's second round
(≈210k tokens, ≈9 min) mostly confirmed that each required change had been
applied to the file it named. This does the mechanical part:

  1. reads every required change (`- **RC-01** · \\`path\\` …` or `- F-03 · …`)
     and the files it names;
  2. marks each "changed" when a named file was modified after the decision
     was written (or after --since), "not changed" when none was, "no file
     named" otherwise;
  3. runs the phase's gate command (--gate), if given.

Without --write it only reports (exit 1 while anything is not changed or the
gate fails). The orchestrator then reads the changed files for a sample of
the changes — at least every change from a Critical or High finding — and
re-runs with --write --spot-checked <ids>: that appends "## Round 2 (scripted
check)" and a new verdict block to the decision (go when every change is
"changed" and the gate passed, otherwise no-go with the open ones).

Invoke the judge instead when a spot check finds a change applied wrongly or
an owner disputes one. Last line: ROUND2: {json}.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


def required_changes(text: str) -> list:
    sec = re.split(r"^##\s+Required changes before proceeding\s*$", text, flags=re.MULTILINE)
    if len(sec) < 2:
        return []
    body = re.split(r"^##\s+", sec[1], maxsplit=1, flags=re.MULTILINE)[0]
    out = []
    for m in re.finditer(r"^-\s+\**((?:RC|F)-\d+)\**(.*)$", body, flags=re.MULTILINE):
        line = m.group(2)
        paths = [p for p in re.findall(r"`([^`\s]+\.[A-Za-z0-9]+)`", line)]
        out.append({"id": m.group(1), "files": paths, "text": line.strip(" ·:—-")[:160]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Scripted second-round check of required changes.")
    ap.add_argument("decision")
    ap.add_argument("--gate", default=None, help="command that must pass (e.g. the phase's validator)")
    ap.add_argument("--since", default=None,
                    help="ISO time the round started (default: when the decision file was last written; "
                         "pass it if anything touched the decision since)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--spot-checked", default="", help="comma list of change ids the orchestrator read")
    a = ap.parse_args()

    dp = Path(a.decision)
    try:
        text = dp.read_text()
    except OSError as ex:
        print(f"ERROR: cannot read {dp}: {ex}")
        return 1
    since = dp.stat().st_mtime
    if a.since:
        try:
            t = dt.datetime.fromisoformat(a.since.replace("Z", "+00:00"))
            since = (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()
        except ValueError:
            print(f"ERROR: --since {a.since!r} is not an ISO date-time")
            return 1
    rcs = required_changes(text)
    if not rcs:
        print("No required changes listed — nothing to check.")
        print("ROUND2: " + json.dumps({"changes": 0, "open": [], "gate": None}))
        return 0
    rows, open_ = [], []
    for rc in rcs:
        files = [Path(p) for p in rc["files"]]
        existing = [p for p in files if p.exists()]
        if not files:
            status = "no file named"
        elif any(p.stat().st_mtime > since for p in existing):
            status = "changed"
        else:
            status = "not changed"
            open_.append(rc["id"])
        rows.append((rc["id"], ", ".join(rc["files"]) or "—", status))
    gate_ok = None
    if a.gate:
        r = subprocess.run(shlex.split(a.gate), capture_output=True, text=True)
        gate_ok = r.returncode == 0
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        print(f"GATE: {'pass' if gate_ok else 'FAIL'} — {tail[0][:200]}")
    for rid, files, status in rows:
        print(f"{rid}: {status} ({files})")
    spot = [x.strip() for x in a.spot_checked.split(",") if x.strip()]
    ok = not open_ and gate_ok is not False
    if a.write:
        if not spot:
            print("ERROR: --write needs --spot-checked: read a sample of the changed files first "
                  "(every change that came from a Critical or High finding)")
            return 1
        when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        L = ["", "## Round 2 (scripted check)", "",
             f"Checked {when} by check_required_changes.py; the orchestrator read the changes {', '.join(spot)}."
             + (f" Gate: {'passed' if gate_ok else 'FAILED'}." if gate_ok is not None else ""), "",
             "| Change | File(s) | Status |", "|---|---|---|"]
        L += [f"| {rid} | {files} | {status} |" for rid, files, status in rows]
        L += ["", "```yaml", f"verdict: {'go' if ok else 'no-go'}", f"required_changes: [{', '.join(open_)}]",
              "reason: " + ("Every required change touched its file and the spot checks held (scripted round 2)."
                            if ok else "Required changes still open or the gate failed (scripted round 2)."), "```", ""]
        with dp.open("a") as f:
            f.write("\n".join(L))
        print(f"Appended round 2 to {dp}: {'go' if ok else 'no-go'}")
    print("ROUND2: " + json.dumps({"changes": len(rcs), "open": open_, "gate": gate_ok, "ok": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
