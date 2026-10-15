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
import re
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
            ".pas", ".dpr", ".frm", ".bas", ".cls",
            # server-rendered views and project files hold real logic in older stacks (found in the eShopOnWeb run)
            ".cshtml", ".razor", ".aspx", ".ascx", ".master", ".asp", ".jsp", ".jspx", ".erb", ".twig", ".cfm",
            ".xaml", ".kts", ".groovy", ".dart", ".pl", ".config", ".properties", ".gradle", ".csproj", ".vbproj"}
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
            with p.open(errors="ignore") as fh:
                n = sum(1 for _ in fh)
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


def nuget_packages(target: Path) -> dict:
    """Direct NuGet packages and versions from Directory.Packages.props, *.csproj / *.vbproj and
    packages.config — OSV-Scanner only reads NuGet lock files, which most .NET repos do not commit."""
    import re as _re
    pk = {}
    for p in walk(target):
        if p.name == "Directory.Packages.props" or p.suffix in (".csproj", ".vbproj", ".fsproj") or p.name == "packages.config":
            try:
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            for m in _re.finditer(r'<(?:PackageVersion|PackageReference|package)\s+(?:Include|id)="([^"]+)"[^>]*?'
                                  r'(?:Version|version)="([^"]+)"', txt):
                name, ver = m.group(1), m.group(2).strip("[]() ").split(",")[0].strip()
                if ver and not ver.startswith("$"):
                    pk.setdefault(name, ver)
            for m in _re.finditer(r'<PackageReference\s+Include="([^"]+)"\s*>\s*<Version>([^<]+)</Version>', txt):
                pk.setdefault(m.group(1), m.group(2).strip("[]() ").split(",")[0].strip())
    return pk


def osv_parse(so: str, secs, f: Path) -> dict:
    d = json.loads(so)
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
    return {"status": "ran", "seconds": secs, "output": str(f), "vulnerable_packages": len(pkgs),
            "advisories": sum(x["advisories"] for x in names), "by_severity": dict(sev),
            "top": sorted(names, key=lambda x: -(x["max_cvss"] or 0))[:15]}


def deps(target: Path, out: Path, lockfile, timeout) -> dict:
    res = {}
    osv = tool("osv-scanner")
    if osv:
        f = out / "osv.json"
        cmd = [osv, "scan", "source", "--format", "json"]
        cmd += ["-L", str(lockfile)] if lockfile else ["-r", str(target)]
        rc, so, se, secs = run(cmd, timeout=timeout, out_file=f)
        if not (so or "").strip():
            # exit 128 "No package sources found": nothing was scanned — never report that as "0 vulnerable"
            res["osv-scanner"] = {"status": "no-manifests" if "No package sources" in (se or "") else "failed",
                                  "seconds": secs, "error": (se or "no output")[-300:].strip()}
            nu = nuget_packages(target)
            if nu:
                nd = out / "nuget"
                nd.mkdir(parents=True, exist_ok=True)
                lock = nd / "packages.lock.json"
                lock.write_text(json.dumps({"version": 1, "dependencies": {"any": {
                    n: {"type": "Direct", "requested": f"[{v}, )", "resolved": v} for n, v in sorted(nu.items())}}}, indent=1))
                rc2, so2, se2, secs2 = run([osv, "scan", "source", "--format", "json", "-L", str(lock)],
                                           timeout=timeout, out_file=f)
                try:
                    r = osv_parse(so2, secs2, f) if so2.strip() else {"status": "failed", "error": (se2 or "")[-300:]}
                except ValueError:
                    r = {"status": "failed", "error": (se2 or "no JSON output")[-300:]}
                r.update({"source": "NuGet packages read from .csproj / Directory.Packages.props (direct packages only; "
                                    "transitive ones need a restore and packages.lock.json)",
                          "packages_scanned": len(nu), "manifest": str(lock)})
                res["osv-scanner"] = r
        else:
            try:
                res["osv-scanner"] = osv_parse(so, secs, f)
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


CODE_KEYS = {"fragment", "lines", "Match", "Secret", "Line"}


def scrub_code(f: Path) -> int:
    """Drop copied source text from a scanner's JSON (jscpd clone fragments,
    Semgrep matched lines, any unredacted gitleaks match). Reviewers read the
    code at path:line; a copy in the evidence pack can carry a password into
    the report folder. Returns how many fields were removed."""
    try:
        d = json.loads(f.read_text())
    except (OSError, ValueError):
        return 0
    n = 0

    def walk(x):
        nonlocal n
        if isinstance(x, dict):
            for k in [k for k in x if k in CODE_KEYS and isinstance(x[k], str)]:
                del x[k]
                n += 1
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d)
    f.write_text(json.dumps(d, indent=1))
    return n


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
    scrub_code(f)
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
            "note": "raw hits — triage each in code before it becomes a finding (precision was 40% to over 90% in trials)"}


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
        scrub_code(f)          # --redact masks the secret; the copied source line goes too
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
    scrub_code(d / "jscpd-report.json")
    try:
        rep = json.loads((d / "jscpd-report.json").read_text())
        tot = rep["statistics"]["total"]
        return {"status": "ran", "seconds": secs, "output": str(d / "jscpd-report.json"),
                "duplicated_lines": tot["duplicatedLines"], "lines": tot["lines"],
                "percentage": round(tot["percentage"], 2), "clones": tot["clones"]}
    except (OSError, ValueError, KeyError):
        return {"status": "failed", "seconds": secs, "error": (se or "")[-300:]}


