#!/usr/bin/env python3
"""Read-only check that ASDR can test on the chosen cloud — before any deploy.

Usage:
  python3 cloud_preflight.py [--cloud .harness/cloud.json] [--iac infra]
                             [--json .harness/cloud-preflight.json] [--timeout 60]

v3.8. Nothing here creates, changes or deletes anything. It checks:

  tools       docker, terraform or tofu, kubectl, and the test cloud's CLI
              (aws / az / gcloud); the other clouds' CLIs are listed for info
  signed in   aws sts get-caller-identity · az account show ·
              gcloud config get-value account/project — the CLI's own sign-in;
              ASDR never stores keys
  IaC         every folder under --iac holding *.tf: terraform (or tofu)
              init -backend=false, validate, fmt -check; checkov if installed
  compose     docker compose config -q for each docker-compose*.yml
  settings    .harness/cloud.json has a region, a time-to-live and a daily budget

Prints READY or NOT READY with the reasons, writes the JSON report, and ends
with CLOUD-PREFLIGHT: {json}. Exit 0 always — the orchestrator decides; a
deploy may only follow READY and the user's approval.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

CLI = {"aws": "aws", "azure": "az", "gcp": "gcloud"}
SIGNIN = {
    "aws": [["aws", "sts", "get-caller-identity", "--output", "json"]],
    "azure": [["az", "account", "show", "--output", "json"]],
    "gcp": [["gcloud", "config", "get-value", "account"], ["gcloud", "config", "get-value", "project"]],
}


def run(cmd, cwd=None, timeout=60):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 127, "", str(ex)


def signin(cloud: str, timeout: int) -> dict:
    if not shutil.which(CLI[cloud]):
        return {"ok": False, "detail": f"{CLI[cloud]} CLI not installed"}
    outs = []
    for cmd in SIGNIN[cloud]:
        rc, so, se = run(cmd, timeout=timeout)
        if rc != 0 or not so or so.lower() in ("(unset)", "none"):
            return {"ok": False, "detail": f"`{' '.join(cmd)}` failed — sign in with the CLI first "
                                           f"({'aws sso login' if cloud == 'aws' else 'az login' if cloud == 'azure' else 'gcloud auth login'})",
                    "error": (se or so)[-200:]}
        outs.append(so)
    who = ""
    if cloud == "aws":
        try:
            d = json.loads(outs[0])
            who = f"account …{str(d.get('Account', ''))[-4:]}, {d.get('Arn', '').split('/')[-2:-1] or ''}"
        except ValueError:
            who = "signed in"
    elif cloud == "azure":
        try:
            d = json.loads(outs[0])
            who = f"subscription {d.get('name')} (…{str(d.get('id', ''))[-4:]})"
        except ValueError:
            who = "signed in"
    else:
        who = f"{outs[0]} on project {outs[1]}"
    return {"ok": True, "detail": who}


def iac(root: Path, timeout: int) -> list:
    tf = shutil.which("terraform") or shutil.which("tofu")
    dirs = sorted({p.parent for p in root.rglob("*.tf") if ".terraform" not in p.parts}) if root.is_dir() else []
    out = []
    for d in dirs:
        r = {"dir": str(d)}
        if not tf:
            r.update(ok=None, detail="terraform/tofu not installed — not validated")
        else:
            rc, so, se = run([tf, f"-chdir={d}", "init", "-backend=false", "-input=false", "-no-color"], timeout=timeout * 3)
            if rc != 0:
                r.update(ok=False, detail="init failed: " + (se or so)[-200:])
            else:
                rc, so, se = run([tf, f"-chdir={d}", "validate", "-no-color"], timeout=timeout)
                fm, _, _ = run([tf, f"-chdir={d}", "fmt", "-check", "-recursive"], timeout=timeout)
                r.update(ok=rc == 0, detail=("valid" if rc == 0 else (se or so)[-300:])
                         + ("" if fm == 0 else "; not formatted (terraform fmt)"))
        if shutil.which("checkov"):
            rc, so, _ = run(["checkov", "-d", str(d), "--quiet", "--compact", "-o", "json"], timeout=timeout * 3)
            try:
                data = json.loads(so)
                data = data if isinstance(data, list) else [data]
                failed = sum(len((x.get("results") or {}).get("failed_checks") or []) for x in data)
                r["checkov_failed"] = failed
            except ValueError:
                r["checkov_failed"] = None
        out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only cloud test preflight.")
    ap.add_argument("--cloud", default=".harness/cloud.json")
    ap.add_argument("--iac", default="infra")
    ap.add_argument("--json", default=".harness/cloud-preflight.json")
    ap.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args()
    try:
        cfg = json.loads(Path(a.cloud).read_text())
    except (OSError, ValueError):
        cfg = {}
    target = (cfg.get("test_cloud") or "none").lower().replace("google cloud", "gcp")
    reasons, report = [], {"test_cloud": target}

    report["tools"] = {t: shutil.which(t) for t in ("docker", "terraform", "tofu", "kubectl", "aws", "az", "gcloud")}
    if target == "none":
        print("Test cloud: none — local only. Cloud deploy tests are skipped; infrastructure is validated only.")
    elif target not in CLI:
        reasons.append(f"unknown test_cloud '{target}' (aws, azure, gcp or none)")
    else:
        si = signin(target, a.timeout)
        report["signed_in"] = si
        if not si["ok"]:
            reasons.append(si["detail"])
        for k in ("region", "ttl_hours", "budget_usd_per_day"):
            v = cfg.get(k)
            if v in (None, "") or str(v).startswith("<"):
                reasons.append(f"cloud.json: set {k}")
        if not (report["tools"]["terraform"] or report["tools"]["tofu"]):
            reasons.append("terraform or tofu is not installed")
    if not report["tools"]["docker"]:
        reasons.append("docker is not installed — services cannot be run standalone")

    report["iac"] = iac(Path(a.iac), a.timeout)
    for r in report["iac"]:
        if r.get("ok") is False:
            reasons.append(f"IaC {r['dir']}: {r['detail'][:160]}")
    compose = []
    if report["tools"]["docker"]:
        for f in sorted(Path(".").glob("docker-compose*.y*ml")):
            rc, so, se = run(["docker", "compose", "-f", str(f), "config", "-q"], timeout=a.timeout)
            compose.append({"file": str(f), "ok": rc == 0, "detail": (se or so)[-200:]})
            if rc != 0:
                reasons.append(f"{f}: docker compose config failed")
    report["compose"] = compose
    report["ready"] = not reasons
    report["reasons"] = reasons
    try:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(report, indent=2) + "\n")
    except OSError:
        pass
    if target != "none":
        print(("READY: " if not reasons else "NOT READY: ") + target
              + (f" — {report.get('signed_in', {}).get('detail', '')}" if not reasons else ""))
    for r in reasons:
        print(f"  - {r}")
    print("CLOUD-PREFLIGHT: " + json.dumps({"test_cloud": target, "ready": report["ready"], "reasons": reasons}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
