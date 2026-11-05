#!/usr/bin/env python3
"""Secrets gate: fail when a credential appears in docs or harness evidence.

Usage:
  python3 check_secrets.py [paths ...] [--gate] [--allowlist .harness/secrets-allowlist.txt]
                           [--json .harness/secrets-report.json]

Default paths: docs/ and .harness/ (evidence, eval reports, traces).

v4.2 (brief 8.3). The 3.7 release fixed one leaked password that an agent had
pasted into evidence as proof of work; that fix was a one-off. This makes the
sweep mechanical and standing: evidence must PROVE a credential was handled
without BECOMING a copy of it.

Uses gitleaks when installed (`gitleaks dir <path>`); always ALSO runs the
built-in patterns, so the gate never silently weakens when gitleaks is absent.
Findings are printed REDACTED (first 4 characters, then asterisks) — the gate
itself must not republish what it caught.

Allowlist: one entry per line in .harness/secrets-allowlist.txt; `#` comments.
An entry matches by exact string or, prefixed `re:`, by regex. Allowlisted
findings are reported as "allowed" and do not fail the gate. Placeholders
(<YOUR_KEY>, xxx..., example/dummy/sample values) are skipped by rule.

Exit: 0 clean (or findings all allowlisted), 1 findings with --gate,
0 with findings but no --gate (report-only). Wire-in points: riskgate
prerequisites, PUBLISHING.md pre-tag checklist, templates/hooks/pre-commit.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
            ".env", ".csv", ".log", ".sh", ".py", ".js", ".ts", ".html"}
MAX_BYTES = 2_000_000

# Each: (rule id, regex, group that holds the secret value)
PATTERNS = [
    ("aws-access-key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), 1),
    ("google-api-key", re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b"), 1),
    ("github-token", re.compile(r"\b(gh[pousr]_[0-9A-Za-z]{36,255})\b"), 1),
    ("slack-token", re.compile(r"\b(xox[baprs]-[0-9A-Za-z-]{10,250})\b"), 1),
    ("stripe-key", re.compile(r"\b(sk_(?:live|test)_[0-9A-Za-z]{16,})\b"), 1),
    ("private-key-block", re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)"), 1),
    ("jwt", re.compile(r"\b(eyJ[0-9A-Za-z_\-]{10,}\.eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,})\b"), 1),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]{3,}:([^@\s/]{6,})@"), 1),
    ("assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|secret|passwd|password|token|auth[_-]?token"
        r"|access[_-]?token|client[_-]?secret|credential)s?\b"
        r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"), 1),
]
# Values that are clearly placeholders, not credentials.
PLACEHOLDER = re.compile(
    r"(?i)^(<[^>]+>|\{\{[^}]+\}\}|\$\{[^}]+\}|x{4,}|\*{3,}|\.{3,}|your[_-]"
    r"|example|sample|dummy|changeme|placeholder|redacted"
    r"|test[_-]?(key|token|secret)|sk_test_?(x+|1234)|0{6,})")


def redact(value: str) -> str:
    return value[:4] + "*" * max(4, min(12, len(value) - 4))


def load_allowlist(path: Path):
    exact, regexes = set(), []
    if path.exists():
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("re:"):
                try:
                    regexes.append(re.compile(line[3:]))
                except re.error:
                    print(f"WARN: bad allowlist regex skipped: {line[3:]}")
            else:
                exact.add(line)
    return exact, regexes


def allowed(value: str, exact, regexes) -> bool:
    return value in exact or any(r.search(value) for r in regexes)


def iter_files(roots):
    for root in roots:
        p = Path(root)
        if p.is_file():
            yield p
            continue
        for f in p.rglob("*"):
            if (f.is_file() and f.suffix.lower() in TEXT_EXT
                    and f.stat().st_size <= MAX_BYTES
                    and "node_modules" not in f.parts and ".git" not in f.parts):
                yield f


def scan_builtin(roots, exact, regexes):
    findings = []
    for f in iter_files(roots):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        if f.name == "secrets-allowlist.txt":
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for rule, pat, grp in PATTERNS:
                for m in pat.finditer(line):
                    value = m.group(grp)
                    if PLACEHOLDER.match(value):
                        continue
                    findings.append({
                        "rule": rule, "file": str(f), "line": lineno,
                        "redacted": redact(value),
                        "allowed": allowed(value, exact, regexes),
                    })
    return findings


def scan_gitleaks(roots):
    """Extra layer when gitleaks is installed. Never the only layer."""
    if not shutil.which("gitleaks"):
        return None
    found = []
    for root in roots:
        if not Path(root).exists():
            continue
        r = subprocess.run(
            ["gitleaks", "dir", str(root), "--no-banner", "--report-format", "json",
             "--report-path", "/dev/stdout", "--exit-code", "0"],
            capture_output=True, text=True, timeout=300)
        try:
            for item in json.loads(r.stdout or "[]"):
                found.append({"rule": "gitleaks:" + item.get("RuleID", "?"),
                              "file": item.get("File", "?"), "line": item.get("StartLine", 0),
                              "redacted": redact(item.get("Secret", "") or "????"),
                              "allowed": False})
        except ValueError:
            pass
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=None)
    ap.add_argument("--gate", action="store_true", help="exit 1 on non-allowlisted findings")
    ap.add_argument("--allowlist", default=".harness/secrets-allowlist.txt")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    roots = [p for p in (args.paths or ["docs", ".harness"]) if Path(p).exists()]
    if not roots:
        print("OK: nothing to scan (no docs/ or .harness/ here)")
        return 0

    exact, regexes = load_allowlist(Path(args.allowlist))
    findings = scan_builtin(roots, exact, regexes)
    gl = scan_gitleaks(roots)
    if gl:
        seen = {(f["file"], f["line"], f["redacted"]) for f in findings}
        for f in gl:
            # gitleaks reports a redacted value only, so an allowlist entry
            # cannot be matched against it — a gitleaks finding is never
            # auto-allowed; confirmed false positives go in its own .gitleaksignore.
            if (f["file"], f["line"], f["redacted"]) not in seen:
                findings.append(f)

    live = [f for f in findings if not f["allowed"]]
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(
            {"scanned": roots, "gitleaks": gl is not None,
             "findings": findings, "blocking": len(live)}, indent=2) + "\n")

    for f in findings:
        tag = "allowed" if f["allowed"] else "SECRET"
        print(f"{tag}: {f['file']}:{f['line']} [{f['rule']}] {f['redacted']}")

    if live:
        print(f"\n{len(live)} secret(s) found in {roots} (gitleaks layer: "
              f"{'on' if gl is not None else 'not installed'}).")
        print("Fix: remove the value, reference where it lives instead "
              "(e.g. 'set in the deploy env'), or allowlist a confirmed false "
              f"positive in {args.allowlist}.")
        return 1 if args.gate else 0
    print(f"OK: no secrets in {roots} "
          f"({'builtin+gitleaks' if gl is not None else 'builtin patterns'}; "
          f"{sum(1 for f in findings if f['allowed'])} allowlisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
