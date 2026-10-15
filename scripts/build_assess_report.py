#!/usr/bin/env python3
"""Build the two-part assessment report: a business report for owners and a
technical appendix for their IT team. HTML + PDF, printable, private.

Usage:
  python3 build_assess_report.py [--dir docs/assess] [--out docs/assess/report]
                                 [--brand <brand.json>] [--fragment FILE] [--no-pdf]

Reads (all under --dir):
  intake.json          client, system, scope, authorisation, reference, contact
  as-is.json           roles, features, use cases, flows, rules, gaps, unknowns
  findings.json        technical findings (validate_assessment.py schema)
  opportunities.json   summary, recommendations by horizon, new-feature fit,
                       options (fix / replace piece by piece / rebuild), commitment
  technical.md         architecture and code-health narrative (optional)
  evidence/scan-summary.json   scanner results (optional, from assess_scan.py)

Brand: --brand, else .harness/brand.json, else ~/.asdr/brand.json, else a
neutral ASDR style. A brand file sets colours, fonts, the monogram, the
footer line and the reference prefix (templates/assess/brand.json).

Run validate_assessment.py --strict first: the report assumes every claim is
already cited. Private by default — a filled-in assessment describes a
client's weaknesses, so it is shared as a file with the client, never
published as a public page. --fragment writes an Artifact-format copy only
when the user explicitly asks for a private page.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_style import to_pdf  # noqa: E402

SEV_ORDER = ["critical", "high", "medium", "low"]
AREAS = [("process", "Business processes"), ("architecture", "Architecture"), ("code", "Code health"),
         ("security", "Security"), ("performance", "Performance"), ("operations", "Operations"), ("data", "Data")]

NEUTRAL = {
    "name": "ASDR assessment", "monogram": "AS", "lockup": "AI Software Delivery Room",
    "footer": "CONFIDENTIAL", "email": "", "linkedin": "", "reference_prefix": "AS",
    "colors": {"ink": "#111214", "graphite": "#3C3F44", "slate": "#62666C", "hairline": "#DCDCDC",
               "tint": "#F7F8FA", "blue": "#23408E", "deep": "#152C66"},
    "fonts": {"words": '"Helvetica Neue", Helvetica, Arial, sans-serif',
              "meta": '"IBM Plex Mono", ui-monospace, Menlo, monospace'},
}


def e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def load_brand(arg):
    for p in [Path(arg)] if arg else [Path(".harness/brand.json"), Path.home() / ".asdr" / "brand.json"]:
        b = read_json(p, None)
        if isinstance(b, dict):
            out = {**NEUTRAL, **b}
            out["colors"] = {**NEUTRAL["colors"], **(b.get("colors") or {})}
            out["fonts"] = {**NEUTRAL["fonts"], **(b.get("fonts") or {})}
            return out, str(p)
    return NEUTRAL, "built-in neutral"


# ── minimal markdown → HTML for technical.md (headings, lists, tables, code) ──

def inline(s: str) -> str:
    s = e(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    return s


def md_to_html(md: str, demote: int = 1) -> str:
    out, i = [], 0
    lines = md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            lang = ln[3:].strip()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j])
                j += 1
            cls = ' class="mermaid"' if lang == "mermaid" else ""
            out.append(f"<pre{cls}>{e(chr(10).join(buf))}</pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            lvl = min(len(m.group(1)) + demote, 6)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if ln.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [c.strip() for c in ln.strip().strip("|").split("|")]
            j = i + 2
            rows = []
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(h)}</th>" for h in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")
            i = j
            continue
        if re.match(r"^\s*[-*]\s+", ln) or re.match(r"^\s*\d+\.\s+", ln):
            ordered = bool(re.match(r"^\s*\d+\.\s+", ln))
            items = []
            while i < len(lines) and (re.match(r"^\s*[-*]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])):
                items.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if not ln.strip() or ln.strip() == "---":
            i += 1
            continue
        buf = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|```|\s*[-*]\s|\s*\d+\.\s|\s*\|)", lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


# ── scoring: a fixed rule, stated in the report ──────────────────────────────

def rating(findings, area):
    sev = [f.get("severity") for f in findings if f.get("area") == area]
    if "critical" in sev:
        return "Critical", "crit"
    if "high" in sev:
        return "Weak", "weak"
    if "medium" in sev:
        return "Fair", "fair"
    if sev:
        return "Good", "good"
    return "Not assessed", "na"


def process_rating(gaps, findings):
    n = len(gaps) + sum(1 for f in findings if f.get("area") == "process")
    if n >= 10:
        return "Weak", "weak"
    if n >= 4:
        return "Fair", "fair"
    return ("Good", "good") if n else ("Not assessed", "na")


# ── page ──────────────────────────────────────────────────────────────────────

def css(b) -> str:
    c, f = b["colors"], b["fonts"]
    foot = " · ".join(x for x in [b.get("footer"), b.get("email"), b.get("linkedin")] if x)
    return f"""
