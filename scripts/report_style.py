"""Shared page style for publish_test_report.py and build_manual.py.

One stylesheet so the test report and the user manuals look like they come
from the same product. Tokens follow the claude.ai Artifact contract (light
values on :root, dark values under prefers-color-scheme and [data-theme]), so
the same HTML works as a repo page, a CI artifact and a private Artifact.
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600;700'
         '&family=IBM+Plex+Mono:wght@400;500&display=swap">')

CSS = r"""
/* Layout: a single reading column; summary band first, detail rows after. */
:root {
  --bg: #f5f6f8; --surface: #ffffff; --fg: #17202b; --muted: #5a6573; --line: #dde2e8;
  --accent: #2f5d8a; --pass: #1f7a4d; --fail: #c2382f; --skip: #9a6b00; --err: #8a3fb0;
  --pass-bg: #e6f3ec; --fail-bg: #fbe9e7; --skip-bg: #fbf1dc; --err-bg: #f3e8f8;
  --hl: #e5484d;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11161c; --surface: #19212a; --fg: #e4e9ef; --muted: #9aa6b3; --line: #2b3542;
  --accent: #7fb0e0; --pass: #5cc98f; --fail: #f07a70; --skip: #e0b04a; --err: #c79be0;
  --pass-bg: #163326; --fail-bg: #3a1d1b; --skip-bg: #33290f; --err-bg: #2d1f36;
  --hl: #ff6b70; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #11161c; --surface: #19212a; --fg: #e4e9ef; --muted: #9aa6b3; --line: #2b3542;
  --accent: #7fb0e0; --pass: #5cc98f; --fail: #f07a70; --skip: #e0b04a; --err: #c79be0;
  --pass-bg: #163326; --fail-bg: #3a1d1b; --skip-bg: #33290f; --err-bg: #2d1f36;
  --hl: #ff6b70; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font: 15px/1.55 var(--body); margin: 0; }
.wrap { max-width: 1040px; margin: 0 auto; padding-inline: 20px; padding-block: 28px 64px; display: grid; gap: 28px; }
h1, h2, h3 { font-family: var(--display); line-height: 1.15; text-wrap: balance; margin: 0; }
h1 { font-size: 2rem; } h2 { font-size: 1.35rem; } h3 { font-size: 1.05rem; }
p { margin: 0; max-width: 68ch; }
a { color: var(--accent); }
a:focus-visible, summary:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
code, .mono { font-family: var(--mono); font-size: .88em; }
.muted { color: var(--muted); }
.eyebrow { font: 500 .72rem/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.row { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
.stack { display: grid; gap: 12px; min-width: 0; }
.band { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 20px; display: grid; gap: 16px; }
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font: 600 .78rem/1.4 var(--body); }
.pill.passed { background: var(--pass-bg); color: var(--pass); }
.pill.failed { background: var(--fail-bg); color: var(--fail); }
.pill.error { background: var(--err-bg); color: var(--err); }
.pill.skipped { background: var(--skip-bg); color: var(--skip); }
.pill.neutral { background: var(--bg); color: var(--muted); border: 1px solid var(--line); }
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px 20px; margin: 0; }
.facts div { min-width: 0; } .facts dt { margin-bottom: 2px; }
.facts dd { margin: 0; font: 500 .95rem/1.3 var(--mono); font-variant-numeric: tabular-nums; overflow-wrap: break-word; }
.facts dd small { display: block; font: .75rem var(--body); color: var(--muted); }
.bar { display: flex; height: 10px; border-radius: 5px; overflow: hidden; background: var(--line); }
.bar span { display: block; height: 100%; }
.bar .passed { background: var(--pass); } .bar .failed { background: var(--fail); }
.bar .error { background: var(--err); } .bar .skipped { background: var(--skip); }
.counts { font: 500 .85rem/1 var(--mono); font-variant-numeric: tabular-nums; display: flex; flex-wrap: wrap; gap: 6px 14px; }
.counts b { font-weight: 600; }
.counts .zero { color: var(--muted); }
section.suite { display: grid; gap: 10px; }
.cases { border: 1px solid var(--line); border-radius: 10px; background: var(--surface); overflow: hidden; }
details.case { border-top: 1px solid var(--line); border-left: 4px solid transparent; }
details.case:first-child { border-top: 0; }
details.case.passed { border-left-color: var(--pass); } details.case.failed { border-left-color: var(--fail); }
details.case.error { border-left-color: var(--err); } details.case.skipped { border-left-color: var(--skip); }
details.case > summary { list-style: none; cursor: pointer; padding: 10px 14px; display: flex; gap: 12px; align-items: baseline; }
details.case > summary::-webkit-details-marker { display: none; }
details.case > summary .name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
details.case > summary .t { font: .8rem var(--mono); color: var(--muted); font-variant-numeric: tabular-nums; }
.case-body { padding: 4px 14px 16px 14px; display: grid; gap: 12px; min-width: 0; }
pre { margin: 0; padding: 12px; background: var(--bg); border: 1px solid var(--line); border-radius: 6px; overflow-x: auto; font: .8rem/1.5 var(--mono); white-space: pre; }
.shots { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.shots figure { margin: 0; display: grid; gap: 4px; min-width: 0; }
.shots img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 6px; cursor: zoom-in; background: var(--bg); }
.shots img.zoom { grid-column: 1 / -1; cursor: zoom-out; }
.shots figcaption { font-size: .75rem; color: var(--muted); overflow-wrap: anywhere; }
video { width: 100%; max-width: 720px; border-radius: 6px; border: 1px solid var(--line); background: #000; }
.links { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: .88rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: .88rem; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font: 500 .72rem/1 var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
tr:last-child td { border-bottom: 0; }
hr { border: 0; border-top: 2px solid var(--line); margin: 12px 0; }
footer { font-size: .8rem; color: var(--muted); border-top: 1px solid var(--line); padding-top: 14px; }
/* Manual pages */
.toc { display: grid; gap: 4px; padding-left: 1.2em; margin: 0; }
.step { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: 20px; align-items: start; padding-block: 18px; border-top: 1px solid var(--line); }
.step .num { font: 700 .8rem/1 var(--mono); color: var(--accent); }
.step img { width: 100%; height: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
.step .text { display: grid; gap: 8px; min-width: 0; }
.note { font-size: .88rem; color: var(--muted); border-left: 3px solid var(--line); padding-left: 10px; }
.version-flag { border: 2px solid var(--hl); border-radius: 10px; padding: 12px 16px; display: grid; gap: 4px; background: var(--surface); }
.levels { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.level { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 6px; align-content: start; }
@media (max-width: 720px) { .step { grid-template-columns: 1fr; } h1 { font-size: 1.6rem; } }
@media print {
  body { background: #fff; color: #000; font-size: 11pt; }
  .wrap { max-width: none; padding: 0; gap: 18px; }
  @page { margin: 14mm; }
  .step { break-inside: avoid; grid-template-columns: 1fr; gap: 10px; padding-block: 14px; }
  .step img { max-height: 80mm; width: auto; max-width: 100%; justify-self: start; }
  h2, h3 { break-after: avoid; page-break-after: avoid; }
  section.stack > h2 { break-before: auto; }
  .band, .level, .version-flag { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
"""

ZOOM_JS = ("<script>document.addEventListener('click',function(e){var t=e.target;"
           "if(t.tagName==='IMG'&&t.closest('.shots')){t.classList.toggle('zoom');}});</script>")


def page(title: str, body: str, fragment: bool = False, extra_head: str = "") -> str:
    """Wrap body HTML. fragment=True omits doctype/html/head/body for an Artifact publish."""
    head = (f"<title>{title}</title>\n{FONTS}\n<style>{CSS}</style>\n{extra_head}")
    if fragment:
        return f"{head}\n{body}\n"
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            f"{head}</head>\n<body>\n{body}\n</body>\n</html>\n")
