#!/usr/bin/env python3
"""Validate an ASDR acceptance contract.

Usage: python3 validate_contract.py .harness/contracts/contract-sprint-01.md

Checks structure only (a machine can't judge criterion quality — the
evaluator does that). Exit 0 = structurally valid. Exit 1 = invalid, with
every problem printed as an "ERROR:" line to feed back to the generator.
"""
import re
import sys
from pathlib import Path

VALID_STATUSES = {"in-negotiation", "revision-requested", "ratified"}

# Every contract must cover all seven categories, each with at least this
# many criteria. The minimums sum to 3+3+3+3+3+2+3 = 20, which meets the
# MIN_TOTAL rule below while guaranteeing coverage instead of filler.
REQUIRED_CATEGORIES = {
    "happy path": 3,
    "failure & error handling": 3,
    "security": 3,
    "accessibility": 3,
    "data persistence": 3,
    "performance": 2,
    "edge cases": 3,
}
REQUIRED_SECTIONS = ["## Test plan", "## Out of scope", "## Done definition"]
MIN_TOTAL = 20


def main() -> int:
    if len(sys.argv) < 2:
        print("ERROR: usage: validate_contract.py <path-to-contract.md>")
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1
    text = path.read_text()
    # Instruction comments in the template are not content — strip them so
    # they can't trip the placeholder or section checks.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    errors = []

    m = re.search(r"^Status:\s*(\S+)", text, re.MULTILINE)
    if not m:
        errors.append("ERROR: missing 'Status:' line")
    elif m.group(1) not in VALID_STATUSES:
        errors.append(
            f"ERROR: Status '{m.group(1)}' invalid; must be one of {sorted(VALID_STATUSES)}"
        )

    if not re.search(r"^## Sprint goal", text, re.MULTILINE):
        errors.append("ERROR: missing '## Sprint goal' section")
    for section in REQUIRED_SECTIONS:
        if section.lower() not in text.lower():
            errors.append(f"ERROR: missing '{section}' section")

    total = 0
    for category, minimum in REQUIRED_CATEGORIES.items():
        pattern = re.compile(r"^###\s*" + re.escape(category) + r"\s*$",
                             re.IGNORECASE | re.MULTILINE)
        m = pattern.search(text)
        if not m:
            errors.append(f"ERROR: missing '### {category.title()}' category section")
            continue
        rest = text[m.end():]
        nxt = re.search(r"^##", rest, re.MULTILINE)
        block = rest[: nxt.start()] if nxt else rest
        count = len(re.findall(r"^\s*\d+\.\s+\S", block, re.MULTILINE))
        total += count
        if count < minimum:
            errors.append(
                f"ERROR: category '{category}' has {count} criteria; needs at least {minimum}"
            )

    if total < MIN_TOTAL:
        errors.append(f"ERROR: {total} total criteria; needs at least {MIN_TOTAL}")

    placeholders = len(re.findall(r"<single testable assertion>|<[^>]*fill[^>]*>", text, re.IGNORECASE))
    if placeholders:
        errors.append(f"ERROR: {placeholders} unfilled template placeholders remain")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: contract structurally valid with {total} criteria")
    return 0


if __name__ == "__main__":
    sys.exit(main())
