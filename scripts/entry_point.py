#!/usr/bin/env python3
"""Where should this ASDR run start? Recommend a start point, let the user choose (v4.0).

Usage:
  python3 entry_point.py recommend [--prompt "<the user's request>" | --prompt-file f] [--root .] [--json]
  python3 entry_point.py choose <start> [--by "<who chose>"] [--prompt ...] [--local-only] [--root .]
  python3 entry_point.py catchup [--root .] [--json]

Start points, in project order: validate, discover, design, build, release; plus
assess (an existing system) and resume (an earlier ASDR run past Phase 1).

`recommend` reads the request and looks at the project folder: an earlier ASDR
run (.harness/progress.json), ASDR's own documents and their phase decisions,
the user's own documents (PRDs, specs, architecture notes) and existing code.
It prints every start point with what it skips, what has to be caught up
first, and the risk of skipping, and marks one as recommended with the
reasons. The orchestrator shows that to the user and the USER chooses.

A stage counts as done only when its documents exist AND its phase decision
does (docs/decision-discovery.md, docs/decision-architecture.md, or the
catch-up's docs/decision-intake.md): documents nobody reviewed are reviewed in
the catch-up, never skipped. A run whose progress.json is still in the
strategic phase continues from its documents, not through next_action.py.

`choose` records the choice in .harness/entry.json with the catch-up list:
starting late skips stages, never the evidence later gates check. Each missing
document is written by its owner agent in INTAKE mode, from the user's
documents where they exist; the set is then challenged by one critic pass.

A resumed run that began before 4.0 may lack documents. ASDR knows a
project's origin from .harness/origin.json (stamped by init_asdr.py from 4.1
on), else from the record it replaces (every 4.0 run records its start);
when it cannot tell (a 4.0.x resume record), it sets origin_unknown and the
user answers (`choose resume --began-before 4.0`). `choose resume` lists them in entry.json `legacy_gaps`
with `began_before: "4.0"`, each with a kind: `gate` (a release gate reads it:
brief, requirements, use cases, feature list, flows, test cases,
architecture), `missing` (the run should have had it), or `optional` (added
by a later ASDR: architecture options and portability in 3.8, the
configurable-decisions register in 4.0). A register the user does not write
is skipped by validate_configurability.py --gate, not demanded. A run that
began on 4.0 or later has no legacy gaps; its earlier start is kept as
`resumed_from`.

`catchup` re-checks the recorded start (re-reading what the product needs —
a UI, AI, microservices — from the documents written since): exit 0 when
nothing is missing, 2 while something is (each listed), 1 when no start was
recorded. Last line of every command: ENTRY: {json}.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

ORDER = ["validate", "discover", "design", "build", "release"]
LABEL = {
    "validate": "Validate the idea",
    "discover": "Discovery",
    "design": "Design",
    "build": "Build",
    "release": "Release gate",
    "assess": "Assess an existing system",
    "resume": "Resume the earlier run",
}
WHAT = {
    "validate": "Test whether the idea is worth building: real evidence first, then a simulated customer panel.",
    "discover": "Write down what to build: brief, requirements, use cases, journeys and test cases.",
    "design": "Decide how to build it: architecture, cloud, configurable decisions, security and deployment.",
    "build": "Plan the sprints and build, with a separate tester signing off each one.",
    "release": "Security review, deployment readiness and a release rating for a finished build.",
    "assess": "Recover how an existing system works and what state it is in, then improve or rebuild it.",
    "resume": "Carry on from where the last run stopped, without redoing approved work.",
}
SKIP_RISK = {
    "validate": "No check that people want it. Fine when a client is paying for it or demand is already proven.",
    "discover": "Requirements, journeys and test cases are converted from your documents instead of being "
                "written and challenged from scratch; gaps surface later, when they cost more to fix.",
    "design": "Architecture, security and deployment are taken from your documents; the options and their "
              "costs are only compared where the catch-up finds a decision missing.",
    "build": "The release gate can only classify a build ASDR tracked sprint by sprint.",
}

# (path, plain name, owner agent), in the order the catch-up runs them
DISCOVERY = [("docs/01-product-brief.md", "product brief", "product-owner"),
             ("docs/02-requirements.md", "requirements", "business-analyst"),
             ("docs/02b-use-cases.md", "use cases", "business-analyst"),
             ("docs/02c-features.md", "feature list", "product-manager"),
             ("docs/02d-process-flows.md", "end-to-end process flows", "product-manager"),
             ("docs/02e-test-cases.md", "test cases", "business-analyst")]
DESIGN = [("docs/03c-architecture-options.md", "architecture options and your decision", "solution-architect"),
          ("docs/03-architecture.md", "architecture", "solution-architect"),
          ("docs/03e-services.md", "services and contracts", "solution-architect", "microservices"),
          ("docs/03b-design-system.md", "design system", "solution-architect", "ui"),
          ("docs/04-agent-design.md", "AI design", "ai-architect", "ai"),
          ("docs/03d-portability.md", "portability and cloud decision", "devops", "cloud"),
          ("docs/03f-configuration.md", "configurable decisions", "solution-architect"),
          ("docs/05-security.md", "security design", "security-compliance"),
          ("docs/06-devops.md", "deployment plan", "devops")]
PHASE_DECISION = {"discover": "docs/decision-discovery.md", "design": "docs/decision-architecture.md"}
INTAKE_DECISION = "docs/decision-intake.md"
BUILT = ("built:sprints", "every sprint built and passed (this cannot be caught up: build first)", "build")
# Documents a release gate reads (validate_product_map.py --gate; the riskgate prerequisites).
GATE_READS = {"docs/01-product-brief.md", "docs/02-requirements.md", "docs/02b-use-cases.md",
              "docs/02c-features.md", "docs/02d-process-flows.md", "docs/02e-test-cases.md",
              "docs/03-architecture.md"}
# Documents a later ASDR added: a run that began earlier never had them.
INTRODUCED = {"docs/02c-features.md": "3.4", "docs/02d-process-flows.md": "3.4", "docs/02e-test-cases.md": "3.4",
              "docs/03b-design-system.md": "3.3", "docs/03c-architecture-options.md": "3.8",
              "docs/03d-portability.md": "3.8", "docs/03e-services.md": "3.8", "docs/03f-configuration.md": "4.0"}

VALIDATORS = {
    "design": ["validate_product_map.py --require-coverage"],
    "build": ["validate_product_map.py --require-coverage", "validate_architecture_options.py",
              "validate_portability.py", "validate_configurability.py --require-tests"],
    "release": ["validate_product_map.py --require-coverage", "validate_architecture_options.py",
                "validate_portability.py", "validate_configurability.py --require-tests", "validate_sprints.py"],
}
CONTINUE_AT = {
    "validate": "Phase 1 step 0 (run the validate skill; do not ask again)",
    "discover": "Phase 1 step 1 (product-owner)",
    "design": "Phase 1 step 4c (architecture options)",
    "build": "Phase 1 steps 11-13 (blueprint summary, project facts, traceability seed), the user checkpoint, "
             "then Phase 2 (sprint planning)",
    "release": "Phase 4 (final gates)",
    "assess": "the assess skill (PLUGIN_ROOT/skills/assess/SKILL.md)",
    "resume": "the Resume protocol",
}

CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".go", ".rb", ".php", ".kt", ".swift",
            ".rs", ".vue", ".svelte", ".scala", ".c", ".cpp", ".h", ".m", ".dart", ".ex", ".exs", ".sql"}
MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "build.gradle", "go.mod",
             "Gemfile", "composer.json", "Cargo.toml", "pubspec.yaml", "mix.exs", "setup.py"}
SKIP_DIRS = {".git", ".harness", "node_modules", "venv", ".venv", "env", "dist", "build", "__pycache__", ".next",
             "target", "bin", "obj", "vendor", ".idea", ".vscode", "coverage", "site-packages"}
NOT_USER_DOCS = ("docs/validation", "docs/assess", "docs/test-reports", "docs/manuals", "docs/dashboard")
DOC_EXT = {".md", ".txt", ".docx", ".doc", ".pdf", ".rtf", ".odt"}
DOC_DISCOVERY = re.compile(r"prd|requirement|spec|brief|scope|user[ _-]?stor|use[ _-]?case|feature|journey|"
                           r"flow|test[ _-]?(case|plan)|backlog|epic", re.I)
DOC_DESIGN = re.compile(r"architect|design[ _-]?doc|system[ _-]?design|technical[ _-]?design|security|"
                        r"threat|deploy|infra|devops|adr", re.I)
MAX_ENTRIES = 20000

SIGNALS = {
    "validate": r"worth building|validat|will (people|customers|anyone)|would (people|customers)|market|demand|"
                r"not sure|should (i|we) build|is (this|it) a good idea|pay for",
    "assess": r"existing (system|app|codebase|product|platform)|legacy|audit|assess|take over|inherited|"
              r"moderni[sz]|review (this|our|the) (code|codebase|system)|what'?s wrong with|rescue",
    "release": r"ready to (ship|release|launch|go live)|release (it|this)|go live|risk gate|riskgate|"
               r"pre-?release|classify (my|the) release",
    "build": r"start coding|just build|jump straight|implement (it|this|the)|build (it|this) now|"
             r"we have (the )?(spec|requirements|architecture|design)",
    "design": r"design the (architecture|system)|system design|architecture|which cloud|microservices|"
              r"serverless|tech(nical)? stack",
    "discover": r"requirements|user stories|scope (it|this|out)|what should (i|we) build|plan (my|our|the) "
                r"(software|product|app)|product discovery",
}


def exists(root: Path, rel: str) -> bool:
    p = root / rel
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def mtime(root: Path, rel: str) -> float:
    try:
        return (root / rel).stat().st_mtime
    except OSError:
        return 0.0


def go(root: Path, rel: str) -> bool:
    """A decision document that exists and does not say no-go."""
    if not exists(root, rel):
        return False
    try:
        text = (root / rel).read_text(errors="ignore")
    except OSError:
        return False
    return not re.search(r"verdict\s*:\s*no-?go", text, re.I)


def phase_docs(phase: str, surf: set) -> list:
    if phase == "discover":
        return [p for p, *_ in DISCOVERY]
    return [d[0] for d in DESIGN if len(d) == 3 or d[3] in surf]


def reviewed(root: Path, phase: str, surf: set) -> bool:
    """The phase's own decision says go, or the catch-up's decision says go and is at least as new as
    every document of that phase (a decision written before a document cannot have reviewed it)."""
    if go(root, PHASE_DECISION[phase]):
        return True
    if not go(root, INTAKE_DECISION):
        return False
    t = mtime(root, INTAKE_DECISION)
    return all(mtime(root, d) <= t + 1 for d in phase_docs(phase, surf) if exists(root, d))


def read_json(p: Path, default):
    try:
        v = json.loads(p.read_text())
        return v if isinstance(v, type(default)) or default is None else default
    except (OSError, ValueError):
        return default


def scan(root: Path) -> dict:
    """What is already in the folder (breadth-first, so top-level documents are seen first)."""
    progress = read_json(root / ".harness" / "progress.json", {})
    phase = progress.get("phase") if isinstance(progress, dict) else None
    resume = bool(isinstance(progress, dict) and (phase not in (None, "", "strategic") or progress.get("sprint")))
    code_files, manifests = 0, []
    user_docs = {"discovery": [], "design": []}
    canonical = {d[0] for d in DISCOVERY + DESIGN} | {"docs/00-blueprint-summary.md", "docs/00a-idea-validation.md",
                                                      "docs/00b-roadmap.md", "docs/01b-business-case.md"}
    queue = collections.deque([root])
    seen = 0
    while queue and seen < MAX_ENTRIES:
        d = queue.popleft()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            seen += 1
            try:
                if e.is_symlink():
                    continue                     # never follow links out of the project
                is_dir = e.is_dir()
            except OSError:
                continue
            if is_dir:
                if e.name not in SKIP_DIRS and not e.name.startswith("."):
                    queue.append(e)
                continue
            rel = e.relative_to(root).as_posix()
            in_docs = rel.startswith("docs/")
            if e.name in MANIFESTS and not in_docs:
                manifests.append(rel)
            if e.suffix.lower() in CODE_EXT and not in_docs:
                code_files += 1
            if (e.suffix.lower() in DOC_EXT and rel not in canonical and e.name not in MANIFESTS
                    and e.name.lower() not in ("readme.md", "changelog.md", "license", "license.md", "claude.md")
                    and len(Path(rel).parts) <= 3 and not rel.startswith(NOT_USER_DOCS)):
                if DOC_DISCOVERY.search(e.name):
                    user_docs["discovery"].append(rel)
                elif DOC_DESIGN.search(e.name):
                    user_docs["design"].append(rel)
    sp = read_json(root / "sprints.json", None)
    sprints = [s for s in ((sp.get("sprints") or []) if isinstance(sp, dict) else (sp if isinstance(sp, list) else []))
               if isinstance(s, dict)]
    live = [s for s in sprints if s.get("status") != "torn-down"]
    return {
        "resume": resume,
        "phase": phase,
        "code_files": code_files,
        "manifests": sorted(manifests)[:10],
        "existing_code": code_files >= 10 or (bool(manifests) and code_files >= 3),
        "user_docs": {k: sorted(v)[:20] for k, v in user_docs.items()},
        "discovery_done": [p for p, *_ in DISCOVERY if exists(root, p)],
        "design_done": [d[0] for d in DESIGN if len(d) == 3 and exists(root, d[0])],
        "discovery_decided": reviewed(root, "discover", set()),
        "design_decided": reviewed(root, "design", set()),
        "sprints_done": bool(live) and all(s.get("status") == "done" for s in live),
        "truncated": seen >= MAX_ENTRIES,
    }


def signals(prompt: str) -> list:
    t = (prompt or "").lower()
    return [k for k, rx in SIGNALS.items() if re.search(rx, t)]


def _read(p: Path, n: int = 20000) -> str:
    try:
        return p.read_text(errors="ignore").lower()[:n]
    except OSError:
        return ""


def surfaces(prompt: str, root: Path, user_docs: "dict | None" = None) -> set:
    """ui / ai / cloud / microservices, judged loosely from the request, the user's text documents and
    ASDR's own brief and requirements once they exist."""
    text = (prompt or "").lower()
    for rel in ("docs/02-requirements.md", "docs/01-product-brief.md", "docs/03-architecture.md"):
        text += " " + _read(root / rel)
    for rel in [x for v in (user_docs or {}).values() for x in v]:
        if rel.lower().endswith((".md", ".txt")):
            text += " " + _read(root / rel)
    out = set()
    if re.search(r"\b(ui|web ?app|website|dashboard|screens?|mobile|portal|front-?end|pages?)\b", text):
        out.add("ui")
    if re.search(r"\b(ai|llm|agents?|rag|chatbot|assistant|machine learning|ml|gpt|claude)\b", text):
        out.add("ai")
    out.add("cloud")                     # portability runs by default (asdr Phase 1 step 6b)
    arch = read_json(root / ".harness" / "architecture.json", {})
    if isinstance(arch, dict) and arch.get("style") == "microservices":
        out.add("microservices")
    return out


