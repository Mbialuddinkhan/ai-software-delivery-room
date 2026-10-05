#!/usr/bin/env python3
"""Turn a run_tests.py bundle into a readable test report and publish it.

Usage:
  python3 publish_test_report.py [--run latest|<run_dir>] [--label TEXT]
                                 [--out docs/test-reports] [--no-repo]
                                 [--inline FILE] [--fragment] [--max-inline-mb 12]

Where the report goes is set per project in .harness/publish.json (seeded by
init_asdr.py). Private by default:

  {"repo": true,             docs/test-reports/<label>/  (committed with the code)
   "ci_artifacts": true,     the CI workflow uploads the run folder + report
   "claude_artifact": true,  a single-file copy for a private claude.ai page
   "github_pages": false}    public. Only when the user opts in for the project

repo: writes docs/test-reports/<label>/index.html with the screenshots,
videos, traces, logs and Playwright HTML report it links to, plus
docs/test-reports/index.html listing every published run.

claude_artifact: writes <run>/report-artifact.html — one self-contained file
(images and, within --max-inline-mb, videos embedded), without doctype/head
tags, ready for the Artifact tool. The orchestrator publishes it; this script
only prepares it (it cannot reach claude.ai).

ci_artifacts and github_pages are honoured by the CI workflow
(templates/ci-asdr.yml); this script reports them so the agent can say where
results went. The last line printed is `PUBLISH: {json}` for agents to parse.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_style import ZOOM_JS, page  # noqa: E402

DEFAULT_PUBLISH = {"repo": True, "ci_artifacts": True, "claude_artifact": True, "github_pages": False}
IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VID = {".webm", ".mp4"}
STATUS_ORDER = {"failed": 0, "error": 1, "skipped": 2, "passed": 3}
e = html.escape


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "run"


def load_publish(root: Path) -> dict:
    cfg = dict(DEFAULT_PUBLISH)
    p = root / ".harness" / "publish.json"
    if p.is_file():
        try:
            cfg.update(json.loads(p.read_text()))
        except ValueError:
            print(f"WARN: {p} is not valid JSON; using private defaults")
    return cfg


def resolve_run(root: Path, run: str) -> Path:
    if run != "latest":
        return Path(run).resolve()
    latest = root / ".harness" / "test-results" / "latest.json"
    if not latest.is_file():
        raise SystemExit("ERROR: no .harness/test-results/latest.json — run run_tests.py first")
    return Path(json.loads(latest.read_text())["path"])


class Assets:
    """Maps run-folder files to what the page references: a copied path or a data URI."""

    def __init__(self, run_dir: Path, out_dir: Path | None, inline: bool, budget_mb: float):
        self.run_dir, self.out_dir, self.inline = run_dir, out_dir, inline
        self.budget = budget_mb * 1024 * 1024
        self.used = 0
        self.skipped = []

    def ref(self, rel: str, kind: str = "file") -> str | None:
        src = self.run_dir / rel
        if not src.is_file():
            return None
        if self.inline:
            size = src.stat().st_size
            if kind != "image" and self.used + size > self.budget:
                self.skipped.append(rel)
                return None
            self.used += size
            mime = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
            if src.suffix == ".webm":
                mime = "video/webm"
            return f"data:{mime};base64,{base64.b64encode(src.read_bytes()).decode()}"
        dest = self.out_dir / "assets" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src, dest)
        return f"assets/{rel}"

    def copy_tree(self, rel_dir: str) -> str | None:
        if self.inline:
            return None
        src = self.run_dir / rel_dir
        if not src.is_dir():
            return None
        dest = self.out_dir / "assets" / rel_dir
        if not dest.exists():
            shutil.copytree(src, dest)
        return f"assets/{rel_dir}"


def bar(t: dict) -> str:
    total = max(t.get("tests", 0), 1)
    parts = "".join(f'<span class="{k}" style="width:{100 * t.get(k, 0) / total:.2f}%"></span>'
                    for k in ("passed", "failed", "error", "skipped") if t.get(k))
    return f'<div class="bar" role="img" aria-label="{t.get("passed", 0)} of {t.get("tests", 0)} passed">{parts}</div>'


def counts(t: dict) -> str:
    def part(key, word, var):
        n = t.get(key, 0)
        style = f' style="color:var({var})"' if n else ' class="zero"'
        return f'<span{style}><b>{n}</b> {word}</span>'
    return ('<div class="counts">'
            f'<span><b>{t.get("tests", 0)}</b> tests</span>'
            + part("passed", "passed", "--pass") + part("failed", "failed", "--fail")
            + part("error", "errors", "--err") + part("skipped", "skipped", "--skip") + '</div>')


def when(iso: str | None) -> str:
    """2026-10-05T16:09:45+00:00 -> 2026-10-05 16:09 UTC"""
    if not iso:
        return "—"
    return iso.replace("T", " ")[:16] + (" UTC" if iso.endswith("+00:00") else "")


MODE_TEXT = {
    "live": "Live — headed browser, slowed down, watched on screen",
    "recorded": "Recorded — no screen available, so it ran headless with video",
    "ci": "Headless (CI)",
    "collected": "Collected from an existing run",
}


def case_html(c: dict, assets: Assets) -> str:
    st = c["status"]
    body = []
    if c.get("message"):
        body.append(f"<pre>{e(c['message'])}</pre>")
    shots, vids, files = [], [], []
    for rel in c.get("attachments", []):
        ext = Path(rel).suffix.lower()
        if ext in IMG:
            src = assets.ref(rel, "image")
            if src:
                cap = Path(rel).name
                shots.append(f'<figure><img loading="lazy" src="{src}" alt="Screenshot {e(cap)}">'
                             f'<figcaption>{e(cap)}</figcaption></figure>')
        elif ext in VID:
            src = assets.ref(rel, "video")
            vids.append(f'<video controls preload="none" src="{src}"></video>' if src else
                        f'<p class="muted">Video {e(Path(rel).name)} is in the repo report and CI artifacts.</p>')
        else:
            src = assets.ref(rel) if not assets.inline else None
            files.append(f'<a href="{src}">{e(Path(rel).name)}</a>' if src else f'<code>{e(rel)}</code>')
    if shots:
        body.append(f'<div class="shots">{"".join(shots)}</div>')
    body += vids
    if files:
        body.append(f'<div class="links"><span class="muted">Files:</span> {" ".join(files)}</div>')
    if not body:
        body.append('<p class="muted">No screenshots or messages recorded for this test.</p>')
    opened = " open" if st in ("failed", "error") else ""
    where = f'<div class="muted mono">{e(c["file"])}</div>' if c.get("file") else ""
    return (f'<details class="case {st}"{opened}><summary><span class="pill {st}">{st}</span>'
            f'<span class="name">{e(c["name"] or "")}</span><span class="t">{c.get("time", 0):.2f}s</span></summary>'
            f'<div class="case-body">{where}{"".join(body)}</div></details>')


def history_rows(run_dir: Path) -> list:
    hist = run_dir.parent / "history.jsonl"
    if not hist.is_file():
        return []
    rows = []
    for line in hist.read_text().splitlines()[-12:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(rows))


def build_report(s: dict, run_dir: Path, assets: Assets) -> str:
    t = s["totals"]
    st = s["status"]
    head = (
        '<header class="band">'
        f'<div class="row"><span class="eyebrow">Test report · {e(s.get("product") or "project")}</span>'
        f'<span class="pill {st}">{"All tests passed" if st == "passed" else "Tests failed"}</span></div>'
        f'<h1>{e(s.get("label") or s["run_id"])}</h1>'
        f'{bar(t)}{counts(t)}'
        '<dl class="facts">'
        f'<div><dt class="eyebrow">Commit</dt><dd>{e(s.get("commit") or "—")}'
        f'{"<small>plus uncommitted changes</small>" if s.get("dirty") else ""}</dd></div>'
        f'<div><dt class="eyebrow">Branch</dt><dd>{e(s.get("branch") or "—")}</dd></div>'
        f'<div><dt class="eyebrow">Run</dt><dd>{e(s["run_id"])}</dd></div>'
        f'<div><dt class="eyebrow">Finished</dt><dd>{e(when(s.get("finished_at")))}</dd></div>'
        f'<div><dt class="eyebrow">Duration</dt><dd>{s.get("duration_s", 0)} s</dd></div>'
        f'<div><dt class="eyebrow">App URL</dt><dd>{e((s.get("environment") or {}).get("base_url") or "—")}</dd></div>'
        '</dl>'
        f'<p class="muted">Mode: {e(MODE_TEXT.get(s.get("mode"), s.get("mode") or ""))}'
        f'{" · manual tours only" if s.get("tours_only") else ""}.</p>'
        '</header>')

    suites = []
    for su in s["suites"]:
        links = []
        if su.get("html_report"):
            d = assets.copy_tree(str(Path(su["html_report"]).parent))
            if d:
                links.append(f'<a href="{d}/{Path(su["html_report"]).name}">Full {e(su["framework"] or "")} report</a>')
        if su.get("log") and not assets.inline:
            ref = assets.ref(su["log"])
            if ref:
                links.append(f'<a href="{ref}">Console log</a>')
        for j in su.get("junit", []):
            if not assets.inline:
                ref = assets.ref(j)
                if ref:
                    links.append(f'<a href="{ref}">{e(Path(j).name)}</a>')
        log_tail = ""
        if assets.inline and su.get("log") and su["totals"].get("failed", 0) + su["totals"].get("error", 0):
            lines = (run_dir / su["log"]).read_text(errors="ignore").splitlines()[-60:]
            log_tail = f'<details><summary>Last 60 lines of the console log</summary><pre>{e(chr(10).join(lines))}</pre></details>'
        cases = sorted(su["cases"], key=lambda c: STATUS_ORDER.get(c["status"], 9))
        suites.append(
            f'<section class="suite" id="{e(slug(su["name"]))}">'
            f'<div class="row"><h2>{e(su["name"])}</h2><span class="pill neutral">{e(su.get("framework") or "")}</span>'
            f'<span class="muted mono">exit {su.get("exit_code")} · {su.get("duration_s") or 0} s</span></div>'
            f'{bar(su["totals"])}{counts(su["totals"])}'
            + (f'<div class="links">{"".join(links)}</div>' if links else "")
            + (f'<div class="muted mono">$ {e(su["cmd"])}</div>' if su.get("cmd") else "")
            + log_tail
            + f'<div class="cases">{"".join(case_html(c, assets) for c in cases)}</div></section>')

    m = s.get("manual") or {}
    tours = "".join(
        f'<tr><td>{e(x["tour"])}</td><td>{e(x.get("framework") or "")}</td><td>{x["steps"]}</td>'
        f'<td>{e(x.get("commit") or "—")}</td><td><span class="pill {"passed" if x.get("current") else "skipped"}">'
        f'{"current" if x.get("current") else "older build"}</span></td></tr>' for x in m.get("tours", []))
    manual = (
        '<section class="stack"><h2>Manual screenshots captured</h2>'
        f'<p class="muted">{len(m.get("tours", []))} tours, {m.get("screenshots", 0)} screenshots. '
        'build_manual.py turns these into the user manuals.</p>'
        + (f'<div class="table-wrap"><table><thead><tr><th>Tour</th><th>Framework</th><th>Steps</th>'
           f'<th>Commit</th><th>State</th></tr></thead><tbody>{tours}</tbody></table></div>' if tours else "")
        + '</section>')

    hist = history_rows(run_dir)
    history = ""
    if hist:
        rows = "".join(
            f'<tr><td>{e(when(h.get("finished_at")))}</td><td>{e(h.get("commit") or "—")}</td>'
            f'<td>{e(h.get("mode") or "")}</td><td><span class="pill {e(h.get("status") or "")}">{e(h.get("status") or "")}</span></td>'
            f'<td>{h.get("passed", 0)}/{h.get("tests", 0)}</td><td>{h.get("failed", 0) + h.get("error", 0)}</td></tr>'
            for h in hist)
        history = ('<section class="stack"><h2>Recent runs</h2><div class="table-wrap"><table><thead><tr>'
                   '<th>Finished</th><th>Commit</th><th>Mode</th><th>Status</th><th>Passed</th><th>Failed</th>'
                   f'</tr></thead><tbody>{rows}</tbody></table></div></section>')

    skipped = ""
    if assets.skipped:
        skipped = (f'<p class="muted">{len(assets.skipped)} large files (videos, traces) were left out of this '
                   'single-file copy to keep it small. They are in the repo report and the CI artifacts.</p>')
    foot = (f'<footer>Generated by ASDR publish_test_report.py from {e(s["run_id"])}. '
            'Each test links to the evidence its framework recorded.</footer>')
    return f'<main class="wrap">{head}{"".join(suites)}{manual}{history}{skipped}{foot}</main>{ZOOM_JS}'


def write_index(out_root: Path, fragment: bool = False) -> None:
    runs = []
    for d in out_root.iterdir() if out_root.is_dir() else []:
        f = d / "summary.json"
        if f.is_file():
            try:
                runs.append((d.name, json.loads(f.read_text())))
            except ValueError:
                continue
    runs.sort(key=lambda r: r[1].get("finished_at") or "", reverse=True)
    rows = "".join(
        f'<tr><td><a href="{e(name)}/index.html">{e(s.get("label") or name)}</a></td>'
        f'<td>{e(when(s.get("finished_at")))}</td><td>{e(s.get("commit") or "—")}</td><td>{e(s.get("mode") or "")}</td>'
        f'<td><span class="pill {e(s.get("status") or "")}">{e(s.get("status") or "")}</span></td>'
        f'<td>{s["totals"].get("passed", 0)}/{s["totals"].get("tests", 0)}</td></tr>' for name, s in runs)
    product = next((s.get("product") for _, s in runs if s.get("product")), "Project")
    body = (f'<main class="wrap"><header class="stack"><span class="eyebrow">{e(product)}</span><h1>Test reports</h1>'
            f'<p class="muted">{len(runs)} published runs, newest first.</p></header>'
            '<div class="table-wrap"><table><thead><tr><th>Report</th><th>Finished</th><th>Commit</th><th>Mode</th>'
            f'<th>Status</th><th>Passed</th></tr></thead><tbody>{rows}</tbody></table></div></main>')
    (out_root / "index.html").write_text(page(f"{e(product)} Test Reports", body, fragment))


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a run_tests.py bundle as a test report.")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--label", default=None)
    ap.add_argument("--out", default="docs/test-reports")
    ap.add_argument("--no-repo", action="store_true", help="skip the docs/test-reports copy")
    ap.add_argument("--inline", metavar="FILE", default=None, help="write a single-file report here")
    ap.add_argument("--fragment", action="store_true", help="omit doctype/head/body (Artifact tool format)")
    ap.add_argument("--max-inline-mb", type=float, default=12.0)
    args = ap.parse_args()

    root = Path.cwd()
    pub = load_publish(root)
    run_dir = resolve_run(root, args.run)
    s = json.loads((run_dir / "summary.json").read_text())
    if args.label:
        s["label"] = args.label
    title = f'{s.get("product") or "Test"} {s.get("label") or s["run_id"]}'
    outputs = {}

    if pub.get("repo") and not args.no_repo:
        out_dir = Path(args.out) / slug(s.get("label") or s["run_id"])
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        html_text = build_report(s, run_dir, Assets(run_dir, out_dir, False, 0))
        (out_dir / "index.html").write_text(page(f"{e(title)} Report", html_text))
        (out_dir / "summary.json").write_text(json.dumps(s, indent=2))
        write_index(Path(args.out))
        outputs["repo"] = str(out_dir / "index.html")

    inline_path = args.inline
    if not inline_path and pub.get("claude_artifact"):
        inline_path = str(run_dir / "report-artifact.html")
        args.fragment = True
    if inline_path:
        assets = Assets(run_dir, None, True, args.max_inline_mb)
        html_text = build_report(s, run_dir, assets)
        Path(inline_path).write_text(page(f"{e(title)} Report", html_text, args.fragment))
        outputs["claude_artifact" if args.fragment else "inline"] = inline_path
        mb = Path(inline_path).stat().st_size / 1024 / 1024
        print(f"OK: single-file report {inline_path} ({mb:.1f} MB"
              f"{f', {len(assets.skipped)} large files left out' if assets.skipped else ''})")

    if pub.get("ci_artifacts"):
        outputs["ci_artifacts"] = "uploaded by the CI workflow (asdr-test-results)"
    if pub.get("github_pages"):
        outputs["github_pages"] = "deployed by the CI workflow's pages job (public)"
    for k, v in outputs.items():
        print(f"  {k}: {v}")
    print("PUBLISH: " + json.dumps({"status": s["status"], "label": s.get("label"), "outputs": outputs}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
