#!/usr/bin/env python3
"""Pre-flight satisfiability linter for an ASDR contract.

Usage:
  python3 preflight_contract.py .harness/contracts/contract-sprint-07.md
      [--facts .harness/facts.json] [--root .] [--max-per-file 7] [--max-new-files 12]

Runs BEFORE the evaluator sees a draft. `validate_contract.py` checks the
contract's *shape*; this checks whether a correct implementation could actually
satisfy it.

Authoring rule (b): no criterion may require an outcome the code's own
invariants make unreachable. Field evidence says first drafts break it
routinely — seven violations in one draft, three by a reviewer against itself —
and each one costs a negotiation round, which is one of the largest context
sinks in the system.

Every check below is a real violation class observed in production:

  P01 unmeasurable    a numeric claim with no facts.json key to grade it
  P02 unresolved-ref  a cited file:line that does not exist
  P03 zero-delta      "must equal zero" over a file the same criterion edits
  P04 self-report     asks an agent to transcribe command output
  P05 regex-conflict  forbids a pattern another criterion requires
  P06 cost-floor      a `>=` floor on a cost metric a better build would fail
  P07 clock-conflict  absolute time assertion against a clamped fixture clock
  P08 file-overload   one integration file named by > N criteria
  P09 new-file-budget more new files than the sprint budget
  P10 no-derivation   a numeric bound with no derivation and no fact key

Exit 0 = ready for ratification. Exit 1 = every problem printed as an "ERROR:"
line for the generator. Advisories print as "WARN:" and do not fail.
Zero dependencies.
"""
import argparse
import json
import re
import sys
from pathlib import Path

FACT_REF = re.compile(r"facts:([A-Za-z0-9_./\[\]-]+)")
NUMERIC = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(ms|s|kb|mb|lines?|rows?|reads?|"
                     r"writes|queries|bytes|chars|files?|calls?)?\b", re.I)
# Every phrasing of a bound the field data used. Missing "under"/"within" let
# the contract template's own GOOD example ("under 300ms") through unmeasured.
COMPARATOR = re.compile(r"(<=|>=|<|>|≤|≥|at most|no more than|at least|exactly|"
                        r"must not exceed|fewer than|greater than|less than|"
                        r"more than|under|within|below|up to|no later than|"
                        r"not exceed|maximum of|minimum of|no fewer than|"
                        r"over(?=\s*\d)|above(?=\s*\d))", re.I)
# Numbers that are identifiers, not measurements: HTTP status codes, ports,
# error codes, version strings. They are never "unmeasurable"; a criterion
# saying "returns exactly HTTP 404" needs no facts.json key.
IDENT_NUM = re.compile(r"\b(?:HTTP|status(?:\s+code)?|port|error(?:\s+code)?|code|"
                       r"v)\s*\d+(?:\.\d+)*\b", re.I)
URL = re.compile(r"\bhttps?://\S+", re.I)
CMD_OUTPUT = re.compile(r"(git\s+diff|--stat|wc\s+-l|npm\s+(?:run\s+)?test|pytest|"
                        r"docker\s+build|coverage\s+report|\bls\b)", re.I)
SELF_REPORT = re.compile(r"(generator|builder|implementer)\s+(must\s+)?"
                         r"(report|transcribe|record|state|paste|cite)", re.I)
ZERO_CLAIM = re.compile(r"(zero|no|0)\s+(removed|deleted|new|added|changed)\s+"
                        r"[`'\"]?([\w()]+)", re.I)
FILE_REF = re.compile(r"([\w./-]+\.(?:ts|tsx|js|jsx|py|go|rb|java|rs|sql|md|json))"
                      r"(?::(\d+))?")
# Source files only — the new-file budget (P09) measures fixture-isolation
# risk, which docs and JSON config do not carry.
CODE_FILE_REF = re.compile(r"([\w./-]+\.(?:ts|tsx|js|jsx|py|go|rb|java|rs|sql))")
# A regex literal /.../ must not be a path segment: `src/4/legacy.ts` is not
# the regex /4/. The opening slash may not follow a path character.
REGEX_LIT = re.compile(r"(?<![\w./])/((?:[^/\\\n]|\\.)+)/[gimsuy]*(?![\w/])")
# Word-bounded: without \b, "already" matched "read" and "called" matched
# "call", turning ordinary sentences into P06 errors.
COST_WORDS = re.compile(r"\b(database|db|network|http|api|disk|query|queries|read|"
                        r"reads|write|writes|call|calls|request|requests)\b", re.I)
