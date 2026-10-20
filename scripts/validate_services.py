#!/usr/bin/env python3
"""Check that microservices stay independent, connected only by tested contracts.

Usage:
  python3 validate_services.py [--doc docs/03e-services.md] [--root .] [--gate]
                               [--arch .harness/architecture.json]
                               [--portability .harness/portability.json]
                               [--tests docs/02e-test-cases.md] [--json .harness/services.json]

v3.8. Runs only when the architecture decision is microservices
(.harness/architecture.json → style); otherwise prints SKIP and exits 0.
Reads docs/03e-services.md (template services.md) and checks:

  - every service owns its data, and no table belongs to two services;
  - every synchronous call has an http contract (provider = callee,
    consumer = caller); every consumed event has a publisher and an event
    contract;
  - no cycle of synchronous calls (a cycle means two services cannot be
    released or run alone);
  - every service has a standalone run (its own data store, stubs for what it
    calls);
  - every service that owns data has adapters, filled for local and for each
    production cloud in .harness/portability.json;
  - with --gate: every contract file exists and every contract's test case
    is in docs/02e-test-cases.md.

Contract ids (CT-xx) are also testable items for validate_product_map.py.
Writes .harness/services.json. Exit 1 on any ERROR. Last line: SERVICES: {json}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def filled(v: str) -> bool:
    v = (v or "").strip()
    return bool(v) and not v.startswith("<") and v not in ("…", "...", "-", "—", "TBD", "tbd")


def items(v: str) -> list:
    v = (v or "").strip()
    if not filled(v) or v.lower() in ("none", "n/a", "-"):
        return []
    return [x.strip().strip("`") for x in re.split(r"[,;]", v) if x.strip()]


def table(text: str, num: str, cols: int) -> list:
    parts = re.split(rf"^##\s+{num}\b.*$", text, flags=re.MULTILINE)
    if len(parts) < 2:
        return []
    out = []
    for line in parts[1].split("\n## ")[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.strip().startswith("|") or len(cells) < cols or set(cells[0]) <= set("-: "):
            continue
        out.append(cells[:cols])
    return out[1:] if out else []         # drop the header row


def cycles(edges: dict) -> list:
    found, state = [], {}

    def dfs(n, path):
        state[n] = 1
        for m in edges.get(n, []):
            if state.get(m) == 1:
                cyc = path[path.index(m):] + [m] if m in path else [n, m]
                if sorted(cyc) not in [sorted(c) for c in found]:
                    found.append(cyc)
            elif not state.get(m):
                dfs(m, path + [m])
        state[n] = 2
    for n in list(edges):
        if not state.get(n):
            dfs(n, [n])
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the microservices catalogue.")
    ap.add_argument("--doc", default="docs/03e-services.md")
    ap.add_argument("--root", default=".")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--force", action="store_true", help="validate even if the decision is not microservices")
    ap.add_argument("--arch", default=".harness/architecture.json")
    ap.add_argument("--portability", default=".harness/portability.json")
    ap.add_argument("--tests", default="docs/02e-test-cases.md")
    ap.add_argument("--json", default=".harness/services.json")
    a = ap.parse_args()

    try:
        style = json.loads(Path(a.arch).read_text()).get("style")
    except (OSError, ValueError):
        style = None
    if style != "microservices" and not a.force:
        print(f"SKIP: architecture style is {style or 'not decided'} — services are checked only for microservices")
        print("SERVICES: " + json.dumps({"skipped": True, "style": style}))
        return 0
    try:
        text = Path(a.doc).read_text()
    except OSError:
        print(f"ERROR: {a.doc} not found — the solution-architect writes it from .harness/templates/services.md")
        print("SERVICES: " + json.dumps({"ok": False}))
        return 1
    try:
        clouds = json.loads(Path(a.portability).read_text()).get("production_clouds") or []
    except (OSError, ValueError):
        clouds = []
    try:
        tests_md = Path(a.tests).read_text()
    except OSError:
        tests_md = ""
    errors, warns = [], []
    gate_or_warn = errors if a.gate else warns

    svcs = {}
    for c in table(text, "01", 7):
        name = c[0].strip("`")
        if name.startswith("<"):
            errors.append("services table: replace the template rows")
            continue
        svcs[name] = {"responsibility": c[1], "owns": items(c[2]), "calls": items(c[3]),
                      "publishes": items(c[4]), "consumes": items(c[5]), "standalone": c[6]}
    if len(svcs) < 2:
        errors.append("microservices need at least two services in section 01")

    owner = {}
    for n, s in svcs.items():
        if not filled(s["responsibility"]):
            errors.append(f"{n}: state its responsibility")
        if not s["owns"]:
            warns.append(f"{n}: owns no data — fine for a stateless service, otherwise list its tables")
        for t in s["owns"]:
            if t in owner:
                errors.append(f"data '{t}' is owned by both {owner[t]} and {n}: one owner per table "
                              "(the other reads it through the owner's API or events)")
            owner.setdefault(t, n)
        if not filled(s["standalone"]):
            errors.append(f"{n}: describe how it runs standalone (own data store, stubs for what it calls)")
        for callee in s["calls"]:
            if callee not in svcs:
                errors.append(f"{n} calls '{callee}', which is not a service in section 01")

    contracts = []
    for c in table(text, "02", 6):
        cid = c[0].strip("`")
        if not re.fullmatch(r"CT-\d+", cid):
            if cid.startswith("<"):
                errors.append("contracts table: replace the template rows")
            continue
        contracts.append({"id": cid, "provider": c[1].strip("`"), "consumer": c[2].strip("`"), "kind": c[3],
                          "file": c[4].strip("`"), "test_case": c[5]})
    for ct in contracts:
        for role in ("provider", "consumer"):
            if ct[role] not in svcs:
                errors.append(f"{ct['id']}: {role} '{ct[role]}' is not a service")
        if not filled(ct["file"]):
            errors.append(f"{ct['id']}: name the contract file (OpenAPI / AsyncAPI / event schema)")
        elif not (Path(a.root) / ct["file"]).is_file():
            gate_or_warn.append(f"{ct['id']}: contract file {ct['file']} does not exist yet")
        tc = re.search(r"TC-\d+", ct["test_case"] or "")
        if not tc:
            errors.append(f"{ct['id']}: name the test case that checks it (TC-xx)")
        elif tests_md and not re.search(rf"\b{tc.group(0)}\b", tests_md):
            gate_or_warn.append(f"{ct['id']}: {tc.group(0)} is not in {a.tests}")
        elif not tests_md:
            gate_or_warn.append(f"{ct['id']}: no test cases document to check {tc.group(0)} against")

    def has(provider, consumer, kind):
        return any(c["provider"] == provider and c["consumer"] == consumer and kind in c["kind"].lower()
                   for c in contracts)
    for n, s in svcs.items():
        for callee in s["calls"]:
            if callee in svcs and not has(callee, n, "http"):
                errors.append(f"{n} → {callee}: synchronous call with no http contract (CT-xx)")
        for ev in s["consumes"]:
            pubs = [p for p, ps in svcs.items() if ev in ps["publishes"]]
            if not pubs:
                errors.append(f"{n} consumes '{ev}', which no service publishes")
            elif not any(has(p, n, "event") for p in pubs):
                errors.append(f"{n} consumes '{ev}' with no event contract (CT-xx)")

    edges = {n: [c for c in s["calls"] if c in svcs] for n, s in svcs.items()}
    for cyc in cycles(edges):
        errors.append("synchronous call cycle " + " → ".join(cyc) +
                      ": neither side can run or release alone — break it with an event or merge the services")

    adapters = {}
    for c in table(text, "03", 7):
        if c[0].startswith("<"):
            continue
        adapters.setdefault(c[0].strip("`"), []).append(dict(zip(["block", "port", "local", "aws", "azure", "gcp"], c[1:7])))
    for n, s in svcs.items():
        rows = adapters.get(n, [])
        if s["owns"] and not rows:
            errors.append(f"{n} owns data but has no adapter rows (section 03)")
        for r in rows:
            if not filled(r["port"]):
                errors.append(f"{n}/{r['block']}: name the port (the interface in the code)")
            if not filled(r["local"]):
                errors.append(f"{n}/{r['block']}: no local adapter — the service could not run standalone")
            for cl in clouds:
                if not filled(r.get(cl, "")) or r.get(cl, "").lower() == "n/a":
                    errors.append(f"{n}/{r['block']}: no {cl.upper()} adapter, but {cl} is a production cloud")
    if not clouds:
        warns.append("no portability decision yet (.harness/portability.json): cloud adapters not checked")

    for w in warns:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    out = {"ok": not errors, "services": sorted(svcs), "contracts": [c["id"] for c in contracts],
           "sync_edges": sum(len(v) for v in edges.values()), "production_clouds": clouds}
    try:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({**out, "detail": svcs, "contract_detail": contracts}, indent=2) + "\n")
    except OSError:
        pass
    print(f"{'OK' if not errors else 'FAIL'}: {len(svcs)} services, {len(contracts)} contracts, "
          f"{out['sync_edges']} synchronous calls, {len(errors)} error(s)")
    print("SERVICES: " + json.dumps(out))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
