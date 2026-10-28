#!/usr/bin/env python3
"""Build the ASDR project dashboard — one page that answers "where is this
project right now, when will it land, and what do you need from me?"
HTML + PDF, private, printable.

Usage:
  python3 build_dashboard.py [--out docs/dashboard] [--inline FILE] [--fragment]
                             [--no-pdf] [--title "<Project>"]
                             [--audience internal|client] [--brand brand.json]

--audience client (v3.7) writes docs/dashboard/client/index.html and
status-report.pdf: a branded status report for the client, built from the same
facts with the same status rule (it can never look better than the private
view). It leaves out agent activity, ASDR effort, git internals and local
paths, questions not marked --client in log_question.py, environments marked
"client": false or on localhost, links not marked "client": true, risks listed
in dashboard.json → client.hide_risks, and process records (critiques,
contracts, evaluation reports). Read it before sending it.

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
    ("Validation", "Idea validation", "docs/00a-idea-validation.md", "product-owner"),
    ("Validation", "Desk evidence", "docs/validation/desk-evidence.md", "product-owner"),
    ("Validation", "Panel roster", "docs/validation/panel/roster.json", "business-analyst"),
    ("Validation", "Persona walkthrough", "docs/validation/panel/walkthrough-summary.md", "panelist"),
    ("Validation", "Validation critique", "docs/critique-validation.md", "critic"),
    ("Validation", "Validation decision", "docs/decision-validation.md", "judge"),
    ("Discovery", "Product brief", "docs/01-product-brief.md", "product-owner"),
    ("Discovery", "Business case", "docs/01b-business-case.md", "product-owner"),
    ("Discovery", "Roadmap", "docs/00b-roadmap.md", "product-owner"),
    ("Discovery", "Requirements", "docs/02-requirements.md", "business-analyst"),
    ("Discovery", "Use cases", "docs/02b-use-cases.md", "business-analyst"),
    ("Discovery", "Feature list", "docs/02c-features.md", "product-manager"),
    ("Discovery", "Process flows", "docs/02d-process-flows.md", "product-manager"),
    ("Discovery", "Test cases", "docs/02e-test-cases.md", "business-analyst"),
    ("Discovery", "Parity list (existing systems)", "docs/02f-parity.md", "business-analyst"),
    ("Discovery", "Discovery critique", "docs/critique-discovery.md", "critic"),
    ("Discovery", "Discovery decision", "docs/decision-discovery.md", "judge"),
    ("Architecture", "Architecture options and decision", "docs/03c-architecture-options.md", "solution-architect"),
    ("Architecture", "Architecture", "docs/03-architecture.md", "solution-architect"),
    ("Architecture", "Services and contracts (microservices)", "docs/03e-services.md", "solution-architect"),
    ("Architecture", "Portability and cloud decision", "docs/03d-portability.md", "devops"),
    ("Architecture", "Design system (UI)", "docs/03b-design-system.md", "solution-architect"),
    ("Architecture", "Configurable decisions and settings", "docs/03f-configuration.md", "solution-architect"),
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
    ("Final gates", "Parity with the old system", "docs/parity-report.md", "compare_parity.py"),
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
OPTIONAL = {"docs/03b-design-system.md", "docs/04-agent-design.md", "docs/02f-parity.md", "docs/parity-report.md",
            "docs/03e-services.md", "docs/03d-portability.md"}

PHASES = [  # (key in progress.json, label, gate document, gate kind, weight for overall %)
    ("strategic", "Discovery & architecture", ["docs/decision-discovery.md", "docs/decision-architecture.md"], "judge verdicts", 30),
    ("planning", "Sprint planning", ["sprints.json"], "sprint plan", 5),
    ("execution", "Sprint execution", [], "sprints done", 55),
    ("final-gates", "Final gates", ["docs/09-risk-review.md"], "risk classification", 5),
    ("done", "Release", ["docs/10-release-notes.md"], "release notes", 5),
]


SKIPPED_PHASE_DOCS = {"discover": ("docs/decision-discovery.md", "docs/critique-discovery.md"),
                      "design": ("docs/decision-architecture.md", "docs/critique-architecture.md")}


def start_note(root: Path, path: str):
    """How a late start or a resumed earlier run explains a missing canonical document (v4.1):
    ("text", "passed" | "failed" | "skipped" | "neutral"), or None when the start does not explain it."""
    en = read_json(root / ".harness" / "entry.json", {})
    if not isinstance(en, dict):
        return None
    start, skipped = en.get("start"), en.get("skipped")
    rf = en.get("resumed_from")
    if start == "resume" and isinstance(rf, dict):          # a 4.0+ late start, resumed: keep what it skipped
        start, skipped = rf.get("start"), rf.get("skipped")
    skipped = skipped if isinstance(skipped, list) else []
    if start in ("design", "build", "release"):
        for ph in skipped:
            if path not in SKIPPED_PHASE_DOCS.get(ph, ()):
                continue
            intake = root / "docs" / "decision-intake.md"
            if not intake.is_file():
                return ("due: the intake review (decision-intake.md)", "skipped")
            v = verdict_of(intake)
            if v == "no-go":
                return ("intake review · no-go", "failed")
            prog = read_json(root / ".harness" / "progress.json", {})
            fresh = True
            if not isinstance(prog, dict) or prog.get("phase") in (None, "strategic"):
                # While the catch-up is open, a document written after the review is unreviewed (the start
                # chooser's rule). Later edits (setting tests, scope changes) go through their own gates.
                try:
                    import entry_point as _ep
                    surf = set(en.get("surfaces") or []) if isinstance(en.get("surfaces"), list) else set()
                    fresh = _ep.reviewed(root, ph, surf)
                except Exception:                             # noqa: BLE001 — no chooser: trust the file
                    fresh = True
            return ((f"covered by the intake review{' · ' + v if v else ''}", "passed") if fresh
                    else ("due: documents changed after the intake review", "skipped"))
    if en.get("start") == "resume" and isinstance(en.get("legacy_gaps"), list):
        for g in en["legacy_gaps"]:
            if not isinstance(g, dict) or g.get("path") != path:
                continue
            kind = g.get("kind") or ("gate" if g.get("gate") else "optional")
            if kind == "gate":
                return ("not in this run yet · needed before release", "skipped")
            if kind == "optional":
                return (f"not in this run (added in ASDR {g.get('introduced')})" if g.get("introduced")
                        else "not in this run (began on an earlier ASDR)", "neutral")
    return None


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

def classify_full(progress, pmap, facts, questions, open_risks, regressions, parity=None):
    """The fixed status rule. Returns (state, reasons, client_reasons): the
    same rule and the same state for both views; only the wording differs —
    the client view never names agents, attempts or internal files, and never
    shows a better state than the private one."""
    blocked, at_risk = [], []                    # (private wording, client wording)
    if progress.get("last_eval_result") == "teardown":
        blocked.append(("the last sprint evaluation ordered a teardown",
                        "a sprint failed its review and is being re-planned"))
    open_qs = [q for q in questions if q.get("status") == "open"]
    if open_qs:
        ext = sum(1 for q in open_qs if q.get("client"))
        blocked.append((f"{len(open_qs)} question(s) waiting on you",
                        "; ".join(x for x in [f"{ext} decision(s) waiting on you" if ext else "",
                                              "waiting on an internal decision" if len(open_qs) > ext else ""] if x)))
    if progress.get("attempt", 0) >= 4:
        at_risk.append((f"{progress.get('sprint')} is on attempt {progress.get('attempt')}",
                        "the current sprint has needed several rounds of fixes"))
    tr = (facts or {}).get("test_runs") or {}
    if tr:
        if tr.get("status") == "failed":
            at_risk.append(("the latest test run failed", "the latest automated test run found failures, being fixed"))
        a = tr.get("a11y") or {}
        if a.get("critical", 0) or a.get("serious", 0):
            at_risk.append(("serious or critical accessibility violations", "accessibility problems found, being fixed"))
        if tr.get("commit_matches_head") is False:
            at_risk.append(("the latest test run is not on the current commit",
                            "the tests have not yet been re-run on the latest changes"))
        for name, m in (tr.get("metrics") or {}).items():
            if m.get("within_budget") is False:
                at_risk.append((f"measurement '{name}' is over budget", f"a performance target ({name}) is not met yet"))
    flows = (pmap or {}).get("flows") or {}
    title = lambda k: flows.get(k, {}).get("title") or k
    failing_must = sorted(k for k, v in flows.items() if v.get("status") == "failing" and v.get("priority") == "must")
    failing_other = sorted(k for k, v in flows.items() if v.get("status") == "failing" and v.get("priority") != "must")
    if failing_must:
        at_risk.append((f"must-have journey(s) failing: {', '.join(failing_must)}",
                        f"must-have journey(s) failing their end-to-end test: {'; '.join(title(k) for k in failing_must)}"))
    if failing_other:
        at_risk.append((f"journey(s) failing: {', '.join(failing_other)}",
                        f"journey(s) failing their end-to-end test: {'; '.join(title(k) for k in failing_other)}"))
    if regressions:
        at_risk.append((f"regression: {', '.join(regressions)} worked before and does not now",
                        f"something that worked before does not now: {'; '.join(title(k) for k in regressions)}"))
    pc = (parity or {}).get("counts") or {}
    if pc.get("differs"):
        bad = sorted(k for k, v in (parity.get("items") or {}).items() if v.get("status") in ("differs", "unstable"))
        at_risk.append((f"{pc['differs']} kept behaviour(s) differ from the old system: {', '.join(bad)}",
                        f"{pc['differs']} behaviour(s) of your current system differ in the new build (see Quality)"))
    if (pmap or {}).get("errors"):
        at_risk.append((f"{pmap['errors']} product-map error(s)",
                        "gaps between features, journeys and tests are being closed"))
    high = [r for r in open_risks if str(r.get("severity", "")).lower() in ("critical", "high")]
    if high:
        at_risk.append((f"{len(high)} open high/critical risk(s)", f"{len(high)} open high or critical risk(s) (see Risks)"))
    if blocked:
        state, rs = "blocked", blocked + at_risk
    elif at_risk:
        state, rs = "at risk", at_risk
    else:
        return "on track", ["no blocking or risk rule triggered"], ["no blocking or risk rule triggered"]
    return state, [a for a, _ in rs], [b for _, b in rs]


def classify(progress, pmap, facts, questions, open_risks, regressions, parity=None):
    state, reasons, _ = classify_full(progress, pmap, facts, questions, open_risks, regressions, parity)
    return state, reasons


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
        # a journey that was ever proven stays "proven" in the snapshot, so a regression keeps
        # showing on every rebuild (private or client) until the journey is proven again
        snap = {k: ("proven" if prev.get(k) == "proven" else v.get("status")) for k, v in flows.items()}
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps({"ts": dt.datetime.now(UTC).isoformat(timespec="seconds"),
                                         "flows": snap}, indent=1))
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


def agent_cost(h: Path) -> dict:
    """Tokens and time per agent run (log_agent_run.py) against the budget (estimate_run.py)."""
    rows = jsonl(h / "agent-runs.jsonl")
    by = {}
    for r in rows:
        b = by.setdefault(r.get("agent") or "?", [0, 0, 0.0])
        b[0] += 1
        b[1] += int(r.get("tokens") or 0)
        b[2] += float(r.get("seconds") or 0)
    out = {"runs": len(rows), "tokens": sum(v[1] for v in by.values()),
           "hours": round(sum(v[2] for v in by.values()) / 3600, 1), "by_agent": by}
    budget = read_json(h / "budget.json", {})
    if budget.get("tokens"):
        out["budget"] = budget
        out["pct"] = round(100 * out["tokens"] / budget["tokens"], 1)
    return out


def cloud_state(h: Path, now: dt.datetime) -> dict:
    """v3.8: architecture and portability decisions, test environments still running, cloud parity."""
    envs = {}
    for ev in jsonl(h / "cloud-envs.jsonl"):
        if ev.get("event") == "create":
            envs[ev.get("name")] = ev
        elif ev.get("event") == "destroyed":
            envs.pop(ev.get("name"), None)
    running = []
    for ev in envs.values():
        t0 = _ts(ev.get("ts"))
        exp = t0 + dt.timedelta(hours=float(ev.get("ttl_hours") or 8)) if t0 else None
        running.append({**ev, "expires": exp, "overdue": bool(exp and now > exp)})
    return {"arch": read_json(h / "architecture.json", {}), "port": read_json(h / "portability.json", {}),
            "services": read_json(h / "services.json", {}), "cloud": read_json(h / "cloud.json", {}),
            "parity": read_json(h / "cloud-parity.json", {}), "envs": running}


def run_setup(h: Path, now: dt.datetime) -> dict:
    """v4.0: where the run started, the model plan, and the configurable decisions (tolerates bad files)."""
    def obj(x):
        return x if isinstance(x, dict) else {}
    entry, models, conf = (obj(read_json(h / n, {})) for n in ("entry.json", "models.json", "configuration.json"))
    settings = [x for x in (conf.get("setting_list") or []) if isinstance(x, dict)] \
        if isinstance(conf.get("setting_list"), list) else []
    conf = {**conf, "setting_list": settings}
    today = now.date().isoformat()
    overdue = [x for x in settings if isinstance(x.get("review_by"), str) and x["review_by"] < today]
    by_model = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import model_plan as _mp
        resolved = {r: _mp.role_model(r, models) for r in _mp.ROLES} if models.get("plan") else {}
    except Exception:          # the dashboard never fails because of this table
        resolved = {r: m for r, m in obj(models.get("map")).items() if isinstance(m, str)}
    for _role, m in resolved.items():
        by_model[m] = by_model.get(m, 0) + 1
    return {"entry": entry, "models": models, "by_model": by_model, "conf": conf, "overdue": overdue}


def gather(root: Path, now: dt.datetime) -> dict:
    """Read every input once; both views render from this."""
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
    parity = read_json(H / "parity.json", {}) if (root / "docs" / "02f-parity.md").is_file() else {}
    state, reasons, client_reasons = classify_full(progress, pmap, facts, questions, risks, regs, parity)
    cost = agent_cost(H)
    cloud = cloud_state(H, now)
    setup = run_setup(H, now)
    if setup["overdue"]:
        reasons.append("setting(s) past their review date: " + ", ".join(str(x.get("id", "?")) for x in setup["overdue"]))
        client_reasons.append("a product setting is past its agreed review date")
        if state == "on track":
            state = "at risk"
    over = [x["name"] for x in cloud["envs"] if x["overdue"]]
    if over:
        reasons.append(f"test environment past its time-to-live, still costing money: {', '.join(over)}")
        if state == "on track":
            state = "at risk"
    cp = cloud["parity"]
    if cp and cp.get("ok") is False:
        reasons.append(f"the cloud run differs from the local run ({cp.get('broken', 0)} failing, "
                       f"{cp.get('missing', 0)} missing)")
        client_reasons.append("the cloud test environment does not yet behave like the local build")
        if state == "on track":
            state = "at risk"
    if cost.get("pct", 0) >= 100:          # internal only: the client view never shows ASDR's own cost
        reasons.append(f"over the {cost['budget'].get('rigor') or ''} token budget: {cost['pct']}% used".replace("  ", " "))
        if state == "on track":
            state = "at risk"
    default_reason = "no blocking or risk rule triggered"
    if len(reasons) > 1:
        reasons = [x for x in reasons if x != default_reason]
    if len(client_reasons) > 1:
        client_reasons = [x for x in client_reasons if x != default_reason]
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
    return dict(progress=progress, sprints=sprints, pmap=pmap, facts=facts, metrics=metrics, trace=trace, cfg=cfg,
                traces=traces, clock=clock, history=history, questions=questions, risks=risks, regs=regs, times=times,
                fc=fc, fhist=fhist, parity=parity, state=state, reasons=reasons, client_reasons=client_reasons, tr=tr,
                flows=flows, features=features, counts=counts, project=project, cur=cur, ci=ci,
                done_sprints=done_sprints, live_sprints=live_sprints, overall=overall, cost=cost, cloud=cloud, setup=setup)


def feature_status(features, flows, sprints) -> dict:
    """planned → in progress (its sprint is active) → delivered (sprint passed) → verified (journeys proven)."""
    flow_sprint = {}
    for s in sprints:
        for f_ in s.get("flows") or []:
            flow_sprint.setdefault(f_, []).append(s)
    out = {}
    for fid, f in features.items():
        fl = f.get("flows") or []
        sp_ = [s for x in fl for s in flow_sprint.get(x, [])]
        if fl and all(flows.get(x, {}).get("status") == "proven" for x in fl):
            out[fid] = ("verified", "passed", sp_)
        elif any(s.get("status") == "done" for s in sp_):
            out[fid] = ("delivered", "passed", sp_)
        elif any(s.get("status") == "active" for s in sp_):
            out[fid] = ("in progress", "skipped", sp_)
        else:
            out[fid] = ("planned", "neutral", sp_)
    return out


def build(root: Path, now: dt.datetime, ctx: "dict | None" = None) -> str:
    c = ctx or gather(root, now)
    (progress, sprints, pmap, facts, metrics, cfg, traces, history, questions, risks, regs, times, fc, fhist, parity,
     state, reasons, tr, flows, features, counts, project, cur, ci, done_sprints, live_sprints, overall) = (
        c[k] for k in ("progress", "sprints", "pmap", "facts", "metrics", "cfg", "traces", "history", "questions", "risks",
                       "regs", "times", "fc", "fhist", "parity", "state", "reasons", "tr", "flows", "features", "counts",
                       "project", "cur", "ci", "done_sprints", "live_sprints", "overall"))

    out = []
    # 1 status and progress
    nxt = progress.get("awaiting")
    out.append(
        f'<main class="wrap"><header class="stack"><span class="eyebrow">{e(project)} · ASDR project dashboard</span>'
        f'<div class="row" style="justify-content:space-between"><h1>Where the project is</h1>'
        f'<span class="pill state {STATE_PILL[state]}">{e(state.upper())}</span></div>'
        f'<p>Phase <b>{e(dict((p[0], p[1]) for p in PHASES).get(cur, cur))}</b>'
        f'{" · active sprint <b>" + e(progress.get("sprint")) + "</b>" if progress.get("sprint") else ""}'
        f'{" · waiting on: <b>" + e(nxt) + "</b>" if nxt else ""} · rigor {e(progress.get("rigor") or "standard")}'
        f'{" · started at " + e(((c.get("setup") or {}).get("entry") or {}).get("label") or "") if ((c.get("setup") or {}).get("entry") or {}).get("label") else ""}'
        f'{" · model plan " + e(((c.get("setup") or {}).get("models") or {}).get("plan") or "") if ((c.get("setup") or {}).get("models") or {}).get("plan") else ""}</p>'
        f'<div class="stack" style="gap:6px"><div class="row" style="justify-content:space-between">'
        f'<span class="eyebrow">Overall progress</span><span class="mono">{overall}%</span></div>'
        f'<div class="progress" role="progressbar" aria-valuenow="{overall}" aria-valuemin="0" aria-valuemax="100"><span style="width:{overall}%"></span></div>'
        f'<span class="muted" style="font-size:.8rem">Discovery &amp; architecture 30% · planning 5% · sprints 55% (by sprints done) · final gates 5% · release 5%.</span></div>'
        f'<p class="muted">Why {e(state)}: {e("; ".join(reasons))}.</p>'
        f'<p class="muted" style="font-size:.8rem">Generated {e(when(now))} from the project files — refreshed at the end of every phase and sprint, and on request.</p>'
        '<ul class="toc">' + "".join(f'<li><a href="#{a}">{e(b)}</a></li>' for a, b in [
            ("glance", "At a glance"), ("phases", "Phases"), ("setup", "Set-up & settings"), ("forecast", "Delivery"), ("roadmap", "Roadmap"),
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
            if k == "strategic" and any(v is None for _, v in vs) and (root / "docs/decision-intake.md").is_file():
                vs.append(("decision-intake.md", verdict_of(root / "docs/decision-intake.md")))
            gate = "; ".join(f"{n}: {v}" for n, v in vs if v) or "—"
            fin = max((mtime(root / g) for g in gates if (root / g).exists()), default=None) if st == "done" else None
        prow.append([e(lbl), pill(st, {"done": "passed", "current": "skipped", "upcoming": "neutral"}[st]),
                     e(gkind), e(gate), f'<span class="mono">{e(when(fin)) if fin else "—"}</span>'])
    out.append(section("phases", "Phases and gates", table(["Phase", "State", "Gate", "Gate result", "Finished"], prow)))

    # 3b run set-up and settings (v4.0)
    su = c.get("setup") or {}
    en, md, cf = su.get("entry") or {}, su.get("models") or {}, su.get("conf") or {}
    srows = []
    if en.get("start"):
        srows.append(["Start point", e(en.get("label")) + ("" if en.get("followed_recommendation")
                      else f' <span class="muted">(ASDR recommended {e(en.get("recommended"))})</span>'),
                      e(f"chosen by {en.get('chosen_by') or 'user'}; skipped: {', '.join(en.get('skipped') or []) or 'nothing'}")])
    if md.get("plan"):
        srows.append(["Model plan", e(f"{md['plan']} (top = {md.get('top', 'opus')})"),
                      e(", ".join(f"{k}: {v} roles" for k, v in sorted((su.get("by_model") or {}).items())))])
    if cf:
        bt = cf.get("by_type") or {}
        srows.append(["Configurable decisions", e(f"{cf.get('decisions', 0)} decided"),
                      e(f"{bt.get('configure', 0)} configure, {bt.get('prepare', 0)} prepare, {bt.get('decide-once', 0)} decide-once; "
                        f"{cf.get('settings', 0)} settings")])
    crow = [[f'<span class="mono">{e(x.get("id"))}</span>', f'<span class="mono">{e(x.get("key"))}</span>', e(x.get("default")),
             e(x.get("who")), e(x.get("owner")),
             pill(x.get("review_by") or "—", "failed" if x in (su.get("overdue") or []) else "neutral"),
             e(", ".join(x.get("tests") or []))] for x in (cf.get("setting_list") or [])]
    out.append(section("setup", "Run set-up and settings",
                       table(["Item", "Value", "Detail"], srows, "Set at Phase 0: entry_point.py and model_plan.py.")
                       + "<h3>Settings built as configurable</h3>"
                       + table(["Setting", "Key", "Default", "Who can change it", "Owner", "Review by", "Tests"], crow,
                               "No configurable settings (docs/03f-configuration.md)."),
                       "A setting past its review date turns the status at risk and fails the release gate: keep it with "
                       "a new date, make the value permanent, or remove it."))

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
    ] + ([(f"{(parity.get('counts') or {}).get('same', 0)}/{(parity.get('counts') or {}).get('keep', 0)}",
           "kept behaviours match the old system")] if parity else []))
    par_icon = {"same": "passed", "differs": "failed", "unstable": "failed", "changed": "neutral",
                "dropped": "neutral", "change not seen": "skipped", "no baseline": "skipped", "not captured": "skipped"}
    par_rows = [[f'<span class="mono">{e(k)}</span>', e(v.get("behaviour")),
                 e(v.get("decision")) + (f'<br><span class="muted">{e(v.get("approval"))}</span>' if v.get("approval") else ""),
                 pill(v.get("status") or "—", par_icon.get(v.get("status"), "neutral"))]
                for k, v in sorted((parity.get("items") or {}).items())]
    par_html = ("<h3>Parity with the old system</h3>"
                + f'<p class="muted">Old system run {e((parity.get("old") or {}).get("run_id") or "—")} · new build run '
                  f'{e((parity.get("new") or {}).get("run_id") or "—")} · docs/parity-report.md</p>'
                + table(["ID", "Behaviour kept", "Decision", "Result"], par_rows)) if parity else ""
    out.append(section("quality", "Quality",
                       qk + '<div class="two"><div class="stack"><h3>Journeys</h3>'
                       + table(["Flow", "Journey", "Priority", "Status", "Journey test"], fl_rows, "No process flows yet.")
                       + '</div><div class="stack"><h3>Coverage of every testable item</h3>'
                       + table(["Kind", "Items", "Named by a test", "Reached by a passing test"], cov_rows, "No coverage data yet.")
                       + '</div></div>' + ("<h3>Measurements</h3>" + table(["Measure", "Value", "Budget", "Result"], meas) if meas else "")
                       + par_html))

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
        elif start_note(root, path):
            st, upd = pill(*start_note(root, path)), "—"
        else:
            reached = [k for k, *_ in PHASES].index({"Validation": "strategic", "Discovery": "strategic", "Architecture": "strategic", "Planning": "planning",
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
    cl = c.get("cloud") or {}
    for x in cl.get("envs") or []:
        left = "past its time-to-live" if x["overdue"] else (f"until {x['expires']:%d %b %H:%M} UTC" if x.get("expires") else "")
        erows.append([e(f"{x.get('name')} (temporary test, {str(x.get('cloud', '')).upper()})"),
                      f'<a href="{e(x.get("url"))}">{e(x.get("url"))}</a>' if x.get("url") else "—",
                      e(f"approved by {x.get('approved_by')}; destroy: {x.get('stack') or 'see devops notes'}"),
                      "—", "—", pill(left or "running", "failed" if x["overdue"] else "skipped")])
    facts_line = []
    ar, po, sv = cl.get("arch") or {}, cl.get("port") or {}, cl.get("services") or {}
    if ar.get("style"):
        facts_line.append(f"architecture: <b>{e(ar['style'])}</b>" + (f" ({len(sv.get('services') or [])} services, "
                          f"{len(sv.get('contracts') or [])} contracts)" if sv.get("services") else ""))
    if po.get("strategy"):
        facts_line.append(f"portability: <b>{e(po['strategy'])} · {e(po.get('title') or '')}</b> on "
                          f"{e(', '.join(po.get('production_clouds') or []) or '—')}")
    tcl = (cl.get("cloud") or {}).get("test_cloud")
    if tcl:
        facts_line.append(f"test cloud: <b>{e(tcl)}</b>")
    cp = cl.get("parity") or {}
    if cp:
        facts_line.append("cloud parity: " + pill("same as local" if cp.get("ok") else "differs", "passed" if cp.get("ok") else "failed"))
    head = ('<p>' + " · ".join(facts_line) + '</p>') if facts_line else ""
    out.append(section("environments", "Environments", head + table(
        ["Environment", "URL", "Used for", "Deployed version / branch", "Test logins (roles)", "Reachable now"], erows,
        "No environments listed. Add dev, test, staging, UAT and production to .harness/dashboard.json → environments."),
        "Test logins show role names only — credentials stay in environment variables and are never written here. "
        "Temporary test environments come from cloud_env.py; one past its time-to-live is still costing money."))

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
    cost = c.get("cost") or {}
    if cost.get("runs"):
        b = cost.get("budget") or {}
        eff += kpis([(f"{cost['tokens'] / 1e6:.1f}M", "tokens used"),
                     (f"{cost['pct']}%" if "pct" in cost else "—", f"of the {b.get('rigor', '')} budget".strip()),
                     (f"{cost['hours']}", "agent-hours"), (cost["runs"], "logged agent runs")])
        eff += "<h3>Tokens by role</h3>" + bars(
            [(k, round(v[1] / 1e6, 2)) for k, v in sorted(cost["by_agent"].items(), key=lambda kv: -kv[1][1])][:12], "M")
    out.append(section("effort", "ASDR effort", eff + "<h3>By role</h3>" + bars([(k, v) for k, v in list(inv.items())[:12]], "runs"),
                       "From run_metrics.py and the agent-run log. Where the time and tokens went, so the next run "
                       "can change something."))

    out.append('<footer>Generated by build_dashboard.py from the project files. Single source of truth — do not hand-edit; '
               'rerun the script. Private working view. To print or save as PDF, use dashboard.pdf in the same folder, '
               'or print this page from a browser.</footer></main>')
    return "\n".join(out)


# ── client view: the same facts, for the client, in the consultant's brand ────

CLIENT_DOCS = {  # canonical documents a client receives; process records (critiques, contracts, …) stay private
    "docs/01-product-brief.md", "docs/01b-business-case.md", "docs/00b-roadmap.md", "docs/02-requirements.md",
    "docs/02b-use-cases.md", "docs/02c-features.md", "docs/02d-process-flows.md", "docs/02e-test-cases.md",
    "docs/02f-parity.md", "docs/03c-architecture-options.md", "docs/03-architecture.md", "docs/03d-portability.md",
    "docs/03e-services.md", "docs/03b-design-system.md", "docs/04-agent-design.md",
    "docs/05-security.md", "docs/06-devops.md", "docs/08-e2e-testing.md", "docs/parity-report.md",
    "docs/09-product-integrity.md", "docs/09-risk-review.md", "CHANGELOG.md", "docs/10-release-notes.md",
    "docs/10-release-checklist.md", "docs/10-post-release-monitoring.md",
}


AGENT_ROLES = {"ai-architect", "business-analyst", "critic", "devops", "documentation", "evaluator", "generator", "judge",
               "planner", "product-integrity-qa", "product-manager", "product-owner", "release-manager", "risk-manager",
               "security-compliance", "solution-architect", "stage-planner", "stage-qa", "orchestrator"}


def owner_for_client(owner) -> str:
    """Risk owners are often ASDR roles; a client sees the delivery team, not the agent."""
    o = str(owner or "").strip()
    return "Delivery team" if not o or o.lower() in AGENT_ROLES else o


def client_css(b) -> str:
    from build_assess_report import css as brand_css
    c, f = b["colors"], b["fonts"]
    return (brand_css(b) + f"""
