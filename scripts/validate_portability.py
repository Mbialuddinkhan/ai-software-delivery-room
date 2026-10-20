#!/usr/bin/env python3
"""Gate the portability decision: which building blocks, which strategy, which clouds.

Usage:
  python3 validate_portability.py [--doc docs/03d-portability.md]
                                  [--catalogue .harness/templates/cloud/catalogue.json]
                                  [--cloud .harness/cloud.json] [--json .harness/portability.json]

v3.8. devops writes docs/03d-portability.md (template portability.md) after the
architecture decision: the building blocks the product needs with the portable
choice, the native service on AWS, Azure and GCP and a local stand-in; at least
two strategies with pros, cons, business impact and monthly run cost; a cost
comparison with stated assumptions and pricing source; a recommendation; and
the USER's decision. As portable as possible — but the user decides, knowing
the cost.

Exit 0  decided → writes .harness/portability.json (strategy, production clouds,
        test cloud, blocks) for devops, validate_services.py and the dashboard
Exit 2  complete, waiting for the user's decision
Exit 1  ERROR lines
Last line: PORTABILITY: {json}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CLOUDS = ("aws", "azure", "gcp")
FIELDS = ["Pros", "Cons", "Business impact", "Monthly run cost"]


def filled(v: str) -> bool:
    v = (v or "").strip()
    return bool(v) and not v.startswith("<") and v not in ("…", "...", "-", "—", "TBD", "tbd")


def bullet(body: str, name: str) -> str:
    m = re.search(rf"^\s*-\s*{re.escape(name)}\s*:\s*(.*)$", body, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def section(text: str, num: str) -> str:
    parts = re.split(rf"^##\s+{num}\b.*$", text, flags=re.MULTILINE)
    return parts[1].split("\n## ")[0] if len(parts) > 1 else ""


def clouds_in(v: str) -> list:
    v = v.lower().replace("google cloud", "gcp")
    return [c for c in CLOUDS if re.search(rf"\b{c}\b", v)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the portability and cloud decision.")
    ap.add_argument("--doc", default="docs/03d-portability.md")
    ap.add_argument("--catalogue", default=".harness/templates/cloud/catalogue.json")
    ap.add_argument("--cloud", default=".harness/cloud.json")
    ap.add_argument("--json", default=".harness/portability.json")
    a = ap.parse_args()
    try:
        text = Path(a.doc).read_text()
    except OSError:
        print(f"ERROR: {a.doc} not found — devops writes it from .harness/templates/portability.md")
        print("PORTABILITY: " + json.dumps({"ok": False, "decided": False}))
        return 1
    try:
        catalogue = json.loads(Path(a.catalogue).read_text()).get("blocks", {})
    except (OSError, ValueError):
        catalogue = {}
    try:
        test_cloud = json.loads(Path(a.cloud).read_text()).get("test_cloud")
    except (OSError, ValueError):
        test_cloud = None
    errors, warns = [], []

    dec = re.search(r"^\s*-\s*Decision:\s*\**\s*([A-Za-z0-9]+)", text, re.MULTILINE)
    prod = re.search(r"^\s*-\s*Production cloud\(s\):\s*(.*)$", text, re.MULTILINE)
    prod_clouds = clouds_in(prod.group(1)) if prod and filled(prod.group(1)) else []
    scope = prod_clouds or list(CLOUDS)

    blocks = {}
    for line in section(text, "01").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0] in ("Block", "") or set(cells[0]) <= set("-: "):
            continue
        name = cells[0].strip("`")
        if name.startswith("<"):
            errors.append("building blocks table: replace the template row")
            continue
        if catalogue and name not in catalogue:
            warns.append(f"block '{name}' is not in the catalogue — check the name or add it there")
        row = dict(zip(["need", "portable", "aws", "azure", "gcp", "local"], cells[1:7]))
        for k in ("need", "portable", "local"):
            if not filled(row[k]):
                errors.append(f"block '{name}': '{k}' is empty")
        for c in scope:
            if not filled(row[c]) and row[c].lower() != "n/a":
                errors.append(f"block '{name}': no {c.upper()} service")
        blocks[name] = row
    if not blocks:
        errors.append("list the building blocks this product needs (section 01)")

    strategies = {}
    parts = re.split(r"^###\s+(S\d)\s*[—–-]\s*(.*)$", text, flags=re.MULTILINE)
    for i in range(1, len(parts) - 2, 3):
        sid, title, body = parts[i], parts[i + 1].strip(), parts[i + 2].split("\n## ")[0]
        vals = {f: bullet(body, f) for f in FIELDS}
        empty = [f for f, v in vals.items() if not filled(v)]
        if len(empty) == len(FIELDS):
            errors.append(f"{sid} ({title}) is still the template: fill it or delete it")
            continue
        errors += [f"{sid}: '{f}' is empty" for f in empty]
        if filled(vals["Monthly run cost"]) and not re.search(r"\d", vals["Monthly run cost"]):
            errors.append(f"{sid}: 'Monthly run cost' needs figures (ranges), labelled as estimates")
        strategies[sid] = title
    if len(strategies) < 2:
        errors.append("compare at least two strategies")

    cmp_ = section(text, "03")
    rows = [r for r in cmp_.splitlines() if r.startswith("|") and not r.startswith("|---")][1:]
    if len(rows) < 2:
        errors.append("cost comparison table: at least two strategies")
    elif any(c.strip().startswith("<") for r in rows for c in r.split("|")[2:-1]):
        errors.append("cost comparison table has unfilled cells")
    src = re.search(r"Prices from:\s*(.*)", cmp_)
    if not src or not filled(src.group(1)) or not re.search(r"20\d\d", src.group(1)):
        errors.append("say where the prices came from and when (tool or calculator, date)")
    asm = re.search(r"Assumptions:\s*(.*)", cmp_)
    if not asm or not filled(asm.group(1)):
        errors.append("state the assumptions behind the costs")

    rec = re.search(r"Recommended:\s*\**\s*(S\d)\b", text)
    if not rec or rec.group(1) not in strategies:
        errors.append("the recommendation must name one of the strategies")
    by = re.search(r"^\s*-\s*Decided by:\s*(.*)$", text, re.MULTILINE)
    decided = bool(dec and dec.group(1) in strategies)
    if dec and dec.group(1).lower() != "pending" and not decided:
        errors.append(f"Decision '{dec.group(1)}' is not one of the strategies")
    if decided:
        if not prod_clouds:
            errors.append("name the production cloud(s): aws, azure and/or gcp")
        if not (by and filled(by.group(1))):
            errors.append("record who decided and when (Decided by)")

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    res = {"ok": not errors, "decided": decided and not errors, "strategies": strategies,
           "recommended": rec.group(1) if rec else None, "blocks": sorted(blocks)}
    if errors:
        print("PORTABILITY: " + json.dumps(res))
        return 1
    if not decided:
        print(f"WAIT: complete — ask the user to choose (recommended: {res['recommended']}); "
              "log the answer with log_question.py --client")
        print("PORTABILITY: " + json.dumps(res))
        return 2
    out = {"strategy": dec.group(1), "title": strategies[dec.group(1)], "production_clouds": prod_clouds,
           "test_cloud": test_cloud, "decided_by": by.group(1).strip(), "recommended": res["recommended"],
           "blocks": blocks}
    if test_cloud and test_cloud != "none" and test_cloud not in prod_clouds:
        print(f"WARN: the test cloud ({test_cloud}) is not a production cloud — tests there prove less")
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(out, indent=2) + "\n")
    print(f"OK: {dec.group(1)} on {', '.join(prod_clouds)}; {len(blocks)} building blocks")
    print("PORTABILITY: " + json.dumps({**res, "strategy": out["strategy"], "production_clouds": prod_clouds}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
