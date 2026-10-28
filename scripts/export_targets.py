#!/usr/bin/env python3
"""Export ASDR to OpenAI Codex CLI and Google Gemini CLI (v4.1).

Usage:
  python3 export_targets.py codex  [--out DIR] [--install] [--root DIR] [--plan P --models opus=ID,sonnet=ID,...]
  python3 export_targets.py gemini [--out DIR] [--install]                [--plan P --models opus=ID,sonnet=ID,...]
  python3 export_targets.py both   [--out DIR]

ASDR's skills already use the open Agent Skills format (SKILL.md), so both CLIs
can run them; its 19 roles are Claude Code subagents and are converted:

  codex   a bundle with a portable plugin.json, the 8 skills (renamed asdr,
          asdr-discover, ... so they cannot clash with other skills), one
          custom-agent TOML per role (agents/asdr-<role>.toml: name,
          description, developer_instructions) and ASDR's scripts and
          templates. Codex reads files through its shell, so every role keeps
          it; a role that has no Bash in Claude is told to use it only to
          read and search.
          --install copies the bundle to --root (default ~/.asdr/codex: that
          is PLUGIN_ROOT), the skills to ~/.agents/skills and the agents to
          ~/.codex/agents ($CODEX_HOME/agents). Codex plugins cannot ship
          custom agents, so the agents are installed as files.
  gemini  a Gemini CLI extension "asdr": gemini-extension.json, GEMINI.md,
          the skills, one subagent per role (agents/asdr-<role>.md with the
          Claude tools mapped to Gemini's: read_file, write_file, replace,
          run_shell_command, glob, grep_search, google_web_search, web_fetch),
          /asdr and /asdr:<skill> commands, and the scripts and templates.
          --install runs Gemini's own installer when the gemini CLI is on
          PATH (`gemini extensions install <dir> --consent`; an ASDR
          extension already installed is uninstalled first). Running
          --install is the consent to Gemini's third-party notice; Gemini
          still asks the user to trust the folder, and only the user answers.

Every exported skill and agent starts with a short host adapter: where
PLUGIN_ROOT is, how to invoke a role (spawn the Codex custom agent / delegate
to the Gemini subagent asdr-<role>), how to ask the user, and which Claude-only
features (private Artifacts, `claude plugin`, companion plugins) to skip.

Models: by default every role inherits the session's model, so nothing names
a model that may not exist. With --models (host model ids for ASDR's opus,
sonnet, haiku and fable tiers) each role gets the model --plan gives it
(economy, balanced or maximum; default balanced).

Install never overwrites a skill, agent or folder ASDR did not write (each
carries a marker); --force replaces foreign asdr* skill folders and
asdr-*.toml agent files only, never a folder given as --root or --out. A
--root that is, or contains, your home, ~/.codex or ~/.agents/skills is
refused. Nothing is published anywhere.
Last line: EXPORT: {json}.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
sys.path.insert(0, str(HERE))
import model_plan as mp  # noqa: E402

MARKER = ".asdr-export.json"
AGENT_MARK = "exported by ASDR"
RUNTIME = ["scripts", "templates", "docs", "CHANGELOG.md", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]
SKIP = {"__pycache__", ".DS_Store"}
TIERS = ("opus", "sonnet", "haiku", "fable")
GEMINI_TOOLS = {"Read": ["read_file", "read_many_files", "list_directory"], "Write": ["write_file"],
                "Edit": ["replace"], "Bash": ["run_shell_command"], "Glob": ["glob"], "Grep": ["grep_search"],
                "WebSearch": ["google_web_search"], "WebFetch": ["web_fetch"]}
GEMINI_LIMITS = {"generator": (300, 240), "evaluator": (200, 150), "devops": (150, 90), "documentation": (150, 90),
                 "security-compliance": (120, 60), "panelist": (15, 10)}   # (max_turns, timeout_mins)
GEMINI_DEFAULT_LIMITS = (80, 45)
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ── reading ASDR ─────────────────────────────────────────────────────────────

def split_front(text: str):
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    return text[3:end].strip("\n"), text[end + 4:].lstrip("\n")


def front_value(front: str, key: str) -> str:
    """A top-level key of the simple YAML ASDR uses: inline values and folded (>) blocks."""
    lines = front.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(rf"^{re.escape(key)}:\s*(.*)$", ln)
        if not m:
            continue
        v = m.group(1).strip()
        if v in (">", "|", ">-", "|-"):
            block = []
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith((" ", "\t")):
                    break
                block.append(nxt.strip())
            return "\n".join(block).strip()
        return v.strip().strip('"').strip("'")
    return ""


def clean_description(desc: str, limit: int = 600) -> str:
    desc = re.sub(r"<example>.*?</example>", " ", desc, flags=re.S)
    desc = re.sub(r"\s+", " ", desc).strip()
    if len(desc) > limit:
        cut = desc[:limit].rsplit(". ", 1)[0]
        desc = (cut if len(cut) > limit // 2 else desc[:limit].rsplit(" ", 1)[0]) + "."
    return desc


def parse_tools(front: str):
    """An agent's tools: a flow list, a block list, or None when there is no tools key (every tool)."""
    raw = front_value(front, "tools")
    if raw:
        try:
            return json.loads(raw)
        except ValueError:
            return [x.strip().strip('"').strip("'") for x in raw.strip("[]").split(",") if x.strip()]
    lines = front.split("\n")
    for i, ln in enumerate(lines):
        if re.match(r"^tools:\s*$", ln):
            out = []
            for nxt in lines[i + 1:]:
                m = re.match(r"^\s+-\s*(.+?)\s*$", nxt)
                if not m:
                    break
                out.append(m.group(1).strip('"').strip("'"))
            return out
    return None


