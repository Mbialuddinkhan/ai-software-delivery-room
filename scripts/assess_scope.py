#!/usr/bin/env python3
"""Give each /assess reviewer a starting list of files instead of "read the repo".

Usage:
  python3 assess_scope.py --target <source path> [--evidence docs/assess/evidence]
                          [--max 120] [--out docs/assess/evidence]

v3.8 (efficiency). In the first full run each reviewer spent 150k–350k
tokens, mostly finding its way around the code. This ranks the source files
for each review area by path and content signals, scanner hits (Semgrep,
gitleaks, OSV front-end locations) and hotspots, and writes

  scope-process.txt  scope-architecture.txt  scope-security.txt  scope-operations.txt

one path per line, most relevant first. Reviewers start there and read other
files only to follow a call or a reference — the files are a starting point,
not a fence: anything they cite must still be read in full.
Prints `ASSESS-SCOPE: {json}`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXCLUDE = {".git", "node_modules", "dist", "build", "vendor", "venv", ".venv", "__pycache__", "target", "out",
           "coverage", ".next", "bin", "obj", "wwwroot/lib", ".idea", ".vscode"}
TEXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".py", ".java", ".kt", ".cs", ".go", ".rb", ".php", ".rs", ".swift",
        ".scala", ".vb", ".sql", ".html", ".vue", ".svelte", ".cshtml", ".razor", ".aspx", ".jsp", ".json", ".yml",
        ".yaml", ".xml", ".config", ".props", ".csproj", ".tf", ".bicep", ".sh", ".ps1", ".toml", ".ini", ".env",
        ".gradle", ".properties", ".md"}
NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Jenkinsfile", "Makefile", "Procfile"}

AREAS = {
    "security": {
        "path": r"auth|identity|login|logout|account|token|jwt|oauth|crypto|password|permission|role|polic|"
                r"middleware|filter|guard|cors|csrf|session|cookie|secret|key|cert|appsettings|\.env|config|"
                r"controller|endpoint|api|route|handler|upload|download|\.bicep$|\.tf$|docker",
        "content": r"\[Authorize|\[AllowAnonymous|authorize|authenticate|password|secret|token|jwt|bcrypt|hash|"
                   r"sql|query\(|exec\(|eval\(|innerHTML|redirect|cookie|cors|csrf|permission|role",
    },
    "operations": {
        "path": r"^\.github/|gitlab-ci|azure-pipelines|jenkinsfile|dockerfile|docker-compose|^infra/|terraform|"
                r"\.bicep$|\.tf$|helm|k8s|kubernetes|deploy|azure\.yaml|appsettings|global\.json|\.props$|"
                r"health|logging|serilog|nlog|program\.|startup\.|makefile|procfile|\.devcontainer",
        "content": r"healthcheck|health|logging|migrat|seed|retry|backup|monitor|telemetry|insights|"
                   r"environment|ASPNETCORE_ENVIRONMENT|NODE_ENV",
    },
    "architecture": {
        "path": r"program\.|startup\.|main\.|app\.|module|service|repositor|interface|infrastructure|"
                r"applicationcore|domain|core/|\.csproj$|package\.json$|pom\.xml$|go\.mod$|\.sln$|context|"
                r"dbcontext|config",
        "content": r"interface |class .*Service|AddScoped|AddSingleton|AddTransient|DbContext|@Injectable|"
                   r"createApp|express\(|FastAPI|@Module|HttpClient|fetch\(|axios",
    },
    "process": {
        "path": r"controller|endpoint|api/|page|view|handler|feature|service|entit|model|aggregate|order|basket|cart|"
                r"checkout|payment|invoice|user|customer|catalog|product|migration|seed|workflow|state",
        "content": r"status|state|enum |approve|reject|submit|checkout|order|invoice|payment|email|notify|"
                   r"if \(.*(role|status)|throw new|ValidationException|Guard\.",
    },
}


def walk(root: Path):
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not any(seg in EXCLUDE for seg in rel.split("/")[:-1]) \
                and not any(rel.startswith(x + "/") for x in EXCLUDE) \
                and (p.suffix.lower() in TEXT or p.name in NAMES) and p.stat().st_size < 400_000:
            yield p, rel


# Files every reviewer needs: entry points, manifests, CI, compose, infrastructure roots.
CORE = re.compile(r"(^|/)(program|startup|main|app|server|index)\.(cs|ts|js|py|go|java|kt)$|(^|/)directory\.packages\.props$|"
                  r"\.(csproj|sln)$|(^|/)(package|composer)\.json$|(^|/)(pom\.xml|go\.mod|requirements\.txt|pyproject\.toml)$|"
                  r"^\.github/workflows/|(^|/)docker-compose[^/]*\.ya?ml$|(^|/)dockerfile$|^azure\.yaml$|"
                  r"(^|/)main\.(bicep|tf)$|(^|/)appsettings\.json$|^global\.json$", re.IGNORECASE)
GENERATED = re.compile(r"(^|/)migrations?/|\.designer\.|modelsnapshot|\.g\.cs$|\.min\.(js|css)$|"
                       r"package-lock\.json$|yarn\.lock$|\.map$", re.IGNORECASE)


def hits(evidence: Path) -> dict:
    """area -> {path: bonus}: scanner hits count for security, hotspots for architecture."""
    out = {"security": {}, "architecture": {}}

    def bump(path, n=1, area="security"):
        if path:
            out[area][path] = out[area].get(path, 0) + n
    try:
        for r in json.loads((evidence / "semgrep.json").read_text()).get("results", []):
            bump(r.get("path"), 3)
    except (OSError, ValueError):
        pass
    for g in ("gitleaks-code.json",):
        try:
            for r in json.loads((evidence / g).read_text()) or []:
                bump(r.get("File"), 3)
        except (OSError, ValueError, TypeError):
            pass
    try:
        for lib in json.loads((evidence / "osv-frontend.json").read_text()).get("libraries", []):
            bump(str(lib.get("location", "")).split(":")[0], 2)
    except (OSError, ValueError):
        pass
    try:
        for h in json.loads((evidence / "scan-summary.json").read_text()).get("hotspots", []):
            bump(h.get("file"), 2, "architecture")
    except (OSError, ValueError):
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank source files per /assess review area.")
    ap.add_argument("--target", required=True)
    ap.add_argument("--evidence", default="docs/assess/evidence")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max", type=int, default=120)
    a = ap.parse_args()
    root = Path(a.target).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory")
        return 1
    ev = Path(a.evidence)
    out_dir = Path(a.out or a.evidence)
    out_dir.mkdir(parents=True, exist_ok=True)
    extra = hits(ev)
    files = []
    for p, rel in walk(root):
        try:
            head = p.read_text(errors="ignore")[:20000]
        except OSError:
            head = ""
        files.append((rel, head, rel.lower().startswith(("test", "tests/")) or "/test" in rel.lower()))
    res = {}
    for area, sig in AREAS.items():
        rp, rc = re.compile(sig["path"], re.IGNORECASE), re.compile(sig["content"], re.IGNORECASE)
        scored = []
        for rel, head, is_test in files:
            s = (4 if rp.search(rel) else 0) + min(4, len(rc.findall(head)) // 3) + extra.get(area, {}).get(rel, 0)
            if GENERATED.search(rel):
                s = s // 4
            if is_test:
                s = s // 3 if area != "operations" else s // 2
            if s > 0:
                scored.append((-s, rel))
        core = [rel for rel, _, is_test in files if CORE.search(rel) and not is_test][:30]
        top = core + [rel for _, rel in sorted(scored) if rel not in core][: max(0, a.max - len(core))]
        (out_dir / f"scope-{area}.txt").write_text(
            f"# Start here for the {area} review ({len(top)} of {len(files)} files, most relevant first).\n"
            "# A starting point, not a fence: follow calls and references into other files; read every file you cite.\n"
            + "\n".join(top) + "\n")
        res[area] = len(top)
    print(f"OK: {len(files)} files ranked; " + ", ".join(f"{k} {v}" for k, v in res.items()))
    print("ASSESS-SCOPE: " + json.dumps({"files": len(files), "scope": res, "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
