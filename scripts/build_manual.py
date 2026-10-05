#!/usr/bin/env python3
"""Build the user manuals — one per persona and one per experience tier —
from manual-tour screenshots, as HTML and PDF.

Usage:
  python3 build_manual.py [--spec docs/manuals/manual.json] [--manual-dir .harness/manual]
                          [--out docs/manuals] [--version X] [--commit SHA]
                          [--changelog CHANGELOG.md] [--no-pdf] [--allow-stale]
                          [--artifact FILE] [--check]

Inputs
------
manual.json (written by the documentation agent; template:
templates/e2e/manual.json) says WHAT each manual teaches:
  steps   one explanation per captured step, keyed "<tour>/<step-id>", with
          optional per-level wording: {"text": "...", "levels": {"beginner": "..."}}
  levels  each manual. kind "persona" (persona + part: Getting started /
          Advanced) or kind "tier" (Beginner, Everyday user, Power user,
          Administrator). Sections list steps as "tour/id", "tour/*" or
          "tour/first..last".
Tour manifests in <manual-dir>/tours/*.json (written by the Playwright,
Cypress and Selenium helpers during run_tests.py) say what the screen looked
like: one screenshot per step, the URL, the outlined element, and the commit.

Gate
----
The build fails (exit 1) and lists every problem when a manual references a
step no tour captured, a step has no explanation, a screenshot is missing, or
a screenshot was taken from a different commit than the one being released
(--allow-stale to override for drafts). Tours no manual uses are warnings.
--check validates without writing anything.

Every explanation is also checked against the screen it describes: each
**bold** name ("Click **Add task**") must be readable on that step's
screenshot (the tour helpers record the on-screen text). Keyboard keys
(**Enter**, **N**) are exempt; a step entry may list deliberate exceptions in
"offscreen". This catches the commonest manual error — a button renamed in
the app but not in the manual.

Human review
------------
A person must read the explanations before they ship. Approvals live in
docs/manuals/review.json, keyed by step with a hash of its text, so only new
or changed explanations need reading again:
  --review-page FILE        one self-contained page with every step's screenshot,
                            text per level and review state (publish it privately)
  --approve all|KEY,KEY --reviewer NAME   record approval of the current text
  --flag KEY --note TEXT    record that a step needs fixing
  --require-review          fail unless every step in use is approved (release)

Screen changes between releases
-------------------------------
By default (--compare-to auto) the build compares this version's screenshots
with the previous version's in docs/manuals/ (compare_screens.py): changed
steps carry a "Screen changed since <version>" badge, new ones "New in this
version", and docs/manuals/<version>/ui-changes.html shows before / after /
diff for each. The release-manager lists them so a person confirms every UI
change was intended. --compare-to <version> picks the baseline; none skips it.

Outputs  docs/manuals/<version>/
  index.html            every manual for this version, by role and by experience
  <level>.html / .pdf   one per level; PDF via headless Chrome/Chromium
  screens/              the screenshots the manuals use
  build.json            what was built, from which commit, and any warnings
docs/manuals/index.html lists every version; docs/manuals/latest.json points at
the newest. --artifact FILE also writes every manual as one self-contained page
(images embedded, no doctype) for a private claude.ai Artifact.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_style import ZOOM_JS, page  # noqa: E402
from compare_screens import compare_dirs  # noqa: E402

e = html.escape
TIER_ORDER = ["beginner", "everyday", "power", "administrator"]
KEYS = {"enter", "return", "tab", "esc", "escape", "space", "spacebar", "shift", "ctrl", "control",
        "cmd", "command", "alt", "option", "delete", "backspace", "up", "down", "left", "right",
        "home", "end", "page up", "page down", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8",
        "f9", "f10", "f11", "f12"}


def _norm(t: str) -> str:
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", t).strip().lower()


def offscreen_terms(text: str, st: dict, allow) -> list:
    """Bold UI names in an explanation that do not appear on the step's screen."""
    pool = _norm((st.get("page_text") or "") + "\n" + (st.get("target_text") or ""))
    allowed = {_norm(a) for a in allow or []}
    missing = []
    for term in re.findall(r"\*\*(.+?)\*\*", text or ""):
        t = _norm(term)
        if not t or t in KEYS or re.fullmatch(r"[a-z0-9]", t) or t in allowed:
            continue
        if any(re.search(r"(?<![a-z0-9])" + re.escape(c) + r"(?![a-z0-9])", pool)
               for c in {t, t.rstrip(".:!")} if c):
            continue
        if term not in missing:
            missing.append(term)
    return missing