def read_agents() -> list:
    out = []
    for p in sorted((SRC / "agents").glob("*.md")):
        front, body = split_front(p.read_text())
        name = front_value(front, "name") or p.stem
        tools = parse_tools(front)
        if tools is not None and not isinstance(tools, list):
            raise SystemExit(f"ERROR: agents/{p.name}: tools must be a list")
        out.append({"role": name, "description": clean_description(front_value(front, "description")),
                    "model": front_value(front, "model"), "tools": tools, "body": body})
    return out


def read_skills() -> list:
    out = []
    for d in sorted(p for p in (SRC / "skills").iterdir() if (p / "SKILL.md").is_file()):
        front, body = split_front((d / "SKILL.md").read_text())
        name = front_value(front, "name") or d.name
        out.append({"src": d, "name": name, "export": exported_skill_name(name),
                    "description": clean_description(front_value(front, "description"), 1000), "body": body})
    return out


def exported_skill_name(name: str) -> str:
    return name if name == "asdr" else f"asdr-{name}"


def version() -> str:
    return json.loads((SRC / ".claude-plugin" / "plugin.json").read_text())["version"]


# ── adapters ─────────────────────────────────────────────────────────────────

def model_sentence(models: dict | None, plan: str) -> str:
    if not models:
        return ("Skip the `model:` step: every `asdr-<role>` agent inherits your session's model (this export "
                "names no model). `model_plan.py` still records the plan the user chose.")
    shown = ", ".join(f"{k}→{v}" for k, v in models.items())
    return (f"Skip the `model:` step: each `asdr-<role>` agent already runs on the model the **{plan}** plan gives "
            f"it ({shown}). To change plan, re-export with `--plan`.")