NPM_NAME = {"twitter-bootstrap": "bootstrap", "jquery-validate": "jquery-validation",
            "jquery.validate": "jquery-validation", "jquery.validation.unobtrusive": "jquery-validation-unobtrusive",
            "jquery-validation-unobtrusive": "jquery-validation-unobtrusive", "jquery.min": "jquery"}
CDN = [
    re.compile(r"cdnjs\.cloudflare\.com/ajax/libs/(?P<n>[\w.\-]+)/(?P<v>\d[\w.\-]*)/"),
    re.compile(r"cdn\.jsdelivr\.net/npm/(?P<n>@?[\w.\-/]+?)@(?P<v>\d[\w.\-]*)"),
    re.compile(r"unpkg\.com/(?P<n>@?[\w.\-/]+?)@(?P<v>\d[\w.\-]*)"),
    re.compile(r"(?:stackpath|maxcdn|netdna)\.bootstrapcdn\.com/(?P<n>bootstrap|font-awesome)/(?P<v>\d[\w.\-]*)/"),
    re.compile(r"ajax\.aspnetcdn\.com/ajax/(?P<n>[\w.\-]+?)/(?P<v>\d[\w.\-]*)/"),
    re.compile(r"(?:ajax\.aspnetcdn\.com/ajax/jquery|code\.jquery\.com)/(?P<n>jquery)-(?P<v>\d[\w.\-]*?)(?:\.min|\.slim)*\.js"),
]
PAGE_EXT = {".html", ".htm", ".cshtml", ".razor", ".aspx", ".ascx", ".master", ".jsp", ".php", ".vue", ".erb", ".hbs",
            ".ejs", ".twig", ".vbhtml"}


def frontend(target: Path, out: Path, timeout) -> dict:
    """Front-end libraries the dependency scanners do not see: libman.json and
    CDN <script>/<link> tags. Each is looked up in OSV (npm); no network means
    the list is kept and marked unchecked."""
    libs = []
    for p in walk(target):
        rel = str(p.relative_to(target))
        if p.name == "libman.json":
            try:
                text = p.read_text(errors="ignore")
                for lib in json.loads(text).get("libraries", []):
                    name, _, ver = str(lib.get("library", "")).rpartition("@")
                    if name and ver:
                        line = next((i for i, l in enumerate(text.splitlines(), 1) if lib["library"] in l), 1)
                        libs.append({"name": NPM_NAME.get(name, name), "version": ver, "source": "libman",
                                     "location": f"{rel}:{line}", "integrity": None})
            except (OSError, ValueError, AttributeError):
                pass
        elif p.suffix.lower() in PAGE_EXT:
            text = p.read_text(errors="ignore")
            for tag in re.finditer(r"<(?:script|link)\b[^>]*>", text, re.IGNORECASE | re.DOTALL):
                url = re.search(r"(?:src|href)\s*=\s*[\"']([^\"']+)", tag.group(0))
                if not url:
                    continue
                for pat in CDN:
                    m = pat.search(url.group(1))
                    if m:
                        n = m.group("n").lower()
                        libs.append({"name": NPM_NAME.get(n, n), "version": m.group("v").rstrip("."), "source": "cdn",
                                     "location": f"{rel}:{text.count(chr(10), 0, tag.start()) + 1}",
                                     "integrity": "integrity=" in tag.group(0).lower()})
                        break
    if not libs:
        return {"status": "none-found"}
    uniq = sorted({(x["name"], x["version"]) for x in libs})
    vulns, status = {}, "ran"
    try:
        import urllib.request
        body = json.dumps({"queries": [{"package": {"name": n, "ecosystem": "npm"}, "version": v} for n, v in uniq]}).encode()
        req = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=min(timeout, 60)) as r:
            res = json.loads(r.read().decode()).get("results", [])
        for (n, v), r in zip(uniq, res):
            vulns[f"{n}@{v}"] = [x.get("id") for x in r.get("vulns", [])]
    except Exception as ex:  # offline, proxy, API change: keep the list
        status, vulns = "listed-unchecked", {}
        err = str(ex)[:200]
    for x in libs:
        x["advisories"] = vulns.get(f"{x['name']}@{x['version']}") if status == "ran" else None
    f = out / "osv-frontend.json"
    f.write_text(json.dumps({"checked_against": "OSV (npm)" if status == "ran" else None,
                             "queried_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds") if status == "ran" else None,
                             "libraries": libs}, indent=1))
    vulnerable = sorted({f"{x['name']}@{x['version']}" for x in libs if x["advisories"]})
    res = {"status": status, "output": str(f), "libraries": len(uniq), "from_cdn": sum(1 for x in libs if x["source"] == "cdn"),
           "cdn_without_integrity": sum(1 for x in libs if x["source"] == "cdn" and x["integrity"] is False),
           "vulnerable": vulnerable, "advisories": sum(len(v) for v in vulns.values())}
    if status != "ran":
        res["error"] = err
    return res


