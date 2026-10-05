#!/usr/bin/env python3
"""Emit .harness/facts.json — the single source of MEASURED truth.

Usage:
  python3 emit_facts.py [--base <git-ref>] [--out .harness/facts.json]
                        [--test-cmd "npm test -- --json"] [--no-tests]

  --base defaults to `sprint_base_ref` in .harness/progress.json (the commit
  the active sprint started from), then HEAD. Per-file diff keys:
    added / removed                 raw lines, as `git diff --numstat`
    added_nonblank / removed_nonblank  non-blank, non-comment lines in the patch
    net_nonblank                    added_nonblank − removed_nonblank (the
                                    unit a diff budget is written in)
    file_nonblank                   whole-file substantive line count
    untracked: true                 a new file git does not know yet

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


def hunk_counts(base, path, root):
    """Substantive lines added and removed in the patch for one file.

    `net_nonblank` is a DIFF measure (added − removed, non-blank non-comment),
    which is what a diff budget bounds. The whole-file count is reported
    separately as `file_nonblank` so the two can never be confused again.
    """
    ok, out = run(["git", "diff", "-U0", "--no-color", base, "--", path], cwd=root)
    if not ok:
        return None, None
    added = removed = 0
    for line in out.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line.startswith("+"):
            added += substantive_lines(line[1:])
        elif line.startswith("-"):
            removed += substantive_lines(line[1:])
    return added, removed


def diff_facts(base, root):
    """Per-file added/removed (raw and substantive) versus `base`.

    Includes untracked files: a generator's brand-new module is exactly the
    file a diff budget must see, and `git diff` alone omits it until staged.
    Harness bookkeeping under `.harness/` is skipped, as the census skips it.
    """
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
        if added == "-" or removed == "-" or path.startswith(".harness/"):
            continue  # binary, or harness bookkeeping
        entry = {"added": int(added), "removed": int(removed)}
        a, r = hunk_counts(base, path, root)
        entry["added_nonblank"] = a
        entry["removed_nonblank"] = r
        entry["net_nonblank"] = (a - r) if a is not None else None
        f = Path(root) / path
        if f.is_file():
            try:
                entry["file_nonblank"] = substantive_lines(f.read_text(errors="ignore"))
            except OSError:
                entry["file_nonblank"] = None
        else:
            entry["file_nonblank"] = 0  # deleted
        files[path] = entry

    ok, out = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=root)
    if ok:
        for path in out.splitlines():
            path = path.strip()
            if not path or path.startswith(".harness/") or path in files:
                continue
            f = Path(root) / path
            if not f.is_file() or f.suffix not in CODE_EXT:
                continue
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            n = substantive_lines(text)
            files[path] = {"added": len(text.splitlines()), "removed": 0,
                           "added_nonblank": n, "removed_nonblank": 0,
                           "net_nonblank": n, "file_nonblank": n,
                           "untracked": True}
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


def test_run_facts(root, commit):
    """Summarise the latest run_tests.py bundle (browser suites, manual tours).

    Criteria cite these keys, e.g. `facts:test_runs.totals.failed == 0` or
    `facts:test_runs.commit_matches_head == true`.
    """
    latest = root / ".harness" / "test-results" / "latest.json"
    if not latest.is_file():
        return None, "test_runs: no .harness/test-results/latest.json (run run_tests.py)"
    try:
        ptr = json.loads(latest.read_text())
        s = json.loads((Path(ptr["path"]) / "summary.json").read_text())
    except (OSError, ValueError, KeyError) as e:
        return None, f"test_runs: unreadable latest run ({e})"
    return {
        "run_id": s.get("run_id"),
        "mode": s.get("mode"),
        "status": s.get("status"),
        "commit": s.get("commit"),
        "commit_matches_head": bool(commit) and s.get("commit") == commit,
        "dirty": s.get("dirty"),
        "totals": s.get("totals"),
        "suites": {x["name"]: x["totals"] for x in s.get("suites", [])},
        "a11y": ({"checks": s["a11y"]["checks"], **s["a11y"]["by_impact"]} if s.get("a11y") else None),
        "manual_tours": len(s.get("manual", {}).get("tours", [])),
        "manual_screenshots": s.get("manual", {}).get("screenshots", 0),
        "manual_current": all(t.get("current") for t in s.get("manual", {}).get("tours", [])),
        "summary": str(Path(ptr["path"]) / "summary.json"),
    }, None


def product_map_facts(root):
    """End-to-end chain state written by validate_product_map.py.

    Criteria cite e.g. `facts:product_map.flows.PF-02.journey_passing == true`
    or `facts:product_map.errors == 0`.
    """
    p = root / ".harness" / "product-map.json"
    if not p.is_file():
        return None, "product_map: no .harness/product-map.json (run validate_product_map.py)"
    try:
        m = json.loads(p.read_text())
    except ValueError as e:
        return None, f"product_map: unreadable ({e})"
    return {"generated_at": m.get("generated_at"), "results_run": m.get("results_run"),
            "errors": m.get("errors"), "warnings": m.get("warnings"), "counts": m.get("counts"),
            "flows": {k: {"status": v.get("status"), "journey_passing": v.get("journey_passing"),
                          "priority": v.get("priority")} for k, v in (m.get("flows") or {}).items()}}, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None,
                    help="git ref to diff against (default: sprint_base_ref in "
                         ".harness/progress.json, else HEAD)")
    ap.add_argument("--out", default=".harness/facts.json")
    ap.add_argument("--test-cmd", default=None)
    ap.add_argument("--no-tests", action="store_true")
    args = ap.parse_args()

    root = Path.cwd()
    notes = []

    # The generator commits its own work (v3.2), so a diff against HEAD is
    # empty by the time the evaluator reads it. Prefer the sprint's start ref
    # when the orchestrator recorded one in progress.json.
    base = args.base
    if not base:
        try:
            prog = json.loads((root / ".harness" / "progress.json").read_text())
            base = prog.get("sprint_base_ref") or None
        except (OSError, ValueError):
            base = None
    if not base:
        base = "HEAD"
        notes.append("diff: no --base and no sprint_base_ref in progress.json; "
                     "using HEAD — if the generator already committed, this "
                     "diff is empty; pass --base <sprint-start-ref>")
    args.base = base

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
        "test_runs": None,
        "product_map": None,
        "notes": notes,
    }

    facts["test_runs"], rerr = test_run_facts(root, commit)
    if rerr:
        notes.append(rerr)
    facts["product_map"], merr = product_map_facts(root)
    if merr:
        notes.append(merr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n")

    print(f"OK: wrote {out}")
    print(f"  commit={commit} diff_files={len(diff) if diff else 0} "
          f"census_total={facts['census']['total']} "
          f"tests={'run' if tests else 'skipped'} "
          f"test_runs={facts['test_runs']['status'] if facts['test_runs'] else 'none'}")
    for n in notes:
        print(f"  NOTE: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
