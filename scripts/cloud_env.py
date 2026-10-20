#!/usr/bin/env python3
"""Ledger of temporary cloud test environments — so none is forgotten and left running.

Usage:
  python3 cloud_env.py create --name asdr-test-s3 --cloud aws --approved-by "Bilal, 2026-10-20"
                              [--url https://…] [--ttl-hours 8] [--stack <id or folder>] [--region …]
  python3 cloud_env.py destroyed --name asdr-test-s3 [--note "terraform destroy ok"]
  python3 cloud_env.py list [--overdue]

v3.8. devops records every test environment it creates on the test cloud and
every teardown, in .harness/cloud-envs.jsonl. `create` refuses without
--approved-by: a deploy happens only after the user said yes. `list` shows
what is still running and what is past its time-to-live; the dashboard shows
the same and marks the project "at risk" while one is overdue (it is costing
money), and the release gate refuses while any test environment is still up.

Exit codes: list --overdue → 1 when any environment is past its time-to-live.
Last line: CLOUD-ENVS: {json}.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

LEDGER = Path(".harness/cloud-envs.jsonl")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load(path: Path) -> list:
    out = []
    try:
        for line in path.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def live(events: list, at: dt.datetime) -> list:
    envs = {}
    for ev in events:
        if ev.get("event") == "create":
            envs[ev["name"]] = dict(ev)
        elif ev.get("event") == "destroyed":
            envs.pop(ev.get("name"), None)
    out = []
    for e in envs.values():
        try:
            created = dt.datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            created = at
        expires = created + dt.timedelta(hours=float(e.get("ttl_hours") or 8))
        out.append({**e, "expires": expires.isoformat(timespec="seconds"), "overdue": at > expires,
                    "hours_left": round((expires - at).total_seconds() / 3600, 1)})
    return sorted(out, key=lambda x: x["expires"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Record cloud test environments and their teardown.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--cloud", required=True, choices=["aws", "azure", "gcp"])
    c.add_argument("--approved-by", required=True, help="who said yes to this deploy, and when")
    c.add_argument("--url", default="")
    c.add_argument("--ttl-hours", type=float, default=8)
    c.add_argument("--stack", default="", help="what to destroy: a Terraform folder/workspace, stack or resource group")
    c.add_argument("--region", default="")
    d = sub.add_parser("destroyed")
    d.add_argument("--name", required=True)
    d.add_argument("--note", default="")
    lst = sub.add_parser("list")
    lst.add_argument("--overdue", action="store_true")
    for p in (c, d, lst):
        p.add_argument("--ledger", default=str(LEDGER))
    a = ap.parse_args()
    path = Path(a.ledger)
    events = load(path)
    at = now()

    if a.cmd in ("create", "destroyed"):
        if a.cmd == "create":
            if not a.approved_by.strip() or a.approved_by.strip().startswith("<"):
                print("ERROR: --approved-by must name who approved this deploy and when")
                return 1
            if any(e["name"] == a.name for e in live(events, at)):
                print(f"ERROR: {a.name} is already running — destroy it or use another name")
                return 1
            ev = {"ts": at.isoformat(timespec="seconds"), "event": "create", "name": a.name, "cloud": a.cloud,
                  "url": a.url, "ttl_hours": a.ttl_hours, "stack": a.stack, "region": a.region,
                  "approved_by": a.approved_by}
        else:
            if not any(e["name"] == a.name for e in live(events, at)):
                print(f"WARN: {a.name} is not recorded as running")
            ev = {"ts": at.isoformat(timespec="seconds"), "event": "destroyed", "name": a.name, "note": a.note}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        events.append(ev)
        print(f"OK: {a.cmd} {a.name}")

    running = live(events, at)
    overdue = [e for e in running if e["overdue"]]
    for e in running:
        print(f"{'OVERDUE' if e['overdue'] else 'running'}: {e['name']} on {e['cloud']} "
              f"({'expired' if e['overdue'] else str(e['hours_left']) + ' h left'}; destroy: {e.get('stack') or 'see devops notes'})")
    if not running and a.cmd == "list":
        print("No test environments running.")
    print("CLOUD-ENVS: " + json.dumps({"running": [e["name"] for e in running], "overdue": [e["name"] for e in overdue]}))
    return 1 if (a.cmd == "list" and a.overdue and overdue) else 0


if __name__ == "__main__":
    sys.exit(main())