CLOCK_WORDS = re.compile(r"\b(utc|midnight|timezone|tz|next day|epoch|Date\.now|"
                         r"clamped|frozen clock)\b", re.I)


def strip_fact_refs(body):
    """Remove `facts:<key>` tokens and URLs before scanning for file paths.

    A dotted fact key like `facts:diff.src/tools.ts.net_nonblank` otherwise
    looks like a file path to FILE_REF and produces a bogus 'does not exist'
    warning, and `https://api.example.com/v1/users.json` would count as a new
    file. Fact keys are validated separately against facts.json.
    """
    return URL.sub(" ", FACT_REF.sub(" ", body))


def measurable_numbers(body):
    """Numbers in a criterion that are measurements, not identifiers."""
    return [n for n, _u in NUMERIC.findall(IDENT_NUM.sub(" ", body))]


def split_criteria(text):
    """Return [(id, text)] for numbered criteria under ### category headings."""
    out = []
    cat = None
    for line in text.splitlines():
        h = re.match(r"^###\s+(.*?)\s*$", line)
        if h:
            cat = h.group(1)
            continue
        m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if m and cat:
            out.append((f"{cat} #{m.group(1)}", m.group(2)))
        elif out and line.startswith(("   ", "\t")) and line.strip():
            cid, prev = out[-1]
            out[-1] = (cid, prev + " " + line.strip())
    return out