def required(start: str, surf: set) -> list:
    """Documents a start needs before it begins, in catch-up order: (path, name, owner).
    The review of whatever was not reviewed is one item, always last (see missing())."""
    if start in ("validate", "discover", "assess", "resume"):
        return []
    req = list(DISCOVERY)
    if start in ("build", "release"):
        req += [(d[0], d[1], d[2]) for d in DESIGN if len(d) == 3 or d[3] in surf]
    return req


def skipped(start: str) -> list:
    if start not in ORDER:
        return []
    return [s for s in ORDER[:ORDER.index(start)] if s in SKIP_RISK]


def missing(root: Path, start: str, surf: set) -> list:
    out = [{"path": p, "what": n, "owner": o} for p, n, o in required(start, surf) if not exists(root, p)]
    phases = [] if start in ("validate", "discover", "assess", "resume") else (
        ["discover"] if start == "design" else ["discover", "design"])
    unreviewed = [ph for ph in phases if not reviewed(root, ph, surf)]
    if unreviewed:
        names = " and ".join({"discover": "discovery", "design": "design"}[ph] for ph in unreviewed)
        out.append({"path": INTAKE_DECISION, "what": f"independent review of the {names} documents "
                    "(one critic pass over the catch-up set, then the decision; written after them)",
                    "owner": "critic"})
    if start == "release" and not scan(root)["sprints_done"]:
        out.append({"path": BUILT[0], "what": BUILT[1], "owner": BUILT[2]})
    return out


