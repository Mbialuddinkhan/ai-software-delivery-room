#!/usr/bin/env python3
"""Evidence gate for an assessment — no claim ships without a citation.

Usage:
  python3 validate_assessment.py [--as-is docs/assess/as-is.json]
                                 [--findings docs/assess/findings.json]
                                 [--root .] [--strict]

This is to the assessment what validate_product_map.py is to a build: it refuses
to let the report go out on assertions nobody can check. It verifies that

  - every finding and every as-is feature/rule/flow-step carries evidence;
  - each evidence pointer resolves — `path:line` exists and the file is long
    enough, a `db:`/`api:`/`live:`/`tool:` note is present, or a scanner file
    named under evidence/ exists;
  - severity, confidence, area and effort use the allowed vocabularies;
  - no finding pastes a secret VALUE into the report (keys, tokens, passwords):
    cite the location, never the secret itself.

Warnings by default; `--strict` (used at report time) makes any unmet evidence
or a pasted secret an error. Prints `ASSESS-VALIDATE: {json}` last.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SEV = {"critical", "high", "medium", "low"}
CONF = {"confirmed", "likely", "unconfirmed"}
AREA = {"architecture", "code", "security", "performance", "operations", "process", "data"}
EFFORT = {"S", "M", "L"}

# path:line or path:line-line, found ANYWHERE in a free-form evidence string
# (the agents write several per line, sometimes with a trailing comment).
# The path has an extension so "api: GET /x" is not mistaken for a file.
CITE = re.compile(r"(?P<path>[\w./\-]+\.[A-Za-z0-9]+):(?P<a>\d+)(?:-(?P<b>\d+))?")
NOTE = re.compile(r"\b(db|api|live|tool|git|config|dast|manual)\s*[:=]", re.IGNORECASE)
# obvious pasted secrets (value, not a reference)
SECRET = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)"
    r"|(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,})"   # JWT
    r"|((?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*['\"][^'\"]{6,}['\"])",
    re.IGNORECASE)


def resolve(cite: str, root: Path) -> "tuple[bool, str]":
    """True if the free-form evidence string contains at least one resolvable
    `path:line` reference, a recognised note (db:/api:/live:/tool:/…), or a
    named scanner output under evidence/."""
    cite = (cite or "").strip()
    reasons = []
    for m in CITE.finditer(cite):
        p = root / m.group("path")
        if not p.is_file():
            reasons.append(f"file not found: {m.group('path')}")
            continue
        try:
            n = sum(1 for _ in p.open(errors="ignore"))
        except OSError as ex:
            reasons.append(f"unreadable: {ex}")
            continue
        line = int(m.group("b") or m.group("a"))
        if line <= n:
            return True, "ok"
        reasons.append(f"{m.group('path')} line {line} > {n}")
    if NOTE.search(cite):
        return True, "note"
    if re.search(r"\bevidence/[\w./\-]+", cite) and (root / re.search(r"evidence/[\w./\-]+", cite).group(0)).exists():
        return True, "scanner-output"
    return (False, "; ".join(reasons) if reasons else "no path:line or note found")


def strings(x):
    """Every raw string value in an item (not its JSON encoding, where quotes
    are escaped and a pasted `api_key = "…"` would slip past the pattern)."""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v)


def check_items(items, kind, root, issues, secrets, need_sev=False):
    for it in items:
        ident = it.get("id") or it.get("name") or kind
        ev = it.get("evidence")
        ev = ev if isinstance(ev, list) else ([ev] if ev else [])
        if not ev:
            issues.append(f"{kind} {ident}: no evidence")
        else:
            if not any(resolve(str(c), root)[0] for c in ev):
                why = "; ".join(f"{c} ({resolve(str(c), root)[1]})" for c in ev[:3])
                issues.append(f"{kind} {ident}: no evidence resolves — {why}")
        if any(SECRET.search(s) for s in strings(it)):
            secrets.append(f"{kind} {ident}: looks like a pasted secret value — cite the location instead")
        if need_sev:
            if it.get("severity") not in SEV:
                issues.append(f"{kind} {ident}: severity '{it.get('severity')}' not in {sorted(SEV)}")
            if it.get("confidence") not in CONF:
                issues.append(f"{kind} {ident}: confidence '{it.get('confidence')}' not in {sorted(CONF)}")
            if it.get("area") not in AREA:
                issues.append(f"{kind} {ident}: area '{it.get('area')}' not in {sorted(AREA)}")
            if it.get("effort") and it.get("effort") not in EFFORT:
                issues.append(f"{kind} {ident}: effort '{it.get('effort')}' not in {sorted(EFFORT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evidence gate for an ASDR assessment.")
    ap.add_argument("--as-is", default="docs/assess/as-is.json")
    ap.add_argument("--findings", default="docs/assess/findings.json")
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)

    issues, secrets, counts = [], [], {}
    asis = None
    for cand in (Path(args.as_is), root / args.as_is):
        if cand.is_file():
            try:
                asis = json.loads(cand.read_text())
            except ValueError as ex:
                issues.append(f"as-is.json unreadable: {ex}")
            break
    if asis:
        for key, kind in [("features", "feature"), ("rules", "rule")]:
            check_items(asis.get(key, []), kind, root, issues, secrets)
            counts[key] = len(asis.get(key, []))
        steps = [st for fl in asis.get("flows", []) for st in (fl.get("steps") or [])]
        check_items(steps, "step", root, issues, secrets)
        counts["flow_steps"] = len(steps)

    findings = None
    for cand in (Path(args.findings), root / args.findings):
        if cand.is_file():
            try:
                findings = json.loads(cand.read_text())
            except ValueError as ex:
                issues.append(f"findings.json unreadable: {ex}")
            break
    if findings is not None:
        check_items(findings, "finding", root, issues, secrets, need_sev=True)
        counts["findings"] = len(findings)

    if asis is None and findings is None:
        print("ASSESS-VALIDATE: " + json.dumps({"ok": False, "error": "no as-is.json or findings.json found"}))
        print("ERROR: neither as-is.json nor findings.json found — nothing to validate")
        return 1

    for s in secrets:
        print(f"SECRET: {s}")
    for i in issues:
        print(f"{'ERROR' if args.strict else 'WARN'}: {i}")
    ok = not secrets and (not issues or not args.strict)
    print(f"{'OK' if ok else 'FAIL'}: {counts} — {len(issues)} evidence issue(s), {len(secrets)} secret(s)")
    print("ASSESS-VALIDATE: " + json.dumps({"ok": ok, "counts": counts,
                                            "issues": len(issues), "secrets": len(secrets)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
