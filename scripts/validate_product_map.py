#!/usr/bin/env python3
"""Check that the product holds together end to end, and draw the product map.

Usage:
  python3 validate_product_map.py [--docs docs] [--gate] [--results latest|<summary.json>]
                                  [--sprints sprints.json] [--map docs/product-map.md]
                                  [--json .harness/product-map.json] [--no-write]

It reads the discovery documents and follows every link in the chain

  lifecycle (PF-00) → process flow (PF) → step → use case (UC) → feature (F)
  → requirement (FR) → test case (TC) → automated test → latest result

  docs/02-requirements.md   FR, NFR, BR, EC ids and acceptance criteria AC-<story>.<n>
  docs/02b-use-cases.md     UC ids, their alternate/exception flows (UC-xx.A1,
                            UC-xx.E1) and "Linked requirements"
  docs/02c-features.md      feature Summary table (optional 9th column "Affects":
                            roles whose experience the feature changes)
  docs/02d-process-flows.md PF-00 lifecycle + one section per flow
  docs/02e-test-cases.md    TC sections; "Covers:" lists the items each one tests

and reports every broken link as an "ERROR:" line (exit 1) — a feature no
journey uses, a use case on no flow, a flow nothing leads to, a flow without a
journey test, an exception path nobody tests. These are the gaps that let each
sprint pass while the product as a whole does not work.

Coverage of everything testable (v3.5.1). Every item the project's own
documents define — each FR, NFR, business rule, edge case and acceptance
criterion, each use case and each of its alternate/exception flows, each
feature, each step and exception path of each flow — must be named by at
least one test case. A feature that changes what another role can do
("Affects") must appear in a flow step of that role and be tested from that
role's side at least twice (setting on and off). Gaps are warnings while
building and errors with --require-coverage (end of discovery) or --gate.

--gate (release gate; also usable after any sprint) adds the proof: every Must
test case must be automated and its test — titled "[TC-xx] …" — must have
PASSED in the latest run_tests.py run (--results, default latest). A failing
test of any priority is an error. And linking is not enough: tests record what
they actually exercised (flowStep / covers markers, templates/e2e/*/asdr-cover.*),
so every step and exception path of every Must flow, and every item a test
case lists under Covers, must have been reached by a PASSING test.

It always writes docs/product-map.md (human view, regenerated — never edit by
hand) and .harness/product-map.json (read by emit_facts.py as
facts:product_map.*) unless --no-write. Zero dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PRIORITIES = {"must", "should", "could", "won't", "wont"}
TC_TYPES = {"journey", "exception", "functional", "edge", "nfr"}
NONE_WORDS = {"", "none", "—", "-", "n/a", "na"}


ITEM_RE = re.compile(r"\b(PF-\d+\.E\d+|PF-\d+\.\d+|UC-\d+\.[AE]\d+|UC-\d+|AC-\d+\.\d+|"
                     r"NFR-\d+|FR-\d+|BR-\d+|EC-\d+|F-\d+)\b")
KIND_ORDER = ["FR", "NFR", "AC", "BR", "EC", "UC", "UC-ALT", "F", "STEP", "EXC"]
KIND_LABEL = {"FR": "Functional requirements", "NFR": "Non-functional requirements",
              "AC": "Acceptance criteria", "BR": "Business rules", "EC": "Edge cases",
              "UC": "Use cases (main flow)", "UC-ALT": "Use case alternate and exception flows",
              "F": "Features", "STEP": "Process flow steps", "EXC": "Process flow exception paths"}


def kind_of(item: str) -> str:
    if re.fullmatch(r"PF-\d+\.E\d+", item):
        return "EXC"
    if re.fullmatch(r"PF-\d+\.\d+", item):
        return "STEP"
    if re.fullmatch(r"UC-\d+\.[AE]\d+", item):
        return "UC-ALT"
    return item.split("-")[0]


def items_in(text: str) -> list:
    """Every testable-item id in a piece of text, in order, without duplicates."""
    out = []
    for m in ITEM_RE.findall(text or ""):
        if m not in out:
            out.append(m)
    return out


def ids(text: str, prefix: str) -> list:
    pat = {"PFSTEP": r"PF-\d+\.\d+", "PFEX": r"PF-\d+\.E\d+",
           "PF": r"PF-\d+(?!\d)(?!\.E?\d)", "F": r"(?<![A-Z])F-\d+", "UC": r"UC-\d+(?!\d)(?!\.[AE]\d)",
           "FR": r"FR-\d+", "TC": r"TC-\d+"}[prefix]
    out = []
    for m in re.findall(r"\b" + pat if prefix != "F" else pat, text or ""):
        if m not in out:
            out.append(m)
    return out


def declared_by_feature(tid: str, t: dict, flows: dict, step_info: dict) -> set:
    """Features a test case exercises: named directly, or through the flow steps it walks."""
    named = set(t["declared"])
    if t["flow"] in flows and t["type"] == "journey":
        named |= {st["id"] for st in flows[t["flow"]]["steps"]}
    for pid, f in flows.items():
        for e in f["exceptions"]:
            if t["flow"] == e["id"] and e["at"] in step_info:
                named.add(e["at"])
    out = {x for x in named if x.startswith("F-")}
    for x in named:
        if x in step_info:
            out |= set(step_info[x][1]["feature"])
    return out


def read(path: Path, problems: list, required=True) -> str:
    if path.is_file():
        return path.read_text(errors="ignore")
    if required:
        problems.append(f"{path} is missing")
    return ""


def sections(text: str, prefix: str) -> dict:
    """Split a doc into {id: (title, body)} at '## ID' / '### ID' headings."""
    out = {}
    heads = list(re.finditer(rf"^#{{2,3}}\s+({prefix}-\d+)\b\s*[·:\-–—]?\s*(.*)$", text, re.MULTILINE))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        nxt = re.search(r"^#{1,2}\s+(?!" + prefix + r"-)", text[m.end():end], re.MULTILINE)
        body_end = m.end() + nxt.start() if nxt else end
        out.setdefault(m.group(1), (m.group(2).strip(), text[m.end():body_end]))
    return out


def bullet(body: str, name: str) -> str | None:
    m = re.search(rf"^\s*[-*]\s*{name}\s*:\s*(.*)$", body, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def rows(body: str, first_cell: str) -> list:
    out = []
    for line in body.splitlines():
        if re.match(rf"^\s*\|\s*{first_cell}\s*\|", line):
            out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def tc_refs(text: str) -> list:
    """Test-case ids named in a test title: '[TC-07] …', or 'test_tc_07_…' where
    brackets are not allowed (pytest/JUnit function names)."""
    out = []
    for a, b in re.findall(r"\[TC-(\d+)\]|(?<![A-Za-z0-9])[Tt][Cc][_-](\d+)(?![0-9])", text):
        tid = f"TC-{a or b}"
        if tid not in out:
            out.append(tid)
    return out


def git_head() -> str | None:
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def load_results(arg: str | None, problems: list):
    if not arg:
        return None
    p = Path(arg)
    if arg == "latest":
        latest = Path(".harness/test-results/latest.json")
        if not latest.is_file():
            problems.append("no test results: .harness/test-results/latest.json missing — run run_tests.py")
            return None
        p = Path(json.loads(latest.read_text())["path"]) / "summary.json"
    if p.is_dir():
        p = p / "summary.json"
    if not p.is_file():
        problems.append(f"test results {p} not found")
        return None
    return json.loads(p.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the end-to-end product chain and write the product map.")
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--require-coverage", action="store_true",
                    help="every testable item must be named by a test case (end of discovery)")
    ap.add_argument("--results", default=None, help="'latest' or a summary.json / run folder (default: latest with --gate)")
    ap.add_argument("--sprints", default="sprints.json")
    ap.add_argument("--map", default=None, help="default <docs>/product-map.md")
    ap.add_argument("--json", default=".harness/product-map.json")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    d = Path(args.docs)
    errors, warns = [], []
    req_md = read(d / "02-requirements.md", errors)
    uc_md = read(d / "02b-use-cases.md", errors)
    f_md = read(d / "02c-features.md", errors)
    pf_md = read(d / "02d-process-flows.md", errors)
    tc_md = read(d / "02e-test-cases.md", errors)

    # ── requirements & use cases ──
    frs = []
    for m in re.finditer(r"^\s*(?:[-*|]\s*)?(?:\*\*)?(FR-\d+)\b", req_md, re.MULTILINE):
        if m.group(1) not in frs:
            frs.append(m.group(1))
    if req_md and not frs:
        frs = ids(req_md, "FR")
    cover_gap = errors if (args.require_coverage or args.gate) else warns
    req_items = {}            # id -> text, for FR / NFR / AC / BR / EC defined in the requirements doc
    for m in re.finditer(r"^\s*(?:[-*|]\s*)?(?:\*\*)?(NFR-\d+|FR-\d+|BR-\d+|EC-\d+|AC-\d+\.\d+)\b"
                         r"(?:\*\*)?\s*[:.)\-–—|]*\s*(.*)$", req_md, re.MULTILINE):
        req_items.setdefault(m.group(1), m.group(2).strip().rstrip("|").strip()[:160])
    for fr in frs:
        req_items.setdefault(fr, "")
    ucs, uc_alts = {}, {}
    for uid, (title, body) in sections(uc_md, "UC").items():
        ucs[uid] = {"title": title, "frs": ids(bullet(body, "Linked requirements") or "", "FR")}
        for fr in ucs[uid]["frs"]:
            if fr not in frs:
                errors.append(f"{uid} links {fr}, which is not in 02-requirements.md")
        lines, grab = body.splitlines(), []
        for i, line in enumerate(lines):
            if re.match(r"^\s*[-*]\s*Alternate", line, re.IGNORECASE):
                grab.append(line.split(":", 1)[1] if ":" in line else "")
                for nxt in lines[i + 1:]:
                    if re.match(r"^[-*]\s", nxt) or (nxt.strip() and not nxt.startswith((" ", "\t"))):
                        break
                    grab.append(nxt)
        for line in grab:                            # several labels may share a line: "E1: …; A1: …"
            marks = list(re.finditer(r"\b([AE]\d+)\s*[:.)\-–—]\s*", line))
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(line)
                txt = line[m.end():end].strip().rstrip(";,").strip()
                if m.group(1) not in ("A0", "E0"):
                    uc_alts[f"{uid}.{m.group(1)}"] = {"uc": uid, "text": txt[:160]}

    # ── features ──
    features = {}
    for r in rows(f_md, r"F-\d+"):
        if len(r) < 8:
            errors.append(f"feature row {r[0]} has {len(r)} columns; the Summary table needs 8")
            continue
        fid = r[0]
        if fid in features:
            errors.append(f"{fid} appears twice in the feature Summary table")
        affects = []                                   # [(role, is_switch)]
        if len(r) >= 9 and r[8].strip().lower() not in NONE_WORDS:
            for a in re.split(r"[,;]", r[8]):
                a = a.strip()
                if not a:
                    continue
                m = re.match(r"(.+?)\s*\((?:on/off|on-off|switch|toggle)\)\s*$", a, re.IGNORECASE)
                affects.append((m.group(1).strip(), True) if m else (a, False))
        features[fid] = {"name": r[1], "personas": r[2], "priority": r[3].strip().lower(), "release": r[4],
                         "flows": ids(r[5], "PF"), "ucs": ids(r[6], "UC"), "frs": ids(r[7], "FR"),
                         "affects": affects}
    f_details = sections(f_md, "F")
    for fid, f in features.items():
        if f["priority"] not in PRIORITIES:
            errors.append(f"{fid}: priority '{f['priority']}' must be Must, Should, Could or Won't")
        if fid not in f_details:
            errors.append(f"{fid}: no '### {fid} · …' detail section in 02c-features.md")
        for key, label, known in (("flows", "flow", None), ("ucs", "use case", ucs), ("frs", "requirement", frs)):
            if not f[key] and f["priority"] in ("must", "should"):
                errors.append(f"{fid} ({f['name']}) names no {label}")
            if known is not None:
                for x in f[key]:
                    if x not in known:
                        errors.append(f"{fid} links {x}, which does not exist")

    # ── process flows ──
    flow_secs = sections(pf_md, "PF")
    lifecycle = flow_secs.pop("PF-00", None)
    flows = {}
    for pid, (title, body) in flow_secs.items():
        steps = [{"id": c[0], "actor": c[1] if len(c) > 1 else "", "action": c[2] if len(c) > 2 else "",
                  "response": c[3] if len(c) > 3 else "", "uc": ids(c[4], "UC") if len(c) > 4 else [],
                  "feature": ids(c[5], "F") if len(c) > 5 else [], "data": c[6] if len(c) > 6 else ""}
                 for c in rows(body, rf"{pid}\.\d+")]
        exc = [{"id": c[0], "at": c[1] if len(c) > 1 else "", "condition": c[2] if len(c) > 2 else "",
                "response": c[3] if len(c) > 3 else "", "rejoins": c[4] if len(c) > 4 else ""}
               for c in rows(body, rf"{pid}\.E\d+")]
        prio = (bullet(body, "Priority") or "").lower()
        flows[pid] = {"title": title, "priority": prio, "personas": bullet(body, r"Persona\(s\)") or bullet(body, "Personas?") or "",
                      "trigger": bullet(body, "Trigger") or "", "outcome": bullet(body, "Outcome") or "",
                      "features": ids(bullet(body, "Features") or "", "F"),
                      "preceded": ids(bullet(body, "Preceded by") or "", "PF"),
                      "followed": ids(bullet(body, "Followed by") or "", "PF"),
                      "preceded_raw": (bullet(body, "Preceded by") or "").lower(),
                      "steps": steps, "exceptions": exc,
                      "has_diagram": "```mermaid" in body}
    if pf_md and not flows:
        errors.append("02d-process-flows.md has no '### PF-xx · …' flow sections")
    if pf_md and lifecycle is None:
        errors.append("02d-process-flows.md has no '## PF-00 · Product lifecycle' section")
    elif lifecycle:
        named = set(ids(lifecycle[1], "PF"))
        for pid in flows:
            if pid not in named:
                errors.append(f"{pid} is missing from the PF-00 lifecycle diagram — show how it connects to the other flows")
    for pid, f in flows.items():
        if f["priority"] not in PRIORITIES:
            errors.append(f"{pid}: Priority '{f['priority']}' must be Must, Should, Could or Won't")
        if not f["outcome"]:
            errors.append(f"{pid}: no Outcome — a flow must end in an observable finished state")
        if not f["trigger"]:
            warns.append(f"{pid}: no Trigger")
        if not f["has_diagram"]:
            warns.append(f"{pid}: no Mermaid diagram")
        if not f["steps"]:
            errors.append(f"{pid}: no steps table rows ({pid}.1, {pid}.2, …)")
        for i, s in enumerate(f["steps"], 1):
            if s["id"] != f"{pid}.{i}":
                errors.append(f"{pid}: step {s['id']} out of order (expected {pid}.{i})")
                break
        step_ids = {s["id"] for s in f["steps"]}
        for s in f["steps"]:
            for u in s["uc"]:
                if u not in ucs:
                    errors.append(f"{s['id']} links {u}, which is not in 02b-use-cases.md")
            for x in s["feature"]:
                if x not in features:
                    errors.append(f"{s['id']} links {x}, which is not in the feature list")
            if not s["uc"] and s["action"].strip() not in NONE_WORDS and s["actor"].lower() not in ("system", "—"):
                warns.append(f"{s['id']}: a user step with no use case")
        for x in f["features"]:
            if x not in features:
                errors.append(f"{pid} lists feature {x}, which is not in the feature list")
        for e in f["exceptions"]:
            if e["at"] not in step_ids:
                errors.append(f"{e['id']}: 'At step' {e['at'] or '(empty)'} is not a step of {pid}")
            rj = e["rejoins"].strip().lower()
            if rj not in NONE_WORDS | {"ends", "end"} and e["rejoins"].strip() not in step_ids:
                errors.append(f"{e['id']}: 'Rejoins at' {e['rejoins']} is not a step of {pid} (or 'ends')")
        if f["priority"] == "must" and not f["exceptions"]:
            errors.append(f"{pid} is Must but documents no exception path — list what goes wrong and what the user sees")
        for x in f["preceded"] + f["followed"]:
            if x not in flows:
                errors.append(f"{pid}: Preceded/Followed by {x}, which is not a flow")

    # reachability: an entry flow must lead (through Preceded/Followed links) to every flow
    graph = defaultdict(set)
    for pid, f in flows.items():
        for p in f["preceded"]:
            graph[p].add(pid)
        for n in f["followed"]:
            graph[pid].add(n)
    entries = [pid for pid, f in flows.items() if not f["preceded"]]
    if flows and not entries:
        errors.append("no entry flow: at least one flow needs 'Preceded by: none' (where a new user starts)")
    seen, stack = set(entries), list(entries)
    while stack:
        for n in graph[stack.pop()]:
            if n not in seen:
                seen.add(n)
                stack.append(n)
    for pid in flows:
        if pid not in seen:
            errors.append(f"{pid} cannot be reached from an entry flow — nothing in the product leads a user there")

    # coverage of features and use cases by flows
    f_in_flows = defaultdict(set)
    uc_in_flows = defaultdict(set)
    for pid, f in flows.items():
        for x in f["features"]:
            f_in_flows[x].add(pid)
        for s in f["steps"]:
            for x in s["feature"]:
                f_in_flows[x].add(pid)
            for u in s["uc"]:
                uc_in_flows[u].add(pid)
    for fid, f in features.items():
        if f["priority"] == "must" and not f_in_flows.get(fid):
            errors.append(f"{fid} ({f['name']}) is Must but no process flow uses it — which journey needs it?")
        for p in f["flows"]:
            if p in flows and fid not in f_in_flows.get(p, set()) and p not in f_in_flows.get(fid, set()):
                warns.append(f"{fid} says it is part of {p}, but {p} does not list or use it")
    for u in ucs:
        if not uc_in_flows.get(u):
            errors.append(f"{u} ({ucs[u]['title']}) is not on any process flow — add it to a journey or cut it")

    # ── test cases ──
    tcs = {}
    for tid, (title, body) in sections(tc_md, "TC").items():
        flow_raw = bullet(body, "Flow") or ""
        covers = items_in(bullet(body, "Covers") or "")
        tcs[tid] = {"title": title, "type": (bullet(body, "Type") or "").lower(),
                    "flow": (ids(flow_raw, "PFEX") or ids(flow_raw, "PF") or [None])[0],
                    "ucs": ids(bullet(body, "Use cases") or "", "UC"),
                    "frs": ids(bullet(body, "Requirements") or "", "FR"),
                    "covers": covers,
                    "declared": items_in(" ".join([bullet(body, "Covers") or "", bullet(body, "Requirements") or "",
                                                   bullet(body, "Use cases") or ""])),
                    "persona": (bullet(body, "Persona") or "").strip().lower(),
                    "priority": (bullet(body, "Priority") or "").lower(),
                    "automation": bullet(body, "Automation") or "",
                    "expected": bullet(body, "Expected result") or ""}
    if tc_md and not tcs:
        errors.append("02e-test-cases.md has no '### TC-xx · …' sections")
    exc_ids = {e["id"]: pid for pid, f in flows.items() for e in f["exceptions"]}
    journeys, exc_tested, fr_tested = defaultdict(list), defaultdict(list), defaultdict(list)
    for tid, t in tcs.items():
        if t["type"] not in TC_TYPES:
            errors.append(f"{tid}: Type '{t['type']}' must be one of {', '.join(sorted(TC_TYPES))}")
        if t["priority"] not in PRIORITIES:
            errors.append(f"{tid}: Priority '{t['priority']}' must be Must, Should or Could")
        if not t["expected"]:
            errors.append(f"{tid}: no Expected result")
        fl = t["flow"]
        if t["type"] in ("journey", "exception") and not fl:
            errors.append(f"{tid}: a {t['type']} test case must name its Flow")
        if fl and fl not in flows and fl not in exc_ids:
            errors.append(f"{tid}: Flow {fl} does not exist")
        if t["type"] == "journey" and fl in flows:
            journeys[fl].append(tid)
        if fl in exc_ids:
            exc_tested[fl].append(tid)
        for u in t["ucs"]:
            if u not in ucs:
                errors.append(f"{tid} links {u}, which does not exist")
        for r in t["frs"]:
            if r not in frs:
                errors.append(f"{tid} links {r}, which does not exist")
            fr_tested[r].append(tid)
        if not t["automation"]:
            (errors if args.gate and t["priority"] == "must" else warns).append(
                f"{tid}: no Automation line — name the test titled '[{tid}] …' that proves it")
    if tc_md or flows:
        for pid, f in flows.items():
            if not journeys.get(pid):
                errors.append(f"{pid} has no journey test case (Type: journey, Flow: {pid}) — nothing proves the whole flow works")
            for e in f["exceptions"]:
                if not exc_tested.get(e["id"]):
                    errors.append(f"{e['id']} ({e['condition']}) has no test case")
        for r in frs:
            if not fr_tested.get(r) and not any(r in t["declared"] for t in tcs.values()):
                cover_gap.append(f"{r} is not covered by any test case")
        for tid, t in tcs.items():
            for x in t["covers"]:
                known = (x in req_items or x in ucs or x in uc_alts or x in features
                         or any(x == st["id"] for f in flows.values() for st in f["steps"]) or x in exc_ids)
                if not known:
                    errors.append(f"{tid} covers {x}, which no document defines")

    # ── results (gate) ──
    results_arg = args.results or ("latest" if args.gate else None)
    summary = load_results(results_arg, errors if args.gate else warns)
    by_tc = defaultdict(list)
    if summary:
        for su in summary.get("suites", []):
            for c in su.get("cases", []):
                for tid in tc_refs(f"{c.get('name') or ''} {c.get('classname') or ''}"):
                    by_tc[tid].append({"status": c["status"], "suite": su["name"], "name": c.get("name")})
        head = git_head()
        if head and summary.get("commit") and summary["commit"] != head:
            warns.append(f"test results are from commit {summary['commit']}, HEAD is {head} — rerun run_tests.py")
        for tid in by_tc:
            if tid not in tcs:
                warns.append(f"a test is titled [{tid}] but {tid} is not in 02e-test-cases.md")
    tc_state = {}
    for tid, t in tcs.items():
        manual = t["automation"].lower().startswith("manual")
        res = by_tc.get(tid, [])
        if manual:
            state = "manual"
        elif not summary:
            state = "not run"
        elif not res:
            state = "no result"
        elif all(r["status"] == "passed" for r in res):
            state = "passed"
        elif any(r["status"] in ("failed", "error") for r in res):
            state = "failed"
        else:
            state = "skipped"
        tc_state[tid] = state
        if summary:
            if state == "failed":
                errors.append(f"{tid} ({t['title']}) FAILED in run {summary.get('run_id')}")
            if args.gate and t["priority"] == "must" and state in ("no result", "skipped"):
                errors.append(f"{tid} is Must but has no passing result in run {summary.get('run_id')} "
                              f"— its test must be titled '[{tid}] …' (or test_tc_NN_… in pytest)")
            if args.gate and state == "manual":
                warns.append(f"{tid} is manual ({t['automation']}) — needs a human sign-off at the gate")

    # ── coverage of every testable item ──
    step_info = {st["id"]: (pid, st) for pid, f in flows.items() for st in f["steps"]}
    testable = {}                                   # id -> (kind, description)
    for x, txt in req_items.items():
        testable[x] = (kind_of(x), txt)
    for u, info in ucs.items():
        testable[u] = ("UC", info["title"])
    for x, info in uc_alts.items():
        testable[x] = ("UC-ALT", info["text"])
    for fid, f in features.items():
        if f["priority"] not in ("won't", "wont"):
            testable[fid] = ("F", f["name"])
    for pid, f in flows.items():
        for st in f["steps"]:
            testable[st["id"]] = ("STEP", f"{st['actor']}: {st['action']}")
        for e in f["exceptions"]:
            testable[e["id"]] = ("EXC", e["condition"])

    declared_by = defaultdict(set)                  # item -> test cases that name it
    for tid, t in tcs.items():
        named = set(t["declared"])
        if t["flow"] in flows and t["type"] == "journey":
            named |= {st["id"] for st in flows[t["flow"]]["steps"]} | {t["flow"]}
        if t["flow"] in exc_ids:
            named.add(t["flow"])
        for x in list(named):                       # a named step also names its use case and feature
            if x in step_info:
                named |= set(step_info[x][1]["uc"]) | set(step_info[x][1]["feature"])
        for x in named:
            declared_by[x].add(tid)
    for x, (kind, desc) in testable.items():
        if not declared_by.get(x) and kind not in ("EXC",):       # exception paths are checked above
            if kind == "FR":
                continue                                          # reported above
            cover_gap.append(f"{x} ({KIND_LABEL[kind].lower().rstrip('s')}: {desc or '—'}) is not named by any "
                             "test case — add it to a test case's Covers line")

    # cross-role effects: a feature that changes what another role can do
    for fid, f in features.items():
        for role, is_switch in f["affects"]:
            r = role.lower()
            steps_for_role = [st["id"] for pid, fl in flows.items() for st in fl["steps"]
                              if r in st["actor"].lower() and fid in st["feature"]]
            if not steps_for_role:
                errors.append(f"{fid} ({f['name']}) changes what {role} can do, but no flow has a {role} step "
                              f"using it — add the step where {role} feels the effect")
            role_tcs = [tid for tid, t in tcs.items() if r in t["persona"] and fid in declared_by_feature(tid, t, flows, step_info)]
            need = 2 if is_switch else 1
            if len(role_tcs) < need:
                how = "with it on and with it off" if is_switch else "where they see the change"
                cover_gap.append(f"{fid} ({f['name']}) changes what {role} can do: test it from the {role} side "
                                 f"{how} — needs {need} test case(s) with Persona {role} covering {fid}, found "
                                 f"{len(role_tcs)}")

    # executed coverage: markers the tests recorded at run time
    run_cov = (summary or {}).get("coverage") or {}
    marked = {tid: set(v) for tid, v in (run_cov.get("by_tc") or {}).items()}
    executed_by = defaultdict(set)                  # item -> passing test cases that reached it
    for tid, items in marked.items():
        if tc_state.get(tid) != "passed":
            continue
        reached = set(items)
        for x in list(reached):
            if x in step_info:
                reached |= set(step_info[x][1]["uc"]) | set(step_info[x][1]["feature"])
        for x in reached:
            executed_by[x].add(tid)
    if summary:
        if not marked:
            (errors if args.gate else warns).append(
                "the test run recorded no coverage markers — journey tests must call flowStep('PF-xx.n') at each "
                "step and tests must call covers(...) for the items they check (templates/e2e/*/asdr-cover.*)")
        else:
            gap = errors if args.gate else warns
            for pid, f in flows.items():
                if f["priority"] != "must":
                    continue
                for x in [st["id"] for st in f["steps"]] + [e["id"] for e in f["exceptions"]]:
                    if not executed_by.get(x):
                        gap.append(f"{x} was never reached by a passing test — mark it with flowStep('{x}') "
                                   "where a test walks it")
            for tid, t in tcs.items():
                if tc_state.get(tid) != "passed":
                    continue
                for x in t["covers"]:
                    got = set(marked.get(tid, set()))
                    for y in list(got):
                        if y in step_info:
                            got |= set(step_info[y][1]["uc"]) | set(step_info[y][1]["feature"])
                    if x not in got:
                        gap.append(f"{tid} says it covers {x}, but its test never marked it — call covers('{x}') "
                                   "at the assertion that proves it")
            unknown_marks = sorted({x for v in marked.values() for x in v if x not in testable and kind_of(x) != "PF"})
            if unknown_marks:
                warns.append(f"tests marked items no document defines: {', '.join(unknown_marks[:10])}")
            unreached = [x for x in testable if not executed_by.get(x)]
            if unreached:
                warns.append(f"{len(unreached)} testable item(s) no passing test reached: "
                             f"{', '.join(unreached[:15])}{' …' if len(unreached) > 15 else ''} — add covers(...) "
                             "where a test proves each one (docs/product-map.md lists them)")

    # sprints that deliver each flow (optional "flows" list on sprint entries)
    sprint_flows = defaultdict(list)
    sp = Path(args.sprints)
    if sp.is_file():
        try:
            doc = json.loads(sp.read_text())
            for s in (doc.get("sprints", []) if isinstance(doc, dict) else doc):
                for p in s.get("flows", []) or []:
                    sprint_flows[p].append(s.get("id"))
        except (ValueError, AttributeError):
            warns.append(f"{sp} is not readable JSON")
        if any(sprint_flows.values()):
            for pid, f in flows.items():
                if f["priority"] == "must" and pid not in sprint_flows:
                    warns.append(f"{pid} is Must but no sprint in {sp} lists it under 'flows'")

    # ── model + outputs ──
    def flow_status(pid):
        js = journeys.get(pid, [])
        states = [tc_state.get(t) for t in js + [x for e in flows[pid]["exceptions"] for x in exc_tested.get(e["id"], [])]]
        if not js:
            return "no journey test"
        if any(s == "failed" for s in states):
            return "failing"
        if all(s in ("passed", "manual") for s in states):
            return "proven"
        return "not proven yet"

    model = {
        "schema": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "results_run": summary.get("run_id") if summary else None,
        "results_commit": summary.get("commit") if summary else None,
        "counts": {"flows": len(flows), "must_flows": sum(1 for f in flows.values() if f["priority"] == "must"),
                   "steps": sum(len(f["steps"]) for f in flows.values()), "features": len(features),
                   "use_cases": len(ucs), "requirements": len(frs), "test_cases": len(tcs),
                   "requirements_tested": sum(1 for r in frs if fr_tested.get(r)),
                   "test_cases_passing": sum(1 for s in tc_state.values() if s == "passed"),
                   "flows_proven": sum(1 for p in flows if flow_status(p) == "proven")},
        "flows": {pid: {"title": f["title"], "priority": f["priority"], "status": flow_status(pid),
                        "journey_tests": journeys.get(pid, []), "sprints": sprint_flows.get(pid, []),
                        "steps": len(f["steps"]), "exceptions": len(f["exceptions"]),
                        "journey_passing": bool(journeys.get(pid)) and all(tc_state.get(t) == "passed" for t in journeys[pid])}
                  for pid, f in flows.items()},
        "features": {fid: {"name": f["name"], "priority": f["priority"], "flows": sorted(f_in_flows.get(fid, []))}
                     for fid, f in features.items()},
        "test_cases": {tid: {"title": t["title"], "type": t["type"], "flow": t["flow"], "priority": t["priority"],
                             "state": tc_state.get(tid)} for tid, t in tcs.items()},
        "coverage": {k: {"total": sum(1 for v in testable.values() if v[0] == k),
                         "declared": sum(1 for x, v in testable.items() if v[0] == k and declared_by.get(x)),
                         "executed": sum(1 for x, v in testable.items() if v[0] == k and executed_by.get(x))}
                     for k in KIND_ORDER if any(v[0] == k for v in testable.values())},
        "items": {x: {"kind": k, "description": d, "declared_by": sorted(declared_by.get(x, [])),
                      "executed_by": sorted(executed_by.get(x, []))} for x, (k, d) in testable.items()},
        "errors": len(errors), "warnings": len(warns),
    }
    model["counts"]["items"] = len(testable)
    model["counts"]["items_declared"] = sum(1 for x in testable if declared_by.get(x))
    model["counts"]["items_executed"] = sum(1 for x in testable if executed_by.get(x))

    if not args.no_write:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(model, indent=2))
        Path(args.map or d / "product-map.md").write_text(render_map(model, flows, features, ucs, tcs, tc_state,
                                                                      journeys, exc_tested, lifecycle, errors, warns))

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    c = model["counts"]
    print(f"{'FAIL' if errors else 'OK'}: {c['flows']} flows ({c['flows_proven']} proven), {c['steps']} steps, "
          f"{c['features']} features, {c['use_cases']} use cases, {c['requirements_tested']}/{c['requirements']} "
          f"requirements tested, {c['test_cases']} test cases ({c['test_cases_passing']} passing); "
          f"{c['items_declared']}/{c['items']} testable items named by a test case"
          + (f", {c['items_executed']} reached by a passing test" if summary else "")
          + (f" — {len(errors)} error(s)" if errors else ""))
    return 1 if errors else 0


ICON = {"passed": "✅ passed", "failed": "❌ failed", "manual": "🖐 manual", "no result": "⚠️ no result",
        "not run": "· not run", "skipped": "⚠️ skipped", "proven": "✅ proven", "failing": "❌ failing",
        "no journey test": "❌ no journey test", "not proven yet": "⚠️ not proven yet"}


def render_map(model, flows, features, ucs, tcs, tc_state, journeys, exc_tested, lifecycle, errors, warns) -> str:
    c = model["counts"]
    out = ["# Product map", "",
           "<!-- GENERATED by validate_product_map.py — do not edit by hand; edit the 02*.md docs and rerun. -->", "",
           f"Generated {model['generated_at']}"
           + (f" · test results from run `{model['results_run']}` (commit `{model['results_commit']}`)" if model["results_run"] else " · no test results linked"),
           "",
           f"**{c['flows_proven']}/{c['flows']} flows proven end to end** · {c['test_cases_passing']}/{c['test_cases']} test cases passing · "
           f"{c['requirements_tested']}/{c['requirements']} requirements tested · {c['features']} features · {c['use_cases']} use cases · "
           f"{c.get('items_declared', 0)}/{c.get('items', 0)} testable items named by a test case"
           + (f", {c.get('items_executed', 0)} reached by a passing test" if model["results_run"] else ""), ""]
    if errors:
        out += [f"## Gaps to fix ({len(errors)})", ""] + [f"- {e}" for e in errors] + [""]
    if lifecycle:
        m = re.search(r"```mermaid.*?```", lifecycle[1], re.DOTALL)
        if m:
            out += ["## How the journeys connect", "", m.group(0), ""]
    out += ["## Flows", "", "| Flow | Priority | Steps | Journey test | Status | Sprints |", "|---|---|---|---|---|---|"]
    for pid, f in flows.items():
        mf = model["flows"][pid]
        out.append(f"| {pid} · {f['title']} | {f['priority'].title()} | {len(f['steps'])} | {', '.join(mf['journey_tests']) or '—'} | "
                   f"{ICON.get(mf['status'], mf['status'])} | {', '.join(mf['sprints']) or '—'} |")
    out.append("")
    for pid, f in flows.items():
        out += [f"### {pid} · {f['title']}", "",
                f"{f['personas']} · trigger: {f['trigger'] or '—'} · outcome: {f['outcome'] or '—'}", "",
                "| Step | Actor | Action | Use case | Feature | Requirements |", "|---|---|---|---|---|---|"]
        for s in f["steps"]:
            frs = sorted({r for u in s["uc"] for r in ucs.get(u, {}).get("frs", [])})
            out.append(f"| {s['id']} | {s['actor']} | {s['action']} | {', '.join(s['uc']) or '—'} | "
                       f"{', '.join(s['feature']) or '—'} | {', '.join(frs) or '—'} |")
        out += ["", "| Proven by | Type | Covers | Result |", "|---|---|---|---|"]
        proofs = [(t, "journey", pid) for t in journeys.get(pid, [])]
        proofs += [(t, "exception", e["id"]) for e in f["exceptions"] for t in exc_tested.get(e["id"], [])]
        out += [f"| {t} · {tcs[t]['title']} | {kind} | {cov} | {ICON.get(tc_state.get(t), tc_state.get(t))} |" for t, kind, cov in proofs] or ["| — | | | |"]
        out.append("")
    out += ["## Features", "", "| Feature | Priority | Used in flows |", "|---|---|---|"]
    for fid, f in features.items():
        used = model["features"][fid]["flows"]
        out.append(f"| {fid} · {f['name']} | {f['priority'].title()} | {', '.join(used) or '⚠️ none'} |")
    out.append("")
    if model.get("items"):
        ran = bool(model["results_run"])
        out += ["## Coverage of every testable item", "",
                "Every item the documents define, the test cases that name it, and — from the latest run — the "
                "passing tests that actually reached it (flowStep / covers markers).", "",
                "| Kind | Items | Named by a test case | Reached by a passing test |", "|---|---|---|---|"]
        for k, v in model["coverage"].items():
            out.append(f"| {KIND_LABEL[k]} | {v['total']} | {v['declared']} | {v['executed'] if ran else '—'} |")
        out.append("")
        for k in KIND_ORDER:
            rows_k = [(x, i) for x, i in model["items"].items() if i["kind"] == k]
            if not rows_k:
                continue
            out += [f"### {KIND_LABEL[k]}", "", "| Item | What | Test cases | Reached by | Status |", "|---|---|---|---|---|"]
            for x, i in rows_k:
                if i["executed_by"]:
                    st = "✅ tested"
                elif i["declared_by"]:
                    st = "⚠️ named, not reached" if ran else "· named"
                else:
                    st = "❌ no test case"
                what = (i["description"] or "").replace("|", "/")
                out.append(f"| {x} | {what} | {', '.join(i['declared_by']) or '—'} | "
                           f"{', '.join(i['executed_by']) or '—'} | {st} |")
            out.append("")
    if warns:
        out += [f"## Warnings ({len(warns)})", ""] + [f"- {w}" for w in warns] + [""]
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