def skill_adapter(host: str, root_text: str, skills: list, models, plan) -> str:
    names = ", ".join(f"`{s['export']}`" for s in skills)
    if host == "codex":
        invoke = ("**Invoking an agent** (\"invoke the critic\", \"run this stage via ...\") means spawning a subagent "
                  "with `agent_type` set to the custom agent `asdr-<role>` (for example `asdr-critic`, `asdr-stage-qa`), "
                  "started without your conversation (fork none of it) and with every input path in its message, "
                  "then waiting for its result. Agents share none of your context.")
        ask = ("**AskUserQuestion** means: ask the user in the chat, numbered options with the recommended one "
               "first, and wait for the answer before going on.")
        where = "Codex CLI"
    else:
        invoke = ("**Invoking an agent** means delegating to the subagent `asdr-<role>` (for example `@asdr-critic`, "
                  "`@asdr-stage-qa`) with the same inputs, then waiting for its result. Subagents share none of your "
                  "context and cannot call each other: you, the orchestrator, run every step.")
        ask = "**AskUserQuestion** means the `ask_user` tool (or, if it is unavailable, a question in the chat)."
        where = "Gemini CLI"
    return "\n".join([
        f"> **Running in {where} (ASDR {version()} export).** This skill was written for Claude Code. Read it with "
        "these substitutions:",
        f"> - **PLUGIN_ROOT** is {root_text}. It contains `scripts/` and `templates/`; use it wherever the text "
        "says to resolve PLUGIN_ROOT.",
        f"> - **Skills** are installed as {names}. A path `skills/<name>/` in this text or in a script's output "
        "is `skills/asdr-<name>/` under PLUGIN_ROOT (`skills/asdr/` keeps its name).",
        f"> - {invoke}",
        f"> - **Model per role:** {model_sentence(models, plan)}",
        f"> - {ask}",
        "> - **Cost log:** pass `--usage` with the token counts the CLI reports for the agent run, or leave it out.",
        "> - **Claude-only features** are not available here: private Artifacts, `claude plugin ...` commands, "
        "`/reload-plugins`, and companion plugins such as ui-ux-pro-max. Skip those steps; the files written under "
        "`docs/` are the deliverables. To update ASDR, re-run `scripts/export_targets.py` from a newer checkout.",
        "",
    ])


def agent_adapter(host: str, shell: bool = True) -> str:
    who = "a Codex custom agent" if host == "codex" else "a Gemini CLI subagent"
    tools = ("Read / Write / Edit mean reading, creating and editing files; Bash means running shell commands; "
             "Glob / Grep mean finding and searching files; WebSearch / WebFetch mean web search and fetching a page "
             "(when available)") if host == "codex" else (
             "Read = read_file, Write = write_file, Edit = replace, Bash = run_shell_command, Glob = glob, "
             "Grep = grep_search, WebSearch = google_web_search, WebFetch = web_fetch")
    return (f"> You are running as {who} exported from ASDR {version()}. The tool names below are Claude Code's: "
            f"{tools}. Paths such as `.harness/` and `docs/` are relative to the project folder you were started "
            "in. Do only your role; the orchestrator runs every other step."
            + ("" if shell or host != "codex" else
               " Your role has no shell in Claude Code: use shell commands here only to read and search files "
               "(for example cat, ls, rg), never to run, install or change anything.")
            + "\n\n")


def adapt_body(body: str) -> str:
    """Point cross-skill paths at the renamed skills."""
    return re.sub(r"skills/(?!asdr/)([a-z][a-z0-9-]*)/SKILL\.md", lambda m: f"skills/{exported_skill_name(m.group(1))}/SKILL.md", body)


def skill_text(s: dict, host: str, root_text: str, skills: list, models, plan) -> str:
    front = (f"---\nname: {s['export']}\ndescription: {json.dumps(s['description'], ensure_ascii=False)}\nmetadata:\n"
             f"  version: \"{version()}\"\n  source: ai-software-delivery-room ({host} export)\n---\n\n")
    body = adapt_body(s["body"])
    m = re.match(r"(# [^\n]*\n)", body)
    adapter = skill_adapter(host, root_text, skills, models, plan)
    return front + (m.group(1) + "\n" + adapter + body[m.end():] if m else adapter + "\n" + body)


