#!/usr/bin/env python3
"""Validate an ASDR critique document.

Usage: python3 validate_critique.py docs/critique-discovery.md

The critic's "minimum 8 findings" rule and its self-reported counts used to
live only in prose — nothing checked them. This validator enforces:

  * every finding block (### F-NN) has Severity, Where, Problem, Required fix
  * the summary block's findings_total matches the actual number of findings
  * critical + high + medium + low equals findings_total
  * findings_total >= 8, UNLESS the summary sets shortfall_justified: true
    (the escape hatch for a genuinely small doc set — the critic must then
    have listed what it checked, per its instructions)

Exit 0 = valid; exit 1 = every problem printed as an "ERROR:" line.
Zero dependencies.
"""
import re
import sys
from pathlib import Path

MIN_FINDINGS = 8
REQUIRED_PARTS = ["severity", "where", "problem", "required fix"]


def main() -> int:
    if len(sys.argv) < 2:
        print("ERROR: usage: validate_critique.py <path-to-critique.md>")
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1
    text = path.read_text()
    # Strip template instruction comments so they can't be miscounted.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    errors = []

    # Split into finding blocks on '### F-NN'.
    finding_heads = list(re.finditer(r"^###\s+F-\d+\b.*$", text, re.MULTILINE))
    n_findings = len(finding_heads)
    if n_findings == 0:
        errors.append("ERROR: no findings found; expected '### F-01 ...' blocks")

    for idx, head in enumerate(finding_heads):
        start = head.end()
        end = finding_heads[idx + 1].start() if idx + 1 < len(finding_heads) else len(text)
        # Stop the block at the summary section if it comes first.
        summary_at = re.search(r"^##\s+Summary block", text[start:end], re.MULTILINE)
        block = text[start:start + summary_at.start()] if summary_at else text[start:end]
        low = block.lower()
        title = head.group(0).strip()
        for part in REQUIRED_PARTS:
            if part not in low:
                errors.append(f"ERROR: {title} is missing its '{part.title()}' line")

    # Parse the summary block scalars.
    block = None
    m = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        block = m[-1]
    summary = {}
    if block:
        for line in block.splitlines():
            mm = re.match(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$", line, re.IGNORECASE)
            if mm:
                summary[mm.group(1).lower()] = mm.group(2).strip()
    else:
        errors.append("ERROR: missing '## Summary block' fenced yaml with findings_total")

    def as_int(key):
        try:
            return int(summary.get(key, ""))
        except ValueError:
            return None

    total = as_int("findings_total")
    if block and total is None:
        errors.append("ERROR: summary block 'findings_total' is missing or not a number")
    if total is not None and total != n_findings:
        errors.append(
            f"ERROR: findings_total says {total} but {n_findings} F-blocks exist")

    sev = {k: as_int(k) for k in ("critical", "high", "medium", "low")}
    if block and all(v is not None for v in sev.values()) and total is not None:
        s = sum(sev.values())
        if s != total:
            errors.append(
                f"ERROR: severity counts sum to {s} but findings_total is {total}")

    justified = summary.get("shortfall_justified", "false").lower() == "true"
    effective = total if total is not None else n_findings
    if effective < MIN_FINDINGS and not justified:
        errors.append(
            f"ERROR: only {effective} findings; need at least {MIN_FINDINGS}. If the "
            "doc set is genuinely small, set 'shortfall_justified: true' in the summary "
            "block and list what you checked.")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: critique valid with {n_findings} findings"
          + (" (shortfall justified)" if justified and effective < MIN_FINDINGS else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