def legacy_gaps(root: Path, surf: set) -> list:
    """Documents a resumed pre-4.0 run does not have: gate-read first, then missing, then optional."""
    out = []
    for p, n, o in required("build", surf):
        if exists(root, p):
            continue
        kind = "gate" if p in GATE_READS else "optional" if p in INTRODUCED else "missing"
        note = {"gate": "a release gate reads it: write it now so the remaining sprints are tested against it",
                "missing": "the run should have it: write it before the final gates",
                "optional": (f"added in ASDR {INTRODUCED.get(p)}; optional for this run"
                             + ("; without it the release gate skips the settings check"
                                if p.endswith("03f-configuration.md") else ""))}[kind]
        out.append({"path": p, "what": n, "owner": o, "kind": kind, "gate": kind == "gate",
                    "introduced": INTRODUCED.get(p), "note": note})
    order = {"gate": 0, "missing": 1, "optional": 2}
    return sorted(out, key=lambda m: order[m["kind"]])


def version_tuple(v) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return ()


def resume_record(root: Path, surf: set, prior: dict, began_flag: "str | None" = None) -> dict:
    """legacy_gaps / began_before / resumed_from / origin_unknown for `choose resume`, decided from the
    project's origin stamp (.harness/origin.json, v4.1+) or else from the record this choice replaces."""
    rec = {}
    prior = prior if isinstance(prior, dict) else {}
    pstart = prior.get("start")
    if pstart and pstart != "resume":
        sk = prior.get("skipped")
        rec["resumed_from"] = {"start": pstart, "skipped": sk if isinstance(sk, list) else [], "at": prior.get("at")}
    elif isinstance(prior.get("resumed_from"), dict):
        rec["resumed_from"] = prior["resumed_from"]
    origin = read_json(root / ".harness" / "origin.json", {})
    known = version_tuple(origin.get("asdr_version")) if isinstance(origin, dict) else ()
    if began_flag:                                     # the user said so (Resume protocol)
        began = began_flag
    elif known:
        began = "4.0" if known < (4, 0, 0) else None
    elif pstart and pstart != "resume":                # only 4.0+ records a start
        began = None
    elif pstart == "resume":
        if prior.get("began_before"):
            began = prior["began_before"]
        elif "legacy_gaps" not in prior:               # a 4.0.x resume record: the origin is unknown
            rec["origin_unknown"] = True
            rec["legacy_gaps"] = legacy_gaps(root, surf)
            return rec
        else:
            began = None
    else:
        began = "4.0"                                  # no start record and no stamp: began before 4.0
    rec["legacy_gaps"] = legacy_gaps(root, surf) if began else []
    if began:
        rec["began_before"] = began
    return rec