def host_models(spec: str | None) -> dict | None:
    if not spec:
        return None
    out = {}
    for part in spec.split(","):
        if not part.strip():
            continue
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if k not in TIERS or not v:
            raise SystemExit(f"ERROR: --models takes tier=model pairs for {', '.join(TIERS)}; got {part!r}")
        out[k] = v
    return out


def role_model(role: str, models: dict | None, plan: str) -> str | None:
    if not models:
        return None
    tier = mp.mapping(plan).get(role, "sonnet")
    return models.get(tier) or models.get("opus" if tier == "fable" else "sonnet")


# ── writing ──────────────────────────────────────────────────────────────────

def copy_runtime(dest: Path):
    for item in RUNTIME:
        s = SRC / item
        if s.is_dir():
            shutil.copytree(s, dest / item, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP))
        elif s.is_file():
            shutil.copy2(s, dest / item)
    (dest / ".claude-plugin").mkdir(exist_ok=True)
    shutil.copy2(SRC / ".claude-plugin" / "plugin.json", dest / ".claude-plugin" / "plugin.json")  # check_updates.py


def write_skills(dest: Path, host: str, root_text: str, skills: list, models, plan):
    for s in skills:
        d = dest / "skills" / s["export"]
        shutil.copytree(s["src"], d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP, "SKILL.md"))
        (d / "SKILL.md").write_text(skill_text(s, host, root_text, skills, models, plan))
        write_marker(d, host)


def write_marker(d: Path, host: str):
    (d / MARKER).write_text(json.dumps({"exported_by": "ASDR", "version": version(), "host": host}) + "\n")


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)   # a JSON string is a valid TOML basic string


def codex_agent(a: dict, models, plan) -> str:
    shell = a["tools"] is None or "Bash" in a["tools"]
    instr = agent_adapter("codex", shell) + a["body"]
    if "'''" in instr:
        raise SystemExit(f"ERROR: {a['role']} contains ''' and cannot be a TOML literal string")
    lines = [f"# {AGENT_MARK} {version()} from agents/{a['role']}.md — re-export instead of editing",
             f"name = {toml_str('asdr-' + a['role'])}", f"description = {toml_str(a['description'])}"]
    m = role_model(a["role"], models, plan)
    if m:
        lines.append(f"model = {toml_str(m)}")
    lines.append("developer_instructions = '''\n" + instr.rstrip() + "\n'''")
    return "\n".join(lines) + "\n"


def gemini_agent(a: dict, models, plan) -> str:
    tools = []
    for x in a["tools"] or []:
        for g in GEMINI_TOOLS.get(x, []):
            if g not in tools:
                tools.append(g)
    turns, mins = GEMINI_LIMITS.get(a["role"], GEMINI_DEFAULT_LIMITS)
    m = role_model(a["role"], models, plan)
    front = [f"name: asdr-{a['role']}", f"description: {json.dumps(a['description'], ensure_ascii=False)}", "kind: local",
             ] + (["tools:"] + [f"  - {x}" for x in tools] if a["tools"] is not None else []) + \
            ([f"model: {json.dumps(m)}"] if m else []) + \
            [f"max_turns: {turns}", f"timeout_mins: {mins}"]
    return ("---\n" + "\n".join(front) + "\n---\n\n<!-- " + AGENT_MARK + f" {version()} from agents/{a['role']}.md -->\n\n"
            + agent_adapter("gemini") + a["body"].rstrip() + "\n")