def fact_keys(facts):
    """Flatten facts.json into dotted keys agents may cite."""
    keys = set()

    def walk(node, prefix=""):
        if isinstance(node, dict):
            for k, v in node.items():
                key = f"{prefix}{k}"
                keys.add(key)
                walk(v, key + ".")
        elif isinstance(node, list):
            keys.add(prefix.rstrip("."))
    walk(facts or {})
    return keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("contract")
    ap.add_argument("--facts", default=".harness/facts.json")
    ap.add_argument("--root", default=".")
    ap.add_argument("--max-per-file", type=int, default=7)
    ap.add_argument("--max-new-files", type=int, default=12)
    args = ap.parse_args()

    path = Path(args.contract)
    if not path.exists():
        print(f"ERROR: {path} does not exist")
        return 1
    text = re.sub(r"<!--.*?-->", "", path.read_text(), flags=re.DOTALL)
    root = Path(args.root)

    facts = None
    if Path(args.facts).exists():
        try:
            facts = json.loads(Path(args.facts).read_text())
        except ValueError:
            print(f"WARN: {args.facts} is not valid JSON; measurability unchecked")
    known = fact_keys(facts)

    criteria = split_criteria(text)
    errors, warns = [], []

    if not criteria:
        print("ERROR: no numbered criteria found under '###' categories")
        return 1

    # Cross-criterion indexes for conflict detection.
    required_literals = []          # (cid, literal) values a criterion REQUIRES
    edited_files = {}               # file -> [cid] that mandate an edit
    file_mentions = {}              # file -> [cid]

    for cid, body in criteria:
        scan = strip_fact_refs(body)
        for f in {f for f, _l in FILE_REF.findall(scan)}:
            file_mentions.setdefault(f, []).append(cid)
            if re.search(r"\b(add|edit|modify|update|change|insert|append|"
                         r"refactor|move|extract)\b", body, re.I):
                edited_files.setdefault(f, []).append(cid)
        if re.search(r"\b(contain|include|equal|equals|set to|value of|payload)\b",
                     body, re.I):
            for num, _u in NUMERIC.findall(body):
                required_literals.append((cid, num))

    for cid, body in criteria:
        low = body.lower()
        cited = set(FACT_REF.findall(body))
        scan = strip_fact_refs(body)
        files_here = {f: l for f, l in FILE_REF.findall(scan)}

        # P04 self-report of command output
        if SELF_REPORT.search(body) and CMD_OUTPUT.search(body):
            errors.append(f"ERROR: {cid}: P04 self-report — asks an agent to "
                          "transcribe command output; grade it from facts.json instead")

        # P01/P10 numeric claim with no fact key and no derivation
        has_cmp = bool(COMPARATOR.search(body))
        nums = measurable_numbers(body)
        if has_cmp and nums and not cited:
            if re.search(r"derivation|derived|because|since|=\s*\d+\s*[-+]", low):
                warns.append(f"WARN: {cid}: P10 numeric bound has a derivation but "
                             "no facts.json key; prefer 'facts:<key>' so it is measured")
            else:
                errors.append(f"ERROR: {cid}: P01 numeric bound {nums[:3]} with no "
                              "facts.json citation and no derivation — unmeasurable")

        # P01b cited key must exist
        for key in cited:
            if known and key not in known:
                base = key.split("[")[0]
                if base not in known:
                    errors.append(f"ERROR: {cid}: P01 cites unknown fact key "
                                  f"'facts:{key}' — not present in {args.facts}")

        # P02 unresolved file:line
        for f, line in files_here.items():
            fp = root / f
            if not fp.exists():
                warns.append(f"WARN: {cid}: P02 references '{f}' which does not exist yet")
            elif line:
                try:
                    if int(line) > len(fp.read_text(errors="ignore").splitlines()):
                        errors.append(f"ERROR: {cid}: P02 cites {f}:{line} beyond EOF")
                except OSError:
                    pass

        # P03 zero-delta over a file this criterion also edits
        zm = ZERO_CLAIM.search(body)
        if zm:
            for f in files_here:
                if cid in edited_files.get(f, []):
                    errors.append(f"ERROR: {cid}: P03 asserts '{zm.group(0)}' over "
                                  f"'{f}' while the same criterion mandates an edit "
                                  "to it — mathematically forced")
                    break

        # P05 regex forbids a literal another criterion requires
        if re.search(r"\b(must not|forbid|no\s+match|reject|absent)\b", low):
            for rx in REGEX_LIT.findall(body):
                try:
                    cre = re.compile(rx)
                except re.error:
                    continue
                for ocid, lit in required_literals:
                    if ocid != cid and cre.search(lit):
                        errors.append(f"ERROR: {cid}: P05 forbids /{rx}/ but {ocid} "
                                      f"requires a payload containing '{lit}'")
                        break

        # P06 floor on a cost metric — a better build would fail it
        if re.search(r"(at least|no fewer than|minimum of|>=|≥)\s*\d+", low) \
                and COST_WORDS.search(IDENT_NUM.sub(" ", body)):
            errors.append(f"ERROR: {cid}: P06 sets a FLOOR on a cost metric "
                          "(reads/queries/calls); a strictly better implementation "
                          "would fail it — use a ceiling")

        # P07 absolute clock assertion against a fixture clock
        if CLOCK_WORDS.search(body) and re.search(r"\b(next|following)\b.*\b"
                                                  r"(midnight|day|utc)\b", low):
            warns.append(f"WARN: {cid}: P07 asserts an absolute clock boundary — "
                         "verify the fixture clock is not clamped/frozen")

    # P08 file overload
    for f, cids in file_mentions.items():
        if ("int" in f.lower() or "spec" in f.lower() or "test" in f.lower()) \
                and len(cids) > args.max_per_file:
            errors.append(f"ERROR: P08 '{f}' is named by {len(cids)} criteria "
                          f"(max {args.max_per_file}) — one fixture slip fails all "
                          "of them and hides whether it is a product defect")

    # P09 new-file budget — source files only; docs and config carry no
    # fixture-isolation risk, and a URL is not a file.
    new_files = {f for f in CODE_FILE_REF.findall(strip_fact_refs(text))
                 if not (root / f).exists()}
    if len(new_files) > args.max_new_files:
        errors.append(f"ERROR: P09 contract introduces {len(new_files)} new files "
                      f"(budget {args.max_new_files}) — file count drives "
                      "fixture-isolation risk")

    for w in warns:
        print(w)
    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} blocking issue(s) across {len(criteria)} criteria. "
              "Fix before ratification.")
        return 1
    print(f"OK: {len(criteria)} criteria pass pre-flight "
          f"({len(warns)} advisory warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
