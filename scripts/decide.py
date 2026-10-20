#!/usr/bin/env python3
"""Write a phase decision without a judge run when the critique has nothing serious.

Usage:
  python3 decide.py <critique.md> --out docs/decision-<phase>.md --phase <phase>
                    [--rigor lite|standard|paranoid]

v3.8 (efficiency): the judge exists to settle disagreements and serious
findings. When the critic reports no Critical and no High finding there is
nothing to settle, so a judge run (≈200k tokens, ≈11 min) only re-reads the
documents to accept everything. This script does that mechanically:

  - every Medium finding becomes a required change (its "Required fix"),
    applied by the owner before the next phase — no second review;
  - every Low finding is recorded as a remaining assumption;
  - verdict: go.

It refuses — prints `JUDGE: required` and exits 2, writing nothing — when the
critique has any Critical or High finding (by its summary block or by its
findings), when its summary block is missing or inconsistent, or under
`--rigor paranoid`. Then the orchestrator invokes the judge as before.

The output follows templates/decision.md, so validate_verdict.py --type
decision accepts it. Last line: DECISION: {json}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEVS = ("critical", "high", "medium", "low")


def summary(text: str) -> dict | None:
    blocks = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if not blocks:
        return None
    out = {}
    for k in ("findings_total",) + SEVS:
        m = re.search(rf"^\s*{k}\s*:\s*(\d+)\s*$", blocks[-1], re.MULTILINE)
        if not m:
            return None
        out[k] = int(m.group(1))
    return out


def findings(text: str) -> list:
    out = []
    parts = re.split(r"^###\s+(F-\d+)\s*[·:\-—]?\s*(.*)$", text, flags=re.MULTILINE)
    for i in range(1, len(parts) - 2, 3):
        fid, title, body = parts[i], parts[i + 1].strip(), parts[i + 2]
        body = body.split("\n## ")[0]
        sev = re.search(r"Severity\W*?:?\**\s*\**\s*(Critical|High|Medium|Low)\b", body, re.IGNORECASE)
        where = re.search(r"Where\W*?:\**\s*(.+)", body)
        fix = re.search(r"Required fix\W*?:\**\s*(.+?)(?=\n- \w[\w ]*:|\Z)", body, re.DOTALL)
        out.append({"id": fid, "title": title, "severity": sev.group(1).lower() if sev else None,
                    "where": where.group(1).strip() if where else "",
                    "fix": re.sub(r"\s+", " ", fix.group(1)).strip() if fix else ""})
    return out


def cell(s: str, n: int = 240) -> str:
    s = s.replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description="Scripted decision when a critique has no Critical/High finding.")
    ap.add_argument("critique")
    ap.add_argument("--out", required=True)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--rigor", default="standard", choices=["lite", "standard", "paranoid"])
    a = ap.parse_args()

    try:
        text = Path(a.critique).read_text()
    except OSError as ex:
        print(f"ERROR: cannot read {a.critique}: {ex}")
        return 1
    sm, fs = summary(text), findings(text)
    serious = [f["id"] for f in fs if f["severity"] in ("critical", "high")]
    unknown = [f["id"] for f in fs if f["severity"] is None]
    why = None
    if a.rigor == "paranoid":
        why = "rigor is paranoid: the judge rules on every phase"
    elif sm is None:
        why = "the critique has no valid summary block (run validate_critique.py)"
    elif sm["critical"] + sm["high"] > 0 or serious:
        why = f"{sm['critical']} critical and {sm['high']} high finding(s)" + (f": {', '.join(serious)}" if serious else "")
    elif unknown:
        why = f"finding(s) without a readable severity: {', '.join(unknown)}"
    elif sum(sm[k] for k in SEVS) != sm["findings_total"] or len(fs) != sm["findings_total"]:
        why = f"the summary block says {sm['findings_total']} findings but {len(fs)} are written"
    if why:
        print(f"JUDGE: required — {why}. Invoke the judge as usual.")
        print("DECISION: " + json.dumps({"scripted": False, "reason": why}))
        return 2

    med = [f for f in fs if f["severity"] == "medium"]
    low = [f for f in fs if f["severity"] == "low"]
    L = [f"# Decision · {a.phase}", "",
         "<!-- Written by decide.py (ASDR 3.8): the critique has no Critical or High finding, so no judge run was "
         "needed. Medium findings become required changes for their owners, applied before the next phase without "
         "another review; Low findings are carried as assumptions. Any disagreement → invoke the judge instead. -->", "",
         "## Rulings on critique findings", "", "| Finding | Ruling | Required change / rejection reason |", "|---|---|---|"]
    for f in fs:
        if f["severity"] == "medium":
            L.append(f"| {f['id']} ({f['severity'].capitalize()}) | accepted | {cell(f['fix'] or f['title'])} |")
        else:
            L.append(f"| {f['id']} ({f['severity'].capitalize()}) | accepted as an assumption | "
                     f"{cell('Recorded below; fix when the owner next touches ' + (f['where'].split(' ')[0] if f['where'] else 'the document'))} |")
    L += ["", "## Approved decisions", "",
          f"- The {a.phase} documents are approved: the critique found nothing Critical or High.", "",
          "## Required changes before proceeding", ""]
    L += [f"- {f['id']} · owner of {cell(f['where'].split(' ')[0] if f['where'] else 'the document', 80)}: {cell(f['fix'] or f['title'], 400)}"
          for f in med] or ["- (none)"]
    L += ["", "## Remaining assumptions", ""]
    L += [f"- {f['id']}: {cell(f['title'], 200)}" for f in low] or ["- (none)"]
    ids = ", ".join(f["id"] for f in med)
    L += ["", "## Verdict block", "", "```yaml", "verdict: go", f"required_changes: [{ids}]",
          f"reason: No Critical or High finding; {len(med)} medium change(s) go to their owners before the next phase "
          f"(scripted decision, no judge run).", "```", ""]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))
    print(f"OK: {out} — go, {len(med)} required change(s), {len(low)} assumption(s); judge run skipped")
    print("DECISION: " + json.dumps({"scripted": True, "verdict": "go", "required_changes": [f["id"] for f in med],
                                     "assumptions": [f["id"] for f in low]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