def export_codex(out: Path, root_text: str, models, plan) -> dict:
    skills, agents = read_skills(), read_agents()
    out.mkdir(parents=True, exist_ok=True)
    write_marker(out, "codex")                 # first, so a failed export can be re-run into the same folder
    copy_runtime(out)
    write_skills(out, "codex", root_text, skills, models, plan)
    (out / "agents").mkdir(exist_ok=True)
    for a in agents:
        (out / "agents" / f"asdr-{a['role']}.toml").write_text(codex_agent(a, models, plan))
    manifest = json.loads((SRC / ".claude-plugin" / "plugin.json").read_text())
    (out / "plugin.json").write_text(json.dumps({
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "asdr", "version": version(),
        "description": "ASDR (AI Software Delivery Room) for Codex: the skills; install the asdr-* custom agents "
                       "with export_targets.py --install.",
        "author": manifest.get("author"), "homepage": manifest.get("homepage"),
        "repository": manifest.get("repository"), "license": manifest.get("license"),
        "keywords": manifest.get("keywords")}, indent=2) + "\n")
    (out / "README-codex.md").write_text(CODEX_README.format(v=version(), root=root_text))
    return {"host": "codex", "out": str(out), "skills": [s["export"] for s in skills],
            "agents": [f"asdr-{a['role']}" for a in agents]}


def export_gemini(out: Path, models, plan) -> dict:
    skills, agents = read_skills(), read_agents()
    root_text = ("this extension's directory: normally `~/.gemini/extensions/asdr` (`gemini extensions list` "
                 "shows it), the directory two levels above this skill")
    out.mkdir(parents=True, exist_ok=True)
    write_marker(out, "gemini")
    copy_runtime(out)
    write_skills(out, "gemini", root_text, skills, models, plan)
    (out / "agents").mkdir(exist_ok=True)
    for a in agents:
        (out / "agents" / f"asdr-{a['role']}.md").write_text(gemini_agent(a, models, plan))
    (out / "gemini-extension.json").write_text(json.dumps({
        "name": "asdr", "version": version(),
        "description": "ASDR (AI Software Delivery Room): multi-agent software delivery — validate, discover, "
                       "design, build with independent QA, release.",
        "contextFileName": "GEMINI.md"}, indent=2) + "\n")
    (out / "GEMINI.md").write_text(GEMINI_CONTEXT.format(v=version(), skills=", ".join(s["export"] for s in skills)))
    cmd = out / "commands"
    (cmd / "asdr").mkdir(parents=True, exist_ok=True)
    for s in skills:
        path = cmd / "asdr.toml" if s["export"] == "asdr" else cmd / "asdr" / f"{s['name']}.toml"
        path.write_text(f"# {AGENT_MARK} {version()}\ndescription = {toml_str(s['description'][:200])}\n"
                        f"prompt = '''\nActivate the `{s['export']}` skill and follow it for this request:\n\n"
                        "{{args}}\n'''\n")
    return {"host": "gemini", "out": str(out), "skills": [s["export"] for s in skills],
            "agents": [f"asdr-{a['role']}" for a in agents],
            "commands": ["/asdr"] + [f"/asdr:{s['name']}" for s in skills if s["export"] != "asdr"]}


# ── installing ───────────────────────────────────────────────────────────────

def ours(p: Path, host: "str | None" = None) -> bool:
    """Written by this exporter (for `host`, when given)?"""
    if p.is_symlink():
        return False
    if p.is_dir():
        try:
            m = json.loads((p / MARKER).read_text())
        except (OSError, ValueError):
            return False
        return isinstance(m, dict) and m.get("exported_by") == "ASDR" and (host is None or m.get("host") == host)
    try:
        return AGENT_MARK in p.read_text(errors="ignore")[:400]
    except OSError:
        return False


def inside(a: Path, b: Path) -> bool:
    """a is b or lies under b."""
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


def place(src: Path, dest: Path, force: bool, done: list, refused: list):
    if dest.exists() or dest.is_symlink():
        if dest.resolve() == src.resolve():
            done.append(str(dest))
            return
        if not (ours(dest) or force):
            refused.append(str(dest))
            return
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    (shutil.copytree if src.is_dir() else shutil.copy2)(src, dest)
    done.append(str(dest))