def entry_hash(entry) -> str:
    raw = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    return "sha1:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str | None:
    return "sha1:" + hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else None


def load_review(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return {"schema": 1, "steps": {}}


def review_state(key: str, entry, review: dict) -> tuple:
    """-> (state, record). state: approved | changed | new | needs-fix"""
    rec = (review.get("steps") or {}).get(key)
    if not rec:
        return "new", None
    if rec.get("status") == "needs-fix" and rec.get("hash") == entry_hash(entry):
        return "needs-fix", rec
    if rec.get("hash") != entry_hash(entry):
        return "changed", rec
    return ("approved", rec) if rec.get("status") == "approved" else ("new", rec)


# ── inputs ─────────────────────────────────────────────────────────────────

def git_head() -> str | None:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=20)
        return p.stdout.strip() or None if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def load_tours(manual_dir: Path) -> dict:
    tours = {}
    for f in sorted((manual_dir / "tours").glob("*.json")) if (manual_dir / "tours").is_dir() else []:
        m = json.loads(f.read_text())
        m["steps"] = sorted(m.get("steps", []), key=lambda s: s.get("order", 0))
        tours[m.get("tour", f.stem)] = m
    return tours


def expand(ref: str, tours: dict, problems: list, where: str) -> list:
    """'tour/id' | 'tour/*' | 'tour/a..b'  ->  [(tour, step), ...]"""
    if "/" not in ref:
        problems.append(f"{where}: '{ref}' is not 'tour/step'")
        return []
    tour, sel = ref.split("/", 1)
    if tour not in tours:
        problems.append(f"{where}: tour '{tour}' was not captured (no {tour}.json in the manual folder)")
        return []
    steps = tours[tour]["steps"]
    ids = [s["id"] for s in steps]
    if sel == "*":
        return [(tour, s) for s in steps]
    if ".." in sel:
        a, b = sel.split("..", 1)
        missing = [x for x in (a, b) if x not in ids]
        if missing:
            problems.append(f"{where}: step(s) {', '.join(missing)} not in tour '{tour}' (has: {', '.join(ids)})")
            return []
        i, j = ids.index(a), ids.index(b)
        if i > j:
            problems.append(f"{where}: range {sel} runs backwards in tour '{tour}'")
            return []
        return [(tour, s) for s in steps[i:j + 1]]
    if sel not in ids:
        problems.append(f"{where}: step '{sel}' not in tour '{tour}' (has: {', '.join(ids)})")
        return []
    return [(tour, steps[ids.index(sel)])]


def whats_new(spec: dict, changelog: Path | None, version: str) -> list:
    if spec.get("whats_new"):
        return list(spec["whats_new"])
    if not changelog or not changelog.is_file():
        return []
    items, capture = [], False
    head = re.compile(r"^##\s+\[?v?" + re.escape(version) + r"\]?(\s|$|\s*[-—(])")
    for line in changelog.read_text().splitlines():
        if line.startswith("## "):
            if capture:
                break
            capture = bool(head.match(line))
            continue
        if capture and re.match(r"^\s*[-*]\s+", line):
            items.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
    return items