:root {{ --accent:{c['blue']}; --pass:{c['deep']}; --fail:{c['ink']}; --skip:{c['graphite']}; --muted:{c['slate']};
  --line:{c['hairline']}; --fg:{c['ink']}; --hl:{c['graphite']}; --mono:{f['meta']}; --surface:{c['tint']}; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); border-top:1px solid var(--hair); margin:12px 0; }}
.kpis div {{ padding:10px 12px 10px 0; display:grid; gap:4px; min-width:0; border-bottom:1px solid var(--hair); }}
.kpis b {{ font:600 13pt/1.2 var(--meta); overflow-wrap:anywhere; }}
.kpis span {{ font:500 7.5pt/1.3 var(--meta); letter-spacing:.1em; text-transform:uppercase; color:var(--slate); }}
.st {{ font:600 7.5pt/1 var(--meta); letter-spacing:.06em; text-transform:uppercase; padding:3px 6px; display:inline-block;
  border:1px solid var(--hair); color:var(--graphite); white-space:nowrap; }}
.st.passed {{ color:var(--blue); border-color:var(--blue); }}
.st.failed {{ color:var(--paper); background:var(--ink); border-color:var(--ink); }}
.st.skipped {{ color:var(--ink); border-color:var(--ink); }}
.progress {{ height:8px; background:var(--hair); }} .progress span {{ display:block; height:100%; background:var(--blue); }}
.legend {{ display:flex; flex-wrap:wrap; gap:6px 16px; font:8pt var(--meta); color:var(--slate); }}
.legend i {{ display:inline-block; width:12px; height:10px; margin-right:5px; vertical-align:-1px; }}
.q {{ border-top:1px solid var(--hair); padding:10px 0; display:grid; gap:3px; break-inside:avoid; }}
.q.open {{ border-left:4px solid var(--blue); padding-left:12px; }}
.q .meta {{ font:8pt var(--meta); color:var(--slate); }}
svg {{ max-width:100%; height:auto; }}
@media (max-width:640px) {{ .kpis {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
@media print {{ .kpis div, svg, .legend {{ break-inside:avoid; }} }}
""")


def build_client(root: Path, now: dt.datetime, brand: dict, ctx: dict) -> str:
    c = ctx
    cfg, fc, flows, features, sprints, times = c["cfg"], c["fc"], c["flows"], c["features"], c["sprints"], c["times"]
    tr, counts, parity, state = c["tr"], c["counts"], c["parity"], c["state"]
    ccfg = cfg.get("client") or {}
    client = ccfg.get("name") if ccfg.get("name") and "<" not in ccfg["name"] else "the client"
    hidden = set(ccfg.get("hide_risks") or [])
    est = '<span class="est">estimate</span>'
    sec = [0]

    def h2(title):
        sec[0] += 1
        return f'<h2><span class="no">{sec[0]:02d} ·</span>{e(title)}</h2>'

    def st(text, cls):
        return f'<span class="st {cls}">{e(text)}</span>'

    def kp(items):
        return '<div class="kpis">' + "".join(f"<div><b>{v}</b><span>{e(k)}</span></div>" for v, k in items) + "</div>"

    from build_assess_report import tbl
    state_cls = {"on track": "good", "at risk": "weak", "blocked": "crit"}[state]
    ref = ccfg.get("reference") if ccfg.get("reference") and "<" not in str(ccfg.get("reference")) else "—"
    contact = ccfg.get("contact") if ccfg.get("contact") and "<" not in str(ccfg.get("contact")) else (brand.get("email") or "—")
    fields = [("Date", now.strftime("%d %b %Y")), ("Reference", ref), ("Status", state.upper()), ("Contact", contact)]
    out = ['<article class="doc">',
           '<section class="cover"><div class="lockup">'
           f'<div class="mono-sq" aria-hidden="true">{e(brand.get("monogram"))}</div>'
           f'<span class="name">{e(brand.get("lockup"))}</span></div>'
           f'<div class="title"><span class="eyebrow">Project status report</span>'
           f'<h1>{e(c["project"])}: where the project stands</h1>'
           f'<span class="for">Prepared for {e(client)}</span></div>'
           '<dl class="fields">' + "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in fields) + "</dl></section>"]

    # 01 summary
    fstat = feature_status(features, flows, sprints)
    verified = sum(1 for v in fstat.values() if v[0] == "verified")
    t = tr.get("totals") or {}
    exp = (f'{e(day(fc["expected"]))} ± {e(fmt_span(fc["sd_h"]))}' if fc["available"] else "after two sprints")
    out.append(h2("Summary"))
    out.append(f'<p><span class="r {state_cls}">{e(state)}</span> &nbsp;{e("; ".join(c["client_reasons"]).capitalize())}.</p>')
    out.append(f'<div class="progress" role="progressbar" aria-valuenow="{c["overall"]}" aria-valuemin="0" aria-valuemax="100">'
               f'<span style="width:{c["overall"]}%"></span></div>')
    out.append(kp([(f'{c["overall"]}%', "overall progress"), (exp, "expected delivery (estimate)"),
                   (f'{c["done_sprints"]}/{len(c["live_sprints"])}', "sprints done"),
                   (f"{verified}/{len(features)}" if features else "—", "features verified"),
                   (f"{sum(1 for v in flows.values() if v.get('status') == 'proven')}/{len(flows)}" if flows else "—", "journeys proven"),
                   (f"{t.get('passed', 0)}/{t.get('tests', 0)}" if t else "—", "automated tests passing"),
                   (len([r for r in c["risks"] if r["id"] not in hidden]), "open risks"),
                   (sum(1 for q in c["questions"] if q.get("client") and q.get("status") == "open"), "decisions waiting on you")]))
    if fc["available"]:
        out.append('<div class="callout"><span class="eyebrow">Expected delivery · estimate</span>'
                   f'<p style="font-size:14pt"><b>{e(day(fc["expected"]))}</b> ± {e(fmt_span(fc["sd_h"]))}</p>'
                   f'<p>95% range {e(span_fmt(*fc["r95"]))}. Forecast from the measured time of {fc["n"]} finished sprints; '
                   'it narrows as each sprint finishes. Not a fixed date.</p></div>')
    else:
        out.append('<div class="callout"><span class="eyebrow">Expected delivery · estimate</span>'
                   '<p>A delivery date is given once two sprints have finished: before then it would be a guess.</p></div>')

    # 02 phases
    prow = []
    for i, (k, lbl, gates, gkind, w) in enumerate(PHASES):
        s_ = "done" if i < c["ci"] or c["cur"] == "done" else ("current" if i == c["ci"] else "upcoming")
        fin = None
        if s_ == "done":
            fin = (max((t_.get("done") for t_ in times.values() if t_.get("done")), default=None) if k == "execution"
                   else max((mtime(root / g) for g in gates if (root / g).exists()), default=None))
        prow.append([e(lbl), st(s_, {"done": "passed", "current": "skipped", "upcoming": ""}[s_]),
                     f'<span class="mono">{e(day(fin)) if fin else "—"}</span>'])
    out.append(h2("Phases") + tbl(["Phase", "State", "Finished"], prow))

    # 03 delivery forecast
    out.append(h2("Delivery forecast"))
    if fc["available"]:
        rows = [[f'<span class="mono">{e(s.get("id"))}</span>', e(s.get("goal") or ""), e(day(d)) + " " + est,
                 f'<span class="mono">± {e(fmt_span(sdi))}</span>'] for s, d, sdi in fc["per_sprint"]]
        out.append(kp([(e(span_fmt(*fc["r68"])), "68% range"), (e(span_fmt(*fc["r95"])), "95% range"),
                       (f'{fc["pending"]}', "sprints to go"), (e(fc["confidence"]), "confidence")])
                   + "<h3>When each remaining sprint should finish</h3>"
                   + tbl(["Sprint", "What you will be able to do", "Expected finish", "± 1 SD"], rows)
                   + drift_chart(c["fhist"])
                   + f'<p class="muted">How this is worked out: the finished sprints took {fc["mean_h"]:.1f} hours each on '
                     f'average from one finish to the next (so waiting time is included), varying by {fc["sd_sprint_h"]:.1f} hours. '
                     'The ± allows for that variation and for how few sprints have been measured so far. It assumes the '
                     'remaining sprints are similar in size and excludes the final checks and release.</p>')
    else:
        out.append(f'<p class="muted">No date yet: {fc["done"]} sprint(s) finished, {fc["pending"]} to go. A forecast with an '
                   'honest margin needs at least two measured sprints.</p>')

    # 04 roadmap
    rm = read_roadmap(root)
    srows = [[f'<span class="mono">{e(s.get("id"))}</span>', e(s.get("goal") or ""),
              st(s.get("status") or "pending", {"done": "passed", "active": "skipped", "torn-down": "failed"}.get(s.get("status"), "")),
              f'<span class="mono">{e(day(times.get(s.get("id"), {}).get("start")) if times.get(s.get("id"), {}).get("start") else "—")}</span>',
              f'<span class="mono">{e(day(times.get(s.get("id"), {}).get("done")) if times.get(s.get("id"), {}).get("done") else "—")}</span>']
             for s in sprints if s.get("status") != "torn-down"]
    out.append(h2("Roadmap") + gantt([s for s in sprints if s.get("status") != "torn-down"], times, fc, now)
               + ("<h3>Product roadmap</h3>" + tbl(["Horizon", "Milestone", "Outcomes", "Timeframe"],
                  [[e(r["horizon"]), e(r["milestone"]), e(r["outcomes"]), e(r["timeframe"])] for r in rm]) if rm else "")
               + "<h3>Sprints</h3>" + tbl(["Sprint", "What a user can do after it", "Status", "Started", "Finished"], srows))

    # 05 features
    frows = [[f'<span class="mono">{e(fid)}</span>', e(f.get("name")), e(f.get("personas") or ""),
              e((f.get("priority") or "").title()), e(f.get("release") or ""), st(fstat[fid][0], fstat[fid][1])]
             for fid, f in sorted(features.items())]
    out.append(h2("Features") + tbl(["ID", "Feature", "Who uses it", "Priority", "Release", "Status"], frows)
               + '<p class="muted">Planned → in progress → delivered (its sprint passed review) → verified (every journey it is '
                 'part of passed its end-to-end test on the latest run).</p>')

    # 06 quality
    a = tr.get("a11y") or {}
    jrows = [[e(v.get("title") or k), e((v.get("priority") or "").title()),
              st(v.get("status") or "pending", {"proven": "passed", "failing": "failed"}.get(v.get("status"), ""))]
             for k, v in sorted(flows.items())]
    meas = [[e(n), f'<span class="mono">{e(m.get("value"))} {e(m.get("unit") or "")}</span>',
             f'<span class="mono">{e(m.get("budget") if m.get("budget") is not None else "—")}</span>',
             st("within target" if m.get("within_budget") else ("over target" if m.get("within_budget") is False else "no target"),
                "passed" if m.get("within_budget") else ("failed" if m.get("within_budget") is False else ""))]
            for n, m in (tr.get("metrics") or {}).items()]
    qhtml = kp([(f"{t.get('passed', 0)}/{t.get('tests', 0)}" if t else "—", "automated tests passing"),
                (f"{counts.get('items_executed', 0)}/{counts['items']}" if counts.get("items") else "—", "documented items tested"),
                (f"{a.get('critical', 0) + a.get('serious', 0)}" if a else "—", "accessibility blockers"),
                (len(c["regs"]), "things that worked before and do not now")])
    qhtml += "<h3>End-to-end journeys</h3>" + tbl(["Journey", "Priority", "Result"], jrows)
    if meas:
        qhtml += "<h3>Measured targets</h3>" + tbl(["Measure", "Value", "Target", "Result"], meas)
    if parity:
        pc = parity.get("counts") or {}
        prow2 = [[f'<span class="mono">{e(k)}</span>', e(v.get("behaviour")),
                  e(v.get("decision")) + (f'<br><span class="muted">{e(v.get("approval"))}</span>' if v.get("approval") else ""),
                  st(v.get("status") or "—", {"same": "passed", "differs": "failed", "unstable": "failed"}.get(v.get("status"), ""))]
                 for k, v in sorted((parity.get("items") or {}).items())]
        qhtml += (f"<h3>Your current system’s behaviour, kept</h3><p>{pc.get('same', 0)} of {pc.get('keep', 0)} behaviours you "
                  "rely on today were compared with your current system and match. Changes are listed with who approved them.</p>"
                  + tbl(["ID", "Behaviour", "Decision", "Result"], prow2))
    out.append(h2("Quality") + qhtml)

    # 07 risks
    rrows = [[f'<span class="mono">{e(r["id"])}</span>', e(r["risk"]), e(r["severity"]), e(owner_for_client(r["owner"])),
              e(r["mitigation"])] for r in c["risks"] if r["id"] not in hidden]
    out.append(h2("Risks") + tbl(["ID", "Risk", "Severity", "Owner", "What is being done"], rrows))

    # 08 decisions
    cq = sorted([q for q in c["questions"] if q.get("client")], key=lambda q: q.get("ts") or "", reverse=True)
    waiting = [q for q in cq if q.get("status") == "open"]
    answered = [q for q in cq if q.get("status") != "open"]
    dh = "<h3>Waiting on you</h3>" + ("".join(
        f'<div class="q open"><div><b>{e(q.get("question"))}</b></div><div class="meta">{e(q.get("id"))} · asked {e(day(_ts(q.get("ts"))))}</div></div>'
        for q in waiting) or '<p class="muted">Nothing is waiting on you.</p>')
    dh += "<h3>Decisions you have made</h3>" + ("".join(
        f'<div class="q"><div><b>{e(q.get("question"))}</b></div><div>{e(q.get("answer"))}</div>'
        f'<div class="meta">{e(q.get("id"))} · {e(day(_ts(q.get("ts"))))}</div></div>' for q in answered)
        or '<p class="muted">None recorded yet.</p>')
    adrs = sorted((root / "docs/adr").glob("*.md")) if (root / "docs/adr").is_dir() else []
    if adrs:
        dh += "<h3>Architecture decisions</h3>" + tbl(["Decision", "Date"], [
            [e(next((ln.lstrip("# ").strip() for ln in p_.read_text(errors="ignore").splitlines() if ln.startswith("#")), p_.stem)),
             f'<span class="mono">{e(day(mtime(p_)))}</span>'] for p_ in adrs])
    out.append(h2("Decisions and what we need from you") + dh)

    # 09 deliverables
    drows = []
    for ph, name, path, _owner in CANON:
        if path not in CLIENT_DOCS:
            continue
        p_ = root / path
        if p_.exists():
            s_, upd = st("ready", "passed"), day(mtime(p_))
        elif path in OPTIONAL:
            continue
        elif start_note(root, path):
            _txt, kind = start_note(root, path)
            if kind == "neutral":
                continue
            s_, upd = (st("covered by the review", "passed") if kind == "passed" else st("outstanding", "skipped")), "—"
        else:
            reached = [k for k, *_ in PHASES].index({"Validation": "strategic", "Discovery": "strategic", "Architecture": "strategic", "Planning": "planning",
                                                       "Final gates": "final-gates", "Release": "done"}[ph]) < c["ci"]
            s_, upd = (st("outstanding", "skipped") if reached else st("not yet", "")), "—"
        drows.append([e(ph), e(name), s_, f'<span class="mono">{e(upd)}</span>'])
    man = root / "docs/manuals"
    vers = sorted(x.name for x in man.iterdir() if x.is_dir() and re.match(r"^\d", x.name)) if man.is_dir() else []
    if vers:
        drows.append([e("Release"), e("User manuals (HTML + PDF)"), st("ready", "passed"), f'<span class="mono">{e(", ".join(vers))}</span>'])
    trd = root / "docs/test-reports"
    labs = sorted(x.name for x in trd.iterdir() if x.is_dir()) if trd.is_dir() else []
    if labs:
        drows.append([e("Testing"), e(f"Test reports ({len(labs)})"), st("ready", "passed"), f'<span class="mono">{e(labs[-1])}</span>'])
    out.append(h2("Deliverables") + tbl(["Phase", "Document", "Status", "Updated"], drows)
               + '<p class="muted">“Outstanding” means its phase has finished and the document is still due.</p>')

    # 10 environments and links
    filled = lambda x: isinstance(x, dict) and x.get("url") and "<" not in str(x.get("url"))
    local = lambda u: str(u).startswith(("http://localhost", "http://127.", "https://localhost"))
    envs = [x for x in (cfg.get("environments") or []) if filled(x) and x.get("client", True) is not False and not local(x.get("url"))]
    # no live check here: "unreachable from here" on a client's VPN-only environment would read as an outage
    erows = [[e(x.get("name")), f'<a href="{e(x["url"])}">{e(x["url"])}</a>', e(x.get("purpose") or ""),
              f'<span class="mono">{e(x.get("deployed") or "—")}</span>', e(", ".join(x.get("test_roles") or []) or "—")]
             for x in envs]
    links = [[e(l.get("label") or l["url"]), f'<a href="{e(l["url"])}">{e(l["url"])}</a>']
             for l in (cfg.get("links") or []) if filled(l) and l.get("client") is True]
    out.append(h2("Environments and links")
               + tbl(["Environment", "Address", "Used for", "Version", "Test logins (roles)"], erows)
               + ('<p class="muted">Logins are shared separately; no passwords appear in this report.</p>' if erows else "")
               + ("<h3>Links</h3>" + tbl(["Resource", "Address"], links) if links else ""))

    foot = " · ".join(x for x in [brand.get("footer"), brand.get("email"), brand.get("linkedin")] if x)
    out.append(f'<footer class="docfoot">{e(foot)}<br>Prepared {e(now.strftime("%d %b %Y %H:%M UTC"))} from the project records. '
               'Dates marked estimate are forecasts from measured sprint times, not commitments.</footer></article>')
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ASDR project dashboard (HTML + PDF).")
    ap.add_argument("--out", default="docs/dashboard")
    ap.add_argument("--inline", metavar="FILE", default=None, help="also write a single-file (Artifact) copy here")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--audience", choices=["internal", "client"], default="internal",
                    help="client: a branded status report for the client — no agent activity, effort, internal "
                         "questions, local paths or internal links; same status rule")
    ap.add_argument("--brand", default=None, help="client view: brand file (default .harness/brand.json, then ~/.asdr/brand.json)")
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
    if args.audience == "client":
        from build_assess_report import load_brand
        brand, brand_src = load_brand(args.brand)
        body = build_client(root, now, brand, gather(root, now))
        title = f"{cfg.get('project') or 'Project'} Status Report"
        out_dir = Path(args.out if args.out != "docs/dashboard" else "docs/dashboard/client")
        out_dir.mkdir(parents=True, exist_ok=True)
        hf = out_dir / "index.html"
        hf.write_text("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
                      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">"
                      f"<title>{html.escape(title)}</title><style>{client_css(brand)}</style></head><body>{body}</body></html>\n")
        outputs = {"html": str(hf)}
        if not args.no_pdf:
            pf = out_dir / "status-report.pdf"
            outputs["pdf"] = str(pf) if to_pdf(hf, pf) else "no Chrome found — open index.html in a browser and print to PDF"
        for k, v in outputs.items():
            print(f"  {k}: {v}")
        print(f"  brand: {brand_src}")
        print("Client view: read it before you send it. Share the PDF; it is not published anywhere.")
        print("DASHBOARD: " + json.dumps({"outputs": outputs, "audience": "client"}))
        return 0
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