:root {{ --ink:{c['ink']}; --graphite:{c['graphite']}; --slate:{c['slate']}; --hair:{c['hairline']};
  --tint:{c['tint']}; --blue:{c['blue']}; --deep:{c['deep']}; --paper:#ffffff;
  --words:{f['words']}; --meta:{f['meta']}; color-scheme: light; }}
* {{ box-sizing: border-box; }}
html, body {{ background: var(--paper); color: var(--ink); }}
body {{ margin: 0; font: 10.5pt/1.55 var(--words); }}
.doc {{ max-width: 860px; margin: 0 auto; padding-block: 32px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
h1, h2, h3, h4 {{ font-family: var(--words); color: var(--ink); text-wrap: balance; margin: 0; }}
h1 {{ font-size: 26pt; line-height: 1.1; font-weight: 700; letter-spacing: -.01em; }}
h2 {{ font-size: 15pt; font-weight: 700; margin-top: 30px; padding-top: 10px; border-top: 1px solid var(--hair); }}
h2 .no {{ font-family: var(--meta); font-weight: 500; color: var(--blue); margin-right: 6px; }}
h3 {{ font-size: 11.5pt; margin-top: 18px; }}
h4 {{ font-size: 10.5pt; margin-top: 12px; }}
p, li {{ max-width: 72ch; }}
p {{ margin: 8px 0; }}
.meta, .eyebrow, th, .mono {{ font-family: var(--meta); }}
.eyebrow {{ font-size: 8.5pt; letter-spacing: .12em; text-transform: uppercase; color: var(--slate); }}
.muted {{ color: var(--slate); }}
.lockup {{ display: flex; align-items: center; gap: 12px; }}
.mono-sq {{ width: 40px; height: 40px; background: var(--blue); color: #fff; display: grid; place-items: center;
  font: 700 14pt/1 var(--words); letter-spacing: .02em; }}
.lockup .name {{ font-weight: 700; font-size: 11pt; }}
.cover {{ min-height: 230mm; display: flex; flex-direction: column; justify-content: space-between; gap: 32px;
  padding-bottom: 12px; border-bottom: 2px solid var(--ink); }}
.cover .title {{ display: grid; gap: 14px; margin-top: 80px; }}
.cover .for {{ font-size: 12pt; color: var(--graphite); }}
.fields {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; border-top: 1px solid var(--hair); }}
.fields div {{ padding: 10px 12px 10px 0; display: grid; gap: 4px; min-width: 0; overflow-wrap: anywhere; }}
.fields dt {{ font: 500 7.5pt/1 var(--meta); letter-spacing: .12em; text-transform: uppercase; color: var(--slate); }}
.fields dd {{ margin: 0; font: 500 9.5pt/1.3 var(--meta); }}
.part {{ margin-top: 40px; padding: 14px 0; border-top: 6px solid var(--blue); }}
.part .eyebrow {{ color: var(--blue); }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 9pt; }}
th {{ text-align: left; font-size: 7.5pt; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--slate);
  border-bottom: 1px solid var(--ink); padding: 6px 8px 6px 0; }}
td {{ border-bottom: 1px solid var(--hair); padding: 7px 8px 7px 0; vertical-align: top; overflow-wrap: break-word; word-break: normal; hyphens: manual; }}
td .mono, td code, td .sev, td b, td .est {{ white-space: nowrap; }}
td code {{ white-space: normal; }}
.table-wrap {{ overflow-x: auto; }}
code {{ font: 8.5pt var(--meta); background: var(--tint); padding: 0 3px; }}
pre {{ font: 8pt/1.45 var(--meta); background: var(--tint); padding: 10px; overflow-x: auto; white-space: pre-wrap; }}
.sev {{ font: 600 7.5pt/1 var(--meta); letter-spacing: .06em; text-transform: uppercase; padding: 3px 6px; display: inline-block;
  border: 1px solid currentColor; white-space: nowrap; }}
