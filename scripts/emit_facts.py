#!/usr/bin/env python3
"""Emit .harness/facts.json — the single source of MEASURED truth.

Usage:
  python3 emit_facts.py [--base <git-ref>] [--out .harness/facts.json]
                        [--test-cmd "npm test -- --json"] [--no-tests]

Why this exists
---------------
Agents without a shell cannot measure. Asked for a line count they read whole
files into context and derive a number — paying twice: once in tokens, once in
error. This script runs where a shell always exists (CI, or any operator
terminal) and writes every number the contract is allowed to assert.

The rule that makes it bite (enforced by preflight_contract.py):

    No numeric criterion may be graded except by citing a key in facts.json.

So a criterion says `facts:diff.src/tools.ts.net_nonblank <= 120`, not "the
generator reports 112 lines". A criterion whose pass condition is command output,
assigned to an agent that cannot run commands, grades the environment.

Everything here degrades gracefully: a missing git, missing test runner or
missing coverage file produces a null section and a note, never a crash. A
partial facts file is still better than a derived one.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Files that are code for census purposes.
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rb", ".java", ".rs",
            ".sql", ".css", ".scss", ".vue", ".svelte"}
# Line-comment prefixes, used for the non-blank/non-comment count.
COMMENT_PREFIXES = ("//", "#", "*", "/*", "*/", "--", "<!--")


def run(cmd, cwd=None):
    """Run a command; return (ok, stdout). Never raises."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=600)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:  # noqa: BLE001 - any failure is just "unavailable"
        return False, str(e)


def have(binary):
    return shutil.which(binary) is not None


def substantive_lines(text):
    """Non-blank, non-comment lines.

    The unit matters: a diff cap in raw `git diff --stat` lines counts the
    documentation the method itself mandates. Measuring behaviour means
    excluding blanks and comment-only lines.
    """
    n = 0
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(COMMENT_PREFIXES):
            continue
        n += 1
    return n


def diff_facts(base, root):
    """Per-file added/removed, plus net substantive lines of the working tree."""
    if not have("git"):
        return None, "git not available"
    ok, _ = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)
    if not ok:
        return None, "not a git work tree"

    ok, out = run(["git", "diff", "--numstat", base], cwd=root)
    if not ok:
        return None, f"git diff against '{base}' failed"

    files = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        if added == "-" or removed == "-":
            continue  # binary
        entry = {"added": int(added), "removed": int(removed)}
        f = Path(root) / path
        if f.is_file():
            try:
                entry["net_nonblank"] = substantive_lines(f.read_text(errors="ignore"))
            except OSError:
                entry["net_nonblank"] = None
        else:
            entry["net_nonblank"] = 0  # deleted
        files[path] = entry
    return files, None


def census(root):
    """Count code files by test tier, so 'a census of 110/53/13' is measured."""
    root = Path(root)
    buckets = {"unit": 0, "integration": 0, "e2e": 0, "source": 0, "total": 0}
    skip = {".git", "node_modules", "dist", "build", ".next", "coverage",
            "__pycache__", ".venv", "venv", ".harness"}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in CODE_EXT:
            continue
        if any(part in skip for part in p.parts):
            continue
        rel = str(p.relative_to(root)).lower()
        buckets["total"] += 1
        if "e2e" in rel or "cypress" in rel:
            buckets["e2e"] += 1
        elif "integration" in rel or "/int/" in rel or ".int." in rel:
            buckets["integration"] += 1
        elif "test" in rel or "spec" in rel or "__tests__" in rel:
            buckets["unit"] += 1
        else:
            buckets["source"] += 1
    return buckets


def assertion_counts(root):
    """Count assertion calls per test file — the `expect(` delta, measured."""
    root = Path(root)
    counts = {}
    pat = re.compile(r"\b(expect|assert|should)\s*\(")
    skip = {".git", "node_modules", "dist", "build", "coverage", ".harness"}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in CODE_EXT:
            continue
        if any(part in skip for part in p.parts):
            continue
        rel = str(p.relative_to(root)).lower()
        if not ("test" in rel or "spec" in rel or "e2e" in rel or "cypress" in rel):
            continue
        try:
            counts[str(p.relative_to(root))] = len(pat.findall(p.read_text(errors="ignore")))
        except OSError:
            continue
    return counts


def test_facts(test_cmd, root):
    """Run the suite. Records the command and a pass/fail summary as evidence."""
    if not test_cmd:
        return None, "no --test-cmd given"
    ok, out = run(test_cmd if isinstance(test_cmd, list) else ["sh", "-c", test_cmd],
                  cwd=root)
    tail = "\n".join(out.strip().splitlines()[-40:])
    res = {"command": test_cmd if isinstance(test_cmd, str) else " ".join(test_cmd),
           "exit_ok": ok, "output_tail": tail}
    m = re.search(r"(\d+)\s+pass(?:ed|ing)", out, re.I)
    if m:
        res["passed"] = int(m.group(1))
    m = re.search(r"(\d+)\s+fail(?:ed|ing)", out, re.I)
    res["failed"] = int(m.group(1)) if m else (0 if ok else None)
    return res, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD", help="git ref to diff against")
    ap.add_argument("--out", default=".harness/facts.json")
    ap.add_argument("--test-cmd", default=None)
    ap.add_argument("--no-tests", action="store_true")
    args = ap.parse_args()

    root = Path.cwd()
    notes = []

    diff, err = diff_facts(args.base, root)
    if err:
        notes.append(f"diff: {err}")

    tests = None
    if not args.no_tests:
        tests, terr = test_facts(args.test_cmd, root)
        if terr:
            notes.append(f"tests: {terr}")

    commit = None
    if have("git"):
        ok, out = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)
        commit = out.strip() if ok else None

    facts = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "emit_facts.py",
        "commit": commit,
        "diff_base": args.base,
        "diff": diff,
        "census": census(root),
        "assertions": assertion_counts(root),
        "tests": tests,
        "notes": notes,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n")

    print(f"OK: wrote {out}")
    print(f"  commit={commit} diff_files={len(diff) if diff else 0} "
          f"census_total={facts['census']['total']} "
          f"tests={'run' if tests else 'skipped'}")
    for n in notes:
        print(f"  NOTE: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
