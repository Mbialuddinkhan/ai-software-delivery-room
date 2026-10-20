#!/usr/bin/env python3
"""Detect optional companion plugins/skills and record them for the run.

Usage: python3 detect_companions.py [--write .harness/companions.json]

ASDR never bundles third-party plugins; it detects what the host session
has installed and adapts. Output is a JSON map the orchestrator reads in
Phase 0 and every later phase. Exit code is always 0 — a missing companion
is a fact, not an error. WARN lines go to stderr and into the JSON.

Companions:
  uupm      UI UX Pro Max (nextlevelbuilder/ui-ux-pro-max-skill) — offline
            design-system generator. Used by the `design-system` stage.
  ponytail  DietrichGebert/ponytail — YAGNI ladder injected via hooks.
            SAFE ONLY when scoped to the generator subagent.
  graphify  Graphify-Labs/graphify — AST knowledge graph. Optional for
            brownfield entry and per-sprint `--update`.
  rtk       enixCode/rtk-plugin — lossy shell-output compression. Detected
            so the orchestrator can warn: it rewrites the evaluator's
            evidence commands (pytest, jest, playwright, git, grep, cat).
  cloud     (v3.8) the cloud vendors' own agent tooling and CLIs, used by
            devops and security instead of ASDR re-implementing cloud
            knowledge: AWS MCP Server, Azure Skills plugin / Azure MCP
            Server, Google Cloud MCP servers, HashiCorp Terraform MCP, and
            the aws / az / gcloud / terraform / tofu / docker / kubectl CLIs.
            Found by name in MCP and plugin configuration; the orchestrator
            also checks its own tool list (mcp__* names). Never installed by
            ASDR — the user adds them.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"
PLUGINS = CLAUDE / "plugins"
CWD = Path.cwd()

REQUIRED_PONYTAIL_MATCHER = r"^generator$"


def _glob_first(roots, pattern, max_depth=8):
    """First match of a glob pattern under any root, bounded depth."""
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for hit in root.rglob(pattern):
                if len(hit.relative_to(root).parts) <= max_depth:
                    return hit
        except (PermissionError, OSError):
            continue
    return None


def detect_uupm():
    env = os.environ.get("UUPM_SEARCH")
    if env and Path(env).is_file():
        return {"installed": True, "search_py": env, "source": "env:UUPM_SEARCH"}
    roots = [CWD / ".claude" / "skills", CLAUDE / "skills", PLUGINS]
    hit = _glob_first(roots, "ui-ux-pro-max/scripts/search.py")
    if hit:
        version = None
        sj = _glob_first([hit.parents[2]], "skill.json", 3)
        if sj:
            try:
                version = json.loads(sj.read_text()).get("version")
            except Exception:
                pass
        return {"installed": True, "search_py": str(hit), "version": version,
                "source": str(hit.parents[2])}
    return {"installed": False}


def detect_ponytail():
    hit = _glob_first([PLUGINS, CLAUDE / "skills"], "ponytail-subagent.js") \
        or _glob_first([PLUGINS, CLAUDE / "skills"], "ponytail/SKILL.md")
    if not hit:
        return {"installed": False}
    matcher = os.environ.get("PONYTAIL_SUBAGENT_MATCHER", "")
    scoped = matcher.strip() == REQUIRED_PONYTAIL_MATCHER
    return {"installed": True, "path": str(hit),
            "subagent_matcher": matcher or None, "scoped_to_generator": scoped}


def detect_graphify():
    cli = shutil.which("graphify")
    mod = subprocess.run([sys.executable, "-c", "import graphify"],
                         capture_output=True).returncode == 0
    skill = _glob_first([CWD / ".claude" / "skills", CLAUDE / "skills"], "graphify/SKILL.md", 3)
    return {"installed": bool(cli or mod), "cli": cli, "python_module": mod,
            "skill": str(skill) if skill else None}


def detect_rtk():
    bin_hit = _glob_first([PLUGINS], "rtk-plugin/rtk/rtk*", 6) \
        or _glob_first([PLUGINS], "rtk-plugin/**/dispatch.mjs", 6)
    return {"installed": bool(bin_hit), "path": str(bin_hit) if bin_hit else None}


CLOUD_TOOLS = {
    "aws": r"aws-mcp|awslabs|\.api\.aws|aws-api-mcp|aws-knowledge|aws-skills|agent-toolkit-for-aws",
    "azure": r"@azure/mcp|azure-mcp|azure-skills|azure/mcp|foundry-mcp",
    "gcp": r"googleapis\.com/mcp|gcloud-mcp|google-cloud-mcp|cloud\.google\.com/mcp|mcp\.googleapis",
    "terraform": r"terraform-mcp|hashicorp/terraform|terraform_mcp",
}
CLOUD_CLIS = {"aws": "aws", "azure": "az", "gcp": "gcloud", "terraform": "terraform"}


def detect_cloud():
    import re as _re
    sources = [CWD / ".mcp.json", HOME / ".claude.json", CLAUDE / "settings.json", CWD / ".claude" / "settings.json",
               CWD / ".vscode" / "mcp.json"]
    texts = []
    for f in sources:
        try:
            if f.is_file() and f.stat().st_size < 5_000_000:
                texts.append((str(f), f.read_text(errors="ignore")))
        except OSError:
            continue
    names = []
    for root in (PLUGINS, CLAUDE / "skills", CWD / ".claude" / "skills", CWD / ".github" / "plugins"):
        if root.is_dir():
            try:
                for d in root.rglob("*"):
                    if d.is_dir() and len(d.relative_to(root).parts) <= 4:
                        names.append(str(d))
            except (PermissionError, OSError):
                continue
    out = {}
    for vendor, pat in CLOUD_TOOLS.items():
        rx = _re.compile(pat, _re.IGNORECASE)
        found = sorted({src for src, t in texts if rx.search(t)} | {n for n in names if rx.search(n)})[:5]
        out[vendor] = {"cli": shutil.which(CLOUD_CLIS[vendor]), "agent_tools": found}
    out["terraform"]["tofu"] = shutil.which("tofu")
    out["docker"] = shutil.which("docker")
    out["kubectl"] = shutil.which("kubectl")
    out["note"] = ("Also look for mcp__aws*, mcp__azure*, mcp__google*/gcloud*, mcp__terraform* in your own tool "
                   "list: hosted MCP servers may not appear in local configuration.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", default=".harness/companions.json")
    args = ap.parse_args()

    result = {
        "uupm": detect_uupm(),
        "ponytail": detect_ponytail(),
        "graphify": detect_graphify(),
        "rtk": detect_rtk(),
        "cloud": detect_cloud(),
        "warnings": [],
    }

    pt = result["ponytail"]
    if pt["installed"] and not pt["scoped_to_generator"]:
        result["warnings"].append(
            "WARN: ponytail is installed but PONYTAIL_SUBAGENT_MATCHER is not "
            f"'{REQUIRED_PONYTAIL_MATCHER}'. Its SubagentStart hook will inject the "
            "YAGNI ladder into EVERY subagent, including critic, judge, "
            "security-compliance and the evaluator. Set it in "
            ".claude/settings.json → \"env\" (see docs/COMPANIONS.md) and restart "
            "the session, or run `/plugin disable ponytail` before Phase 1.")
    if result["rtk"]["installed"]:
        result["warnings"].append(
            "WARN: rtk-plugin is installed. It rewrites pytest/jest/playwright/git/"
            "grep/cat output — the evaluator's evidence path. ASDR requires all "
            "measured numbers to come from emit_facts.py (python3 is not "
            "rewritten); evaluator and stage-qa must never read raw shell "
            "output as evidence while RTK is active. Consider "
            "`/plugin disable rtk-plugin@enix` for ASDR runs.")

    for w in result["warnings"]:
        print(w, file=sys.stderr)

    out = Path(args.write)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
