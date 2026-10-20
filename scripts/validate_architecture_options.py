#!/usr/bin/env python3
"""Gate the architecture decision: monolith or microservices, chosen by the user.

Usage:
  python3 validate_architecture_options.py [--doc docs/03c-architecture-options.md]
                                           [--json .harness/architecture.json]

v3.8. The solution-architect writes docs/03c-architecture-options.md (template
architecture-options.md) before any design: criteria scored 0–2 with evidence,
each option with pros, cons, business impact, build and run cost (estimates)
and when it wins, a side-by-side table, a recommendation and the USER's
decision. This checks that the document can support a decision and records it.

Exit 0  decided and complete → writes .harness/architecture.json
        {"style": "modular-monolith|microservices|serverless", ...}
Exit 2  complete, waiting for the user's decision (ask them; do not design yet)
Exit 1  ERROR lines: the architect must fix the document

The criteria rule (8+ points with two of C1–C4 at 2 → microservices; 4–7 →
modular monolith with service-ready boundaries; ≤3 → modular monolith) is
checked against the recommendation; a mismatch is a warning the architect must
answer in writing. Last line: ARCH-OPTIONS: {json}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FIELDS = ["Pros", "Cons", "Business impact", "Build cost", "Run cost per month", "When it wins"]


def filled(v: str) -> bool:
    v = (v or "").strip()
    return bool(v) and not v.startswith("<") and v not in ("…", "...", "-", "—", "TBD", "tbd")


def style_of(title: str) -> str:
    t = title.lower()
    if "microservice" in t:
        return "microservices"
    if "serverless" in t:
        return "serverless"
    return "modular-monolith" if "monolith" in t else "other"


def bullet(body: str, name: str) -> str:
    m = re.search(rf"^\s*-\s*{re.escape(name)}\s*:\s*(.*)$", body, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the architecture options and the user's decision.")
    ap.add_argument("--doc", default="docs/03c-architecture-options.md")
    ap.add_argument("--json", default=".harness/architecture.json")
    a = ap.parse_args()
    try:
        text = Path(a.doc).read_text()
    except OSError:
        print(f"ERROR: {a.doc} not found — the solution-architect writes it from "
              ".harness/templates/architecture-options.md before any design")
        print("ARCH-OPTIONS: " + json.dumps({"ok": False, "decided": False}))
        return 1
    errors, warns = [], []

    scores = {}
    for m in re.finditer(r"^\|\s*(C\d)\s*\|[^|]*\|\s*([^|]*)\|\s*([^|]*)\|", text, re.MULTILINE):
        cid, sc, ev = m.group(1), m.group(2).strip(), m.group(3).strip()
        if not re.fullmatch(r"[012]", sc):
            errors.append(f"{cid}: score must be 0, 1 or 2 (found '{sc}')")
            continue
        scores[cid] = int(sc)
        if int(sc) > 0 and not filled(ev):
            errors.append(f"{cid}: a score above 0 needs evidence (document + quoted line)")
    if len(scores) < 8:
        errors.append(f"criteria table: {len(scores)} of C1–C8 scored")
    total = sum(scores.values())
    strong = sum(1 for c in ("C1", "C2", "C3", "C4") if scores.get(c) == 2)
    rule = ("microservices" if total >= 8 and strong >= 2 else
            "modular-monolith" if total >= 4 else "modular-monolith")

    options = {}
    parts = re.split(r"^###\s+Option\s+([A-Z])\s*[—–-]\s*(.*)$", text, flags=re.MULTILINE)
    for i in range(1, len(parts) - 2, 3):
        letter, title, body = parts[i], parts[i + 1].strip(), parts[i + 2].split("\n## ")[0]
        vals = {f: bullet(body, f) for f in FIELDS}
        empty = [f for f, v in vals.items() if not filled(v)]
        if len(empty) == len(FIELDS):
            errors.append(f"Option {letter} ({title}) is still the template: fill it or delete the section")
            continue
        for f in empty:
            errors.append(f"Option {letter}: '{f}' is empty")
        for f in ("Build cost", "Run cost per month"):
            if filled(vals[f]) and not re.search(r"\d", vals[f]):
                errors.append(f"Option {letter}: '{f}' needs a figure (a range), labelled as an estimate")
        options[letter] = {"title": title, "style": style_of(title)}
    if len(options) < 2:
        errors.append("at least two options must be compared")

    table = re.split(r"^##\s+03\b.*$", text, flags=re.MULTILINE)
    if len(table) > 1:
        rows = [r for r in table[1].split("\n## ")[0].splitlines() if r.startswith("|") and not r.startswith("|---")][1:]
        holes = [r.split("|")[1].strip() for r in rows if any(c.strip().startswith("<") for c in r.split("|")[2:-1])]
        if holes:
            errors.append(f"side-by-side table: unfilled rows: {', '.join(holes[:5])}")
        am = re.search(r"Assumptions behind the figures:\s*(.*)", table[1])
        if not am or not filled(am.group(1)):
            errors.append("state the assumptions behind the figures (load, team rate, pricing source and date)")
    else:
        errors.append("section 03 (side by side) is missing")

    rec = re.search(r"Recommended:\s*\**\s*([A-Z])\b", text)
    if not rec or rec.group(1) not in options:
        errors.append("the recommendation must name one of the options")
    elif options[rec.group(1)]["style"] != rule:
        warns.append(f"the recommendation ({options[rec.group(1)]['style']}) differs from the criteria rule "
                     f"({rule}, {total} points, {strong} of C1–C4 at 2): say why under the recommendation")

    dec = re.search(r"^\s*-\s*Decision:\s*\**\s*([A-Za-z]+)", text, re.MULTILINE)
    by = re.search(r"^\s*-\s*Decided by:\s*(.*)$", text, re.MULTILINE)
    decided = bool(dec and dec.group(1) in options)
    if dec and dec.group(1).lower() not in ("pending",) and dec.group(1) not in options:
        errors.append(f"Decision '{dec.group(1)}' is not one of the options")
    if decided and not (by and filled(by.group(1))):
        errors.append("record who decided and when (Decided by)")

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    res = {"ok": not errors, "decided": decided and not errors, "score": total, "rule": rule,
           "recommended": rec.group(1) if rec else None, "options": options}
    if errors:
        print("ARCH-OPTIONS: " + json.dumps(res))
        return 1
    if not decided:
        print(f"WAIT: complete — ask the user to choose (recommended: {res['recommended']}, "
              f"{options[res['recommended']]['title']}); log the answer with log_question.py --client")
        print("ARCH-OPTIONS: " + json.dumps(res))
        return 2
    choice = options[dec.group(1)]
    out = {"option": dec.group(1), "style": choice["style"], "title": choice["title"],
           "decided_by": by.group(1).strip(), "recommended": res["recommended"], "score": total, "rule": rule}
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    print(f"OK: decided {dec.group(1)} ({choice['style']}) by {out['decided_by']}; criteria {total} points → {rule}")
    print("ARCH-OPTIONS: " + json.dumps({**res, **out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
