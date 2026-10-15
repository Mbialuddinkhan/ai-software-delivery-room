#!/usr/bin/env python3
"""Compare the old system with the new build, behaviour by behaviour.

Usage:
  python3 compare_parity.py [--doc docs/02f-parity.md] [--old baseline|<run>]
                            [--new latest|<run>] [--gate] [--allow-same-url]
                            [--report docs/parity-report.md] [--json .harness/parity.json]
                            [--no-write]

For work on an existing system (/assess hand-off). docs/02f-parity.md lists
the behaviours the business relies on (PAR-xx), each with a decision: keep,
change (approved) or drop (approved). Tests capture what the user sees or gets
with parity('PAR-xx', value[, label]); run_tests.py --parity old records a run
against the OLD system as the baseline; every normal run of the new build is
compared with it.

Per item:
  same              keep, and every capture matches the old system after Ignore
  differs           keep, and something differs → ERROR (a kept behaviour broke)
  unstable          one run captured different values for the same item and
                    label → ERROR (the capture is not deterministic: normalise it)
  no baseline       the old system's run never captured it (error with --gate)
  not captured      the new build's run never captured it (error with --gate)
  changed           an approved change, and the behaviour did change
  change not seen   an approved change, but the behaviour is identical (warning)
  dropped           an approved drop
A change or drop with no approval text counts as keep. Only captures from
tests that PASSED (by their [TC-xx] id) count. Comparing a run with itself
(same base URL) is an error: it would prove nothing.

--gate (release, and any sprint that touches an existing behaviour): missing
captures, a baseline that is not an old-system run, or new results from a
different commit than HEAD are errors too.

Writes docs/parity-report.md and .harness/parity.json (facts:parity.*, the
dashboard). Last line: PARITY: {json}. Exit 1 on any error. Zero dependencies.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

RESULTS = Path(".harness/test-results")
RESERVED = {"timestamps", "uuids", "order", "whitespace", "case", "numbers-in-ids"}
TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
                   r"|\b\d{1,2}:\d{2}(?::\d{2})?\s?(?:[AaPp][Mm])?\b")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
ID_KEY = re.compile(r"(^id$|_id$|Id$|^uuid$)")
TC_RE = re.compile(r"\[TC-(\d+)\]|(?<![A-Za-z0-9])[Tt][Cc][_-](\d+)(?![0-9])")
PLACEHOLDER = re.compile(r"^<.*>$")


# ── the parity document ──────────────────────────────────────────────────────

def read_doc(path: Path, warns: list) -> dict:
    items = {}
    if not path.is_file():
        return items
    for line in path.read_text(errors="ignore").splitlines():
        if not re.match(r"^\s*\|\s*PAR-\d+\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cells += [""] * (6 - len(cells))
        pid, behaviour, src, compare, ignore, decision = cells[:6]
        d = decision.strip()
        kind = (re.match(r"(keep|change|drop)", d, re.IGNORECASE) or [None, "keep"])[1].lower() if d else "keep"
        approval = re.sub(r"^(keep|change|drop)\s*[—–:\-]*\s*", "", d, flags=re.IGNORECASE).strip()
        if kind in ("change", "drop") and (not approval or PLACEHOLDER.match(approval)
                                           or "approved" not in approval.lower()):
            warns.append(f"{pid} says {kind} but names no approval (\"approved by <who>, <when>, <where>\") "
                         "— treated as keep")
            kind = "keep"
        tokens = [t.strip() for t in ignore.split(",") if t.strip() and not PLACEHOLDER.match(t.strip())]
        items[pid] = {"behaviour": behaviour, "from": src, "compare": compare.lower() or "value",
                      "ignore": tokens, "decision": kind, "approval": approval if kind != "keep" else ""}
    return items


# ── runs ─────────────────────────────────────────────────────────────────────

def load_run(arg: str, problems: list, what: str):
    p = Path(arg)
    if arg in ("baseline", "latest"):
        ptr = RESULTS / ("parity-baseline.json" if arg == "baseline" else "latest.json")
        if not ptr.is_file():
            problems.append(f"no {what} run: {ptr} is missing — "
                            + ("run run_tests.py --parity old --base-url <old system URL> --no-server"
                               if arg == "baseline" else "run run_tests.py"))
            return None
        p = Path(json.loads(ptr.read_text())["path"])
    if p.is_dir():
        p = p / "summary.json"
    if not p.is_file():
        problems.append(f"{what} run {p} not found")
        return None
    try:
        return json.loads(p.read_text())
    except ValueError as e:
        problems.append(f"{what} run {p} unreadable: {e}")
        return None


def passed_tcs(summary: dict) -> set:
    by = {}
    for su in summary.get("suites", []):
        for c in su.get("cases", []):
            for a, b in TC_RE.findall(f"{c.get('name') or ''} {c.get('classname') or ''}"):
                by.setdefault(f"TC-{a or b}", []).append(c.get("status"))
    return {t for t, sts in by.items() if sts and all(s == "passed" for s in sts)}


def captures(summary: dict) -> "tuple[dict, list]":
    """{id: {label: [value, …]}} from passing tests; plus captures that did not count."""
    ok = passed_tcs(summary)
    out, dropped = {}, []
    for c in ((summary.get("coverage") or {}).get("parity") or []):
        tcs = c.get("tc") or []
        if not tcs:
            dropped.append(f"{c.get('id')} captured by an untagged test ({c.get('test')}) — title it '[TC-xx] …'")
            continue
        if not all(t in ok for t in tcs):
            dropped.append(f"{c.get('id')} captured by {', '.join(tcs)}, which did not pass")
            continue
        out.setdefault(c.get("id"), {}).setdefault(c.get("label") or "", []).append(c.get("value"))
    return out, dropped


# ── normalisation ────────────────────────────────────────────────────────────

def normalise(v, ignore: list):
    keys = {t.lower() for t in ignore if t.lower() not in RESERVED}
    flags = {t.lower() for t in ignore} & RESERVED

    def s(x: str) -> str:
        if "timestamps" in flags:
            x = TS_RE.sub("<ts>", x)
        if "uuids" in flags:
            x = UUID_RE.sub("<uuid>", x)
        if "whitespace" in flags:
            x = " ".join(x.split())
        if "case" in flags:
            x = x.lower()
        return x

    def walk(x, key=None):
        if isinstance(x, dict):
            return {k: walk(val, k) for k, val in x.items() if k.lower() not in keys}
        if isinstance(x, list):
            items = [walk(i) for i in x]
            if "order" in flags:
                items.sort(key=lambda i: json.dumps(i, sort_keys=True, default=str))
            return items
        if "numbers-in-ids" in flags and key is not None and ID_KEY.search(str(key)):
            return "<id>"
        if isinstance(x, str):
            return s(x)
        return x

    v = walk(v)
    if isinstance(v, str) and "order" in flags:             # text: compare its lines as a set
        v = "\n".join(sorted(v.splitlines()))
    return v


def canon(v) -> str:
    return json.dumps(v, sort_keys=True, indent=1, ensure_ascii=False, default=str)


def diff(a, b, limit=40) -> str:
    if isinstance(a, str) and isinstance(b, str):
        la, lb = a.splitlines() or [a], b.splitlines() or [b]
    else:
        la, lb = canon(a).splitlines(), canon(b).splitlines()
    d = list(difflib.unified_diff(la, lb, "old system", "new build", lineterm="", n=1))
    return "\n".join(d[:limit] + (["… (diff truncated)"] if len(d) > limit else []))


# ── compare ──────────────────────────────────────────────────────────────────

def compare(doc: dict, old: dict, new: dict, gate: bool, errors: list, warns: list) -> dict:
    out = {}
    miss = errors if gate else warns
    for pid, it in doc.items():
        o, n = old.get(pid, {}), new.get(pid, {})
        rec = {**it, "status": None, "labels": {}, "diff": ""}
        unstable = []
        for side, caps in (("old system", o), ("new build", n)):
            for label, vals in caps.items():
                distinct = {canon(normalise(v, it["ignore"])) for v in vals}
                if len(distinct) > 1:
                    unstable.append(f"{side}{' [' + label + ']' if label else ''}")
        if unstable:
            rec["status"] = "unstable"
            errors.append(f"{pid} captured different values within one run ({', '.join(unstable)}) — the capture "
                          "is not deterministic; add what varies to Ignore or capture something stable")
            out[pid] = rec
            continue
        if it["decision"] == "drop":
            rec["status"] = "dropped"
            if n and o and all(canon(normalise(o[k][0], it["ignore"])) == canon(normalise(n[k][0], it["ignore"]))
                               for k in o if k in n):
                warns.append(f"{pid} was dropped ({it['approval']}), but the new build still behaves the same")
            out[pid] = rec
            continue
        if not o:
            rec["status"] = "no baseline"
            miss.append(f"{pid} ({it['behaviour']}) has no capture from the old system — its test must call "
                        f"parity('{pid}', …) and pass in the --parity old run")
            out[pid] = rec
            continue
        if not n:
            rec["status"] = "not captured"
            miss.append(f"{pid} ({it['behaviour']}) was not captured by a passing test of the new build")
            out[pid] = rec
            continue
        same_all, diffs = True, []
        for label in sorted(set(o) | set(n)):
            if label not in o or label not in n:
                same_all = False
                where = "the new build" if label not in n else "the old system"
                diffs.append(f"[{label or 'default'}] captured only by {'the old system' if label in o else 'the new build'}"
                             f" — missing in {where}")
                rec["labels"][label] = {"same": False}
                continue
            a, b = normalise(o[label][0], it["ignore"]), normalise(n[label][0], it["ignore"])
            same = canon(a) == canon(b)
            rec["labels"][label] = {"same": same}
            if not same:
                same_all = False
                diffs.append((f"[{label}]\n" if label else "") + diff(a, b))
        rec["diff"] = "\n".join(diffs)
        if it["decision"] == "change":
            rec["status"] = "changed" if not same_all else "change not seen"
            if same_all:
                warns.append(f"{pid} is an approved change ({it['approval']}), but the new build behaves exactly "
                             "like the old system — was the change built?")
        else:
            rec["status"] = "same" if same_all else "differs"
            if not same_all:
                errors.append(f"{pid} ({it['behaviour']}) differs from the old system — fix the new build, or record "
                              "an approved change in docs/02f-parity.md:\n    " + rec["diff"].replace("\n", "\n    ")[:1500])
        out[pid] = rec
    return out


def git_head():
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def run_meta(s: dict) -> dict:
    return {"run_id": s.get("run_id"), "commit": s.get("commit"), "finished_at": s.get("finished_at"),
            "base_url": (s.get("environment") or {}).get("base_url"), "parity_role": s.get("parity_role")}


def render(model: dict, errors: list, warns: list) -> str:
    c = model["counts"]
    L = ["# Parity with the old system", "",
         "<!-- Generated by compare_parity.py — do not edit by hand. -->", "",
         f"Old system: run `{model['old'].get('run_id')}` at {model['old'].get('base_url') or '—'} "
         f"({model['old'].get('finished_at') or '—'}) · New build: run `{model['new'].get('run_id')}` at "
         f"{model['new'].get('base_url') or '—'}, commit `{model['new'].get('commit') or '—'}`", "",
         f"**{c['same']}/{c['keep']} kept behaviours match** · {c['differs']} differ · {c['missing']} not compared · "
         f"{c['changed']} approved change(s) · {c['dropped']} dropped", "",
         "| ID | Behaviour | Decision | Result |", "|---|---|---|---|"]
    icon = {"same": "✅ same", "differs": "❌ differs", "unstable": "❌ unstable", "no baseline": "⚠️ no baseline",
            "not captured": "⚠️ not captured", "changed": "↻ changed (approved)",
            "change not seen": "⚠️ change not seen", "dropped": "— dropped (approved)"}
    for pid, it in model["items"].items():
        dec = it["decision"] + (f" — {it['approval']}" if it["approval"] else "")
        L.append(f"| {pid} | {it['behaviour']} | {dec} | {icon.get(it['status'], it['status'])} |")
    shown = [(p, it) for p, it in model["items"].items() if it.get("diff")]
    if shown:
        L += ["", "## Differences", ""]
        for p, it in shown:
            L += [f"### {p} · {it['behaviour']}", "", "```diff", it["diff"], "```", ""]
    if errors or warns:
        L += ["", "## Problems", ""] + [f"- ERROR: {e.splitlines()[0]}" for e in errors] + [f"- WARN: {w}" for w in warns]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare the old system with the new build (parity items).")
    ap.add_argument("--doc", default="docs/02f-parity.md")
    ap.add_argument("--old", default="baseline", help="'baseline' (default) or a run folder / summary.json")
    ap.add_argument("--new", default="latest", help="'latest' (default) or a run folder / summary.json")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--allow-same-url", action="store_true", help="only for a deliberate self-check")
    ap.add_argument("--report", default="docs/parity-report.md")
    ap.add_argument("--json", default=".harness/parity.json")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    errors, warns = [], []
    doc = read_doc(Path(args.doc), warns)
    if not doc:
        print(f"OK: no parity items ({args.doc} absent or empty) — nothing to compare")
        print("PARITY: " + json.dumps({"ok": True, "items": 0}))
        return 0
    old = load_run(args.old, errors, "old-system")
    new = load_run(args.new, errors, "new-build")
    if old is None or new is None:
        for e in errors:
            print(f"ERROR: {e}")
        print("PARITY: " + json.dumps({"ok": False, "items": len(doc), "errors": len(errors)}))
        return 1

    om, nm = run_meta(old), run_meta(new)
    if om["base_url"] and om["base_url"] == nm["base_url"] and not args.allow_same_url:
        errors.append(f"the old-system run and the new-build run both tested {om['base_url']} — that compares a "
                      "system with itself; run the baseline against the old system's URL")
    if om["parity_role"] != "old":
        (errors if args.gate else warns).append(
            f"the baseline run {om['run_id']} was not recorded with --parity old — make sure it tested the old system")
    head = git_head()
    if head and nm["commit"] and nm["commit"] != head:
        (errors if args.gate else warns).append(f"the new-build results are from commit {nm['commit']}, HEAD is {head} "
                                                "— rerun run_tests.py")

    ocap, odrop = captures(old)
    ncap, ndrop = captures(new)
    for x in odrop:
        warns.append(f"old system: {x}")
    for x in ndrop:
        warns.append(f"new build: {x}")
    for pid in sorted((set(ocap) | set(ncap)) - set(doc)):
        warns.append(f"tests captured {pid}, which docs/02f-parity.md does not define")

    items = compare(doc, ocap, ncap, args.gate, errors, warns)
    st = [it["status"] for it in items.values()]
    keep = [it for it in items.values() if it["decision"] == "keep"]
    counts = {"items": len(items), "keep": len(keep), "same": st.count("same"),
              "differs": st.count("differs") + st.count("unstable"),
              "missing": st.count("no baseline") + st.count("not captured"),
              "changed": st.count("changed") + st.count("change not seen"), "dropped": st.count("dropped")}
    model = {"schema": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "old": om, "new": nm, "items": items, "counts": counts,
             "all_kept_match": counts["same"] == counts["keep"] and not errors,
             "errors": len(errors), "warnings": len(warns)}
    if not args.no_write:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(model, indent=2, default=str))
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(render(model, errors, warns))

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"{'FAIL' if errors else 'OK'}: {counts['same']}/{counts['keep']} kept behaviours match the old system; "
          f"{counts['differs']} differ, {counts['missing']} not compared, {counts['changed']} approved change(s), "
          f"{counts['dropped']} dropped")
    print("PARITY: " + json.dumps({"ok": not errors, **counts, "errors": len(errors), "warnings": len(warns)}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
