#!/usr/bin/env python3
"""Set the delivery profile: founder (validate fast, cheap) or enterprise.

Usage:
  python3 set_profile.py founder [--rationale "pre-seed, one buyer committed"]
  python3 set_profile.py enterprise [--rationale "…"]
  python3 set_profile.py show

v4.2 (brief 7.2). The founder profile is for the university-founder /
pre-seed audience: prove a demo-able slice to a buyer in one sprint, spend
as little as possible doing it, and keep the upgrade path documented. It is
a named bundle over knobs that already exist — not a different harness:

  founder     rigor=lite, model plan=economy, scope note "buyer-justified
              first" (hypothesis items deferred unless the contract says
              otherwise), and the asdr start recommendation leans Validate/Build.
  enterprise  rigor=standard, model plan=balanced — the defaults; everything
              the release gate checks stays on.

What founder mode does NOT change: the evaluator still signs off every
sprint, the secrets gate still runs, no-go still stops the run. Cheap never
means unreviewed. Upgrading later is one command: `set_profile.py enterprise`
(already-approved documents are not redone; the next stages simply run at
the higher setting).

Writes .harness/profile.json, applies the rigor to .harness/progress.json and
the plan via model_plan.py, and logs the choice to docs/decision-log.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROFILES = {
    "founder": {"rigor": "lite", "plan": "economy",
                "scope": "buyer-justified-first",
                "deliverable": "demo-able slice in one sprint"},
    "enterprise": {"rigor": "standard", "plan": "balanced",
                   "scope": "full", "deliverable": "release-gated build"},
}
SCRIPTS = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", choices=["founder", "enterprise", "show"])
    ap.add_argument("--rationale", default="")
    args = ap.parse_args()

    pj = Path(".harness/profile.json")
    if args.profile == "show":
        if pj.exists():
            print(pj.read_text().strip())
        else:
            print('{"profile": "enterprise", "source": "default (no profile set)"}')
        return 0

    spec = PROFILES[args.profile]
    pj.parent.mkdir(parents=True, exist_ok=True)
    pj.write_text(json.dumps({"profile": args.profile, **spec,
                              "rationale": args.rationale}, indent=2) + "\n")

    # Rigor into progress.json (create a minimal one when none exists yet).
    pr = Path(".harness/progress.json")
    try:
        prog = json.loads(pr.read_text())
    except (OSError, ValueError):
        prog = {}
    prog["rigor"] = spec["rigor"]
    pr.write_text(json.dumps(prog, indent=2) + "\n")

    # Model plan via the existing tool; its absence is reported, not fatal.
    mp = SCRIPTS / "model_plan.py"
    if mp.exists():
        r = subprocess.run([sys.executable, str(mp), "set", "--plan", spec["plan"]],
                           capture_output=True, text=True)
        print((r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "")
    else:
        print(f"WARN: {mp} not found — set the model plan by hand")

    dl = SCRIPTS / "decision_log.py"
    if dl.exists():
        subprocess.run([sys.executable, str(dl), "add",
                        "--decision", "Delivery profile",
                        "--options", "founder|enterprise",
                        "--chosen", args.profile,
                        "--rationale", args.rationale or f"{spec['deliverable']}",
                        "--source", ".harness/profile.json"],
                       capture_output=True, text=True)

    print(f"OK: profile={args.profile} rigor={spec['rigor']} plan={spec['plan']} "
          f"scope={spec['scope']}")
    if args.profile == "founder":
        print("Founder mode: evaluator sign-off, secrets gate and no-go stops all "
              "stay ON. Upgrade later with: python3 scripts/set_profile.py enterprise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