def md(text: str) -> str:
    """Escape, then allow **bold** and `code` — all the manual text needs."""
    t = e(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def level_title(lv: dict) -> str:
    if lv.get("kind") == "persona":
        return f'{lv.get("persona", "User")}: {lv.get("part", "Guide")}'
    return lv.get("title") or lv["id"]


# ── validation ─────────────────────────────────────────────────────────────

def plan(spec: dict, tours: dict, manual_dir: Path, commit: str | None, allow_stale: bool,
         catalog: dict | None = None):
    problems, warnings, built = [], [], []
    seen_ids, used = set(), set()
    catalog = {} if catalog is None else catalog   # key -> what a reviewer needs to see
    no_text_tours = set()
    texts = spec.get("steps", {})
    levels = spec.get("levels") or []
    if not levels:
        problems.append("manual.json has no levels")
    kinds = {lv.get("kind") for lv in levels}
    if "persona" not in kinds:
        warnings.append("no persona manuals (kind 'persona'): add one per role, Getting started + Advanced")
    if "tier" not in kinds:
        warnings.append("no experience-tier manuals (kind 'tier'): Beginner, Everyday user, Power user, Administrator")
    for lv in levels:
        lid = lv.get("id")
        if not lid or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", lid):
            problems.append(f"level id '{lid}' must be lowercase letters, digits and dashes")
            continue
        if lid in seen_ids:
            problems.append(f"level id '{lid}' is used twice")
        seen_ids.add(lid)
        if lv.get("kind") not in ("persona", "tier"):
            problems.append(f"level '{lid}': kind must be 'persona' or 'tier'")
        sections = []
        for si, sec in enumerate(lv.get("sections") or []):
            where = f"level '{lid}' section '{sec.get('title', si + 1)}'"
            steps = []
            for ref in sec.get("steps") or []:
                for tour, st in expand(ref, tours, problems, where):
                    key = f"{tour}/{st['id']}"
                    used.add(key)
                    entry = texts.get(key)
                    text = None
                    if isinstance(entry, str):
                        text = entry
                    elif isinstance(entry, dict):
                        text = (entry.get("levels") or {}).get(lid) or entry.get("text")
                    if not text:
                        problems.append(f"{where}: step '{key}' has no explanation in manual.json steps")
                    shot = manual_dir / st["screenshot"]
                    if not shot.is_file():
                        problems.append(f"{where}: screenshot {st['screenshot']} is missing")
                    allow = entry.get("offscreen") if isinstance(entry, dict) else None
                    if "page_text" not in st:
                        no_text_tours.add(tour)
                    elif text:
                        for term in offscreen_terms(text, st, allow):
                            msg = (f"step '{key}' ({lid}): the explanation names **{term}**, which is not on "
                                   f"that screen ({st['screenshot']}) — fix the wording, or list it under "
                                   f"\"offscreen\" if it is deliberate")
                            if msg not in problems:
                                problems.append(msg)
                    c = catalog.setdefault(key, {"entry": entry, "title": st.get("title") or st["id"],
                                                 "screenshot": st["screenshot"], "levels": {},
                                                 "target_text": st.get("target_text")})
                    c["levels"][lid] = text or ""
                    steps.append({"key": key, "title": st.get("title") or st["id"], "text": text or "",
                                  "note": st.get("note"), "screenshot": st["screenshot"], "url": st.get("url")})
            if not steps:
                problems.append(f"{where}: no steps")
            sections.append({"title": sec.get("title") or f"Part {si + 1}", "intro": sec.get("intro"),
                             "steps": steps})
        if not sections:
            problems.append(f"level '{lid}' has no sections")
        built.append({**lv, "title_text": level_title(lv), "sections": sections})

    for t in sorted(no_text_tours):
        warnings.append(f"tour '{t}' has no on-screen text recorded (older manual helper) — the "
                        "bold-name check was skipped; copy the current helper from .harness/templates/e2e/")
    for name, m in tours.items():
        if commit and m.get("commit") != commit:
            msg = (f"tour '{name}' screenshots are from commit {m.get('commit') or 'unknown'}, "
                   f"not {commit} — rerun run_tests.py on this commit")
            (warnings if allow_stale else problems).append(msg)
        unused = [s["id"] for s in m["steps"] if f"{name}/{s['id']}" not in used]
        if len(unused) == len(m["steps"]):
            warnings.append(f"tour '{name}' is not used by any manual")
        elif unused:
            warnings.append(f"tour '{name}': steps not used by any manual: {', '.join(unused)}")
    for key in texts:
        if key not in used:
            warnings.append(f"manual.json explains '{key}' but no manual uses it")
    return built, problems, warnings


# ── rendering ──────────────────────────────────────────────────────────────

def version_flag(product: str, version: str, commit: str | None, captured: str, reviewed: str = "") -> str:
    return ('<div class="version-flag" role="note"><span class="eyebrow">This manual matches</span>'
            f'<strong>{e(product)} {e(version)}</strong>'
            f'<span class="muted mono">commit {e(commit or "unknown")} · screenshots taken {e(captured)}</span>'
            + (f'<span class="muted">{e(reviewed)}</span>' if reviewed else "") + '</div>')


def render_level(lv: dict, ctx: dict, img_src, anchor_prefix: str = "") -> str:
    p = anchor_prefix
    toc = "".join(f'<li><a href="#{p}s{i + 1}">{e(sec["title"])}</a></li>' for i, sec in enumerate(lv["sections"]))
    new = ""
    if ctx["whats_new"]:
        new = ('<section class="band"><h2>What is new in this version</h2><ul class="toc">'
               + "".join(f"<li>{md(x)}</li>" for x in ctx["whats_new"]) + "</ul></section>")
    secs, n = [], 0
    for i, sec in enumerate(lv["sections"]):
        rows = []
        for st in sec["steps"]:
            n += 1
            note = f'<p class="note">{md(st["note"])}</p>' if st.get("note") else ""
            rows.append(
                f'<div class="step"><div class="text"><div class="row"><span class="num">STEP {n}</span>'
                f'{step_badge(ctx, st["screenshot"])}</div>'
                f'<h3>{e(st["title"])}</h3><p>{md(st["text"])}</p>{note}</div>'
                f'<img src="{img_src(st["screenshot"])}" alt="{e(st["title"])}: screenshot of {e(ctx["product"])}" loading="lazy"></div>')
        intro = f'<p>{md(sec["intro"])}</p>' if sec.get("intro") else ""
        secs.append(f'<section class="stack" id="{p}s{i + 1}"><h2>{e(sec["title"])}</h2>{intro}{"".join(rows)}</section>')
    kind = "By role" if lv.get("kind") == "persona" else "By experience"
    return (
        f'<header class="stack"><span class="eyebrow">{e(ctx["product"])} user manual · {kind}</span>'
        f'<h1>{e(lv["title_text"])}</h1>'
        + (f'<p>{md(lv["audience"])}</p>' if lv.get("audience") else "")
        + (f'<p class="muted">{md(ctx["intro"])}</p>' if ctx.get("intro") else "")
        + '</header>'
        + version_flag(ctx["product"], ctx["version"], ctx["commit"], ctx["captured"], ctx.get("reviewed", ""))
        + new
        + f'<nav class="band" aria-label="Contents"><h2>In this guide</h2><ol class="toc">{toc}</ol>'
          '<p class="muted">In every screenshot, the part of the screen you use is outlined in red.</p></nav>'
        + "".join(secs))


def step_badge(ctx: dict, shot: str) -> str:
    ui = ctx.get("ui")
    if not ui:
        return ""
    name = Path(shot).name
    if name in ui["changed_names"]:
        return f'<span class="pill skipped">Screen changed since {e(ui["compared_to"])}</span>'
    if name in ui["added"]:
        return '<span class="pill neutral">New in this version</span>'
    return ""


def ui_changes_body(ctx: dict, src) -> str:
    """Before / after / diff for every changed screen. src(kind, name) -> image URL."""
    ui = ctx["ui"]
    cards = []
    for c in ui["changed"]:
        imgs = "".join(f'<figure><img src="{src(k, c["name"])}" alt="{lab} {e(c["name"])}"><figcaption>{lab}</figcaption></figure>'
                       for k, lab in (("before", f"Before ({ui['compared_to']})"), ("after", f"Now ({ctx['version']})"),
                                      ("diff", "Changed pixels in red")) if src(k, c["name"]))
        cards.append(f'<section class="stack"><div class="row"><h3>{e(c["name"])}</h3>'
                     f'<span class="pill skipped">{c["pct"]}% of the screen</span>'
                     + (f'<span class="muted">{e(c["note"])}</span>' if c.get("note") else "")
                     + f'</div><div class="shots">{imgs}</div></section>')
    extra = ""
    if ui["added"]:
        extra += f'<p><strong>New screens:</strong> {e(", ".join(ui["added"]))}</p>'
    if ui["removed"]:
        extra += f'<p><strong>No longer in the manuals:</strong> {e(", ".join(ui["removed"]))}</p>'
    return (f'<header class="stack"><span class="eyebrow">{e(ctx["product"])} {e(ctx["version"])}</span>'
            f'<h1>What changed on screen since {e(ui["compared_to"])}</h1>'
            f'<p>{len(ui["changed"])} screens changed, {len(ui["added"])} new, {len(ui["removed"])} removed. '
            'Confirm each change was intended before the release goes out.</p></header>'
            + extra + "".join(cards))


def find_previous(root: Path, version: str, choice: str):
    if choice == "none" or not root.is_dir():
        return None
    cands = []
    for d in root.iterdir():
        b = d / "build.json"
        if b.is_file() and (d / "screens").is_dir():
            try:
                info = json.loads(b.read_text())
            except ValueError:
                continue
            if str(info.get("version")) != version:
                cands.append((info.get("built_at") or "", str(info.get("version")), d))
    if choice != "auto":
        cands = [c for c in cands if c[1] == choice or c[2].name == choice]
    return max(cands)[1:] if cands else None


def footer(ctx: dict) -> str:
    return (f'<footer>{e(ctx["product"])} {e(ctx["version"])} · commit {e(ctx["commit"] or "unknown")} · '
            f'screenshots taken {e(ctx["captured"])} from the automated test run · built by ASDR build_manual.py</footer>')


def index_body(levels: list, ctx: dict, link) -> str:
    def card(lv):
        pdf = link(lv, "pdf")
        return (f'<article class="level"><span class="eyebrow">{e(lv.get("part") or "Guide")}</span>'
                f'<h3><a href="{link(lv, "html")}">{e(lv["title_text"])}</a></h3>'
                + (f'<p class="muted">{md(lv["audience"])}</p>' if lv.get("audience") else "")
                + f'<p class="muted mono">{sum(len(s["steps"]) for s in lv["sections"])} steps'
                + (f' · <a href="{pdf}">PDF</a>' if pdf else "") + '</p></article>')
    personas = [lv for lv in levels if lv.get("kind") == "persona"]
    tiers = sorted([lv for lv in levels if lv.get("kind") == "tier"],
                   key=lambda lv: TIER_ORDER.index(lv["id"]) if lv["id"] in TIER_ORDER else 99)
    groups = {}
    for lv in personas:
        groups.setdefault(lv.get("persona", "User"), []).append(lv)
    role_html = "".join(f'<section class="stack"><h3>{e(name)}</h3><div class="levels">{"".join(card(x) for x in lvs)}</div></section>'
                        for name, lvs in groups.items())
    tier_html = "".join(card(x) for x in tiers)
    ui = ctx.get("ui")
    changes = ""
    if ui:
        what = (f'{len(ui["changed"])} screens changed, {len(ui["added"])} new, {len(ui["removed"])} removed'
                if ui["changed"] or ui["added"] or ui["removed"] else "no screens changed")
        link_ui = ctx.get("ui_link")
        changes = (f'<section class="band"><h2>What changed on screen since {e(ui["compared_to"])}</h2><p>{e(what)}.'
                   + (f' <a href="{link_ui}">See before and after</a>.' if link_ui and ui["changed"] else "")
                   + '</p></section>')
    return (f'<header class="stack"><span class="eyebrow">{e(ctx["product"])}</span><h1>User manuals</h1>'
            + (f'<p>{md(ctx["intro"])}</p>' if ctx.get("intro") else "") + '</header>'
            + version_flag(ctx["product"], ctx["version"], ctx["commit"], ctx["captured"], ctx.get("reviewed", ""))
            + changes
            + (f'<section class="stack"><h2>By role</h2>{role_html}</section>' if role_html else "")
            + (f'<section class="stack"><h2>By experience</h2><div class="levels">{tier_html}</div></section>' if tier_html else ""))


def find_chrome() -> str | None:
    cands = [os.environ.get("ASDR_CHROME"), "/opt/pw-browsers/chromium",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    home = Path.home()
    for pat in ("Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                "Library/Caches/ms-playwright/chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                ".cache/ms-playwright/chromium-*/chrome-linux*/chrome"):
        cands += sorted(str(x) for x in home.glob(pat))
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        w = shutil.which(name)
        if w:
            cands.append(w)
    return next((c for c in cands if c and Path(c).is_file()), None)


def to_pdf(chrome: str, html_file: Path, pdf_file: Path) -> bool:
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
           "--virtual-time-budget=8000", f"--print-to-pdf={pdf_file}", html_file.resolve().as_uri()]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:  # noqa: BLE001
        return False
    return pdf_file.is_file() and pdf_file.stat().st_size > 1000


# ── human review ───────────────────────────────────────────────────────────

def record_review(args, catalog: dict, review: dict, path: Path, manual_dir: Path) -> int:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    who = args.reviewer or os.environ.get("USER") or "unknown"
    if args.flag:
        keys, status = [args.flag], "needs-fix"
        if not args.note:
            print("ERROR: --flag needs --note saying what is wrong")
            return 1
    else:
        keys = list(catalog) if args.approve.strip() == "all" else [k.strip() for k in args.approve.split(",") if k.strip()]
        status = "approved"
    unknown = [k for k in keys if k not in catalog]
    if unknown:
        print(f"ERROR: not a step used by any manual: {', '.join(unknown)}")
        return 1
    steps = review.setdefault("steps", {})
    for k in keys:
        c = catalog[k]
        steps[k] = {"status": status, "hash": entry_hash(c["entry"]), "reviewer": who, "at": now,
                    "screen": file_sha(manual_dir / c["screenshot"]), "note": args.note or None}
    review["schema"] = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n")
    print(f"OK: {len(keys)} step(s) {status} by {who} in {path}")
    return 0


def write_review_page(out: Path, spec: dict, catalog: dict, states: dict, manual_dir: Path,
                      problems: list, version, commit) -> None:
    badge = {"approved": ("passed", "Approved"), "changed": ("skipped", "Changed since approval"),
             "new": ("neutral", "Not reviewed yet"), "needs-fix": ("failed", "Needs fixing")}
    order = {"needs-fix": 0, "changed": 1, "new": 2, "approved": 3}
    cards = []
    for k in sorted(catalog, key=lambda k: (order[states[k][0]], k)):
        c, (st, rec) = catalog[k], states[k]
        cls, label = badge[st]
        shot = manual_dir / c["screenshot"]
        src = ("data:image/png;base64," + base64.b64encode(shot.read_bytes()).decode()) if shot.is_file() else ""
        texts = {}
        for lid, t in c["levels"].items():
            texts.setdefault(t, []).append(lid)
        body = "".join(f'<p>{md(t)}</p><p class="muted mono">used in: {e(", ".join(lids))}</p>' for t, lids in texts.items())
        note = (f'<p class="note">{e(rec.get("reviewer") or "")}: {e(rec.get("note") or "")}</p>'
                if rec and rec.get("note") else "")
        cards.append(f'<div class="step"><div class="text"><div class="row"><span class="pill {cls}">{label}</span>'
                     f'<code>{e(k)}</code></div><h3>{e(c["title"])}</h3>{body}{note}</div>'
                     f'<img src="{src}" alt="{e(c["title"])}"></div>')
    counts = {s: sum(1 for v in states.values() if v[0] == s) for s in order}
    probs = ("".join(f"<li>{e(p)}</li>" for p in problems))
    head = (f'<header class="stack"><span class="eyebrow">{e(spec.get("product") or "")} · manual review · '
            f'version {e(str(version))} · commit {e(commit or "unknown")}</span><h1>Manual review</h1>'
            '<p>Read each explanation against its screenshot: is it what a user sees, in words they would use? '
            'Then reply in chat with <strong>approve all</strong>, or name the steps that need changes, '
            'for example <code>flag member-basics/add-task: the button is on the right</code>.</p>'
            f'<p class="muted mono">{counts["needs-fix"]} need fixing · {counts["changed"]} changed · '
            f'{counts["new"]} not reviewed · {counts["approved"]} approved</p></header>'
            + (f'<section class="band"><h2>Automatic checks found</h2><ul class="toc">{probs}</ul></section>' if probs else ""))
    page_html = page(f'{e(spec.get("product") or "Product")} Manual Review',
                     f'<main class="wrap">{head}{"".join(cards)}</main>', fragment=True)
    out.write_text(page_html)


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Build persona and tier user manuals from tour screenshots.")
    ap.add_argument("--spec", default="docs/manuals/manual.json")
    ap.add_argument("--manual-dir", default=".harness/manual")
    ap.add_argument("--out", default="docs/manuals")
    ap.add_argument("--version", default=None)
    ap.add_argument("--commit", default=None, help="commit the release is cut from (default: git HEAD)")
    ap.add_argument("--changelog", default="CHANGELOG.md")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--allow-stale", action="store_true", help="accept screenshots from another commit (drafts)")
    ap.add_argument("--artifact", metavar="FILE", help="also write all manuals as one self-contained page")
    ap.add_argument("--check", action="store_true", help="validate only; write nothing")
    ap.add_argument("--review-file", default=None, help="default: review.json next to the spec")
    ap.add_argument("--review-page", metavar="FILE", help="write the human review page and stop")
    ap.add_argument("--approve", metavar="all|KEY,KEY", help="record approval of the current explanations")
    ap.add_argument("--flag", metavar="KEY", help="record that a step's explanation needs fixing")
    ap.add_argument("--note", default="", help="what is wrong (with --flag) or a remark (with --approve)")
    ap.add_argument("--reviewer", default=None, help="who reviewed (with --approve / --flag)")
    ap.add_argument("--compare-to", default="auto", help="auto | <version> | none (screen changes)")
    ap.add_argument("--require-review", action="store_true",
                    help="fail unless a person approved every explanation in use (release builds)")
    args = ap.parse_args()

    spec_path, manual_dir = Path(args.spec), Path(args.manual_dir)
    if not spec_path.is_file():
        print(f"ERROR: no manual spec at {spec_path}. Copy .harness/templates/e2e/manual.json.")
        return 1
    spec = json.loads(spec_path.read_text())
    tours = load_tours(manual_dir)
    if not tours:
        print(f"ERROR: no tour manifests in {manual_dir}/tours — run run_tests.py (tours) first.")
        return 1
    commit = args.commit or os.environ.get("ASDR_COMMIT") or git_head()
    version = args.version or spec.get("version")
    if not version and Path("package.json").is_file():
        version = json.loads(Path("package.json").read_text()).get("version")
    version = version or (commit or "draft")

    catalog = {}
    levels, problems, warnings = plan(spec, tours, manual_dir, commit, args.allow_stale, catalog)
    review_path = Path(args.review_file) if args.review_file else spec_path.parent / "review.json"
    review = load_review(review_path)
    states = {k: review_state(k, c["entry"], review) for k, c in catalog.items()}

    if args.approve or args.flag:
        return record_review(args, catalog, review, review_path, manual_dir)
    if args.review_page:
        write_review_page(Path(args.review_page), spec, catalog, states, manual_dir, problems, version, commit)
        counts = {s: sum(1 for v in states.values() if v[0] == s) for s in ("approved", "changed", "new", "needs-fix")}
        print(f"OK: review page {args.review_page} — {len(catalog)} steps: " +
              ", ".join(f"{n} {k}" for k, n in counts.items() if n))
        return 0
    if args.require_review:
        for k, (st, rec) in states.items():
            if st == "needs-fix":
                problems.append(f"step '{k}' was flagged for fixing by {rec.get('reviewer')}: {rec.get('note')}")
            elif st != "approved":
                problems.append(f"step '{k}' explanation is {'new' if st == 'new' else 'changed since it was approved'} "
                                "and has not been reviewed by a person — run --review-page, then --approve")
    for w in warnings:
        print(f"WARN: {w}")
    if problems:
        for p in problems:
            print(f"ERROR: {p}")
        print(f"FAIL: {len(problems)} problem(s); no manual written.")
        return 1
    steps_total = sum(len(s["steps"]) for lv in levels for s in lv["sections"])
    if args.check:
        print(f"OK: {len(levels)} manuals, {steps_total} steps, all screenshots present and current.")
        return 0

    captured = max((m.get("captured_at") or "" for m in tours.values()), default="")[:10] or "unknown"
    approved = [rec for st, rec in states.values() if st == "approved"]
    if catalog and len(approved) == len(catalog):
        who = sorted({r.get("reviewer") or "a reviewer" for r in approved})
        last = max((r.get("at") or "")[:10] for r in approved)
        reviewed = f"Explanations reviewed by {', '.join(who)} (latest {last})"
    else:
        reviewed = f"Explanations not yet fully reviewed by a person ({len(approved)} of {len(catalog)} approved)"
    ctx = {"reviewed": reviewed, "product": spec.get("product") or "The product", "version": str(version), "commit": commit,
           "captured": captured, "intro": spec.get("intro"),
           "whats_new": whats_new(spec, Path(args.changelog), str(version))}
    out = Path(args.out) / re.sub(r"[^A-Za-z0-9._-]+", "-", str(version))
    if out.exists():
        shutil.rmtree(out)
    (out / "screens").mkdir(parents=True)
    used = {st["screenshot"] for lv in levels for s in lv["sections"] for st in s["steps"]}
    for rel in used:
        shutil.copy2(manual_dir / rel, out / rel)

    prev = find_previous(Path(args.out), str(version), args.compare_to)
    if args.compare_to not in ("auto", "none") and not prev:
        warnings.append(f"--compare-to {args.compare_to}: no such earlier build in {args.out}; skipped")
        print(f"WARN: {warnings[-1]}")
    if prev:
        prev_version, prev_dir = prev
        rep_ = compare_dirs(prev_dir / "screens", manual_dir / "screens", out / "changes",
                            only={Path(r).name for r in used})
        for c in rep_["changed"]:
            if (prev_dir / "screens" / c["name"]).is_file():
                shutil.copy2(prev_dir / "screens" / c["name"], out / "changes" / f"before--{c['name']}")
        ctx["ui"] = {"compared_to": prev_version, "changed": rep_["changed"], "added": rep_["added"],
                     "removed": rep_["removed"], "changed_names": {c["name"] for c in rep_["changed"]}}
        ctx["ui_link"] = "ui-changes.html"

        def rel_src(kind, name):
            f = {"before": f"changes/before--{name}", "after": f"screens/{name}", "diff": f"changes/diff--{name}"}[kind]
            return f if (out / f).is_file() else None
        (out / "ui-changes.html").write_text(page(f'{e(ctx["product"])} Screen Changes',
                                                  f'<main class="wrap">{ui_changes_body(ctx, rel_src)}{footer(ctx)}</main>{ZOOM_JS}'))
        print(f"OK: compared with {prev_version}: {len(rep_['changed'])} screens changed, "
              f"{len(rep_['added'])} new, {len(rep_['removed'])} removed")

    chrome = None if args.no_pdf else find_chrome()
    if not args.no_pdf and not chrome:
        warnings.append("no Chrome/Chromium found for PDF output (set ASDR_CHROME); wrote HTML only")
        print(f"WARN: {warnings[-1]}")
    files = []
    for lv in levels:
        body = f'<main class="wrap">{render_level(lv, ctx, lambda r: r)}{footer(ctx)}</main>'
        f = out / f'{lv["id"]}.html'
        f.write_text(page(f'{e(ctx["product"])} {e(lv["title_text"])}', body))
        rec = {"id": lv["id"], "kind": lv.get("kind"), "title": lv["title_text"], "html": f.name, "pdf": None}
        if chrome:
            pdf = out / f'{lv["id"]}.pdf'
            if to_pdf(chrome, f, pdf):
                rec["pdf"] = pdf.name
            else:
                warnings.append(f"PDF failed for {lv['id']}")
                print(f"WARN: {warnings[-1]}")
        files.append(rec)

    pdfs = {r["id"]: r["pdf"] for r in files}
    (out / "index.html").write_text(page(
        f'{e(ctx["product"])} User Manuals',
        f'<main class="wrap">{index_body(levels, ctx, lambda lv, kind: lv["id"] + ".html" if kind == "html" else pdfs.get(lv["id"]))}'
        f'{footer(ctx)}</main>'))
    build = {"schema": 1, "product": ctx["product"], "version": ctx["version"], "commit": commit,
             "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "screenshots_captured": captured, "tours": sorted(tours), "levels": files,
             "steps": steps_total, "warnings": warnings,
             "review": {s: sum(1 for v in states.values() if v[0] == s)
                        for s in ("approved", "changed", "new", "needs-fix")},
             "ui_changes": ({k: v for k, v in ctx["ui"].items() if k != "changed_names"} if ctx.get("ui") else None)}
    (out / "build.json").write_text(json.dumps(build, indent=2))

    root = Path(args.out)
    versions = []
    for d in root.iterdir():
        b = d / "build.json"
        if b.is_file():
            try:
                versions.append((d.name, json.loads(b.read_text())))
            except ValueError:
                continue
    versions.sort(key=lambda v: v[1].get("built_at") or "", reverse=True)
    rows = "".join(f'<tr><td><a href="{e(n)}/index.html">{e(b.get("version"))}</a></td><td>{e(b.get("commit") or "—")}</td>'
                   f'<td>{e((b.get("built_at") or "")[:10])}</td><td>{len(b.get("levels", []))}</td></tr>' for n, b in versions)
    (root / "index.html").write_text(page(
        f'{e(ctx["product"])} Manual Versions',
        f'<main class="wrap"><header class="stack"><span class="eyebrow">{e(ctx["product"])}</span><h1>User manuals by version</h1></header>'
        '<div class="table-wrap"><table><thead><tr><th>Version</th><th>Commit</th><th>Built</th><th>Manuals</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div></main>'))
    (root / "latest.json").write_text(json.dumps({"version": ctx["version"], "path": str(out)}, indent=2))

    if args.artifact:
        cache = {}

        def inline(rel):
            if rel not in cache:
                cache[rel] = "data:image/png;base64," + base64.b64encode((manual_dir / rel).read_bytes()).decode()
            return cache[rel]
        if ctx.get("ui"):
            ctx["ui_link"] = "#ui-changes"
        parts = [index_body(levels, ctx, lambda lv, kind: f'#{lv["id"]}' if kind == "html" else None)]
        for lv in levels:
            parts.append(f'<hr id="{lv["id"]}">' + render_level(lv, ctx, inline, anchor_prefix=f'{lv["id"]}-')
                         + '<p><a href="#top">Back to all manuals</a></p>')
        if ctx.get("ui") and ctx["ui"]["changed"]:
            def data_src(kind, name):
                f = out / {"before": f"changes/before--{name}", "after": f"screens/{name}",
                           "diff": f"changes/diff--{name}"}[kind]
                return ("data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()) if f.is_file() else None
            parts.append('<hr id="ui-changes">' + ui_changes_body(ctx, data_src))
        body = f'<main class="wrap" id="top">{"".join(parts)}{footer(ctx)}</main>{ZOOM_JS}'
        Path(args.artifact).write_text(page(f'{e(ctx["product"])} User Manuals', body, fragment=True))
        print(f"OK: single-page manual for a private Artifact: {args.artifact} "
              f"({Path(args.artifact).stat().st_size / 1024 / 1024:.1f} MB)")

    print(f"OK: {len(files)} manuals ({sum(1 for r in files if r['pdf'])} PDF) for {ctx['product']} "
          f"{ctx['version']} at commit {commit} → {out}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