def unsafe_root(root: Path, bundle: Path, skills_home: Path, codex_home: Path) -> "str | None":
    home = Path.home().resolve()
    for name, p in (("your home folder", home), ("the Codex home", codex_home), ("the skills folder", skills_home)):
        if inside(p, root):
            return f"{root} is or contains {name} ({p})"
    for name, p in (("the Codex home", codex_home), ("the skills folder", skills_home)):
        if inside(root, p):
            return f"{root} is inside {name} ({p})"
    if root != bundle and (inside(root, bundle) or inside(bundle, root)):
        return f"{root} overlaps the export folder {bundle}"
    return None


def install_codex(bundle: Path, root: Path, skills_home: Path, codex_home: Path, force: bool) -> dict:
    done, refused = [], []
    why = unsafe_root(root, bundle, skills_home, codex_home)
    if why:
        return {"installed": [], "refused": [why]}
    if root != bundle:
        if root.is_dir() and not root.is_symlink() and not any(root.iterdir()):
            root.rmdir()                               # an empty folder holds nothing to lose
        if (root.exists() or root.is_symlink()) and not ours(root, "codex"):
            return {"installed": [], "refused": [f"{root} (not an ASDR Codex bundle; --force never replaces a --root)"]}
        place(bundle, root, False, done, refused)
    for d in sorted((bundle / "skills").iterdir()):
        place(d, skills_home / d.name, force, done, refused)
    for f in sorted((bundle / "agents").glob("asdr-*.toml")):
        place(f, codex_home / "agents" / f.name, force, done, refused)
    return {"installed": done, "refused": refused}


def install_gemini(ext: Path) -> dict:
    """Gemini's own installer, in the foreground: it asks the user to trust the folder."""
    gem = shutil.which("gemini")
    if not gem:
        return {"installed": [], "note": f"gemini CLI not found; run: gemini extensions install {ext} --consent"}
    existing = Path.home() / ".gemini" / "extensions" / "asdr"
    try:
        if existing.exists():
            if not ours(existing, "gemini"):
                return {"installed": [], "refused": [f"{existing} (a Gemini extension named asdr that ASDR did not write)"]}
            print("Replacing the earlier ASDR extension (it declares no settings, so nothing else is lost).")
            r = subprocess.run([gem, "extensions", "uninstall", "asdr"], timeout=300)
            if r.returncode != 0:
                return {"installed": [], "error": f"gemini extensions uninstall asdr exited {r.returncode}"}
        r = subprocess.run([gem, "extensions", "install", str(ext), "--consent"], timeout=900)
    except subprocess.TimeoutExpired as ex:
        return {"installed": [], "error": f"gemini timed out: {ex}; install it with: gemini extensions install {ext} --consent"}
    if r.returncode != 0:
        return {"installed": [], "error": f"gemini extensions install exited {r.returncode}; ASDR is not installed in "
                                          f"Gemini now — retry with: gemini extensions install {ext} --consent"}
    return {"installed": [str(ext)]}


CODEX_README = """# ASDR {v} for Codex CLI

Exported from the AI Software Delivery Room by `scripts/export_targets.py codex`.

- `skills/` — the 8 ASDR skills (asdr, asdr-discover, asdr-validate, ...).
- `agents/` — one Codex custom agent per ASDR role (`asdr-critic.toml`, ...).
- `scripts/`, `templates/`, `docs/` — what the skills run and copy into each project.
- `plugin.json` — a portable plugin manifest for the skills.

Install (user scope): `python3 scripts/export_targets.py codex --install` from an
ASDR checkout. It puts this bundle at {root} (PLUGIN_ROOT), the skills in
`~/.agents/skills/` and the agents in `~/.codex/agents/`. Then, in a project
folder, start Codex and type `$asdr` followed by what you want to build.

Codex has no Claude-only features (private Artifacts, companion plugins); the
skills say what to skip. Models: unless exported with `--models`, every role
inherits your session model.
"""

