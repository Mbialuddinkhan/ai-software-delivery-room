#!/usr/bin/env python3
"""Prove the cloud build behaves like the local one: the same tests pass in both.

Usage:
  python3 cloud_parity.py --local <run> --cloud <run> [--json .harness/cloud-parity.json]

A <run> is a run folder, its summary.json, or a run label given to
run_tests.py (--label); a label picks the newest run with that label.
Typical use, after devops deploys the test environment (with approval):

  python3 .harness/scripts/run_tests.py --label local
  python3 .harness/scripts/run_tests.py --label cloud-aws --base-url <test env URL> --no-server
  python3 .harness/scripts/cloud_parity.py --local local --cloud cloud-aws

v3.8. Every test that passed locally must pass on the cloud; a test missing
from the cloud run, or failing there, is an ERROR. Tests that fail locally are
reported but not counted (fix them locally first). Both runs must be from the
same commit, and the cloud run must have hit a non-local base URL.
Writes .harness/cloud-parity.json (the dashboard and the release gate read it).
Exit 1 on any ERROR. Last line: CLOUD-PARITY: {json}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(".harness/test-results")


def find(ref: str) -> Path | None:
    p = Path(ref)
    if p.is_file():
        return p
    if (p / "summary.json").is_file():
        return p / "summary.json"
    best = None
    for s in sorted(RESULTS.glob("*/summary.json")) if RESULTS.is_dir() else []:
        try:
            d = json.loads(s.read_text())
        except (OSError, ValueError):
            continue
        if d.get("label") == ref and (best is None or d.get("finished_at", "") >= best[0]):
            best = (d.get("finished_at", ""), s)
    return best[1] if best else None


def cases(summary: dict) -> dict:
    out = {}
    for s in summary.get("suites") or []:
        for c in s.get("cases") or []:
            key = f"{s.get('name')}::{c.get('classname') or ''}::{c.get('name')}"
            out[key] = c.get("status")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare a local test run with a cloud test run.")
    ap.add_argument("--local", required=True)
    ap.add_argument("--cloud", required=True)
    ap.add_argument("--json", default=".harness/cloud-parity.json")
    a = ap.parse_args()
    errors, warns = [], []
    lp, cp = find(a.local), find(a.cloud)
    for name, p in (("local", lp), ("cloud", cp)):
        if p is None:
            errors.append(f"no {name} run found for '{getattr(a, name)}'")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        print("CLOUD-PARITY: " + json.dumps({"ok": False, "errors": errors}))
        return 1
    ls, cs = json.loads(lp.read_text()), json.loads(cp.read_text())
    if ls.get("commit") and cs.get("commit") and ls["commit"] != cs["commit"]:
        errors.append(f"the runs are from different commits ({ls['commit'][:7]} local, {cs['commit'][:7]} cloud)")
    url = ((cs.get("environment") or {}).get("base_url") or "")
    if not url or any(h in url for h in ("localhost", "127.0.0.1", "0.0.0.0")):
        errors.append(f"the cloud run did not target a cloud URL (base_url: {url or 'none'}) — pass --base-url")
    lc, cc = cases(ls), cases(cs)
    passed_local = [k for k, v in lc.items() if v == "passed"]
    missing = [k for k in passed_local if k not in cc]
    broke = [k for k in passed_local if k in cc and cc[k] != "passed"]
    local_failing = [k for k, v in lc.items() if v in ("failed", "error")]
    errors += [f"missing on the cloud: {k}" for k in missing[:20]]
    errors += [f"passes locally, {cc[k]} on the cloud: {k}" for k in broke[:20]]
    if local_failing:
        warns.append(f"{len(local_failing)} test(s) fail locally — fix them there first; not counted")
    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    res = {"ok": not errors, "local": {"label": ls.get("label"), "commit": ls.get("commit"), "passed": len(passed_local)},
           "cloud": {"label": cs.get("label"), "commit": cs.get("commit"), "base_url": url,
                     "passed": sum(1 for v in cc.values() if v == "passed")},
           "missing": len(missing), "broken": len(broke)}
    try:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(res, indent=2) + "\n")
    except OSError:
        pass
    print(f"{'OK' if not errors else 'FAIL'}: {len(passed_local)} tests pass locally; "
          f"{len(passed_local) - len(missing) - len(broke)} of them pass on the cloud ({url})")
    print("CLOUD-PARITY: " + json.dumps(res))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
