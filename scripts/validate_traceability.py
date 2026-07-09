#!/usr/bin/env python3
"""Validate the ASDR product-integrity traceability matrix.

Usage:
  python3 validate_traceability.py [.harness/traceability.json]
      [--sprints sprints.json] [--requirements docs/02-requirements.md] [--gate]

The matrix maps outcome -> requirement -> use case -> sprint -> criteria ->
tests -> status. This script checks the matrix is internally consistent and,
when given the requirements doc, mechanically detects DRIFT (a requirement's
text changed after a sprint built to it). It does NOT judge mapping quality —
the product-integrity-qa agent does that; this enforces existence and
consistency, the same split as the other validators.

Exit 0 = consistent; exit 1 = every problem printed as an "ERROR:" line so the
orchestrator can feed it back. `--gate` turns "uncovered" into an error (only a
blocker at the final gate; expected mid-build). Zero dependencies.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

VALID_STATUS = {"covered", "uncovered", "drifted", "broken", "deferred"}


def load_json(path, errors):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        errors.append(f"ERROR: {path} does not exist")
    except json.JSONDecodeError as e:
        errors.append(f"ERROR: {path} is not valid JSON: {e}")
    return None


def req_text(requirements_md, req_id):
    """Extract the text of a requirement id from the requirements doc.

    Matches a line whose first token is the id (e.g. 'FR-01: ...' or
    '- FR-01 — ...'); returns the remainder of that line, stripped. Used only
    to hash for drift detection, so exact extraction isn't required — any
    wording change flips the hash.
    """
    pat = re.compile(r"^\s*[-*]?\s*" + re.escape(req_id) + r"\b[:.\)—-]*\s*(.+)$",
                     re.MULTILINE)
    m = pat.search(requirements_md)
    return m.group(1).strip() if m else None


def sha1(text):
    return "sha1:" + hashlib.sha1(text.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("matrix", nargs="?", default=".harness/traceability.json")
    ap.add_argument("--sprints", default="sprints.json")
    ap.add_argument("--requirements", default=None)
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()

    errors = []
    data = load_json(args.matrix, errors)
    if data is None:
        print("\n".join(errors))
        return 1

    requirements = data.get("requirements")
    outcomes = data.get("outcomes", [])
    use_cases = data.get("use_cases", [])
    if not isinstance(requirements, list):
        errors.append("ERROR: 'requirements' must be a list")
        requirements = []

    outcome_ids = {o.get("outcome_id") for o in outcomes if isinstance(o, dict)}
    uc_ids = {u.get("uc_id") for u in use_cases if isinstance(u, dict)}

    # sprint ids that actually exist in the plan
    sprint_ids = set()
    if Path(args.sprints).exists():
        sprints = load_json(args.sprints, errors) or []
        sprint_ids = {s.get("id") for s in sprints if isinstance(s, dict)}

    requirements_md = None
    if args.requirements and Path(args.requirements).exists():
        requirements_md = Path(args.requirements).read_text()

    seen = set()
    referenced_sprints = set()
    for i, r in enumerate(requirements):
        label = r.get("req_id") or f"requirement[{i}]"
        if not r.get("req_id"):
            errors.append(f"ERROR: {label}: missing 'req_id'")
        elif r["req_id"] in seen:
            errors.append(f"ERROR: duplicate req_id {r['req_id']}")
        seen.add(r.get("req_id"))

        status = r.get("status")
        if status not in VALID_STATUS:
            errors.append(f"ERROR: {label}: status '{status}' invalid; "
                          f"must be one of {sorted(VALID_STATUS)}")

        sprints_of = r.get("sprints") or []
        if not isinstance(sprints_of, list):
            errors.append(f"ERROR: {label}: 'sprints' must be a list")
            sprints_of = []
        referenced_sprints.update(sprints_of)

        # referential integrity
        so = r.get("source_outcome")
        if so and outcome_ids and so not in outcome_ids:
            errors.append(f"ERROR: {label}: source_outcome '{so}' not in outcomes")
        for uc in r.get("use_cases", []) or []:
            if uc_ids and uc not in uc_ids:
                errors.append(f"ERROR: {label}: use_case '{uc}' not in use_cases")

        deferred = bool(r.get("deferred")) or status == "deferred"

        # uncovered — only an error at the gate
        if not sprints_of and not deferred:
            msg = f"{label}: no sprint covers it (uncovered)"
            (errors.append("ERROR: " + msg) if args.gate
             else print("WARN: " + msg))

        # broken is always a blocker
        if status == "broken":
            errors.append(f"ERROR: {label}: marked 'broken' — a passed feature "
                          "now fails regression; fix before proceeding")

        # covered rows must carry evidence
        if status == "covered" and not (r.get("tests") or r.get("criteria")):
            errors.append(f"ERROR: {label}: status 'covered' but no tests/criteria listed")

        # drift detection
        if requirements_md is not None and r.get("text_hash") and sprints_of:
            current = req_text(requirements_md, r["req_id"])
            if current is not None and sha1(current) != r["text_hash"]:
                errors.append(f"ERROR: {label}: requirement text changed after a "
                              "sprint built to it (DRIFT); re-align docs + code")

    # orphan sprints — built something no requirement asked for
    orphans = sorted(sid for sid in sprint_ids if sid and sid not in referenced_sprints)
    if orphans:
        errors.append(f"ERROR: orphan sprints not tied to any requirement: {orphans}")

    # uncovered use cases (gate only)
    if args.gate:
        for u in use_cases:
            if isinstance(u, dict) and not (u.get("requirements") or []):
                errors.append(f"ERROR: use case {u.get('uc_id')} maps to no requirement")

    if errors:
        print("\n".join(errors))
        return 1
    print(f"OK: traceability consistent — {len(requirements)} requirements, "
          f"{len(outcomes)} outcomes, {len(use_cases)} use cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
