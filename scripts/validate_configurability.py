#!/usr/bin/env python3
"""Gate the configurable decisions: which choices become settings, and are they tested (v4.0).

Usage:
  python3 validate_configurability.py [--doc docs/03f-configuration.md]
        [--test-cases docs/02e-test-cases.md] [--product-map .harness/product-map.json]
        [--json .harness/configuration.json] [--threshold 15] [--max-settings 12]
        [--require-tests] [--gate] [--today YYYY-MM-DD]

The solution-architect writes docs/03f-configuration.md (template
configuration.md): every decision with more than one sensible answer, typed
configure / prepare / decide-once, with the extra cost of building every option
and whether it splits the data model; the USER decides each one. Decisions
decided as configure become settings (default, allowed values, who may change
them, owner, review date, a test case per allowed value); decisions decided as
prepare name the connection point and the cost to switch later.

Checks: the recommendation follows the rule (configure only when the extra cost
is at most --threshold percent and the data model is not split; the user may
override, which is recorded as a warning); every configure decision has a
setting; defaults are allowed values; every allowed value has a test case and
the test cases exist; prepared options are complete; many settings or many
combinations without a pairwise plan are warned about.

Order (asdr Phase 1 step 6c): the architect drafts, the user decides, then the
business-analyst adds the per-value test cases. Until then a setting without
its test cases is WAITING (exit 2), not an error; --require-tests (after the
business-analyst) and --gate make it an error.

--gate (release): a pending decision, a review date in the past, or a setting
test case not passing in the latest results (.harness/product-map.json) fails.
A project designed before 4.0 has no docs/03f-configuration.md; --gate then
SKIPs with exit 0 (a 4.0 design always writes it). That includes a run
resumed under 4.0 that began earlier (.harness/entry.json start "resume",
began_before "4.0", the register among its optional legacy_gaps) whose
user chose not to write it.

Exit 0  decided and complete -> writes .harness/configuration.json
Exit 2  waiting for the user's decisions, or for the business-analyst's tests
Exit 1  ERROR lines: the architect must fix the document
Last line: CONFIG: {json}.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

TYPES = ("configure", "prepare", "decide-once")
TC_RX = re.compile(r"\bTC-\d+\b")


def filled(v: str) -> bool:
    v = (v or "").strip()
    return bool(v) and not v.startswith("<") and v not in ("…", "...", "-", "—", "TBD", "tbd")


def placeholder(cells) -> bool:
    return any((c or "").strip().startswith("<") for c in cells)


def section(text: str, num: str) -> str:
    m = re.search(rf"^##\s*{num}\b.*?$(.*?)(?=^##\s*\d|\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def rows(body: str) -> list:
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        out.append(cells)
    return out[1:] if out else []            # drop the header row


def norm_type(v: str) -> str:
    v = (v or "").strip().lower().replace(" ", "-")
    return v if v in TYPES else ""


def pct_of(v: str):
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", v or "")]
    return max(nums) if nums else None


def yes(v: str):
    v = (v or "").strip().lower()
    return True if v.startswith("y") else False if v.startswith("n") else None


def values_of(v: str):
    """('list', [...]) or ('range', (lo, hi)) or (None, None)."""
    v = (v or "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)", v)
    if m:
        return "range", (float(m.group(1)), float(m.group(2)))
    vals = [x.strip() for x in re.split(r"[,;]", v) if x.strip()]
    return ("list", vals) if vals else (None, None)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the configurable decisions and their settings.")
    ap.add_argument("--doc", default="docs/03f-configuration.md")
    ap.add_argument("--test-cases", default="docs/02e-test-cases.md")
    ap.add_argument("--product-map", default=".harness/product-map.json")
    ap.add_argument("--json", default=".harness/configuration.json")
    ap.add_argument("--threshold", type=float, default=15.0, help="max extra cost (%%) to recommend configure")
    ap.add_argument("--max-settings", type=int, default=12)
    ap.add_argument("--harness", default=".harness")
    ap.add_argument("--require-tests", action="store_true",
                    help="after the business-analyst step: every allowed value must have its test case")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--today", type=dt.date.fromisoformat, help="YYYY-MM-DD (default: today)")
    a = ap.parse_args()
    today = a.today or dt.date.today()
    need_tests = a.require_tests or a.gate
    try:
        text = Path(a.doc).read_text()
    except OSError:
        v4 = any(Path(a.harness, f).exists() for f in ("entry.json", "models.json"))
        try:
            entry = json.loads(Path(a.harness, "entry.json").read_text())
        except (OSError, ValueError):
            entry = {}
        entry = entry if isinstance(entry, dict) else {}
        gaps = entry.get("legacy_gaps") if isinstance(entry.get("legacy_gaps"), list) else []
        resumed_legacy = (entry.get("start") == "resume" and bool(entry.get("began_before")) and any(
            isinstance(g, dict) and str(g.get("path", "")).endswith("03f-configuration.md")
            and g.get("kind", "optional") == "optional" for g in gaps))
        if a.gate and (not v4 or resumed_legacy):
            print(f"SKIP: {a.doc} not found — a project designed before 4.0 has no configurable decisions"
                  + (" (resumed under 4.0; the user did not write the register)" if resumed_legacy else ""))
            print("CONFIG: " + json.dumps({"ok": True, "decided": True, "skipped": True}))
            return 0
        print(f"ERROR: {a.doc} not found — the solution-architect writes it from "
              ".harness/templates/configuration.md in design (Phase 1 step 6c)")
        print("CONFIG: " + json.dumps({"ok": False, "decided": False}))
        return 1
    errors, warns, waiting = [], [], []
    try:
        tc_text = Path(a.test_cases).read_text()
        known_tcs = set(re.findall(r"\bTC-\d+\b", tc_text))
    except OSError:
        known_tcs = None
        (errors if need_tests else warns).append(f"{a.test_cases} not found — test case ids cannot be checked")
    if not re.search(r"^##\s*02\b", text, re.MULTILINE):
        errors.append("no decision register (section '## 02 · Decision register') — write the document from "
                      ".harness/templates/configuration.md")

    # 02 decision register
    decisions, pending = {}, []
    for cells in rows(section(text, "02")):
        cells += [""] * (9 - len(cells))
        did, what, opts, rec, extra, split, why, by, dec = cells[:9]
        if placeholder(cells):
            errors.append(f"{did or 'decision row'}: still has template placeholders (<…>) — fill it or delete it")
            continue
        if not re.fullmatch(r"DEC-\d+", did):
            errors.append(f"decision id '{did}': use DEC-01, DEC-02, …")
            continue
        if did in decisions:
            errors.append(f"{did}: listed twice")
            continue
        n_opts = len([x for x in re.split(r";|\bor\b", opts) if x.strip()])
        if n_opts < 2:
            errors.append(f"{did}: needs at least two options, separated by ';' (found '{opts}')")
        r = norm_type(rec)
        if not r:
            errors.append(f"{did}: type recommended must be configure, prepare or decide-once (found '{rec}')")
        p = pct_of(extra)
        sp = yes(split)
        if sp is None:
            errors.append(f"{did}: 'Splits the data model?' must be yes or no")
        if r == "configure":
            if p is None:
                errors.append(f"{did}: state the extra cost of building all options as a percentage")
            elif p > a.threshold:
                errors.append(f"{did}: recommended configure but building all options adds {p:g}% "
                              f"(rule: at most {a.threshold:g}%) — recommend prepare or decide-once")
            if sp:
                errors.append(f"{did}: recommended configure but it splits the data model — recommend decide-once or prepare")
        if not filled(why):
            errors.append(f"{did}: say why in one line")
        if (dec or "").strip().lower() == "pending":
            dec = ""
        d = norm_type(dec)
        if filled(dec) and not d:
            errors.append(f"{did}: the decision must be configure, prepare or decide-once (found '{dec}')")
        if d and not filled(by):
            errors.append(f"{did}: decided but 'Decided by' is empty — record who decided and when")
        if not d and not filled(dec):
            pending.append(did)
        if d == "configure" and ((p is not None and p > a.threshold) or sp):
            warns.append(f"{did}: configure chosen against the rule ({'splits the data model' if sp else f'{p:g}% extra'}) "
                         f"— the user's override is recorded")
        decisions[did] = {"id": did, "decision": what, "options": n_opts, "recommended": r, "extra_pct": p,
                          "splits_data_model": sp, "decided": d or None, "decided_by": by if filled(by) else None}

    # 03 settings
    settings, combos, tc_needed = {}, 1, {}
    for cells in rows(section(text, "03")):
        cells += [""] * (10 - len(cells))
        cid, dref, key, default, allowed, who, effect, owner, review, tests = cells[:10]
        if placeholder(cells):
            errors.append(f"{cid or 'setting row'}: still has template placeholders (<…>) — fill it or delete it")
            continue
        if not re.fullmatch(r"CFG-\d+", cid):
            errors.append(f"setting id '{cid}': use CFG-01, CFG-02, …")
            continue
        if cid in settings:
            errors.append(f"{cid}: listed twice")
            continue
        dd = decisions.get(dref)
        if not dd:
            errors.append(f"{cid}: decision '{dref}' is not in the register")
        elif dd["decided"] and dd["decided"] != "configure":
            errors.append(f"{cid}: {dref} was decided as {dd['decided']}, not configure — remove the setting")
        for name, v in (("setting key", key), ("who can change it", who), ("takes effect", effect), ("owner", owner)):
            if not filled(v):
                errors.append(f"{cid}: {name} is empty")
        kind, vals = values_of(allowed)
        n_vals = 0
        if kind == "list":
            n_vals = len(vals)
            if n_vals < 2:
                errors.append(f"{cid}: a setting needs at least two allowed values")
            if default.strip() not in vals:
                errors.append(f"{cid}: default '{default}' is not one of the allowed values ({allowed})")
        elif kind == "range":
            lo, hi = vals
            try:
                dv = float(default)
                if not lo <= dv <= hi:
                    errors.append(f"{cid}: default {default} is outside the range {allowed}")
                n_vals = len({lo, hi, dv})
            except ValueError:
                errors.append(f"{cid}: default '{default}' is not a number in the range {allowed}")
                n_vals = 2
        else:
            errors.append(f"{cid}: allowed values must be a comma-separated list or a range min..max")
        combos *= max(n_vals, 1)
        try:
            rd = dt.date.fromisoformat(review.strip())
            if rd < today:
                (errors if a.gate else warns).append(f"{cid}: review date {rd} has passed — keep it (new date), "
                                                      "make the value permanent or remove the setting")
        except ValueError:
            rd = None
            errors.append(f"{cid}: review by must be a date YYYY-MM-DD (found '{review}')")
        tcs = sorted(set(TC_RX.findall(tests)))
        if len(tcs) < n_vals:
            msg = (f"{cid}: {len(tcs)} test case(s) for {n_vals} value(s) to test — one per allowed value"
                   + (" (a range: minimum, maximum and default)" if kind == "range" else ""))
            if need_tests:
                errors.append(msg)
            else:
                waiting.append(msg + " (the business-analyst adds them after the user decides)")
        if known_tcs is not None:
            for t in tcs:
                if t not in known_tcs:
                    errors.append(f"{cid}: {t} is not in {a.test_cases}")
        tc_needed[cid] = tcs
        settings[cid] = {"id": cid, "decision": dref, "key": key, "default": default, "values": n_vals,
                         "who": who, "owner": owner, "review_by": str(rd) if rd else None, "tests": tcs}
    for did, dd in decisions.items():
        if dd["decided"] == "configure" and not any(s["decision"] == did for s in settings.values()):
            errors.append(f"{did}: decided as configure but has no setting in section 03")

    # 04 prepared options
    prepared = {}
    for cells in rows(section(text, "04")):
        cells += [""] * (5 - len(cells))
        dref, now, later, point, switch = cells[:5]
        if placeholder(cells):
            errors.append(f"{dref or 'prepared row'}: still has template placeholders (<…>) — fill it or delete it")
            continue
        for name, v in (("built now", now), ("prepared for", later), ("connection point", point),
                        ("cost to switch later", switch)):
            if not filled(v):
                errors.append(f"{dref}: {name} is empty")
        dd = decisions.get(dref)
        if not dd:
            errors.append(f"section 04 names '{dref}', which is not in the register")
        elif dd["decided"] and dd["decided"] != "prepare":
            errors.append(f"section 04: {dref} was decided as {dd['decided']}, not prepare — remove the row")
        prepared[dref] = {"decision": dref, "built_now": now, "prepared_for": later, "connection_point": point,
                          "switch_cost": switch}
    for did, dd in decisions.items():
        if dd["decided"] == "prepare" and did not in prepared:
            errors.append(f"{did}: decided as prepare but section 04 does not say what is built now, the "
                          "connection point and the cost to switch")

    # 05 interactions
    inter = []
    for cells in rows(section(text, "05")):
        if placeholder(cells) or not cells or not cells[0]:
            continue
        ids = re.findall(r"CFG-\d+", cells[0])
        for i in ids:
            if i not in settings:
                errors.append(f"section 05 names {i}, which is not a setting")
        inter.append(ids)
    if len(settings) > a.max_settings:
        warns.append(f"{len(settings)} settings — each one is a permanent cost to test and support; "
                     f"the critic should challenge anything above {a.max_settings}")
    if combos > 64 and not inter:
        warns.append(f"{combos} combinations of setting values — list the settings that interact (section 05) "
                     "and test those pairwise instead of every combination")

    # gate: the settings' test cases pass in the latest results
    if a.gate:
        for did in pending:
            errors.append(f"{did}: still undecided at the release gate — the user decides before release")
        states = None
        try:
            pm = json.loads(Path(a.product_map).read_text())
            tcs_ = pm.get("test_cases") if isinstance(pm, dict) else None
            if isinstance(tcs_, dict):
                states = {k: (v.get("state") if isinstance(v, dict) else None) for k, v in tcs_.items()}
            else:
                errors.append(f"{a.product_map} has no test_cases; run validate_product_map.py --results latest")
        except (OSError, ValueError):
            errors.append(f"--gate needs {a.product_map}; run validate_product_map.py --results latest first")
        if states is not None:
            for cid, tcs in tc_needed.items():
                bad = [t for t in tcs if states.get(t) not in ("passed", "manual")]
                if bad:
                    errors.append(f"{cid}: test case(s) not passing in the latest results: {', '.join(bad)}")
                manual = [t for t in tcs if states.get(t) == "manual"]
                if manual:
                    warns.append(f"{cid}: {', '.join(manual)} checked by hand, not by an automated test")

    for e in errors:
        print(f"ERROR: {e}")
    for w in warns:
        print(f"WARN: {w}")
    for w in waiting:
        print(f"WAITING: {w}")
    by_type = {t: sum(1 for d in decisions.values() if d["decided"] == t) for t in TYPES}
    summary = {"ok": not errors, "decided": not pending, "pending": pending, "waiting": len(waiting),
               "decisions": len(decisions),
               "by_type": by_type, "settings": len(settings), "combinations": combos if settings else 0,
               "overdue": [s["id"] for s in settings.values() if s["review_by"] and s["review_by"] < str(today)]}
    if not errors and not pending and not waiting:
        try:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(json.dumps({**summary, "decision_list": list(decisions.values()),
                                                "setting_list": list(settings.values()),
                                                "prepared_list": list(prepared.values())}, indent=2) + "\n")
        except OSError as ex:
            print(f"WARN: could not write {a.json}: {ex}")
    if not errors:
        if pending:
            print(f"Waiting for the user's decision on: {', '.join(pending)}")
        elif waiting:
            print("Decided; waiting for the business-analyst's test cases (then run with --require-tests).")
        elif not decisions:
            print("No decision with more than one sensible answer recorded; the critic confirms that is true.")
        else:
            print(f"{len(decisions)} decision(s): {by_type['configure']} configure, {by_type['prepare']} prepare, "
                  f"{by_type['decide-once']} decide-once; {len(settings)} setting(s).")
    print("CONFIG: " + json.dumps(summary))
    return 1 if errors else (2 if pending or waiting else 0)


if __name__ == "__main__":
    sys.exit(main())
