#!/usr/bin/env python3
"""Validate an ASDR machine-readable verdict block.

Usage:
  python3 validate_verdict.py <file> [--type decision|eval|risk]

The orchestrator parses a fenced ```yaml block at the end of three document
kinds — the judge's decision, the evaluator's eval report, and the
risk-manager's risk review. A malformed block used to stall the loop with no
diagnostic. This checks the block has the required fields, that the headline
field holds one allowed value (not the template's unfilled "a | b | c"), and
that no <placeholder> survived. Exit 0 = valid; exit 1 = every problem printed
as an "ERROR:" line to feed back to the responsible agent.

Zero dependencies (no PyYAML) so it runs anywhere the harness runs.
"""
import re
import sys
from pathlib import Path

SPECS = {
    "decision": {
        "field": "verdict",
        "allowed": {"go", "no-go"},
        "required": ["verdict", "required_changes", "reason"],
    },
    "eval": {
        "field": "verdict",
        "allowed": {"pass", "fail", "teardown"},
        "required": ["verdict", "sprint", "attempt", "failed_criteria",
                     "required_next_action"],
    },
    "risk": {
        "field": "classification",
        "allowed": {"production-ready", "mvp-ready", "prototype", "not-ready"},
        "required": ["classification", "blockers", "warnings", "reason"],
    },
    "qa": {
        "field": "verdict",
        "allowed": {"pass", "revise"},
        "required": ["stage", "verdict", "failed_checks"],
    },
}


def extract_block(text):
    """Return the contents of the last fenced code block in the document."""
    blocks = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    return blocks[-1] if blocks else None


def parse_scalars(block):
    """Parse simple 'key: value' lines. Values are returned as raw strings."""
    out = {}
    for line in block.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def infer_type(fields):
    if "classification" in fields:
        return "risk"
    if "failed_checks" in fields or ("stage" in fields and "attempt" not in fields
                                     and "required_changes" not in fields):
        return "qa"
    if "attempt" in fields or "failed_criteria" in fields:
        return "eval"
    if "verdict" in fields:
        return "decision"
    return None


def main() -> int:
    args = [a for a in sys.argv[1:]]
    kind = None
    if "--type" in args:
        i = args.index("--type")
        kind = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if not args:
        print("ERROR: usage: validate_verdict.py <file> [--type decision|eval|risk]")
        return 1
    path = Path(args[0])
    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1

    text = path.read_text()
    block = extract_block(text)
    if block is None:
        print("ERROR: no fenced ```yaml verdict block found at the end of the document")
        return 1
    fields = parse_scalars(block)

    if kind is None:
        kind = infer_type(fields)
    if kind not in SPECS:
        print(f"ERROR: cannot determine verdict type; pass --type "
              f"{'|'.join(SPECS)} (found keys: {sorted(fields)})")
        return 1

    spec = SPECS[kind]
    errors = []

    for req in spec["required"]:
        if req not in fields:
            errors.append(f"ERROR: {kind} block missing required field '{req}'")

    headline = spec["field"]
    if headline in fields:
        val = fields[headline].strip().strip('"').strip("'")
        if "|" in val or "<" in val:
            errors.append(
                f"ERROR: '{headline}' still holds the template placeholder "
                f"'{val}'; set it to exactly one of {sorted(spec['allowed'])}")
        elif val not in spec["allowed"]:
            errors.append(
                f"ERROR: '{headline}' is '{val}'; must be one of "
                f"{sorted(spec['allowed'])}")

    # Any surviving <angle-bracket> placeholder anywhere in the block is unfilled.
    for key, val in fields.items():
        if "<" in val and key != headline:
            errors.append(f"ERROR: field '{key}' still contains a <placeholder>: '{val}'")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: {kind} verdict block valid ({headline}={fields[headline]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