.sev.critical, .r.crit {{ color: var(--paper); background: var(--ink); border-color: var(--ink); }}
.sev.high, .r.weak {{ color: var(--ink); border-color: var(--ink); }}
.sev.medium, .r.fair {{ color: var(--graphite); border-color: var(--hair); }}
.sev.low, .r.good {{ color: var(--blue); border-color: var(--blue); }}
.r {{ font: 600 8pt/1 var(--meta); letter-spacing: .06em; text-transform: uppercase; padding: 4px 8px; display: inline-block; border: 1px solid; }}
.r.na {{ color: var(--slate); border-color: var(--hair); }}
.callout {{ background: var(--ink); color: var(--paper); padding: 18px 22px; margin: 18px 0; }}
.callout p {{ color: var(--paper); margin: 4px 0; max-width: none; }}
.callout .eyebrow {{ color: #c9ccd2; }}
.est {{ font: 7.5pt var(--meta); color: var(--slate); text-transform: uppercase; letter-spacing: .08em; }}
.finding {{ border-top: 1px solid var(--hair); padding: 12px 0; break-inside: avoid; }}
.finding .head {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }}
.finding dl {{ display: grid; grid-template-columns: 130px 1fr; gap: 4px 12px; margin: 8px 0 0; }}
.finding dt {{ font: 500 7.5pt/1.6 var(--meta); text-transform: uppercase; letter-spacing: .08em; color: var(--slate); }}
.finding dd {{ margin: 0; }}
footer.docfoot {{ margin-top: 40px; border-top: 1px solid var(--ink); padding-top: 10px; font: 8pt var(--meta); color: var(--slate); letter-spacing: .06em; }}
@media (max-width: 640px) {{ .fields {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .finding dl {{ grid-template-columns: 1fr; }}
  .cover .title {{ margin-top: 24px; }} h1 {{ font-size: 20pt; }} }}
@page {{ size: A4; margin: 16mm 16mm 20mm 16mm;
  @bottom-left {{ content: "{e(foot)}"; font: 6pt {f['meta']}; color: {c['slate']}; letter-spacing: .02em; width: 160mm; white-space: nowrap; }}
  @bottom-right {{ content: counter(page) " / " counter(pages); font: 6pt {f['meta']}; color: {c['slate']}; width: 18mm; white-space: nowrap; }} }}
@media print {{
  .doc {{ max-width: none; padding: 0; }}
  .cover {{ min-height: 250mm; break-after: page; }}
  .part {{ break-before: page; }}
  h2, h3 {{ break-after: avoid; }}
  tr, .callout, .finding {{ break-inside: avoid; }}
  .table-wrap {{ overflow: visible; }}
  thead {{ display: table-header-group; }}
  a {{ color: inherit; text-decoration: none; }}
}}
"""


def sev(s) -> str:
    return f'<span class="sev {e(s)}">{e(s)}</span>'


def tbl(head, rows) -> str:
    if not rows:
        return '<p class="muted">None recorded.</p>'
    return ('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{e(h)}</th>" for h in head)
            + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
            + "</tbody></table></div>")


def build(d: Path, brand) -> "tuple[str, dict]":
    intake = read_json(d / "intake.json", {})
    asis = read_json(d / "as-is.json", {})
    findings = read_json(d / "findings.json", [])
    opp = read_json(d / "opportunities.json", {})
    scan = read_json(d / "evidence" / "scan-summary.json", {})
    tech_md = (d / "technical.md").read_text(errors="ignore") if (d / "technical.md").is_file() else ""
    findings = sorted(findings, key=lambda f: (SEV_ORDER.index(f.get("severity")) if f.get("severity") in SEV_ORDER else 9, f.get("id", "")))
    gaps = asis.get("gaps", [])
    today = dt.date.today()
    system = intake.get("system") or "the system"
    client = intake.get("client") or "Client"
    ref = intake.get("reference") or f"{brand.get('reference_prefix', 'AS')}-{today.year}-001"
    counts = {s: sum(1 for f in findings if f.get("severity") == s) for s in SEV_ORDER}

    sec = [0]

    def h2(title):
        sec[0] += 1
        return f'<h2><span class="no">{sec[0]:02d} ·</span>{e(title)}</h2>'

    out = ['<article class="doc">']
    # cover
    fields = [("Date", intake.get("date") or today.strftime("%d %b %Y")), ("Reference", ref),
              ("Based on", intake.get("based_on") or intake.get("code_version") or "—"),
              ("Contact", intake.get("contact") or brand.get("email") or "—")]
    out.append('<section class="cover"><div class="lockup">'
               f'<div class="mono-sq" aria-hidden="true">{e(brand.get("monogram"))}</div>'
               f'<span class="name">{e(brand.get("lockup"))}</span></div>'
               f'<div class="title"><span class="eyebrow">System assessment</span>'
               f'<h1>{e(system)}: what it does, what is wrong, what to do next</h1>'
               f'<span class="for">Prepared for {e(client)}</span></div>'
               '<dl class="fields">' + "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in fields) + "</dl></section>")

    # PART A — business report
    out.append('<section class="part"><span class="eyebrow">Part A · Business report</span></section>')
    out.append(h2("Summary"))
    for para in as_list(opp.get("summary")):
        out.append(f"<p>{inline(para)}</p>")
    score_rows = []
    pr, pc = process_rating(gaps, findings)
    score_rows.append([e("Business processes"), f'<span class="r {pc}">{e(pr)}</span>',
                       e(f"{len(gaps)} process gaps found" if gaps else "—")])
    for key, label in AREAS[1:]:
        r, c = rating(findings, key)
        n = [f for f in findings if f.get("area") == key]
        score_rows.append([e(label), f'<span class="r {c}">{e(r)}</span>',
                           e(", ".join(f"{sum(1 for f in n if f.get('severity') == s)} {s}" for s in SEV_ORDER
                                       if any(f.get('severity') == s for f in n)) or "no findings")])
    out.append("<h3>Health scorecard</h3>" + tbl(["Area", "Rating", "Basis"], score_rows)
               + '<p class="muted">Rating rule: any critical finding → Critical; any high → Weak; medium only → Fair; '
                 'low only → Good. Processes: 10+ gaps → Weak, 4–9 → Fair.</p>')

    out.append(h2("How the business runs today"))
    roles = asis.get("roles", [])
    if roles:
        out.append("<h3>Who uses the system</h3>" + tbl(["Role", "What they can do"],
                   [[e(r.get("name")), e(r.get("can"))] for r in roles]))
    flows = asis.get("flows", [])
    if flows:
        out.append("<h3>The main journeys</h3>" + tbl(["Journey", "Starts when", "Ends with"],
                   [[f'<span class="mono">{e(f.get("id"))}</span> {e(f.get("title"))}', e(f.get("trigger")), e(f.get("outcome"))] for f in flows]))
    feats = asis.get("features", [])
    if feats:
        used = sum(1 for f in feats if f.get("used") and not str(f.get("used")).startswith("no data"))
        out.append(f'<p>{len(feats)} features identified; {used} show evidence of use in the data.</p>')

    out.append(h2("Where the processes break"))
    out.append(tbl(["", "What happens"], [[f'<span class="mono">{e(g.get("id"))}</span>', e(g.get("text"))] for g in gaps]))

    out.append(h2("The most serious risks"))
    top = [f for f in findings if f.get("severity") in ("critical", "high")]
    out.append(tbl(["", "Risk", "What it means for the business", "Effort to fix"],
                   [[sev(f.get("severity")), e(f.get("title")), e(f.get("business_impact")),
                     f'{e(f.get("effort") or "—")} <span class="est">estimate</span>'] for f in top]))
    out.append(f'<p class="muted">Full list: {counts["critical"]} critical, {counts["high"]} high, {counts["medium"]} medium, '
               f'{counts["low"]} low — all in Part B, each with its evidence.</p>')

    out.append(h2("What we recommend"))
    for hz in opp.get("recommendations", []):
        out.append(f'<h3>{e(hz.get("horizon"))}</h3>')
        out.append(tbl(["Action", "Why", "Effort"],
                       [[e(it.get("action")), e(it.get("why")), f'{e(it.get("effort") or "—")} <span class="est">estimate</span>']
                        for it in hz.get("items", [])]))

    nf = opp.get("new_features") or {}
    if nf:
        out.append(h2("Adding new features"))
        for p in as_list(nf.get("summary")):
            out.append(f"<p>{inline(p)}</p>")
        if nf.get("safe_areas") or nf.get("fix_first"):
            out.append(tbl(["Where", "Safe to build on now?", "Why"],
                           [[e(x.get("area")), e("Yes"), e(x.get("why"))] for x in nf.get("safe_areas", [])]
                           + [[e(x.get("area")), e("Fix first"), e(x.get("why"))] for x in nf.get("fix_first", [])]))
        if nf.get("ideas"):
            out.append("<h3>Opportunities</h3>" + tbl(["Idea", "Impact", "Effort"],
                       [[e(x.get("idea")), e(x.get("impact")), f'{e(x.get("effort") or "—")} <span class="est">estimate</span>'] for x in nf["ideas"]]))

    opts = opp.get("options") or []
    if opts:
        out.append(h2("Options"))
        out.append(tbl(["Option", "What it involves", "Cost", "Time", "Risk", ""],
                       [[f'<b>{e(o.get("name"))}</b>', e(o.get("description")),
                         f'{e(o.get("cost") or "—")} <span class="est">estimate</span>',
                         f'{e(o.get("time") or "—")} <span class="est">estimate</span>', e(o.get("risk")),
                         "<b>Recommended</b>" if o.get("recommended") else ""] for o in opts]))
        rec = next((o for o in opts if o.get("recommended")), None)
        if rec and rec.get("why"):
            out.append(f'<p><b>Why {e(rec.get("name"))}:</b> {inline(rec["why"])}</p>')

    if opp.get("commitment"):
        out.append(h2("Our commitment"))
        out.append('<div class="callout"><span class="eyebrow">Commitment</span>'
                   + "".join(f"<p>{inline(p)}</p>" for p in as_list(opp["commitment"])) + "</div>")

    unk = asis.get("unknowns", [])
    out.append(h2("What we need from you"))
    out.append(f'<p>These questions cannot be answered from the code or the data. A short review of this report '
               f'and answers to these {len(unk)} questions replaces a full discovery exercise.</p>')
    out.append(tbl(["", "Question", "Why we are asking"],
                   [[f'<span class="mono">{e(u.get("id"))}</span>', e(u.get("question")), e(u.get("why"))] for u in unk]))

    # PART B — technical appendix
    out.append('<section class="part"><span class="eyebrow">Part B · Technical appendix</span></section>')
    out.append(h2("Scope, method and evidence"))
    sc = intake.get("scope") or {}
    out.append(tbl(["", ""], [[e("System"), e(system)], [e("Access provided"), e(", ".join(as_list(sc.get("access"))) or "—")],
                              [e("In scope"), e(", ".join(as_list(sc.get("in_scope"))) or "—")],
                              [e("Out of scope"), e(", ".join(as_list(sc.get("out_of_scope"))) or "—")],
                              [e("Authorisation"), e((intake.get("authorization") or {}).get("summary") or "—")],
                              [e("Method"), e("Read-only: source code review, standard scanners, the database structure and "
                                              "data counts, and the running application used as each role. No attack testing.")]]))
    if scan.get("status"):
        out.append("<h3>Tools run</h3>" + tbl(["Tool", "Status"], [[e(k), e(v)] for k, v in scan["status"].items()]))
    if tech_md:
        out.append(h2("Architecture and code health"))
        out.append(md_to_html(re.sub(r"^#\s+.*\n", "", tech_md, count=1), demote=1))

    out.append(h2("Findings register"))
    out.append(tbl(["ID", "Area", "Severity", "Confidence", "Finding", "Effort"],
                   [[f'<span class="mono">{e(f.get("id"))}</span>', e(f.get("area")), sev(f.get("severity")), e(f.get("confidence")),
                     e(f.get("title")), f'{e(f.get("effort") or "—")}'] for f in findings]))
    out.append(h2("Finding detail"))
    for f in findings:
        ev = "".join(f"<li><code>{e(x)}</code></li>" for x in as_list(f.get("evidence")))
        out.append(f'<div class="finding"><div class="head"><span class="mono">{e(f.get("id"))}</span>{sev(f.get("severity"))}'
                   f'<b>{e(f.get("title"))}</b></div><dl>'
                   f'<dt>What</dt><dd>{e(f.get("what"))}</dd>'
                   f'<dt>Business impact</dt><dd>{e(f.get("business_impact"))}</dd>'
                   f'<dt>Fix</dt><dd>{e(f.get("fix"))}</dd>'
                   f'<dt>Effort</dt><dd>{e(f.get("effort") or "—")} <span class="est">estimate</span> · confidence {e(f.get("confidence"))}</dd>'
                   f'<dt>Evidence</dt><dd><ul>{ev}</ul></dd></dl></div>')

    out.append(h2("Business process detail"))
    for fl in flows:
        out.append(f'<h3><span class="mono">{e(fl.get("id"))}</span> {e(fl.get("title"))}</h3>')
        out.append(tbl(["Step", "Who", "Does", "System response", "Evidence"],
                       [[e(s.get("id")), e(s.get("actor")), e(s.get("action")), e(s.get("response")),
                         f'<code>{e("; ".join(as_list(s.get("evidence")))[:220])}</code>'] for s in fl.get("steps", [])]))
        if fl.get("exceptions"):
            out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in as_list(fl["exceptions"])) + "</ul>")
    rules = asis.get("rules", [])
    if rules:
        out.append("<h3>Business rules and where they are enforced</h3>" + tbl(["", "Rule", "Enforced"],
                   [[f'<span class="mono">{e(r.get("id"))}</span>', e(r.get("text")), e(r.get("enforcement"))] for r in rules]))
    if feats:
        out.append("<h3>Features</h3>" + tbl(["", "Feature", "Used by", "Evidence of use", "Confidence"],
                   [[f'<span class="mono">{e(f.get("id"))}</span>', e(f.get("name")), e(", ".join(as_list(f.get("roles")))),
                     e(f.get("used")), e(f.get("confidence"))] for f in feats]))

    if scan.get("tools"):
        out.append(h2("Scanner results"))
        t = scan["tools"]
        o = (t.get("deps") or {}).get("osv-scanner") or {}
        if o.get("status") == "ran":
            out.append(f'<p>Dependencies: {o.get("vulnerable_packages")} packages with {o.get("advisories")} known advisories '
                       f'({", ".join(f"{v} {k}" for k, v in (o.get("by_severity") or {}).items()) or "none"}).</p>')
        s = t.get("semgrep") or {}
        if s.get("status") == "ran":
            out.append(f'<p>Static analysis: {s.get("findings")} raw hits, each triaged in the code; only confirmed ones '
                       'appear as findings above.</p>')
        if scan.get("hotspots"):
            out.append("<h3>Hotspots: code that is both complex and changed often</h3>" + tbl(
                ["File", "Changes", "Complexity", "Score"],
                [[f'<code>{e(h["file"])}</code>', e(h["changes"]), e(h["ccn_total"]), e(h["score"])] for h in scan["hotspots"][:10]]))

    out.append(h2("Limits of this assessment"))
    for p in as_list(opp.get("limits")) or ["Code shows what the system does, not why each rule exists; the questions in Part A cover that.",
                                            "Code is not proof of use: features are marked used only where the data shows it.",
                                            "Effort and cost figures are estimates and are labelled as such."]:
        out.append(f"<p>{inline(p)}</p>")
    foot = " · ".join(x for x in [brand.get("footer"), brand.get("email"), brand.get("linkedin")] if x)
    out.append(f'<footer class="docfoot">{e(foot)}</footer></article>')
    stats = {"findings": len(findings), **counts, "gaps": len(gaps), "unknowns": len(unk), "flows": len(flows)}
    return "\n".join(out), {"system": system, "client": client, "reference": ref, "stats": stats}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the two-part assessment report (HTML + PDF).")
    ap.add_argument("--dir", default="docs/assess")
    ap.add_argument("--out", default="docs/assess/report")
    ap.add_argument("--brand", default=None)
    ap.add_argument("--fragment", default=None, help="also write an Artifact-format copy (only if the user asks for a private page)")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()

    d = Path(args.dir)
    if not (d / "findings.json").is_file() and not (d / "as-is.json").is_file():
        print(f"ERROR: no findings.json or as-is.json in {d}")
        return 1
    brand, brand_src = load_brand(args.brand)
    body, info = build(d, brand)
    title = f"{info['system']} Assessment"
    style = f"<style>{css(brand)}</style>"
    mer = '<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"></script><script>if(window.mermaid){mermaid.initialize({startOnLoad:true,theme:"neutral"});}</script>'
    full = ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">"
            f"<title>{e(title)}</title>{style}</head><body>{body}{mer}</body></html>\n")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    hf = out / "index.html"
    hf.write_text(full)
    outputs = {"html": str(hf)}
    if not args.no_pdf:
        pf = out / "assessment.pdf"
        outputs["pdf"] = str(pf) if to_pdf(hf, pf) else "no Chrome found — open index.html in a browser and print to PDF"
    if args.fragment:
        Path(args.fragment).write_text(f"<title>{e(title)}</title>\n<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\n{style}\n{body}\n")
        outputs["fragment"] = args.fragment
    print(f"OK: {info['stats']} · brand: {brand_src}")
    for k, v in outputs.items():
        print(f"  {k}: {v}")
    print("Private: share the PDF with the client directly; do not publish this report as a public page.")
    print("ASSESS-REPORT: " + json.dumps({"outputs": outputs, **info}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