def recommend(prompt: str, root: Path) -> dict:
    s = scan(root)
    sig = signals(prompt)
    surf = surfaces(prompt, root, s["user_docs"])
    disc_full = len(s["discovery_done"]) == len(DISCOVERY)
    design_core = [d[0] for d in DESIGN if len(d) == 3]
    design_full = len(s["design_done"]) == len(design_core)
    has_disc_docs = bool(s["user_docs"]["discovery"])
    has_design_docs = bool(s["user_docs"]["design"])
    reasons = []
    if s["resume"]:
        rec = "resume"
        reasons.append(f"An earlier ASDR run is in this folder (phase: {s['phase'] or 'sprint in progress'}). "
                       "Resuming keeps every approved document.")
    elif s["existing_code"] and not s["discovery_done"]:
        rec = "assess"
        reasons.append(f"There is existing code ({s['code_files']} source files"
                       + (f"; {', '.join(s['manifests'][:3])}" if s["manifests"] else "")
                       + ") but no requirements or test cases ASDR can check it against. Assess recovers them "
                         "from the code before anything is changed.")
        if "release" in sig:
            reasons.append("You asked about releasing: the release gate needs requirements and test cases to "
                           "check against, and Assess produces them.")
    elif exists(root, PHASE_DECISION["discover"]) and not go(root, PHASE_DECISION["discover"]):
        rec = "discover"
        reasons.append("The discovery decision says no-go: its required changes come first; nothing later starts "
                       "until a new decision says go.")
    elif exists(root, PHASE_DECISION["design"]) and not go(root, PHASE_DECISION["design"]):
        rec = "design"
        reasons.append("The architecture decision says no-go: its required changes come first.")
    elif disc_full and design_full and s["discovery_decided"] and s["design_decided"]:
        rec = "release" if s["sprints_done"] else "build"
        reasons.append("Discovery and design are written and decided" + (
            " and every sprint is done." if s["sprints_done"] else "; nothing has been built yet."))
    elif disc_full and s["discovery_decided"]:
        rec = "design"
        reasons.append("Discovery is written and decided; the design is "
                       + ("written but not yet reviewed — the catch-up reviews it." if design_full else "not finished yet."))
        if design_full and not s["design_decided"]:
            rec = "build"
    elif disc_full:
        rec = "design"
        reasons.append("The discovery documents exist but have not been reviewed: the catch-up runs the critic "
                       "and the decision on them before design starts.")
    elif has_disc_docs and has_design_docs:
        rec = "build"
        reasons.append("You already have requirements-type documents ("
                       + ", ".join(s["user_docs"]["discovery"][:3]) + ") and design-type documents ("
                       + ", ".join(s["user_docs"]["design"][:3]) + "). A short catch-up converts them into "
                         "the documents the later checks need, reviews them, then building starts.")
    elif has_disc_docs:
        rec = "design"
        reasons.append("You already have requirements-type documents (" + ", ".join(s["user_docs"]["discovery"][:3])
                       + "). A short catch-up converts and reviews them, then design starts.")
    elif "assess" in sig:
        rec = "assess"
        reasons.append("You asked to assess an existing system. No code was found in this folder: point ASDR at it "
                       "(a path or a repository) when the assessment starts.")
    elif "validate" in sig:
        rec = "validate"
        reasons.append("Your request asks whether the idea is worth building, and nothing is written down yet.")
    else:
        rec = "discover"
        reasons.append("This is a new idea with nothing written down yet. Validation is optional: choose it if "
                       "demand is not proven (no paying client, no evidence that people want it).")
    if s["truncated"]:
        reasons.append(f"The folder is large; only the first {MAX_ENTRIES} entries were looked at. Name any "
                       "requirements or architecture documents ASDR should use.")
    asked = [x for x in sig if x != rec]
    if asked and rec != "resume":
        reasons.append("Your request also mentions: " + ", ".join(LABEL[x].lower() for x in asked)
                       + ". Those are listed below with what they would skip.")

    options = []
    candidates = (["resume"] if s["resume"] else []) + ORDER + ["assess"]
    for st in candidates:
        miss = missing(root, st, surf)
        fit = "recommended" if st == rec else "possible"
        note = ""
        if st == "release" and not s["sprints_done"]:
            fit = "not advised"
            note = "Only a finished build that ASDR tracked sprint by sprint can be classified."
        if st == "assess" and not s["existing_code"] and "assess" not in sig:
            fit = "not advised"
            note = "There is no existing system here to assess."
        if st in ("design", "build") and not (has_disc_docs or disc_full) and st != rec:
            note = ("With nothing written down, the catch-up would have to write discovery from your request "
                    "alone; starting at Discovery costs about the same and is reviewed properly.")
        options.append({"start": st, "label": LABEL[st], "what": WHAT[st], "fit": fit,
                        "skips": [{"stage": k, "label": LABEL[k], "risk": SKIP_RISK[k]} for k in skipped(st)],
                        "catch_up": miss, "validators": VALIDATORS.get(st, []),
                        "continue_at": CONTINUE_AT[st], "note": note})
    options.sort(key=lambda o: (o["fit"] != "recommended", o["fit"] == "not advised"))
    return {"recommended": rec, "reasons": reasons, "signals": sig, "surfaces": sorted(surf), "scan": s,
            "options": options}