GEMINI_CONTEXT = """# ASDR {v} (AI Software Delivery Room)

This extension adds ASDR's skills ({skills}) and one subagent per ASDR role
(`asdr-product-owner`, `asdr-critic`, `asdr-generator`, `asdr-evaluator`, ...).

- Start with `/asdr <what you want to build>` (or `/asdr:validate`, `/asdr:assess`,
  `/asdr:riskgate`, ...): each command activates the matching skill.
- The skill is the orchestrator: it runs ASDR's scripts from this extension's
  directory and delegates each role's work to its `asdr-<role>` subagent. The
  role that builds never signs off its own work.
- Project state lives in the project's `.harness/` folder; documents in `docs/`.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Export ASDR to Codex CLI and Gemini CLI.")
    ap.add_argument("host", choices=["codex", "gemini", "both"])
    ap.add_argument("--out", help="output folder (default: dist/<host> in the ASDR checkout, or a temp folder with --install)")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--root", default=os.path.join("~", ".asdr", "codex"), help="codex: where the bundle is installed (PLUGIN_ROOT)")
    ap.add_argument("--skills-home", default=os.path.join("~", ".agents", "skills"))
    ap.add_argument("--codex-home", default=os.environ.get("CODEX_HOME") or os.path.join("~", ".codex"))
    ap.add_argument("--plan", choices=list(mp.PLANS), default="balanced")
    ap.add_argument("--models", help="host model ids per ASDR tier, e.g. opus=<id>,sonnet=<id>,haiku=<id>")
    ap.add_argument("--force", action="store_true", help="install over files ASDR did not write")
    a = ap.parse_args()
    models = host_models(a.models)
    hosts = ["codex", "gemini"] if a.host == "both" else [a.host]
    if a.install and a.host == "both":
        print("ERROR: install one host at a time")
        return 1
    results = []
    for h in hosts:
        # codex --install copies the bundle to --root, so a temp folder will do; a Gemini extension keeps
        # its source folder for `gemini extensions update`, so it stays in dist/.
        temp = not a.out and a.install and h == "codex"
        base = (Path(a.out).expanduser().resolve() if a.out else Path(tempfile.mkdtemp(prefix="asdr-codex-")).resolve()
                if temp else SRC / "dist" / h)
        out = base / h if a.host == "both" and a.out else base
        if out.is_symlink() or (out.exists() and not out.is_dir()):
            print(f"ERROR: {out} is a file or a link; give --out a folder")
            return 1
        if out.exists() and any(out.iterdir()):
            if not ours(out, h):
                print(f"ERROR: {out} is not empty and was not written by this exporter for {h}")
                return 1
            shutil.rmtree(out)
        try:
            if h == "codex":
                root = Path(a.root).expanduser().resolve()
                res = export_codex(out, f"`{root}`", models, a.plan)
                if a.install:
                    res.update(install_codex(out, root, Path(a.skills_home).expanduser().resolve(),
                                             Path(a.codex_home).expanduser().resolve(), a.force))
                    if temp:
                        res["out"] = str(root) if not res.get("refused") else f"{root} (not installed)"
            else:
                res = export_gemini(out, models, a.plan)
                if a.install:
                    res.update(install_gemini(out))
        finally:
            if temp:
                shutil.rmtree(out, ignore_errors=True)           # the bundle now lives at --root
        res["models"] = models or "inherit"
        results.append(res)
        print(f"{h}: {len(res['skills'])} skills, {len(res['agents'])} agents -> {res['out']}")
        for r in res.get("refused", []):
            print(f"  REFUSED (not written by ASDR or unsafe; nothing replaced there): {r}")
        if res.get("error"):
            print("  ERROR: " + res["error"])
        if res.get("note"):
            print("  " + res["note"])
    print("EXPORT: " + json.dumps(results))
    return 1 if any(r.get("refused") or r.get("error") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