def churn(target: Path, out: Path, since: "str | None") -> dict:
    if not (target / ".git").exists() or not shutil.which("git"):
        return {"status": "skipped", "reason": "no git history"}
    last = run(["git", "log", "-1", "--format=%cI"], cwd=target)[1].strip()
    if not since:
        # two years back from the LAST commit, not from today: an archived or frozen legacy system
        # would otherwise show no activity and no hotspots (found in the eShopOnWeb run)
        try:
            since = (dt.datetime.fromisoformat(last).date() - dt.timedelta(days=730)).isoformat()
        except ValueError:
            since = (dt.date.today() - dt.timedelta(days=730)).isoformat()
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
    return {"status": "ran", "seconds": secs, "output": str(f), "since": since, "last_commit": last[:10], "commits": commits,
            "authors": len(authors), "top_changed": changes.most_common(15), "_changes": changes, "_lines": lines}


def hotspots(cx: dict, ch: dict) -> list:
    by_file = cx.get("_by_file") or {}
    changes = ch.get("_changes") or {}
    out = []
    for f, v in by_file.items():
        c = changes.get(f, 0)
        if c >= 2:       # changed once is not "changed often": the score would only measure file size
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
    if o.get("status") == "ran":
        res = (f"{o.get('vulnerable_packages', '—')} vulnerable packages, {o.get('advisories', '—')} advisories "
               f"{o.get('by_severity', '')}" + (f" — {o['packages_scanned']} {o['source']}" if o.get("source") else ""))
    elif o.get("status") == "no-manifests":
        res = "found no dependency file it can read — dependencies NOT checked (add a lock file, or check them by hand)"
    else:
        res = o.get("error", "")
    row("osv-scanner", o, res)
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
    row("git churn", g, f"{g.get('commits')} commits by {g.get('authors')} authors from {g.get('since')} to the last commit "
                         f"({g.get('last_commit')})" if g.get("status") == "ran" else g.get("reason", ""))
    fe = t.get("frontend", {})
    if fe.get("status") in ("ran", "listed-unchecked"):
        row("front-end libraries (OSV npm)", fe,
            f"{fe.get('libraries')} libraries ({fe.get('from_cdn')} loaded from a CDN, {fe.get('cdn_without_integrity')} "
            f"without an integrity check); "
            + (f"vulnerable: {', '.join(fe['vulnerable']) or 'none'}" if fe.get("status") == "ran"
               else "NOT checked for advisories (no network) — check the versions by hand"))
    elif fe.get("status") == "none-found":
        row("front-end libraries", fe, "no libman.json or CDN script/style tags found")
    if summary["hotspots"]:
        L += ["", "## Hotspots (changes × complexity, files changed at least twice)", "", "| File | Changes | Total complexity | Max | Score |", "|---|---|---|---|---|"]
        L += [f"| `{h['file']}` | {h['changes']} | {h['ccn_total']} | {h['ccn_max']} | {h['score']} |" for h in summary["hotspots"]]
    L += ["", "## What these scanners do not cover", "",
          "Say this in the report's limits. Reviewers found each of these by reading the code, not from a scanner:", "",
          "- secrets kept as constants in code (a hard-coded signing key or default password) — gitleaks matches "
          "patterns and missed them in trials;",
          "- authorisation and business-logic flaws (one customer reading another's order, a price the browser sets);",
          "- infrastructure templates (Bicep, Terraform, CloudFormation) unless trivy ran;",
          "- indirect (transitive) packages when there is no lock file;",
          "- anything that only shows at run time: headers, cookies, configuration in the live environment."]
    missing = [n for n, v in summary["status"].items() if v == "missing"]
    if missing:
        L += ["", f"Not installed (not run): {', '.join(missing)}. Install them and re-run for a fuller picture."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run code-health and security scanners for an assessment.")
    ap.add_argument("--target", required=True, help="path to the system's source code")
    ap.add_argument("--out", default="docs/assess/evidence")
    ap.add_argument("--since", default=None, help="churn window start (default: two years before the last commit)")
    ap.add_argument("--lockfile", default=None)
    ap.add_argument("--skip", default="", help="comma list: deps,semgrep,secrets,complexity,duplication,churn,frontend")
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
    tools["frontend"] = frontend(target, out, args.timeout) if "frontend" not in skip else {"status": "skipped"}
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
        "git": tools["churn"].get("status"), "osv-frontend": tools["frontend"].get("status"),
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