def how(m: dict) -> str:
    if m["owner"] == "critic":
        return "one critic pass over the catch-up set, then decide.py --phase intake"
    if m["owner"] == "build":
        return "not a catch-up: build first"
    return f"{m['owner']}, INTAKE mode"


def show(res: dict) -> None:
    print(f"Recommended start: {LABEL[res['recommended']]}")
    for r in res["reasons"]:
        print(f"  - {r}")
    print()
    for o in res["options"]:
        print(f"[{o['fit']}] {o['label']}: {o['what']}")
        for k in o["skips"]:
            print(f"    skips {k['label']}: {k['risk']}")
        if o["catch_up"]:
            print("    catch-up first: " + "; ".join(f"{m['what']} ({m['owner']})" for m in o["catch_up"]))
        if o["note"]:
            print(f"    note: {o['note']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Recommend where an ASDR run starts; record the user's choice.")
    ap.add_argument("cmd", choices=["recommend", "choose", "catchup"])
    ap.add_argument("start", nargs="?", choices=ORDER + ["assess", "resume"])
    ap.add_argument("--prompt", default="")
    ap.add_argument("--prompt-file")
    ap.add_argument("--root", default=".")
    ap.add_argument("--by", default="")
    ap.add_argument("--local-only", action="store_true",
                    help="the product runs only on the user's own machines: no portability decision")
    ap.add_argument("--began-before", choices=["4.0"],
                    help="choose resume: the user says this project began before ASDR 4.0 (when the origin is unknown)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    prompt = a.prompt
    if a.prompt_file:
        try:
            prompt = Path(a.prompt_file).read_text(errors="ignore")
        except OSError:
            pass
    entry_file = root / ".harness" / "entry.json"

    if a.cmd == "recommend":
        res = recommend(prompt, root)
        if not a.json:
            show(res)
        print("ENTRY: " + json.dumps({"cmd": "recommend", "recommended": res["recommended"],
                                     "reasons": res["reasons"], "options": res["options"],
                                     "surfaces": res["surfaces"], "user_docs": res["scan"]["user_docs"],
                                     "existing_code": res["scan"]["existing_code"]}))
        return 0

    if a.cmd == "choose":
        if not a.start:
            print("ERROR: choose needs a start point: " + ", ".join(ORDER + ["assess", "resume"]))
            return 1
        res = recommend(prompt, root)
        surf = set(res["surfaces"])
        if a.local_only:
            surf.discard("cloud")
        rec = {"start": a.start, "label": LABEL[a.start], "recommended": res["recommended"],
               "followed_recommendation": a.start == res["recommended"], "chosen_by": a.by or "user",
               "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "skipped": skipped(a.start), "catch_up": missing(root, a.start, surf), "prompt": prompt[:4000],
               "local_only": a.local_only, "surfaces": sorted(surf), "user_docs": res["scan"]["user_docs"],
               "validators": VALIDATORS.get(a.start, []), "continue_at": CONTINUE_AT[a.start]}
        if a.start == "resume":
            rec.update(resume_record(root, surf, read_json(entry_file, {}), a.began_before))
        try:
            entry_file.parent.mkdir(parents=True, exist_ok=True)
            entry_file.write_text(json.dumps(rec, indent=2) + "\n")
        except OSError as ex:
            print(f"WARN: could not write {entry_file}: {ex}")
        print(f"Start: {rec['label']}" + ("" if rec["followed_recommendation"]
                                          else f" (ASDR recommended {LABEL[res['recommended']]})"))
        if rec["catch_up"]:
            print("Catch up first, in this order:")
            for m in rec["catch_up"]:
                print(f"  - {m['what']} -> {m['path']} ({how(m)})")
        gaps = rec.get("legacy_gaps") or []
        if rec.get("origin_unknown"):
            print("ASDR cannot tell whether this run began before 4.0. Ask the user; if it did, run "
                  "`entry_point.py choose resume --began-before 4.0`. Until then every release check applies.")
        if gaps:
            print(("This run began before ASDR 4.0; it" if rec.get("began_before") else "This run") +
                  " does not have these documents (ask the user):")
            for m in gaps:
                tag = {"gate": "[before release]", "missing": "[missing]", "optional": "[optional]"}[m["kind"]]
                print(f"  - {tag} {m['what']} -> {m['path']} ({m['owner']}, INTAKE mode): {m['note']}")
        print(f"Then continue at: {rec['continue_at']}")
        print("ENTRY: " + json.dumps({"cmd": "choose", **rec}))
        return 0

    # catchup: re-read what the product needs from the documents written since the choice
    rec = read_json(entry_file, {})
    if not rec.get("start") or rec.get("start") not in LABEL:
        print("ERROR: no start recorded; run entry_point.py recommend, then choose <start>.")
        print("ENTRY: " + json.dumps({"cmd": "catchup", "ok": False, "reason": "no start recorded"}))
        return 1
    surf = set(rec.get("surfaces") or []) | surfaces(rec.get("prompt") or "", root, rec.get("user_docs") or {})
    if rec.get("local_only"):
        surf.discard("cloud")
    miss = missing(root, rec["start"], surf)
    for m in miss:
        print(f"MISSING: {m['what']} -> {m['path']} ({how(m)})")
    if not miss:
        print(f"Catch-up complete for {LABEL[rec['start']]}; run: " + ", ".join(rec.get("validators") or ["(no validators)"]))
    print("ENTRY: " + json.dumps({"cmd": "catchup", "start": rec["start"], "ok": not miss, "missing": miss,
                                 "surfaces": sorted(surf)}))
    return 0 if not miss else 2


if __name__ == "__main__":
    sys.exit(main())
