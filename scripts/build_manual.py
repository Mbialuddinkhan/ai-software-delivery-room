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
from report_style import page  # noqa: E402

e = html.escape
TIER_ORDER = ["beginner", "everyday", "power", "administrator"]


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

def plan(spec: dict, tours: dict, manual_dir: Path, commit: str | None, allow_stale: bool):
    problems, warnings, built = [], [], []
    seen_ids, used = set(), set()
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
                    steps.append({"key": key, "title": st.get("title") or st["id"], "text": text or "",
                                  "note": st.get("note"), "screenshot": st["screenshot"], "url": st.get("url")})
            if not steps:
                problems.append(f"{where}: no steps")
            sections.append({"title": sec.get("title") or f"Part {si + 1}", "intro": sec.get("intro"),
                             "steps": steps})
        if not sections:
            problems.append(f"level '{lid}' has no sections")
        built.append({**lv, "title_text": level_title(lv), "sections": sections})

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

def version_flag(product: str, version: str, commit: str | None, captured: str) -> str:
    return ('<div class="version-flag" role="note"><span class="eyebrow">This manual matches</span>'
            f'<strong>{e(product)} {e(version)}</strong>'
            f'<span class="muted mono">commit {e(commit or "unknown")} · screenshots taken {e(captured)}</span></div>')


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
                f'<div class="step"><div class="text"><span class="num">STEP {n}</span>'
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
        + version_flag(ctx["product"], ctx["version"], ctx["commit"], ctx["captured"])
        + new
        + f'<nav class="band" aria-label="Contents"><h2>In this guide</h2><ol class="toc">{toc}</ol>'
          '<p class="muted">In every screenshot, the part of the screen you use is outlined in red.</p></nav>'
        + "".join(secs))


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
    return (f'<header class="stack"><span class="eyebrow">{e(ctx["product"])}</span><h1>User manuals</h1>'
            + (f'<p>{md(ctx["intro"])}</p>' if ctx.get("intro") else "") + '</header>'
            + version_flag(ctx["product"], ctx["version"], ctx["commit"], ctx["captured"])
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

    levels, problems, warnings = plan(spec, tours, manual_dir, commit, args.allow_stale)
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
    ctx = {"product": spec.get("product") or "The product", "version": str(version), "commit": commit,
           "captured": captured, "intro": spec.get("intro"),
           "whats_new": whats_new(spec, Path(args.changelog), str(version))}
    out = Path(args.out) / re.sub(r"[^A-Za-z0-9._-]+", "-", str(version))
    if out.exists():
        shutil.rmtree(out)
    (out / "screens").mkdir(parents=True)
    used = {st["screenshot"] for lv in levels for s in lv["sections"] for st in s["steps"]}
    for rel in used:
        shutil.copy2(manual_dir / rel, out / rel)

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
             "steps": steps_total, "warnings": warnings}
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
        parts = [index_body(levels, ctx, lambda lv, kind: f'#{lv["id"]}' if kind == "html" else None)]
        for lv in levels:
            parts.append(f'<hr id="{lv["id"]}">' + render_level(lv, ctx, inline, anchor_prefix=f'{lv["id"]}-')
                         + '<p><a href="#top">Back to all manuals</a></p>')
        body = f'<main class="wrap" id="top">{"".join(parts)}{footer(ctx)}</main>'
        Path(args.artifact).write_text(page(f'{e(ctx["product"])} User Manuals', body, fragment=True))
        print(f"OK: single-page manual for a private Artifact: {args.artifact} "
              f"({Path(args.artifact).stat().st_size / 1024 / 1024:.1f} MB)")

    print(f"OK: {len(files)} manuals ({sum(1 for r in files if r['pdf'])} PDF) for {ctx['product']} "
          f"{ctx['version']} at commit {commit} → {out}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
