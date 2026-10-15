#!/usr/bin/env python3
"""Evidence gate for an assessment — no claim ships without a citation.

Usage:
  python3 validate_assessment.py [--as-is docs/assess/as-is.json]
                                 [--findings docs/assess/findings.json]   (+ findings-*.json beside it)
                                 [--root .] [--strict]

This is to the assessment what validate_product_map.py is to a build: it refuses
to let the report go out on assertions nobody can check. It verifies that

  - every finding and every as-is feature/rule/flow-step carries evidence;
  - each evidence pointer resolves — `path:line` exists and the file is long
    enough, a `db:`/`api:`/`live:`/`tool:` note is present, or a scanner file
    named under evidence/ exists;
  - EVERY `path:line` an item cites resolves, not just one of them (a wrong
    line next to a right one is an error). An entry that starts with a note
    (`git: commit abc1234 src/old.xml:2` for a file only in history) is not
    path-checked;
  - findings from different reviewers with similar titles and the same cited
    lines are listed as possible duplicates (a warning: the critic decides);
  - severity, confidence, area and effort use the allowed vocabularies;
  - no finding pastes a secret VALUE into the report (keys, tokens, passwords):
    cite the location, never the secret itself;
  - no file anywhere under the assessment folder (evidence included) contains
    a credential value the source code assigns (a default password, a
    signing key, a connection-string password). The values are collected from
    the source and searched for literally; they are never printed.

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
            with p.open(errors="ignore") as fh:
                n = sum(1 for _ in fh)
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


URL = re.compile(r"https?://\S+")
LEAD_NOTE = re.compile(r"^\s*(db|api|live|tool|git|config|dast|manual)\s*[:=]", re.IGNORECASE)


def cites(text: str):
    """path:line references in a string, ignoring any inside a URL."""
    spans = [m.span() for m in URL.finditer(text or "")]
    for m in CITE.finditer(text or ""):
        if not any(a <= m.start() < b for a, b in spans):
            yield m


def unresolved(text: str, root: Path) -> list:
    """Every path:line in an evidence entry that does not exist (none for a note entry)."""
    if LEAD_NOTE.match(text or ""):
        return []
    bad = []
    for m in cites(text):
        p = root / m.group("path")
        if not p.is_file():
            bad.append(f"{m.group(0)} (file not found)")
            continue
        try:
            with p.open(errors="ignore") as fh:
                n = sum(1 for _ in fh)
        except OSError:
            bad.append(f"{m.group(0)} (unreadable)")
            continue
        a, b = int(m.group("a")), int(m.group("b") or m.group("a"))
        if b < a or b > n or a < 1:
            bad.append(f"{m.group(0)} (file has {n} lines)")
    return bad


def spans_of(item) -> list:
    out = []
    for c in (item.get("evidence") if isinstance(item.get("evidence"), list) else [item.get("evidence") or ""]):
        if LEAD_NOTE.match(str(c)):
            continue
        for m in cites(str(c)):
            out.append((m.group("path"), int(m.group("a")), int(m.group("b") or m.group("a"))))
    return out


STOP = set("the a an and or of to in on for is are be by with from not no any at as it its this that "
           "every one only all can cannot".split())


def _words(t: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", str(t or "").lower()) if w not in STOP and len(w) > 2}


def _overlap(x, y) -> bool:
    return x[0] == y[0] and max(x[1], y[1]) <= min(x[2], y[2])


def duplicates(findings) -> list:
    """Likely duplicates between DIFFERENT reviewers (id prefixes): similar titles,
    plus the same primary citation or most citations shared. Reviewers cite the
    same supporting lines all the time, so shared lines alone mean nothing.
    A warning only: the critic decides which one stands."""
    out = []
    for i, f in enumerate(findings):
        for g in findings[i + 1:]:
            if str(f.get("id", "")).split("-")[0] == str(g.get("id", "")).split("-")[0]:
                continue
            sf, sg = spans_of(f), spans_of(g)
            wf, wg = _words(f.get("title")), _words(g.get("title"))
            title = len(wf & wg) / max(1, len(wf | wg))
            primary = bool(sf and sg and _overlap(sf[0], sg[0]))
            shared = sum(1 for x in sf if any(_overlap(x, y) for y in sg)) / max(1, min(len(sf), len(sg)))
            if title >= 0.4 or (title >= 0.2 and (primary or shared >= 0.5)):
                out.append(f"{f.get('id')} and {g.get('id')} — \"{str(f.get('title'))[:60]}\" / \"{str(g.get('title'))[:60]}\"")
    return out


CRED_NAME = (r"[A-Za-z0-9_.]*(?:password|passwd|pwd|secret|secret_?key|api_?key|access_?key|signing_?key|"
             r"private_?key|client_?secret|auth_?token|access_?token|token)")
CRED_ASSIGN = re.compile(r"\b" + CRED_NAME + r"[\"']?\s*[=:]\s*[\"']([^\"'\s]{8,200})[\"']", re.IGNORECASE)
CONN_PWD = re.compile(r"(?:password|pwd)\s*=\s*([^;\"'\s]{6,200})", re.IGNORECASE)
TEXT_EXT = {".cs", ".js", ".ts", ".py", ".java", ".kt", ".go", ".rb", ".php", ".json", ".yml", ".yaml", ".xml",
            ".config", ".env", ".ini", ".properties", ".bicep", ".tf", ".sh", ".ps1", ".cshtml", ".razor", ".vb", ".toml"}
SKIP_DIRS = {".git", "node_modules", "dist", "build", "vendor", "bin", "obj", ".venv", "venv", "__pycache__"}


def harvest_credentials(root: Path) -> dict:
    """Credential values the source assigns, mapped to where (path:line). Short
    plain words are skipped, so a value like "Password" does not turn every
    mention of the word into an alarm; a long letters-only key still counts."""
    found = {}
    if not root.is_dir():
        return found
    for p in root.rglob("*"):
        if (not p.is_file() or p.suffix.lower() not in TEXT_EXT or any(d in SKIP_DIRS for d in p.parts)
                or p.stat().st_size > 1_000_000):
            continue
        try:
            for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                for m in list(CRED_ASSIGN.finditer(line)) + list(CONN_PWD.finditer(line)):
                    v = m.group(1)
                    if ((v.isalpha() and len(v) < 16) or v.startswith(("<", "${", "{{", "$(", "%")) or "*" in v
                            or v.lower() in {"changeme", "password", "required"}):
                        continue
                    found.setdefault(v, f"{p.relative_to(root)}:{n}")
        except OSError:
            continue
    return found


def leaked(docs: Path, creds: dict) -> list:
    """Assessment files (any depth, evidence included) that contain a harvested value."""
    out = []
    if not creds or not docs.is_dir():
        return out
    for f in docs.rglob("*"):
        if not f.is_file() or f.stat().st_size > 20_000_000 or f.suffix.lower() in {".png", ".jpg", ".pdf", ".gif"}:
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        if f.suffix.lower() == ".json":         # JSON escapes quotes and slashes: compare decoded strings too
            try:
                text += "\n".join(strings(json.loads(text)))
            except ValueError:
                pass
        for v, where in creds.items():
            if v in text:
                out.append(f"{f} contains the credential value assigned at {where} — remove it, cite the location")
        if f.suffix.lower() != ".json" and SECRET.search(text):   # JSON files: their decoded strings are in text too
            out.append(f"{f} contains what looks like a key, token or password value — remove it, cite the location")
        elif f.suffix.lower() == ".json":
            try:
                if any(SECRET.search(x) for x in strings(json.loads(f.read_text(errors="ignore")))):
                    out.append(f"{f} contains what looks like a key, token or password value — remove it, cite the location")
            except ValueError:
                pass
    return out


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
            else:
                bad = [b for c in ev for b in unresolved(str(c), root)]
                if bad:
                    issues.append(f"{kind} {ident}: citation does not resolve — {'; '.join(bad[:4])}")
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
    ap.add_argument("--docs", default=None, help="assessment folder searched for leaked credential values "
                                                 "(default: the folder holding as-is.json)")
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
        files = ([cand] if cand.is_file() else []) + sorted(cand.parent.glob("findings-*.json"))
        files = list({f.resolve(): f for f in files}.values())   # --findings may name one of the merged files
        if files:
            findings = []
            for fp in files:            # one file per reviewing agent (findings-architecture.json, …) — merged here
                try:
                    data = json.loads(fp.read_text())
                except ValueError as ex:
                    issues.append(f"{fp.name} unreadable: {ex}")
                    continue
                findings += [f for f in (data if isinstance(data, list) else []) if isinstance(f, dict) and "_about" not in f]
            seen = {}
            for f in findings:
                if f.get("id") in seen:
                    issues.append(f"finding id {f.get('id')} is used twice — each agent keeps its own prefix")
                seen[f.get("id")] = True
            break
    if findings is not None:
        check_items(findings, "finding", root, issues, secrets, need_sev=True)
        counts["findings"] = len(findings)
    dups = duplicates(findings or [])

    if asis is None and findings is None:
        print("ASSESS-VALIDATE: " + json.dumps({"ok": False, "error": "no as-is.json or findings.json found"}))
        print("ERROR: neither as-is.json nor findings.json found — nothing to validate")
        return 1

    docs = Path(args.docs) if args.docs else None
    if docs is None:
        for cand in (Path(args.as_is), root / args.as_is, Path(args.findings), root / args.findings):
            if cand.parent.is_dir() and cand.parent.name:
                docs = cand.parent
                break
    creds = harvest_credentials(root)
    secrets += leaked(docs, creds) if docs else []
    counts["credential_values_checked"] = len(creds)
    for s in secrets:
        print(f"SECRET: {s}")
    for i in issues:
        print(f"{'ERROR' if args.strict else 'WARN'}: {i}")
    for x in dups:
        print(f"DUPLICATE?: {x} — keep one, or say why both stand")
    ok = not secrets and (not issues or not args.strict)
    print(f"{'OK' if ok else 'FAIL'}: {counts} — {len(issues)} evidence issue(s), {len(secrets)} secret(s)")
    print("ASSESS-VALIDATE: " + json.dumps({"ok": ok, "counts": counts,
                                            "issues": len(issues), "secrets": len(secrets),
                                            "possible_duplicates": len(dups)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
