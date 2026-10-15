#!/usr/bin/env python3
"""Run the standard code-health and security scanners on an existing system
and normalise what they find into one summary — the evidence base for /assess.

Usage:
  python3 assess_scan.py --target <path to the system's source>
                         [--out docs/assess/evidence] [--since 2024-01-01]
                         [--lockfile <path>] [--skip semgrep,jscpd,...]
                         [--timeout 600]

Uses whatever is installed and says what was not, so it degrades gracefully
on any machine (a missing tool is "missing", never an error):

  inventory   built in      languages, lines, stacks, entry files
  deps        osv-scanner   known-vulnerable dependencies (lockfile or source)
              npm audit     fallback for Node projects with a package-lock
              trivy fs      optional second opinion if installed
  semgrep     semgrep       static rules: p/default + p/owasp-top-ten
  secrets     gitleaks      code and git history, run with --redact so no
                            secret VALUE is ever written to the evidence
  complexity  lizard        function complexity
  duplication jscpd (npx)   copy-paste blocks
  churn       git           change frequency per file since --since
  hotspots    derived       complexity × churn: where bugs come from

Scanner output is raw evidence for reviewers, not findings. The trial on a
real codebase measured Semgrep at ~40% precision, so every hit is triaged by
an agent reading the code before it can become a finding in the report.

This is defensive analysis of a codebase the client has authorised: it reads
files and git history and does not touch any running system.

Writes <out>/<tool>.* raw outputs, <out>/scan-summary.json and
<out>/scan-summary.md. Last line: `ASSESS-SCAN: {json}`.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXCLUDE_DIRS = {".git", "node_modules", "dist", "build", "vendor", "venv", ".venv", "__pycache__",
                "target", "out", "coverage", ".next", ".nuxt", "bower_components", ".gradle", ".idea", ".vscode"}
CODE_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".java", ".kt", ".cs", ".go", ".rb", ".php",
            ".rs", ".swift", ".scala", ".c", ".cc", ".cpp", ".h", ".hpp", ".vb", ".sql", ".html", ".vue",
            ".svelte", ".css", ".scss", ".sh", ".ps1", ".tf", ".yml", ".yaml", ".json", ".xml", ".cob", ".cbl",
            ".pas", ".dpr", ".frm", ".bas", ".cls"}
STACK_MARKERS = {
    "package.json": "Node.js", "requirements.txt": "Python", "pyproject.toml": "Python", "Pipfile": "Python",
    "pom.xml": "Java (Maven)", "build.gradle": "Java/Kotlin (Gradle)", "go.mod": "Go", "Gemfile": "Ruby",
    "composer.json": "PHP", "Cargo.toml": "Rust", "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose",
    "angular.json": "Angular", "next.config.js": "Next.js", "manage.py": "Django", "web.config": ".NET (IIS)",
}
LOCKFILES = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "requirements.txt", "poetry.lock", "Pipfile.lock",
             "pom.xml", "gradle.lockfile", "go.sum", "Gemfile.lock", "composer.lock", "Cargo.lock", "packages.lock.json"]


def tool(name: str) -> "str | None":
    local = Path(".harness/bin") / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name)


def run(cmd, cwd=None, timeout=600, out_file: "Path | None" = None):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if out_file is not None:
            out_file.write_text(r.stdout)
        return r.returncode, r.stdout, r.stderr, round(time.time() - t0, 1)
    except subprocess.TimeoutExpired:
        return -9, "", f"timed out after {timeout}s", round(time.time() - t0, 1)
    except OSError as e:
        return -1, "", str(e), round(time.time() - t0, 1)


def walk(target: Path):
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in files:
            yield Path(root) / f


# ── steps ─────────────────────────────────────────────────────────────────────

def inventory(target: Path) -> dict:
    lines = collections.Counter()
    files = collections.Counter()
    stacks = set()
    for p in walk(target):
        if p.name in STACK_MARKERS:
            stacks.add(STACK_MARKERS[p.name])
        if p.suffix == ".csproj" or p.suffix == ".sln":
            stacks.add(".NET")
        ext = p.suffix.lower()
        if ext not in CODE_EXT:
            continue
        try:
            n = sum(1 for _ in p.open(errors="ignore"))
        except OSError:
            continue
        lines[ext] += n
        files[ext] += 1
    top = sorted({p.name for p in target.iterdir() if p.is_dir() and p.name not in EXCLUDE_DIRS and not p.name.startswith(".")}) \
        if target.is_dir() else []
    return {"lines_by_ext": dict(lines.most_common()), "files_by_ext": dict(files.most_common()),
            "total_lines": sum(lines.values()), "total_files": sum(files.values()),
            "stacks": sorted(stacks), "top_level_dirs": top,
            "has_git": (target / ".git").exists(),
            "lockfiles": [f for f in LOCKFILES if (target / f).is_file()]}


def deps(target: Path, out: Path, lockfile, timeout) -> dict:
    res = {}
    osv = tool("osv-scanner")
    if osv:
        f = out / "osv.json"
        cmd = [osv, "scan", "source", "--format", "json"]
        cmd += ["-L", str(lockfile)] if lockfile else ["-r", str(target)]
        rc, so, se, secs = run(cmd, timeout=timeout, out_file=f)
        try:
            d = json.loads(so or "{}")
            pkgs = [p for r in d.get("results", []) for p in r.get("packages", [])]
            sev = collections.Counter()
            names = []
            for p in pkgs:
                scores = [float(g.get("max_severity")) for g in p.get("groups", []) if g.get("max_severity")]
                top = max(scores) if scores else None
                band = "unknown" if top is None else ("critical" if top >= 9 else "high" if top >= 7 else "medium" if top >= 4 else "low")
                sev[band] += 1
                names.append({"package": p["package"]["name"], "version": p["package"].get("version"),
                              "advisories": len(p.get("vulnerabilities", [])), "max_cvss": top})
            res["osv-scanner"] = {"status": "ran", "seconds": secs, "output": str(f), "vulnerable_packages": len(pkgs),
                                  "advisories": sum(x["advisories"] for x in names), "by_severity": dict(sev),
                                  "top": sorted(names, key=lambda x: -(x["max_cvss"] or 0))[:15]}
        except ValueError:
            res["osv-scanner"] = {"status": "failed", "seconds": secs, "error": (se or "no JSON output")[-300:]}
    else:
        res["osv-scanner"] = {"status": "missing"}
    if (target / "package-lock.json").is_file() and shutil.which("npm") and res["osv-scanner"].get("status") != "ran":
        f = out / "npm-audit.json"
        rc, so, se, secs = run(["npm", "audit", "--json"], cwd=target, timeout=timeout, out_file=f)
        try:
            meta = json.loads(so or "{}").get("metadata", {}).get("vulnerabilities", {})
            res["npm-audit"] = {"status": "ran", "seconds": secs, "output": str(f), "by_severity": meta}
        except ValueError:
            res["npm-audit"] = {"status": "failed", "error": (se or "")[-300:]}
    trivy = tool("trivy")
    if trivy:
        f = out / "trivy.json"
        rc, so, se, secs = run([trivy, "fs", "--quiet", "--format", "json", "--scanners", "vuln,misconfig", str(target)],
                               timeout=timeout, out_file=f)
        res["trivy"] = {"status": "ran" if so.strip() else "failed", "seconds": secs, "output": str(f)}
    else:
        res["trivy"] = {"status": "missing"}
    return res


def semgrep(target: Path, out: Path, timeout) -> dict:
    sg = tool("semgrep")
    if not sg:
        return {"status": "missing"}
    f = out / "semgrep.json"
    excl = []
    for d in sorted(EXCLUDE_DIRS):
        excl += ["--exclude", d]
    rc, so, se, secs = run([sg, "scan", "--config", "p/default", "--config", "p/owasp-top-ten", "--metrics=off",
                            "--json", "--quiet", *excl, "-o", str(f), str(target)], timeout=timeout)
    try:
        d = json.loads(f.read_text())
    except (OSError, ValueError):
        return {"status": "failed", "seconds": secs, "error": (se or "no output — registry rules need network")[-300:]}
    r = d.get("results", [])
    by_rule = collections.Counter(x["check_id"].split(".")[-1] for x in r)
    by_sev = collections.Counter(x.get("extra", {}).get("severity", "?") for x in r)
    by_file = collections.Counter(x.get("path") for x in r)
    return {"status": "ran", "seconds": secs, "output": str(f), "findings": len(r), "parse_errors": len(d.get("errors", [])),
            "by_severity": dict(by_sev), "top_rules": by_rule.most_common(15), "top_files": by_file.most_common(10),
            "note": "raw hits — triage each in code before it becomes a finding (measured ~40% precision)"}


def secrets(target: Path, out: Path, timeout) -> dict:
    gl = tool("gitleaks")
    if not gl:
        return {"status": "missing"}
    res = {}
    for mode, args in (("code", ["dir", str(target)]), ("history", ["git", str(target)])):
        if mode == "history" and not (target / ".git").exists():
            res[mode] = {"status": "skipped", "reason": "no git history"}
            continue
        f = out / f"gitleaks-{mode}.json"
        rc, so, se, secs = run([gl, *args, "--redact", "--report-format", "json", "--report-path", str(f),
                                "--no-banner", "--log-level", "error"], timeout=timeout)
        try:
            d = json.loads(f.read_text()) if f.is_file() else []
            res[mode] = {"status": "ran", "seconds": secs, "output": str(f), "hits": len(d),
                         "by_rule": dict(collections.Counter(x.get("RuleID") for x in d).most_common(10)),
                         "files": dict(collections.Counter(x.get("File") for x in d).most_common(10))}
        except (OSError, ValueError):
            res[mode] = {"status": "failed", "seconds": secs, "error": (se or "")[-300:]}
    res["note"] = "run with --redact: locations only, no secret values stored"
    return res


def complexity(target: Path, out: Path, timeout) -> dict:
    lz = tool("lizard")
    if not lz:
        return {"status": "missing"}
    f = out / "lizard.csv"
    excl = []
    for d in sorted(EXCLUDE_DIRS):
        excl += ["-x", f"*/{d}/*"]
    rc, so, se, secs = run([lz, "--csv", *excl, str(target)], timeout=timeout, out_file=f)
    funcs, by_file = [], collections.defaultdict(lambda: {"nloc": 0, "ccn_total": 0, "ccn_max": 0, "functions": 0})
    for row in csv.reader(so.splitlines()):
        try:
            nloc, ccn = int(row[0]), int(row[1])
        except (ValueError, IndexError):
            continue
        path = os.path.relpath(row[6], target) if row[6].startswith(str(target)) else row[6].lstrip("./")
        b = by_file[path]
        b["nloc"] += nloc
        b["ccn_total"] += ccn
        b["ccn_max"] = max(b["ccn_max"], ccn)
        b["functions"] += 1
        if ccn >= 15:
            funcs.append({"file": path, "function": row[7], "ccn": ccn, "nloc": nloc, "line": row[9] if len(row) > 9 else None})
    return {"status": "ran", "seconds": secs, "output": str(f), "functions": sum(b["functions"] for b in by_file.values()),
            "complex_functions": len(funcs), "top_complex": sorted(funcs, key=lambda x: -x["ccn"])[:15],
            "_by_file": by_file}


def duplication(target: Path, out: Path, timeout) -> dict:
    if not shutil.which("npx"):
        return {"status": "missing"}
    d = out / "jscpd"
    ign = ",".join(f"**/{x}/**" for x in sorted(EXCLUDE_DIRS)) + ",**/*.min.js"
    rc, so, se, secs = run(["npx", "-y", "jscpd@4", "--min-tokens", "70", "--reporters", "json", "--output", str(d),
                            "--ignore", ign, "--silent", str(target)], timeout=timeout)
    try:
        rep = json.loads((d / "jscpd-report.json").read_text())
        tot = rep["statistics"]["total"]
        return {"status": "ran", "seconds": secs, "output": str(d / "jscpd-report.json"),
                "duplicated_lines": tot["duplicatedLines"], "lines": tot["lines"],
                "percentage": round(tot["percentage"], 2), "clones": tot["clones"]}
    except (OSError, ValueError, KeyError):
        return {"status": "failed", "seconds": secs, "error": (se or "")[-300:]}


def churn(target: Path, out: Path, since: str) -> dict:
    if not (target / ".git").exists() or not shutil.which("git"):
        return {"status": "skipped", "reason": "no git history"}
    f = out / "churn.txt"
    rc, so, se, secs = run(["git", "log", f"--since={since}", "--numstat", "--format=--%h %aI %an"], cwd=target, out_file=f)
    changes, lines, commits, authors = collections.Counter(), collections.Counter(), 0, set()
    for line in so.splitlines():
        if line.startswith("--"):
            commits += 1
            parts = line[2:].split(" ", 2)
            if len(parts) == 3:
                authors.add(parts[2])
            continue
        p = line.split("\t")
        if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
            changes[p[2]] += 1
            lines[p[2]] += int(p[0]) + int(p[1])
    return {"status": "ran", "seconds": secs, "output": str(f), "since": since, "commits": commits,
            "authors": len(authors), "top_changed": changes.most_common(15), "_changes": changes, "_lines": lines}


def hotspots(cx: dict, ch: dict) -> list:
    by_file = cx.get("_by_file") or {}
    changes = ch.get("_changes") or {}
    out = []
    for f, v in by_file.items():
        c = changes.get(f, 0)
        if c:
            out.append({"file": f, "score": c * v["ccn_total"], "changes": c, "ccn_total": v["ccn_total"],
                        "ccn_max": v["ccn_max"], "nloc": v["nloc"]})
    return sorted(out, key=lambda x: -x["score"])[:15]


def md(summary: dict) -> str:
    t = summary["tools"]
    inv = summary["inventory"]
    L = [f"# Scan summary — {summary['target']}", "",
         f"Generated {summary['generated_at']} by assess_scan.py. Raw scanner output is evidence for reviewers; "
         "nothing here is a finding until an agent has confirmed it in the code.", "",
         "## Inventory", "",
         f"- {inv['total_files']} source files, {inv['total_lines']:,} lines; stacks: {', '.join(inv['stacks']) or 'not detected'}",
         f"- Lockfiles: {', '.join(inv['lockfiles']) or 'none found'}; git history: {'yes' if inv['has_git'] else 'no'}",
         "- Lines by type: " + ", ".join(f"{k} {v:,}" for k, v in list(inv["lines_by_ext"].items())[:10]), "",
         "## Tools", "", "| Tool | Status | Result |", "|---|---|---|"]
    def row(name, d, res):
        L.append(f"| {name} | {d.get('status')} | {res} |")
    o = t["deps"].get("osv-scanner", {})
    row("osv-scanner", o, f"{o.get('vulnerable_packages', '—')} vulnerable packages, {o.get('advisories', '—')} advisories {o.get('by_severity', '')}" if o.get("status") == "ran" else o.get("error", ""))
    if "npm-audit" in t["deps"]:
        row("npm audit", t["deps"]["npm-audit"], str(t["deps"]["npm-audit"].get("by_severity", "")))
    row("trivy", t["deps"].get("trivy", {}), t["deps"].get("trivy", {}).get("output", ""))
    s = t["semgrep"]
    row("semgrep", s, f"{s.get('findings')} raw hits {s.get('by_severity', '')} — triage required" if s.get("status") == "ran" else s.get("error", ""))
    for mode in ("code", "history"):
        g = t["secrets"].get(mode, {}) if isinstance(t["secrets"], dict) else {}
        if g:
            row(f"gitleaks ({mode})", g, f"{g.get('hits')} hits (redacted) {g.get('by_rule', '')}" if g.get("status") == "ran" else g.get("reason", g.get("error", "")))
    if t["secrets"].get("status") == "missing":
        row("gitleaks", t["secrets"], "")
    c = t["complexity"]
    row("lizard", c, f"{c.get('functions')} functions, {c.get('complex_functions')} with complexity ≥ 15" if c.get("status") == "ran" else "")
    d = t["duplication"]
    row("jscpd", d, f"{d.get('percentage')}% duplicated ({d.get('clones')} clones)" if d.get("status") == "ran" else d.get("error", ""))
    g = t["churn"]
    row("git churn", g, f"{g.get('commits')} commits by {g.get('authors')} authors since {g.get('since')}" if g.get("status") == "ran" else g.get("reason", ""))
    if summary["hotspots"]:
        L += ["", "## Hotspots (changes × complexity)", "", "| File | Changes | Total complexity | Max | Score |", "|---|---|---|---|---|"]
        L += [f"| `{h['file']}` | {h['changes']} | {h['ccn_total']} | {h['ccn_max']} | {h['score']} |" for h in summary["hotspots"]]
    missing = [n for n, v in summary["status"].items() if v == "missing"]
    if missing:
        L += ["", f"Not installed (not run): {', '.join(missing)}. Install them and re-run for a fuller picture."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run code-health and security scanners for an assessment.")
    ap.add_argument("--target", required=True, help="path to the system's source code")
    ap.add_argument("--out", default="docs/assess/evidence")
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=730)).isoformat())
    ap.add_argument("--lockfile", default=None)
    ap.add_argument("--skip", default="", help="comma list: deps,semgrep,secrets,complexity,duplication,churn")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"ERROR: target {target} is not a directory")
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    lock = args.lockfile or next((str(target / f) for f in LOCKFILES[:1] if (target / f).is_file()), None)

    tools = {}
    inv = inventory(target)
    tools["deps"] = deps(target, out, lock, args.timeout) if "deps" not in skip else {"status": "skipped"}
    tools["semgrep"] = semgrep(target, out, args.timeout) if "semgrep" not in skip else {"status": "skipped"}
    tools["secrets"] = secrets(target, out, args.timeout) if "secrets" not in skip else {"status": "skipped"}
    tools["complexity"] = complexity(target, out, args.timeout) if "complexity" not in skip else {"status": "skipped"}
    tools["duplication"] = duplication(target, out, args.timeout) if "duplication" not in skip else {"status": "skipped"}
    tools["churn"] = churn(target, out, args.since) if "churn" not in skip else {"status": "skipped"}
    hs = hotspots(tools["complexity"], tools["churn"])
    for k in ("complexity", "churn"):
        for priv in [x for x in tools[k] if x.startswith("_")]:
            tools[k].pop(priv)

    status = {
        "osv-scanner": tools["deps"].get("osv-scanner", {}).get("status", "skipped") if isinstance(tools["deps"], dict) else "skipped",
        "trivy": tools["deps"].get("trivy", {}).get("status", "skipped") if isinstance(tools["deps"], dict) else "skipped",
        "semgrep": tools["semgrep"].get("status"),
        "gitleaks": tools["secrets"].get("status") or tools["secrets"].get("code", {}).get("status"),
        "lizard": tools["complexity"].get("status"), "jscpd": tools["duplication"].get("status"),
        "git": tools["churn"].get("status"),
    }
    summary = {"schema": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "target": str(target), "inventory": inv, "tools": tools, "hotspots": hs, "status": status}
    (out / "scan-summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "scan-summary.md").write_text(md(summary))
    print(f"OK: {inv['total_files']} files, {inv['total_lines']:,} lines; "
          + ", ".join(f"{k} {v}" for k, v in status.items()))
    print("ASSESS-SCAN: " + json.dumps({"out": str(out), "status": status}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
