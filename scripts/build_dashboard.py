#!/usr/bin/env python3
"""Build the ASDR project dashboard — one page that answers "where is this
project right now, when will it land, and what do you need from me?"
HTML + PDF, private, printable.

Usage:
  python3 build_dashboard.py [--out docs/dashboard] [--inline FILE] [--fragment]
                             [--no-pdf] [--title "<Project>"]

Sections (each maps to something the user asked to see):
   1  Status and progress    status (fixed rule, reasons), phase, overall %
   2  At a glance            the numbers that matter, incl. expected delivery
   3  Phases and gates       every phase, its gate verdict, when it finished
   4  Delivery forecast      expected date ± standard deviation, 68%/95%
                             ranges, per-sprint finish dates, how it has moved
   5  Roadmap                Gantt diagram (actual + projected), product
                             roadmap milestones, sprint table
   6  Features               every feature: users, priority, release, journeys,
                             requirements, sprint, development status
   7  Development speed      sprint durations, first-pass rate, rework,
                             features per week, commits, test runs
   8  Quality                tests, journeys proven, coverage by kind,
                             accessibility, measurements, regressions
   9  Risks and blockers     open risks from the register, blockers
  10  Questions and decisions  waiting on you, your answers, gate verdicts, ADRs
  11  Documents and artifacts  every canonical document: present / missing,
                             owner, phase, updated; every other doc; generated reports
  12  Environments           dev / test / staging / UAT / production: URL, what is
                             deployed, test roles, reachable now
  13  Repositories and resources  git remotes, branch, HEAD, activity; links
  14  Recent activity        latest agent actions from the trace log
  15  ASDR effort            agent invocations by role, evaluations, rounds

Single source of truth: every number is read from the files the gates read
(progress.json, sprints.json, product-map.json, facts.json, metrics.json,
traceability.json, questions.jsonl, sprint-clock.jsonl, traces, decision and
risk docs, git). Nothing is hand-edited; rerun the script. Missing inputs
show as "not yet", never as an error. Refresh at the end of every phase and
sprint and on demand; the page states when it was generated.

Delivery date: shown only with >= 2 finished sprints that have start/finish
stamps (sprint_clock.py), as expected date ± 1 standard deviation (a
prediction interval for the remaining sprints, so it is honest about small
samples), with 68% and 95% ranges. Every forecast is logged to
.harness/forecast-history.jsonl so slip is visible.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_style import page, to_pdf  # noqa: E402

H = Path(".harness")
UTC = dt.timezone.utc


# ── small helpers ─────────────────────────────────────────────────────────────

def e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def jsonl(p: Path) -> list:
    rows = []
    if p.is_file():
        for line in p.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def _ts(x):
    try:
        d = dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def when(ts) -> str:
    d = ts if isinstance(ts, dt.datetime) else _ts(ts)
    return d.strftime("%Y-%m-%d %H:%M UTC") if d else "—"


def day(d) -> str:
    return d.strftime("%a %d %b %Y") if d else "—"


def short(d) -> str:
    return d.strftime("%d %b") if d else "—"


def span_fmt(a, b) -> str:
    """Range label: dates, plus times when the range is under two days."""
    if not a or not b:
        return "—"
    if (b - a).total_seconds() < 2 * 86400:
        return f"{a.strftime('%d %b %H:%M')} – {b.strftime('%d %b %H:%M')} UTC"
    return f"{a.strftime('%d %b')} – {b.strftime('%d %b')}"


def mtime(p: Path):
    try:
        return dt.datetime.fromtimestamp(p.stat().st_mtime, UTC)
    except OSError:
        return None


def pct(n, d) -> int:
    return round(100 * n / d) if d else 0


def fmt_span(h: float) -> str:
    return f"{h / 24:.1f} days" if h >= 36 else f"{h:.1f} h"


def git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def pill(text, cls) -> str:
    return f'<span class="pill {cls}">{e(text)}</span>'


def kpis(items) -> str:
    return '<div class="grid">' + "".join(
        f'<div class="kpi"><span class="n">{n}</span><span class="l">{e(l)}</span></div>' for n, l in items) + "</div>"


def table(head, rows, empty="Nothing yet.") -> str:
    if not rows:
        return f'<p class="muted">{e(empty)}</p>'
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def section(sid, title, inner, note="") -> str:
    n = f'<p class="muted">{note}</p>' if note else ""
    return f'<section class="band" id="{sid}"><h2>{e(title)}</h2>{n}{inner}</section>'


# ── canonical documents (skills/asdr/references/file-map.md) ─────────────────

CANON = [
    ("Discovery", "Product brief", "docs/01-product-brief.md", "product-owner"),
    ("Discovery", "Business case", "docs/01b-business-case.md", "product-owner"),
    ("Discovery", "Roadmap", "docs/00b-roadmap.md", "product-owner"),
    ("Discovery", "Requirements", "docs/02-requirements.md", "business-analyst"),
    ("Discovery", "Use cases", "docs/02b-use-cases.md", "business-analyst"),
    ("Discovery", "Feature list", "docs/02c-features.md", "product-manager"),
    ("Discovery", "Process flows", "docs/02d-process-flows.md", "product-manager"),
    ("Discovery", "Test cases", "docs/02e-test-cases.md", "business-analyst"),
    ("Discovery", "Discovery critique", "docs/critique-discovery.md", "critic"),
    ("Discovery", "Discovery decision", "docs/decision-discovery.md", "judge"),
    ("Architecture", "Architecture", "docs/03-architecture.md", "solution-architect"),
    ("Architecture", "Design system (UI)", "docs/03b-design-system.md", "solution-architect"),
    ("Architecture", "Agent design (AI)", "docs/04-agent-design.md", "ai-architect"),
    ("Architecture", "Security", "docs/05-security.md", "security-compliance"),
    ("Architecture", "DevOps", "docs/06-devops.md", "devops"),
    ("Architecture", "Architecture critique", "docs/critique-architecture.md", "critic"),
    ("Architecture", "Architecture decision", "docs/decision-architecture.md", "judge"),
    ("Architecture", "Blueprint digest", "docs/00-blueprint-summary.md", "orchestrator"),
    ("Architecture", "E2E testing plan", "docs/08-e2e-testing.md", "devops"),
    ("Planning", "Sprint plan", "sprints.json", "planner"),
    ("Planning", "Traceability matrix", "docs/traceability.md", "product-integrity-qa"),
    ("Planning", "Product map", "docs/product-map.md", "validate_product_map.py"),
    ("Final gates", "Product integrity", "docs/09-product-integrity.md", "product-integrity-qa"),
    ("Final gates", "Final security review", "docs/09-security-review-final.md", "security-compliance"),
    ("Final gates", "DevOps readiness", "docs/09-devops-readiness.md", "devops"),
    ("Final gates", "Risk review", "docs/09-risk-review.md", "risk-manager"),
    ("Release", "Changelog", "CHANGELOG.md", "release-manager"),
    ("Release", "Release notes", "docs/10-release-notes.md", "release-manager"),
    ("Release", "Release checklist", "docs/10-release-checklist.md", "release-manager"),
    ("Release", "Post-release monitoring", "docs/10-post-release-monitoring.md", "release-manager"),
    ("Release", "Manual spec", "docs/manuals/manual.json", "documentation"),
    ("Release", "Run metrics", "docs/run-metrics.md", "run_metrics.py"),
]
OPTIONAL = {"docs/03b-design-system.md", "docs/04-agent-design.md"}

PHASES = [  # (key in progress.json, label, gate document, gate kind, weight for overall %)
    ("strategic", "Discovery & architecture", ["docs/decision-discovery.md", "docs/decision-architecture.md"], "judge verdicts", 30),
    ("planning", "Sprint planning", ["sprints.json"], "sprint plan", 5),
    ("execution", "Sprint execution", [], "sprints done", 55),
    ("final-gates", "Final gates", ["docs/09-risk-review.md"], "risk classification", 5),
    ("done", "Release", ["docs/10-release-notes.md"], "release notes", 5),
]


def verdict_of(path: Path):
    if not path.is_file():
        return None
    txt = path.read_text(errors="ignore")
    m = re.search(r"^\s*verdict:\s*([a-z-]+)", txt, re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.search(r"\b(Production-ready|MVP-ready|Prototype|Not ready)\b", txt)
    return m.group(1) if m else "written"


# ── status: a fixed rule, not an opinion ─────────────────────────────────────

def classify(progress, pmap, facts, questions, open_risks, regressions):
    blocked, at_risk = [], []
    if progress.get("last_eval_result") == "teardown":
        blocked.append("the last sprint evaluation ordered a teardown")
    open_qs = [q for q in questions if q.get("status") == "open"]
    if open_qs:
        blocked.append(f"{len(open_qs)} question(s) waiting on you")
    if progress.get("attempt", 0) >= 4:
        at_risk.append(f"{progress.get('sprint')} is on attempt {progress.get('attempt')}")
    tr = (facts or {}).get("test_runs") or {}
    if tr:
        if tr.get("status") == "failed":
            at_risk.append("the latest test run failed")
        a = tr.get("a11y") or {}
        if a.get("critical", 0) or a.get("serious", 0):
            at_risk.append("serious or critical accessibility violations")
        if tr.get("commit_matches_head") is False:
            at_risk.append("the latest test run is not on the current commit")
        for name, m in (tr.get("metrics") or {}).items():
            if m.get("within_budget") is False:
                at_risk.append(f"measurement '{name}' is over budget")
    flows = (pmap or {}).get("flows") or {}
    failing_must = sorted(k for k, v in flows.items() if v.get("status") == "failing" and v.get("priority") == "must")
    failing_other = sorted(k for k, v in flows.items() if v.get("status") == "failing" and v.get("priority") != "must")
    if failing_must:
        at_risk.append(f"must-have journey(s) failing: {', '.join(failing_must)}")
    if failing_other:
        at_risk.append(f"journey(s) failing: {', '.join(failing_other)}")
    if regressions:
        at_risk.append(f"regression: {', '.join(regressions)} worked before and does not now")
    if (pmap or {}).get("errors"):
        at_risk.append(f"{pmap['errors']} product-map error(s)")
    high = [r for r in open_risks if str(r.get("severity", "")).lower() in ("critical", "high")]
    if high:
        at_risk.append(f"{len(high)} open high/critical risk(s)")
    if blocked:
        return "blocked", blocked + at_risk
    if at_risk:
        return "at risk", at_risk
    return "on track", ["no blocking or risk rule triggered"]


STATE_PILL = {"on track": "passed", "at risk": "skipped", "blocked": "failed"}


# ── delivery forecast: expected date ± standard deviation ────────────────────

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
       10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}


def t95(df: int) -> float:
    if df <= 0:
        return float("inf")
    if df in T95:
        return T95[df]
    if df > 30:
        return 1.96
    return T95[max(k for k in T95 if k < df)]   # conservative


def sprint_times(clock, traces):
    """{sprint: {"start", "done", "torn_down"}} from sprint-clock.jsonl, falling
    back to the trace log (first line naming the sprint → start; an evaluator
    line with verdict/status=pass → done)."""
    out = {}
    for r in clock:
        sid, ev, t = r.get("sprint"), r.get("event"), _ts(r.get("ts"))
        if not sid or not t:
            continue
        d = out.setdefault(sid, {})
        if ev == "start":
            d.setdefault("start", t)
        elif ev == "done":
            d.setdefault("done", t)          # first pass stamp wins; repeats don't move it
        elif ev == "torn-down":
            d["torn_down"] = t
    for r in traces:
        t = _ts(r.get("ts"))
        text = f"{r.get('action', '')} {r.get('result', '')}"
        for sid in set(re.findall(r"sprint-\d{2}", text)):
            d = out.setdefault(sid, {})
            if "start" not in d and t:
                d["start"] = t
            if (r.get("actor") == "evaluator" and re.search(r"(verdict|status|result)\s*=\s*pass", text)
                    and "done" not in d and t):
                d["done"] = t
    return out


def forecast(sprints, times, now):
    """Expected delivery date with a standard deviation, or why there isn't one.

    Finished sprints' wall-clock durations d1..dn are the sample. For k sprints
    still to run: expected remaining = k × mean − time the active sprint has
    already used. SD = s·sqrt(k + k²/n) — the prediction-interval SD for a sum
    of k future sprints, which includes the uncertainty in the mean, so it is
    wide when n is small. 95% range uses Student-t with n−1 df."""
    status = {s.get("id"): s.get("status") for s in sprints}
    # Cycle time, not just build time: from the previous sprint's finish (or this
    # sprint's start, for the first) to this sprint's finish. That includes the
    # waiting between sprints — reviews, answers, pauses — which a delivery date
    # has to include or it is optimistic every time.
    finished = sorted(((t["done"], sid, t.get("start")) for sid, t in times.items()
                       if status.get(sid) == "done" and t.get("done")), key=lambda x: x[0])
    durs = []
    prev_done = None
    for done_t, sid, start_t in finished:
        origin = prev_done or start_t
        if origin and done_t > origin:
            durs.append((done_t - origin).total_seconds() / 3600)
        prev_done = done_t
    last_done = finished[-1][0] if finished else None
    remaining = [s for s in sprints if s.get("status") in (None, "pending", "active")]
    done_n = sum(1 for s in sprints if s.get("status") == "done")
    if len(durs) < 2 or not remaining:
        need = []
        if len(durs) < 2:
            need.append(f"{2 - len(durs)} more finished sprint(s) with start/finish times")
        if not remaining:
            need.append("remaining sprints")
        return {"available": False, "need": need, "done": done_n, "pending": len(remaining), "durs": durs}
    n = len(durs)
    mean = sum(durs) / n
    sd = (sum((x - mean) ** 2 for x in durs) / (n - 1)) ** 0.5
    k = len(remaining)
    # time already spent on the current cycle (since the last finish)
    used = max(0.0, (now - last_done).total_seconds() / 3600) if last_done else 0.0
    exp_h = max(k * mean - used, 0.0)
    sd_h = sd * (k + k * k / n) ** 0.5
    t = t95(n - 1)
    # per remaining sprint: expected finish (cumulative)
    per, acc = [], 0.0
    for i, s in enumerate(remaining, 1):
        acc += max(mean - used, 0.0) if i == 1 else mean
        sd_i = sd * (i + i * i / n) ** 0.5
        per.append((s, now + dt.timedelta(hours=acc), sd_i))
    return {
        "available": True, "done": done_n, "pending": k, "n": n, "durs": durs,
        "mean_h": mean, "sd_sprint_h": sd, "expected_h": exp_h, "sd_h": sd_h,
        "expected": now + dt.timedelta(hours=exp_h),
        "r68": (now + dt.timedelta(hours=max(exp_h - sd_h, 0)), now + dt.timedelta(hours=exp_h + sd_h)),
        "r95": (now + dt.timedelta(hours=max(exp_h - t * sd_h, 0)), now + dt.timedelta(hours=exp_h + t * sd_h)),
        "t": t, "confidence": "low" if n < 3 else ("medium" if n < 6 else "high"),
        "active_used_h": used, "per_sprint": per,
    }


def record_forecast(fc, path: Path) -> list:
    """Log a forecast when its inputs changed (a sprint finished or was added)."""
    hist = jsonl(path)
    if fc.get("available"):
        key = (fc["n"], fc["pending"])
        last = hist[-1] if hist else None
        if not last or (last.get("n"), last.get("pending")) != key:
            row = {"ts": dt.datetime.now(UTC).isoformat(timespec="seconds"),
                   "expected": fc["expected"].isoformat(timespec="minutes"),
                   "sd_h": round(fc["sd_h"], 1), "n": fc["n"], "pending": fc["pending"]}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                hist.append(row)
            except OSError:
                pass
    return hist


# ── charts (inline SVG: no libraries, prints and exports to PDF cleanly) ─────

def gantt(sprints, times, fc, now) -> str:
    rows = []
    mean = fc.get("mean_h") if fc.get("available") else None
    cursor = now
    for s in sprints:
        sid = s.get("id")
        t = times.get(sid, {})
        st = s.get("status")
        if st == "done" and t.get("start") and t.get("done"):
            rows.append((sid, t["start"], t["done"], "done"))
        elif st == "active" and t.get("start"):
            end = max(now, t["start"] + dt.timedelta(hours=mean or 0))
            rows.append((sid, t["start"], end, "active"))
            cursor = end
        elif st in (None, "pending") and mean:
            end = cursor + dt.timedelta(hours=mean)
            rows.append((sid, cursor, end, "projected"))
            cursor = end
        elif st == "torn-down" and t.get("start"):
            rows.append((sid, t["start"], t.get("torn_down") or t["start"], "torn-down"))
    rows = [r for r in rows if r[2] >= r[1]]
    if not rows:
        return '<p class="muted">The roadmap diagram appears once sprints have start/finish times.</p>'
    t0 = min(r[1] for r in rows)
    t1 = max(max(r[2] for r in rows), now)
    span = max((t1 - t0).total_seconds(), 3600)
    W, L, rh = 760, 92, 26
    Hh = 34 + rh * len(rows)
    x = lambda d: L + (W - L - 12) * ((d - t0).total_seconds() / span)
    color = {"done": "var(--pass)", "active": "var(--accent)", "projected": "var(--muted)", "torn-down": "var(--fail)"}
    out = [f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="Roadmap: sprints over time" style="width:100%;height:auto">']
    # day ticks
    ticks = 6
    for i in range(ticks + 1):
        d = t0 + dt.timedelta(seconds=span * i / ticks)
        xx = x(d)
        out.append(f'<line x1="{xx:.1f}" y1="18" x2="{xx:.1f}" y2="{Hh - 4}" style="stroke:var(--line)" />')
        out.append(f'<text x="{xx:.1f}" y="12" text-anchor="middle" style="fill:var(--muted);font:10px var(--mono)">{e(short(d))}</text>')
    for i, (sid, a, b, kind) in enumerate(rows):
        y = 24 + i * rh
        w = max(x(b) - x(a), 3)
        dash = ' stroke-dasharray="4 3"' if kind == "projected" else ""
        fill = "none" if kind == "projected" else color[kind]
        out.append(f'<text x="4" y="{y + 13}" style="fill:var(--fg);font:11px var(--mono)">{e(sid)}</text>')
        out.append(f'<rect x="{x(a):.1f}" y="{y}" width="{w:.1f}" height="16" rx="3" '
                   f'style="fill:{fill};stroke:{color[kind]}"{dash}><title>{e(sid)} {kind}: {e(when(a))} → {e(when(b))}</title></rect>')
    nx = x(now)
    out.append(f'<line x1="{nx:.1f}" y1="18" x2="{nx:.1f}" y2="{Hh - 4}" style="stroke:var(--hl);stroke-width:1.5" />')
    out.append(f'<text x="{nx + 3:.1f}" y="{Hh - 6}" style="fill:var(--hl);font:10px var(--mono)">now</text>')
    if fc.get("available"):
        ex = x(min(fc["expected"], t1))
        out.append(f'<line x1="{ex:.1f}" y1="18" x2="{ex:.1f}" y2="{Hh - 4}" style="stroke:var(--accent);stroke-dasharray:2 2" />')
    out.append("</svg>")
    legend = ('<div class="legend"><span><i style="background:var(--pass)"></i>done</span>'
              '<span><i style="background:var(--accent)"></i>active</span>'
              '<span><i style="border:1px dashed var(--muted)"></i>projected (mean sprint length)</span>'
              '<span><i style="background:var(--fail)"></i>torn down</span>'
              '<span><i style="background:var(--hl)"></i>now</span></div>')
    return "".join(out) + legend


def bars(items, unit="h") -> str:
    """Horizontal bar list: [(label, value)]."""
    if not items:
        return '<p class="muted">No data yet.</p>'
    mx = max(v for _, v in items) or 1
    rows = "".join(
        f'<div class="hbar"><span class="lbl">{e(l)}</span><span class="track"><span style="width:{100 * v / mx:.1f}%"></span></span>'
        f'<span class="val">{v:.1f} {e(unit)}</span></div>' if isinstance(v, float) else
        f'<div class="hbar"><span class="lbl">{e(l)}</span><span class="track"><span style="width:{100 * v / mx:.1f}%"></span></span>'
        f'<span class="val">{v} {e(unit)}</span></div>' for l, v in items)
    return f'<div class="hbars">{rows}</div>'


def drift_chart(hist) -> str:
    pts = [(_ts(h.get("ts")), _ts(h.get("expected"))) for h in hist]
    pts = [p for p in pts if p[0] and p[1]]
    if len(pts) < 2:
        return ""
    W, Hh, L = 760, 140, 70
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    xspan = max((x1 - x0).total_seconds(), 1)
    yspan = max((y1 - y0).total_seconds(), 3600)
    X = lambda d: L + (W - L - 10) * (d - x0).total_seconds() / xspan
    Y = lambda d: Hh - 22 - (Hh - 40) * (d - y0).total_seconds() / yspan
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(a):.1f},{Y(b):.1f}" for i, (a, b) in enumerate(pts))
    dots = "".join(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="3" style="fill:var(--accent)"><title>{e(short(a))}: expected {e(day(b))}</title></circle>' for a, b in pts)
    return (f'<h3>How the expected date has moved</h3><svg viewBox="0 0 {W} {Hh}" style="width:100%;height:auto" role="img" aria-label="Forecast drift">'
            f'<text x="4" y="{Y(y1) + 4:.1f}" style="fill:var(--muted);font:10px var(--mono)">{e(short(y1))}</text>'
            f'<text x="4" y="{Y(y0) + 4:.1f}" style="fill:var(--muted);font:10px var(--mono)">{e(short(y0))}</text>'
            f'<path d="{path}" style="fill:none;stroke:var(--accent);stroke-width:2" />{dots}'
            f'<text x="{L}" y="{Hh - 4}" style="fill:var(--muted);font:10px var(--mono)">forecast made {e(short(x0))}</text>'
            f'<text x="{W - 10}" y="{Hh - 4}" text-anchor="end" style="fill:var(--muted);font:10px var(--mono)">{e(short(x1))}</text></svg>')


# ── data readers ──────────────────────────────────────────────────────────────

def read_risks(root: Path) -> list:
    """Rows from any risk register table with a Status column; open ones only."""
    out = []
    cands = [root / "docs/09-risk-register.md", root / "docs/risk-register.md", root / ".harness/risk-register.md"]
    cands += sorted((root / "docs").glob("*risk*.md")) if (root / "docs").is_dir() else []
    seen = set()
    for p in cands:
        if not p.is_file() or p in seen:
            continue
        seen.add(p)
        header = None
        for line in p.read_text(errors="ignore").splitlines():
            if not line.strip().startswith("|"):
                header = None if not line.strip() else header
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if header is None:
                low = [c.lower() for c in cells]
                if "status" in low and ("risk" in low or "id" in low):
                    header = low
                continue
            if set("".join(cells)) <= set("-: "):
                continue
            row = dict(zip(header, cells))
            if "open" in row.get("status", "").lower():
                out.append({"id": row.get("id", ""), "risk": row.get("risk", ""), "severity": row.get("severity", ""),
                            "owner": row.get("owner", ""), "mitigation": row.get("mitigation", ""),
                            "source": str(p.relative_to(root))})
    return out


def read_roadmap(root: Path) -> list:
    p = root / "docs/00b-roadmap.md"
    if not p.is_file():
        return []
    out, cur = [], None
    for line in p.read_text(errors="ignore").splitlines():
        m = re.match(r"^##\s+(Now|Next|Later)\b\s*(.*)$", line)
        if m:
            cur = {"horizon": m.group(1), "window": m.group(2).strip(" ()"), "milestone": "", "outcomes": "", "timeframe": ""}
            out.append(cur)
            continue
        if cur:
            for key, label in (("milestone", "Milestone"), ("outcomes", "Target outcomes"), ("timeframe", "Target timeframe")):
                mm = re.match(rf"^-\s*{label}:\s*(.*)$", line.strip())
                if mm:
                    cur[key] = mm.group(1)
    return out


def read_features_doc(root: Path) -> dict:
    """Fallback when product-map.json is absent: the Summary table of
    docs/02c-features.md (ID | Feature | Persona(s) | Priority | Release | Flows |
    Use cases | Requirements | Affects)."""
    p = root / "docs/02c-features.md"
    out = {}
    if not p.is_file():
        return out
    for line in p.read_text(errors="ignore").splitlines():
        m = re.match(r"^\|\s*(F-\d+)\s*\|(.*)\|\s*$", line)
        if not m:
            continue
        c = [x.strip() for x in m.group(2).split("|")]
        c += [""] * (8 - len(c))
        out[m.group(1)] = {"name": c[0], "personas": c[1], "priority": c[2].lower(), "release": c[3],
                           "flows": re.findall(r"PF-\d+", c[4]), "use_cases": re.findall(r"UC-\d+", c[5]),
                           "requirements": re.findall(r"(?:FR|NFR)-\d+", c[6])}
    return out


def check_url(url: str, timeout: float = 4.0) -> str:
    """'up 200', 'answered 404', 'unreachable from here', or 'not checked'."""
    if not url or not re.match(r"^https?://", url):
        return "not checked"
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "asdr-dashboard"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return f"up {r.status}"
    except urllib.error.HTTPError as ex:
        return f"answered {ex.code}"
    except Exception:  # noqa: BLE001
        return "unreachable from here"


def regressions(pmap, snap_path: Path) -> list:
    """Journeys proven in the previous dashboard snapshot and not proven now."""
    flows = (pmap or {}).get("flows") or {}
    prev = read_json(snap_path, {}).get("flows", {})
    regs = sorted(k for k, v in flows.items() if prev.get(k) == "proven" and v.get("status") not in ("proven",))
    try:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps({"ts": dt.datetime.now(UTC).isoformat(timespec="seconds"),
                                         "flows": {k: v.get("status") for k, v in flows.items()}}, indent=1))
    except OSError:
        pass
    return regs


# ── page ──────────────────────────────────────────────────────────────────────

def dash_css() -> str:
    return ("<style>"
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}"
            ".kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;display:grid;gap:4px;min-width:0}"
            ".kpi .n{font:600 1.3rem/1.15 var(--mono);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}"
            ".kpi .l{font:500 .7rem/1.25 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}"
            ".state{font:700 .95rem/1 var(--body);padding:7px 14px}"
            ".progress{height:14px;border-radius:7px;background:var(--line);overflow:hidden}"
            ".progress span{display:block;height:100%;background:var(--accent)}"
            ".toc{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.85rem;padding:0;list-style:none}"
            ".q{border-top:1px solid var(--line);padding:10px 0;display:grid;gap:3px}"
            ".q .meta{font:.74rem var(--mono);color:var(--muted)}"
            ".q.open{border-left:4px solid var(--skip);padding-left:12px}"
            ".legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.78rem;color:var(--muted)}"
            ".legend i{display:inline-block;width:12px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}"
            ".hbars{display:grid;gap:6px}.hbar{display:grid;grid-template-columns:150px 1fr 80px;gap:10px;align-items:center;font-size:.85rem}"
            ".hbar .lbl{overflow-wrap:anywhere}.hbar .track{height:10px;background:var(--line);border-radius:5px;overflow:hidden}"
            ".hbar .track span{display:block;height:100%;background:var(--accent)}.hbar .val{font:.8rem var(--mono);text-align:right}"
            "td{white-space:normal}td.mono,td .mono{white-space:nowrap}"
            ".two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}"
            "@media (max-width:560px){.hbar{grid-template-columns:90px 1fr 60px}}"
            "@page{size:A4;margin:12mm}"
            "@media print{.band{break-inside:auto;padding:12px;gap:10px}.toc{display:none}.kpi,.q,tr,.hbar,svg,.legend{break-inside:avoid}"
            "h2{break-after:avoid}.wrap{gap:14px}.grid{grid-template-columns:repeat(4,minmax(0,1fr))}"
            ".kpi{padding:8px}.kpi .n{font-size:1rem}.two{grid-template-columns:1fr}"
            ".table-wrap{overflow:visible!important;border:0}table{font-size:8pt;table-layout:auto;width:100%}"
            "th,td{padding:3px 5px;white-space:normal!important;overflow-wrap:anywhere}th{overflow-wrap:normal;word-break:keep-all;letter-spacing:.02em}td .mono,td.mono{white-space:normal!important}"
            ".pill{padding:1px 6px;font-size:7.5pt;white-space:nowrap}h3{margin-top:12px;display:block;break-before:auto}"
            "thead{display:table-header-group}tr{page-break-inside:avoid}}"
            "</style>")


def build(root: Path, now: dt.datetime) -> str:
    progress = read_json(H / "progress.json", {})
    sp = read_json(root / "sprints.json", [])
    sprints = [s for s in (sp.get("sprints", []) if isinstance(sp, dict) else sp) if isinstance(s, dict)]
    pmap = read_json(H / "product-map.json", {})
    facts = read_json(H / "facts.json", {})
    metrics = read_json(H / "metrics.json", {})
    trace = read_json(H / "traceability.json", {})
    cfg = read_json(H / "dashboard.json", {})
    traces = jsonl(H / "traces" / "log.jsonl")
    clock = jsonl(H / "sprint-clock.jsonl")
    history = jsonl(H / "test-results" / "history.jsonl")
    qmap = {}
    for q in jsonl(H / "questions.jsonl"):
        qmap[q.get("id") or len(qmap)] = q
    questions = list(qmap.values())
    risks = read_risks(root)
    regs = regressions(pmap, H / "dashboard-snapshot.json")
    times = sprint_times(clock, traces)
    fc = forecast(sprints, times, now)
    fhist = record_forecast(fc, H / "forecast-history.jsonl")
    state, reasons = classify(progress, pmap, facts, questions, risks, regs)
    tr = (facts or {}).get("test_runs") or {}
    flows = (pmap or {}).get("flows") or {}
    features = (pmap or {}).get("features") or {}
    fdoc = read_features_doc(root)
    if not features:
        features = fdoc
    else:
        for k, v in fdoc.items():
            if k in features:
                features[k] = {**v, **{kk: vv for kk, vv in features[k].items() if vv}}
    counts = (pmap or {}).get("counts") or {}
    project = cfg.get("project") or "Project"

    # overall progress: phase weights, execution scaled by sprints done
    cur = progress.get("phase") or "strategic"
    keys = [p[0] for p in PHASES]
    ci = keys.index(cur) if cur in keys else 0
    done_sprints = sum(1 for s in sprints if s.get("status") == "done")
    live_sprints = [s for s in sprints if s.get("status") != "torn-down"]
    overall = 0.0
    for i, (k, _lbl, _g, _gk, w) in enumerate(PHASES):
        if k == "execution":
            if i < ci:
                overall += w
            elif i == ci:
                overall += w * (done_sprints / len(live_sprints) if live_sprints else 0)
        elif k == "done" and cur == "done":
            overall += w
        elif i < ci:
            overall += w
    overall = min(round(overall), 100)

    out = []
    # 1 status and progress
    nxt = progress.get("awaiting")
    out.append(
        f'<main class="wrap"><header class="stack"><span class="eyebrow">{e(project)} · ASDR project dashboard</span>'
        f'<div class="row" style="justify-content:space-between"><h1>Where the project is</h1>'
        f'<span class="pill state {STATE_PILL[state]}">{e(state.upper())}</span></div>'
        f'<p>Phase <b>{e(dict((p[0], p[1]) for p in PHASES).get(cur, cur))}</b>'
        f'{" · active sprint <b>" + e(progress.get("sprint")) + "</b>" if progress.get("sprint") else ""}'
        f'{" · waiting on: <b>" + e(nxt) + "</b>" if nxt else ""} · rigor {e(progress.get("rigor") or "standard")}</p>'
        f'<div class="stack" style="gap:6px"><div class="row" style="justify-content:space-between">'
        f'<span class="eyebrow">Overall progress</span><span class="mono">{overall}%</span></div>'
        f'<div class="progress" role="progressbar" aria-valuenow="{overall}" aria-valuemin="0" aria-valuemax="100"><span style="width:{overall}%"></span></div>'
        f'<span class="muted" style="font-size:.8rem">Discovery &amp; architecture 30% · planning 5% · sprints 55% (by sprints done) · final gates 5% · release 5%.</span></div>'
        f'<p class="muted">Why {e(state)}: {e("; ".join(reasons))}.</p>'
        f'<p class="muted" style="font-size:.8rem">Generated {e(when(now))} from the project files — refreshed at the end of every phase and sprint, and on request.</p>'
        '<ul class="toc">' + "".join(f'<li><a href="#{a}">{e(b)}</a></li>' for a, b in [
            ("glance", "At a glance"), ("phases", "Phases"), ("forecast", "Delivery"), ("roadmap", "Roadmap"),
            ("features", "Features"), ("speed", "Speed"), ("quality", "Quality"), ("risks", "Risks"),
            ("decisions", "Questions & decisions"), ("documents", "Documents"), ("environments", "Environments"), ("repos", "Repos & resources"),
            ("activity", "Activity"), ("effort", "ASDR effort")]) + '</ul></header>')

    # 2 at a glance
    delivered = sum(1 for f in features.values() if f.get("flows") and all(flows.get(x, {}).get("status") == "proven" for x in f["flows"]))
    open_q = sum(1 for q in questions if q.get("status") == "open")
    t = tr.get("totals") or {}
    glance = [
        (f"{overall}%", "overall progress"),
        (e(day(fc["expected"])) + f'<br><small class="muted">± {e(fmt_span(fc["sd_h"]))} (1 SD)</small>' if fc["available"]
         else '<span class="muted">after 2 sprints</span>', "expected delivery"),
        (f"{done_sprints}/{len(live_sprints)}", "sprints done"),
        (f"{delivered}/{len(features)}" if features else "—", "features delivered"),
        (f"{sum(1 for v in flows.values() if v.get('status') == 'proven')}/{len(flows)}" if flows else "—", "journeys proven"),
        (f"{counts.get('items_executed', 0)}/{counts['items']}" if counts.get("items") else "—", "items tested"),
        (f"{t.get('passed', 0)}/{t.get('tests', 0)}" if t else "—", "tests passing"),
        (len(risks), "open risks"),
        (open_q, "questions waiting on you"),
    ]
    out.append(section("glance", "At a glance", kpis(glance)))

    # 3 phases and gates
    prow = []
    for i, (k, lbl, gates, gkind, w) in enumerate(PHASES):
        st = "done" if i < ci or (cur == "done") else ("current" if i == ci else "upcoming")
        if k == "execution":
            gate = f"{done_sprints}/{len(live_sprints)} sprints done" if sprints else "—"
            fin = max((t_.get("done") for t_ in times.values() if t_.get("done")), default=None) if st == "done" else None
        else:
            vs = [(Path(g).name, verdict_of(root / g)) for g in gates]
            gate = "; ".join(f"{n}: {v}" for n, v in vs if v) or "—"
            fin = max((mtime(root / g) for g in gates if (root / g).exists()), default=None) if st == "done" else None
        prow.append([e(lbl), pill(st, {"done": "passed", "current": "skipped", "upcoming": "neutral"}[st]),
                     e(gkind), e(gate), f'<span class="mono">{e(when(fin)) if fin else "—"}</span>'])
    out.append(section("phases", "Phases and gates", table(["Phase", "State", "Gate", "Gate result", "Finished"], prow)))

    # 4 delivery forecast
    if fc["available"]:
        drift = ""
        if len(fhist) >= 2:
            first, prev = _ts(fhist[0]["expected"]), _ts(fhist[-2]["expected"])
            if first and prev:
                w_ = lambda d: (f"slipped {d:.1f} days" if d > 0.05 else (f"moved in {abs(d):.1f} days" if d < -0.05 else "held"))
                drift = (f'<p>Since the previous forecast the date has <b>{w_((fc["expected"] - prev).total_seconds() / 86400)}</b>; '
                         f'since the first forecast ({e(day(first))}) it has <b>{w_((fc["expected"] - first).total_seconds() / 86400)}</b>.</p>')
        per_rows = [[f'<span class="mono">{e(s.get("id"))}</span>', e(s.get("goal") or ""), e(s.get("status") or "pending"),
                     e(day(d)), f'<span class="mono">± {e(fmt_span(sdi))}</span>'] for s, d, sdi in fc["per_sprint"]]
        exp_lbl = day(fc["expected"]) + (fc["expected"].strftime(" %H:%M UTC") if fc["sd_h"] < 48 else "")
        inner = (f'<p style="font-size:1.15rem">Expected delivery <b>{e(exp_lbl)}</b> '
                 f'<span class="mono">± {e(fmt_span(fc["sd_h"]))}</span> <span class="muted">(1 standard deviation)</span></p>'
                 + kpis([(e(span_fmt(*fc["r68"])), "68% range (±1 SD)"),
                         (e(span_fmt(*fc["r95"])), "95% range"),
                         (f'{fc["mean_h"]:.1f} h ± {fc["sd_sprint_h"]:.1f}', "sprint cycle, mean ± SD"),
                         (f'{fc["pending"]} to go', f'{fc["n"]} measured · confidence {fc["confidence"]}')])
                 + drift + "<h3>Expected finish of each remaining sprint</h3>"
                 + table(["Sprint", "Goal", "Status", "Expected finish", "± 1 SD"], per_rows)
                 + drift_chart(fhist)
                 + f'<p class="muted">Method: the last {fc["n"]} sprint cycles took {fc["mean_h"]:.1f} h on average, '
                   f'measured finish-to-finish so waiting between sprints is included (SD {fc["sd_sprint_h"]:.1f} h). '
                   f'{fc["pending"]} sprint(s) remain'
                   + (f'; {fc["active_used_h"]:.1f} h have passed since the last one finished' if fc["active_used_h"] else "")
                   + '. The ± is the prediction-interval standard deviation for the remaining work, s·√(k + k²/n), '
                     f'which includes the uncertainty of the average itself; the 95% range uses Student-t ({fc["t"]:.2f}) '
                     'because the sample is small. Assumes remaining sprints are similar in size and work continues at '
                     'the same pace; excludes final gates and release. Every finished sprint narrows it.</p>')
    else:
        inner = (f'<p class="muted">No delivery date yet — need {e(" and ".join(fc["need"]))}. '
                 f'{fc["done"]} sprint(s) done, {fc["pending"]} to go. A standard deviation needs at least two '
                 'measured sprints, so a date before then would be guesswork and none is shown.</p>')
    out.append(section("forecast", "Delivery forecast", inner))

    # 5 roadmap
    rm = read_roadmap(root)
    rm_html = ""
    if rm:
        rm_html = "<h3>Product roadmap</h3>" + table(
            ["Horizon", "Milestone", "Outcomes", "Target timeframe"],
            [[e(r["horizon"] + (f' ({r["window"]})' if r["window"] else "")), e(r["milestone"]), e(r["outcomes"]),
              e(r["timeframe"])] for r in rm])
    srows = []
    verdicts = {s.get("id"): s for s in metrics.get("sprints", [])}
    for s in sprints:
        sid = s.get("id")
        t_ = times.get(sid, {})
        dur = (t_["done"] - t_["start"]).total_seconds() / 3600 if t_.get("start") and t_.get("done") else None
        mv = verdicts.get(sid, {})
        srows.append([f'<span class="mono">{e(sid)}</span>', e(s.get("goal") or ""),
                      f'<span class="mono">{e(", ".join(s.get("flows") or []))}</span>',
                      pill(s.get("status") or "pending", {"done": "passed", "active": "skipped", "torn-down": "failed"}.get(s.get("status"), "neutral")),
                      f'<span class="mono">{e(short(t_.get("start")))}</span>', f'<span class="mono">{e(short(t_.get("done")))}</span>',
                      f'<span class="mono">{e(f"{dur:.1f} h" if dur else "—")}</span>',
                      f'<span class="mono">{e(mv.get("attempts", "—"))}</span>'])
    out.append(section("roadmap", "Roadmap",
                       gantt(sprints, times, fc, now) + rm_html + "<h3>Sprints</h3>"
                       + table(["Sprint", "Goal (what a user can do)", "Journeys", "Status", "Started", "Finished", "Took", "Evaluations"],
                               srows, "No sprint plan yet.")))

    # 6 features
    flow_sprint = {}
    for s in sprints:
        for f_ in s.get("flows") or []:
            flow_sprint.setdefault(f_, []).append(s)
    frows = []
    for fid, f in sorted(features.items()):
        fl = f.get("flows") or []
        sp_ = [s for x in fl for s in flow_sprint.get(x, [])]
        proven = fl and all(flows.get(x, {}).get("status") == "proven" for x in fl)
        if proven:
            st = ("verified", "passed")
        elif any(s.get("status") == "done" for s in sp_):
            st = ("delivered", "passed")
        elif any(s.get("status") == "active" for s in sp_):
            st = ("in progress", "skipped")
        else:
            st = ("planned", "neutral")
        frows.append([f'<span class="mono">{e(fid)}</span>', e(f.get("name")), e(f.get("personas") or ""),
                      e((f.get("priority") or "").title()), e(f.get("release") or ""),
                      f'<span class="mono">{e(", ".join(fl))}</span>',
                      f'<span class="mono">{e(", ".join(f.get("requirements") or []) or "—")}</span>',
                      f'<span class="mono">{e(", ".join(sorted({s.get("id") for s in sp_})) or "—")}</span>', pill(*st)])
    fst = {}
    for r in frows:
        k = re.search(r">([a-z ]+)</span>$", r[-1])
        fst[k.group(1) if k else "?"] = fst.get(k.group(1) if k else "?", 0) + 1
    fsum = kpis([(fst.get("verified", 0), "verified"), (fst.get("delivered", 0), "delivered, not yet verified"),
                 (fst.get("in progress", 0), "in progress"), (fst.get("planned", 0), "planned")]) if frows else ""
    out.append(section("features", "Features and development status", fsum + table(
        ["ID", "Feature", "Who uses it", "Priority", "Release", "Journeys", "Requirements", "Sprint", "Development status"], frows,
        "No feature list yet (docs/02c-features.md)."),
        "Planned → in progress (its sprint is active) → delivered (sprint passed) → verified (every journey it sits on passed its end-to-end test on the latest run)."))

    # 7 development speed
    durs = [((s.get("id")), (times[s.get("id")]["done"] - times[s.get("id")]["start"]).total_seconds() / 3600)
            for s in sprints if s.get("status") == "done" and times.get(s.get("id"), {}).get("start") and times[s.get("id")].get("done")]
    msp = metrics.get("sprints", [])
    first_pass = sum(1 for s in msp if s.get("attempts") == 1 and s.get("status") == "done")
    done_m = [s for s in msp if s.get("status") == "done"]
    avg_att = (sum(s.get("attempts", 0) for s in done_m) / len(done_m)) if done_m else None
    starts = [t_.get("start") for t_ in times.values() if t_.get("start")]
    weeks = max(((now - min(starts)).total_seconds() / 604800), 1 / 7) if starts else None
    fpw = (delivered / weeks) if weeks else None
    c7 = git("rev-list", "--count", "--since=7.days", "HEAD")
    c30 = git("rev-list", "--count", "--since=30.days", "HEAD")
    runs = len(history)
    passed_runs = sum(1 for r in history if r.get("status") == "passed")
    speed = kpis([
        (f"{sum(d for _, d in durs) / len(durs):.1f} h" if durs else "—", "average sprint length"),
        (f"{first_pass}/{len(done_m)}" if done_m else "—", "sprints passed first time"),
        (f"{avg_att:.1f}" if avg_att else "—", "evaluations per sprint"),
        (metrics.get("negotiation_rounds_total", "—"), "contract negotiation rounds"),
        (f"{fpw:.1f}" if fpw is not None else "—", "features verified per week"),
        (f"{c7 or '—'} / {c30 or '—'}", "commits last 7 / 30 days"),
        (f"{passed_runs}/{runs}" if runs else "—", "test runs passed"),
    ])
    out.append(section("speed", "Development speed",
                       speed + "<h3>Sprint lengths</h3>" + bars([(s, round(d, 1)) for s, d in durs]),
                       "Outcome measures first: rework (evaluations per sprint) and verified features matter more than commit counts."))

    # 8 quality
    fl_rows = [[f'<span class="mono">{e(k)}</span>', e(v.get("title") or ""), e((v.get("priority") or "").title()),
                pill(v.get("status") or "pending", {"proven": "passed", "failing": "failed"}.get(v.get("status"), "neutral")),
                f'<span class="mono">{e(", ".join(v.get("journey_tests") or []) or "—")}</span>'] for k, v in sorted(flows.items())]
    cov = (pmap or {}).get("coverage") or {}
    cov_rows = [[e(k), f'<span class="mono">{v.get("total", 0)}</span>', f'<span class="mono">{v.get("declared", 0)}</span>',
                 f'<span class="mono">{v.get("executed", 0)}</span>'] for k, v in cov.items()]
    a = tr.get("a11y") or {}
    meas = [[e(n), f'<span class="mono">{e(m.get("value"))} {e(m.get("unit") or "")}</span>',
             f'<span class="mono">{e(m.get("budget") if m.get("budget") is not None else "—")}</span>',
             pill("within budget" if m.get("within_budget") else ("over budget" if m.get("within_budget") is False else "no budget"),
                  "passed" if m.get("within_budget") else ("failed" if m.get("within_budget") is False else "neutral"))]
            for n, m in (tr.get("metrics") or {}).items()]
    qk = kpis([
        (f"{t.get('passed', 0)}/{t.get('tests', 0)}" if t else "—", "tests passing (latest run)"),
        (e(tr.get("status") or "—"), "latest run"),
        (f"{a.get('critical', 0) + a.get('serious', 0)}" if a else "—", "accessibility blockers"),
        (", ".join(regs) if regs else "none", "regressions"),
    ])
    out.append(section("quality", "Quality",
                       qk + '<div class="two"><div class="stack"><h3>Journeys</h3>'
                       + table(["Flow", "Journey", "Priority", "Status", "Journey test"], fl_rows, "No process flows yet.")
                       + '</div><div class="stack"><h3>Coverage of every testable item</h3>'
                       + table(["Kind", "Items", "Named by a test", "Reached by a passing test"], cov_rows, "No coverage data yet.")
                       + '</div></div>' + ("<h3>Measurements</h3>" + table(["Measure", "Value", "Budget", "Result"], meas) if meas else "")))

    # 9 risks and blockers
    rrows = [[f'<span class="mono">{e(r["id"])}</span>', e(r["risk"]), e(r["severity"]), e(r["owner"]), e(r["mitigation"]),
              f'<span class="mono">{e(r["source"])}</span>'] for r in risks]
    torn = [s.get("id") for s in sprints if s.get("status") == "torn-down"]
    blockers = [x for x in reasons if x != "no blocking or risk rule triggered"]
    out.append(section("risks", "Risks and blockers",
                       ("<h3>Blockers and warnings</h3><ul>" + "".join(f"<li>{e(b)}</li>" for b in blockers) + "</ul>" if blockers
                        else '<p class="muted">No blockers.</p>')
                       + (f'<p>Torn-down sprints (re-planned): <span class="mono">{e(", ".join(torn))}</span></p>' if torn else "")
                       + "<h3>Open risks</h3>" + table(["ID", "Risk", "Severity", "Owner", "Mitigation", "Source"], rrows,
                                                       "No open risks recorded.")))

    # 10 questions and decisions
    qs = sorted(questions, key=lambda q: q.get("ts") or "", reverse=True)
    waiting = [q for q in qs if q.get("status") == "open"]
    answered = [q for q in qs if q.get("status") != "open"]
    qhtml = "<h3>Waiting on you</h3>" + ("".join(
        f'<div class="q open"><div><b>{e(q.get("question"))}</b></div><div class="meta">{e(q.get("id"))} · asked {e(when(q.get("ts")))}'
        f'{" · " + e(q.get("phase")) if q.get("phase") else ""}{" · by " + e(q.get("asked_by")) if q.get("asked_by") else ""}</div></div>'
        for q in waiting) or '<p class="muted">Nothing waiting on you.</p>')
    qhtml += f"<h3>Your answers ({len(answered)})</h3>" + ("".join(
        f'<div class="q"><div><b>{e(q.get("question"))}</b></div><div>{e(q.get("answer"))}</div>'
        f'<div class="meta">{e(q.get("id"))} · {e(when(q.get("ts")))}{" · " + e(q.get("phase")) if q.get("phase") else ""}'
        f'{" · changed " + e(", ".join(q.get("changed", []))) if q.get("changed") else ""}</div></div>' for q in answered)
        or '<p class="muted">No questions logged yet (log_question.py records each one).</p>')
    gate_rows = []
    for p in sorted((root / "docs").glob("decision-*.md")) if (root / "docs").is_dir() else []:
        gate_rows.append([e(p.stem.replace("decision-", "").title()), e(verdict_of(p) or "—"), f'<span class="mono">{e(when(mtime(p)))}</span>',
                          f'<span class="mono">{e(str(p.relative_to(root)))}</span>'])
    for d in jsonl(root / ".harness/decision-log.jsonl") + jsonl(root / "decision-log.jsonl"):
        if d.get("decision", "").lower().startswith("example"):
            continue
        gate_rows.append([e(f'{d.get("phase", "")} · {d.get("actor", "")}'), e(f'{d.get("decision", "")} ({d.get("status", "")})'),
                          f'<span class="mono">{e(when(d.get("timestamp")))}</span>', e(d.get("reason", ""))])
    adrs = sorted((root / "docs/adr").glob("*.md")) if (root / "docs/adr").is_dir() else []
    adr_rows = []
    for p in adrs:
        first = next((ln.lstrip("# ").strip() for ln in p.read_text(errors="ignore").splitlines() if ln.startswith("#")), p.stem)
        adr_rows.append([f'<span class="mono">{e(p.name)}</span>', e(first), f'<span class="mono">{e(when(mtime(p)))}</span>'])
    out.append(section("decisions", "Questions and decisions", qhtml + "<h3>Gate decisions</h3>"
                       + table(["Gate", "Decision", "When", "Record"], gate_rows, "No gate decisions yet.")
                       + "<h3>Architecture decisions (ADRs)</h3>" + table(["File", "Decision", "Updated"], adr_rows, "No ADRs yet.")))

    # 11 documents and artifacts
    drows = []
    have = 0
    for ph, name, path, owner in CANON:
        p = root / path
        if p.exists():
            have += 1
            stv = verdict_of(p) if Path(path).name.startswith("decision-") else None
            st = pill("present" + (f" · {stv}" if stv and stv != "written" else ""), "passed")
            upd = when(mtime(p))
        elif path in OPTIONAL:
            st, upd = pill("only if needed", "neutral"), "—"
        else:
            reached = [k for k, *_ in PHASES].index({"Discovery": "strategic", "Architecture": "strategic", "Planning": "planning",
                                                       "Final gates": "final-gates", "Release": "done"}[ph]) < ci
            st, upd = (pill("missing", "failed") if reached else pill("not yet", "neutral")), "—"
        drows.append([e(ph), e(name), f'<span class="mono">{e(path)}</span>', e(owner), st, f'<span class="mono">{e(upd)}</span>'])
    gen = []
    tr_dir = root / "docs/test-reports"
    if tr_dir.is_dir():
        labs = sorted(x.name for x in tr_dir.iterdir() if x.is_dir())
        if labs:
            gen.append(["Test reports", f'{len(labs)} published', f'<span class="mono">{e(", ".join(labs[-5:]))}</span>'])
    man = root / "docs/manuals"
    if man.is_dir():
        vers = sorted(x.name for x in man.iterdir() if x.is_dir() and re.match(r"^\d", x.name))
        if vers:
            gen.append(["User manuals (HTML + PDF)", f"{len(vers)} version(s)", f'<span class="mono">{e(", ".join(vers))}</span>'])
    for label, d, pat in [("Sprint contracts", H / "contracts", "*.md"), ("Evaluation reports", H / "eval-reports", "*.md"),
                          ("Stage QA reports", H / "qa-reports", "*.md"), ("Integrity snapshots", root / "docs", "integrity-*.md"),
                          ("Assessment", root / "docs/assess", "*")]:
        fs = sorted(d.glob(pat)) if d.is_dir() else []
        if fs:
            gen.append([e(label), f"{len(fs)} file(s)", f'<span class="mono">{e(", ".join(f.name for f in fs[-4:]))}</span>'])
    canon_paths = {c[2] for c in CANON}
    others = []
    if (root / "docs").is_dir():
        for f in sorted((root / "docs").rglob("*")):
            rel = str(f.relative_to(root))
            if (not f.is_file() or rel in canon_paths or f.suffix.lower() not in (".md", ".pdf", ".html", ".json", ".docx", ".xlsx", ".csv", ".png", ".svg")
                    or any(part in ("test-reports", "dashboard") for part in f.parts) or re.search(r"docs/manuals/\d", rel)):
                continue
            others.append([f'<span class="mono">{e(rel)}</span>', f'<span class="mono">{e(f.suffix.lstrip(".").upper())}</span>',
                           f'<span class="mono">{e(f"{f.stat().st_size / 1024:.0f} KB")}</span>', f'<span class="mono">{e(when(mtime(f)))}</span>'])
    out.append(section("documents", "Documents and artifacts",
                       table(["Phase", "Document", "Path", "Owner", "Status", "Updated"], drows)
                       + f"<h3>All other project documents ({len(others)})</h3>"
                       + table(["File", "Type", "Size", "Updated"], others, "No other documents.")
                       + "<h3>Generated reports and records</h3>" + table(["Kind", "Count", "Latest"], gen, "None generated yet."),
                       f"{have} of {len(CANON)} canonical documents present. “Missing” means the phase that should have written it is already over."))

    # 12a environments
    filled = lambda x: isinstance(x, dict) and "<" not in str(x.get("url") or "")   # skip unfilled template rows
    envs = [x for x in (cfg.get("environments") or []) if filled(x)]
    tc = read_json(H / "test-config.json", {})
    app_url = (tc.get("app") or {}).get("url")
    if app_url and not any(x.get("url") == app_url for x in envs):
        envs.insert(0, {"name": "Automated test run", "url": app_url, "purpose": "where run_tests.py drives the browser suites",
                        "deployed": tr.get("commit") or ""})
    erows = []
    for x in envs:
        health = x.get("health_url") or x.get("url")
        status = check_url(health) if x.get("check", True) and not str(health).startswith(("http://localhost", "http://127.")) else "local only"
        cls = "passed" if status.startswith("up") else ("skipped" if status.startswith("answered") else "neutral")
        roles = ", ".join(x.get("test_roles") or [])
        erows.append([e(x.get("name")), f'<a href="{e(x.get("url"))}">{e(x.get("url"))}</a>' if x.get("url") else "—",
                      e(x.get("purpose") or ""), f'<span class="mono">{e(x.get("deployed") or x.get("branch") or "—")}</span>',
                      e(roles or "—"), pill(status, cls)])
    out.append(section("environments", "Environments", table(
        ["Environment", "URL", "Used for", "Deployed version / branch", "Test logins (roles)", "Reachable now"], erows,
        "No environments listed. Add dev, test, staging, UAT and production to .harness/dashboard.json → environments."),
        "Test logins show role names only — credentials stay in environment variables and are never written here."))

    # 12 repositories and resources
    remotes = git("remote", "-v")
    rrows = []
    seen = set()
    for line in remotes.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in seen:
            seen.add(parts[0])
            url = re.sub(r"https://[^@/]+@", "https://", parts[1])          # never show credentials
            rrows.append([e(parts[0]), f'<span class="mono">{e(url)}</span>'])
    head = git("log", "-1", "--format=%h|%s|%cI|%an")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    total = git("rev-list", "--count", "HEAD")
    authors = git("shortlog", "-sn", "--all", "--no-merges")
    repo_k = []
    if head:
        h_, msg, cdate, who = (head.split("|") + ["", "", "", ""])[:4]
        repo_k = kpis([(f'<span class="mono">{e(branch)}</span>', "branch"), (f'<span class="mono">{e(h_)}</span>', "latest commit"),
                       (e(short(_ts(cdate))), "last commit"), (e(total), "commits"),
                       (len(authors.splitlines()) if authors else "—", "contributors")])
        repo_k += f'<p class="muted">Latest: “{e(msg)}” by {e(who)}. Local path: <span class="mono">{e(str(root.resolve()))}</span></p>'
    extra = [r for r in (cfg.get("repos", []) or []) if filled(r)]
    for r in extra:
        if isinstance(r, dict):
            rrows.append([e(r.get("name") or "repo"), f'<span class="mono">{e(r.get("url"))}</span>' + (f' · {e(r.get("purpose"))}' if r.get("purpose") else "")])
    if cfg.get("repo") and "<" not in cfg["repo"] and not any(cfg["repo"] in str(x) for x in rrows):
        rrows.insert(0, ["project", f'<span class="mono">{e(cfg["repo"])}</span> · branch {e(cfg.get("branch") or branch or "main")}'])
    links = [[e(l.get("label") or l.get("url")), f'<a href="{e(l["url"])}">{e(l["url"])}</a>'] for l in (cfg.get("links") or []) if filled(l) and l.get("url")]
    comp = read_json(H / "companions.json", {})
    tools = [[e(k), e(v if isinstance(v, str) else json.dumps(v)[:80])] for k, v in comp.items()] if isinstance(comp, dict) else []
    out.append(section("repos", "Repositories and resources",
                       (repo_k or '<p class="muted">Not a git repository yet.</p>')
                       + "<h3>Repositories</h3>" + table(["Name", "Where"], rrows, "No remote configured.")
                       + "<h3>Links</h3>" + table(["Resource", "URL"], links, "Add CI, staging, production and published pages in .harness/dashboard.json → links.")
                       + ("<h3>Tools and companions</h3>" + table(["Tool", "Detail"], tools) if tools else "")))

    # 13 recent activity
    arows = [[f'<span class="mono">{e(when(r.get("ts")))}</span>', e(r.get("actor")), e(r.get("action")), e(r.get("result"))]
             for r in traces[-15:][::-1]]
    out.append(section("activity", "Recent activity", table(["When", "Who", "Action", "Result"], arows, "No agent activity logged yet.")))

    # 14 ASDR effort
    inv = metrics.get("agent_invocations") or {}
    eff = kpis([(metrics.get("agent_invocations_total", "—"), "agent invocations"),
                (metrics.get("sprint_attempts_total", "—"), "sprint evaluations"),
                (metrics.get("negotiation_rounds_total", "—"), "negotiation rounds"),
                (sum((metrics.get("stage_qa_rounds") or {}).values()) if metrics.get("stage_qa_rounds") else "—", "stage QA rounds")])
    out.append(section("effort", "ASDR effort", eff + "<h3>By role</h3>" + bars([(k, v) for k, v in list(inv.items())[:12]], "runs"),
                       "From run_metrics.py. Where the time and tokens went, so the next run can change something."))

    out.append('<footer>Generated by build_dashboard.py from the project files. Single source of truth — do not hand-edit; '
               'rerun the script. Private working view. To print or save as PDF, use dashboard.pdf in the same folder, '
               'or print this page from a browser.</footer></main>')
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ASDR project dashboard (HTML + PDF).")
    ap.add_argument("--out", default="docs/dashboard")
    ap.add_argument("--inline", metavar="FILE", default=None, help="also write a single-file (Artifact) copy here")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    root = Path.cwd()
    cfg = read_json(H / "dashboard.json", {})
    if args.title:
        cfg["project"] = args.title
        try:
            H.mkdir(exist_ok=True)
            (H / "dashboard.json").write_text(json.dumps(cfg, indent=2))
        except OSError:
            pass
    pub = read_json(H / "publish.json", {"repo": True})
    now = dt.datetime.now(UTC)
    body = build(root, now)
    title = f"{cfg.get('project') or 'Project'} Dashboard"
    outputs = {}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_file = out_dir / "index.html"
    html_file.write_text(page(title, body, extra_head=dash_css()))
    outputs["html"] = str(html_file)
    if not args.no_pdf:
        pdf_file = out_dir / "dashboard.pdf"
        outputs["pdf"] = str(pdf_file) if to_pdf(html_file, pdf_file) else \
            "no Chrome found — open index.html in a browser and print / save as PDF"
    if args.inline or pub.get("claude_artifact"):
        inline = args.inline or str(out_dir / "dashboard-artifact.html")
        Path(inline).write_text(page(title, body, fragment=True, extra_head=dash_css()))
        outputs["claude_artifact"] = inline
    for k, v in outputs.items():
        print(f"  {k}: {v}")
    print("DASHBOARD: " + json.dumps({"outputs": outputs}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
