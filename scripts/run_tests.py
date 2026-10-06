#!/usr/bin/env python3
"""Run the project's browser test suites and collect one result bundle.

Usage:
  python3 run_tests.py [--config .harness/test-config.json] [--suite NAME ...]
                       [--live] [--slowmo MS] [--tours] [--label TEXT]
                       [--no-server] [--collect-only RUN_DIR]

What it does
------------
1. Reads the suite list from the test config (template: templates/e2e/
   test-config.json). Each suite is one framework — Playwright, Cypress,
   Selenium, or anything that writes JUnit XML.
2. Starts the app once (app.start_cmd) unless it is already answering on
   app.url, and stops it afterwards.
3. Runs each suite with the same environment, so every framework writes into
   one run folder:  .harness/test-results/<run_id>/
     ASDR_RESULTS_DIR  the run folder (JUnit, screenshots, videos, traces)
     ASDR_MANUAL_DIR   manual-tour screenshots + manifests (.harness/manual)
     ASDR_COMMIT       the commit under test
     BASE_URL          app.url
4. Parses every JUnit file, links each test to its screenshots, videos and
   traces, and writes <run>/summary.json plus .harness/test-results/latest.json
   (read by emit_facts.py as facts:test_runs.*, and by publish_test_report.py).

Live mode (--live)
------------------
Runs headed and slowed down (ASDR_LIVE=1, ASDR_SLOWMO=400 ms, one worker) so
the user can watch the browser drive the app. Each suite may define live_cmd
(for example `npx cypress run --headed`). Where there is no screen — Cowork's
cloud sandbox, CI, an SSH session — a headed browser cannot open, so the run
falls back to "recorded" mode: headless with video on (ASDR_RECORD=1), and the
videos are published in the report instead. The summary records which mode ran.

Test users and saved logins
---------------------------
app.seed_cmd (optional) runs once the app answers and before any suite, to
create the test users and data the suites expect. Config "env" values are
passed to every suite; "${VAR}" is expanded from the environment, so test
passwords can come from CI secrets instead of the file. Suites share one
sign-in per role through ASDR_AUTH_DIR (.harness/auth): Playwright's
auth.setup.ts writes it, Cypress's cy.loginAs and Selenium's sign_in_as reuse
it. A full run clears it first; it holds live session tokens, so the folder
gets a "*" .gitignore and is never published.

--tours runs only each suite's tours_cmd (the manual-tour specs). A full run
(no --suite filter) clears the manual folder first so no screenshot from an
older build survives; a filtered run replaces only the tours it re-runs.

A suite that exits non-zero or produces no JUnit tests counts as failed — a
silent suite can never pass the gate. Exit code: 0 all passed, 1 failures,
2 configuration error.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_CONFIG = ".harness/test-config.json"
DEFAULT_RESULTS = ".harness/test-results"
DEFAULT_MANUAL = ".harness/manual"
DEFAULT_AUTH = ".harness/auth"
HISTORY_KEEP = 200


def git(*args):
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True, timeout=30)
        return p.stdout.strip() if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def has_display() -> bool:
    if os.environ.get("CI"):
        return False
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def url_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 - local app URL
            return r.status < 500
    except Exception:  # noqa: BLE001
        return False


def start_app(app: dict, root: Path, env: dict, log_dir: Path):
    url, cmd = app.get("url"), app.get("start_cmd")
    if not cmd or not url:
        return None
    if url_up(url):
        print(f"[run_tests] app already answering at {url}; not starting another")
        return None
    log = open(log_dir / "app.log", "w")
    proc = subprocess.Popen(cmd, shell=True, cwd=root / app.get("cwd", "."), env=env,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + float(app.get("ready_timeout_s", 60))
    while time.time() < deadline:
        if url_up(url):
            print(f"[run_tests] app started: {cmd}")
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    stop_app(proc)
    raise RuntimeError(f"app did not answer at {url} (see {log_dir / 'app.log'})")


def stop_app(proc):
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()


def run_suite(suite: dict, cmd: str, root: Path, env: dict, log_path: Path) -> tuple:
    print(f"\n[run_tests] ── {suite['name']} ({suite.get('framework', '?')}) ──\n$ {cmd}", flush=True)
    t0 = time.time()
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, shell=True, cwd=root / suite.get("cwd", "."), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                start_new_session=True)
        try:
            for line in proc.stdout:  # stream to the user and keep a copy
                sys.stdout.write(line)
                log.write(line)
            code = proc.wait(timeout=float(suite.get("timeout_s", 1800)))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = 124
            log.write("\n[run_tests] suite timed out\n")
    return code, round(time.time() - t0, 2)


# ── JUnit parsing ──────────────────────────────────────────────────────────

def _keep(path: Path, run_dir: Path) -> str | None:
    """Return the attachment's path relative to the run folder, copying it in if needed."""
    path = path.resolve()
    if not path.is_file():
        return None
    try:
        return path.relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        dest = run_dir / "attachments"
        dest.mkdir(exist_ok=True)
        tag = hashlib.sha1(str(path).encode()).hexdigest()[:8]
        target = dest / f"{tag}-{path.name}"
        shutil.copy2(path, target)
        return target.relative_to(run_dir).as_posix()


def _attachments(tc, junit_file: Path, run_dir: Path) -> list:
    found = []
    for tag in ("system-out", "system-err"):
        for node in tc.findall(tag):
            text = node.text or ""
            start = 0
            while True:
                i = text.find("[[ATTACHMENT|", start)
                if i < 0:
                    break
                j = text.find("]]", i)
                if j < 0:
                    break
                raw = text[i + 13:j].strip()
                p = Path(raw) if os.path.isabs(raw) else junit_file.parent / raw
                found.append(p)
                start = j + 2
    for prop in tc.iter("property"):
        if prop.get("name") == "attachment" and prop.get("value"):
            raw = prop.get("value")
            found.append(Path(raw) if os.path.isabs(raw) else junit_file.parent / raw)
    out = []
    for p in found:
        rel = _keep(p, run_dir)
        if rel and rel not in out:
            out.append(rel)
    return out


def _cypress_extras(spec_file: str | None, classname: str, status: str, run_dir: Path) -> list:
    if not spec_file:
        return []
    base = Path(spec_file).name
    extras = []
    for v in sorted(glob.glob(str(run_dir / "cypress" / "videos" / "**" / f"{base}.mp4"), recursive=True)):
        extras.append(Path(v))
    if status in ("failed", "error"):
        for s in glob.glob(str(run_dir / "cypress" / "screenshots" / "**" / base / "*.png"), recursive=True):
            if f"-- {classname} (failed)" in Path(s).name:
                extras.append(Path(s))
    return [r for r in (_keep(p, run_dir) for p in extras) if r]


def parse_junit(files: list, run_dir: Path, framework: str) -> list:
    cases = []
    for f in files:
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as e:
            cases.append({"name": f"unreadable JUnit file {Path(f).name}", "classname": "",
                          "status": "error", "time": 0, "message": str(e), "attachments": []})
            continue
        spec_file = next((ts.get("file") for ts in root.iter("testsuite") if ts.get("file")), None)
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        for ts in suites:
            for tc in ts.findall("testcase"):
                status, message = "passed", None
                for tag in ("failure", "error"):
                    el = tc.find(tag)
                    if el is not None:
                        status = "failed" if tag == "failure" else "error"
                        message = ((el.get("message") or "") + "\n" + (el.text or "")).strip()[:4000]
                        break
                if status == "passed" and tc.find("skipped") is not None:
                    status = "skipped"
                att = _attachments(tc, Path(f), run_dir)
                if framework == "cypress":
                    att += [a for a in _cypress_extras(spec_file, tc.get("classname", ""), status, run_dir)
                            if a not in att]
                cases.append({
                    "suite": ts.get("name"),
                    "classname": tc.get("classname"),
                    "name": tc.get("name"),
                    "file": tc.get("file") or spec_file,
                    "status": status,
                    "time": float(tc.get("time") or 0),
                    "message": message,
                    "attachments": att,
                })
    return cases


def count(cases: list) -> dict:
    c = {"tests": len(cases), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for x in cases:
        c[x["status"]] = c.get(x["status"], 0) + 1
    return c


IMPACT_ORDER = ["critical", "serious", "moderate", "minor"]


def a11y_summary(run_dir: Path) -> dict | None:
    """Add up the accessibility checks the helpers wrote to <run>/a11y/*.json."""
    files = sorted((run_dir / "a11y").glob("*.json")) if (run_dir / "a11y").is_dir() else []
    if not files:
        return None
    by_impact = {k: 0 for k in IMPACT_ORDER}
    rules, checks = {}, []
    for f in files:
        try:
            r = json.loads(f.read_text())
        except ValueError:
            continue
        checks.append({"framework": r.get("framework"), "test": r.get("test"), "label": r.get("label"),
                       "url": r.get("url"), "violations": len(r.get("violations", [])),
                       "file": f.relative_to(run_dir).as_posix()})
        for v in r.get("violations", []):
            imp = v.get("impact") if v.get("impact") in by_impact else "minor"
            by_impact[imp] += 1
            rule = rules.setdefault(v["id"], {"id": v["id"], "impact": imp, "help": v.get("help"),
                                              "helpUrl": v.get("helpUrl"), "checks": 0, "nodes": 0, "where": []})
            rule["checks"] += 1
            rule["nodes"] += int(v.get("nodes") or 0)
            where = f"{r.get('label')} ({r.get('framework')})"
            if where not in rule["where"]:
                rule["where"].append(where)
    return {"checks": len(checks), "by_impact": by_impact,
            "rules": sorted(rules.values(), key=lambda x: (IMPACT_ORDER.index(x["impact"]), x["id"])),
            "pages": checks}


def coverage_summary(run_dir: Path) -> dict | None:
    """Collect the flowStep / covers / metric markers the tests wrote to <run>/coverage/*.jsonl."""
    files = sorted((run_dir / "coverage").glob("*.jsonl")) if (run_dir / "coverage").is_dir() else []
    if not files:
        return None
    by_tc, metrics, untagged = {}, [], 0
    for f in files:
        for line in f.read_text(errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            tcs = rec.get("tc") or []
            if rec.get("kind") in ("step", "covers"):
                if not tcs:
                    untagged += 1
                for t in tcs:
                    bucket = by_tc.setdefault(t, [])
                    for x in rec.get("items") or []:
                        if x not in bucket:
                            bucket.append(x)
            elif rec.get("kind") == "metric":
                budget = rec.get("budget")
                metrics.append({"name": rec.get("name"), "value": rec.get("value"), "unit": rec.get("unit"),
                                "budget": budget, "test": rec.get("test"), "tc": tcs,
                                "within_budget": (None if budget is None or rec.get("value") is None
                                                  else rec["value"] <= budget)})
    return {"by_tc": {k: sorted(v) for k, v in sorted(by_tc.items())}, "metrics": metrics,
            "untagged_markers": untagged}


def manual_inventory(manual_dir: Path, commit: str | None) -> dict:
    tours = []
    for f in sorted((manual_dir / "tours").glob("*.json")) if (manual_dir / "tours").is_dir() else []:
        try:
            m = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        tours.append({"tour": m.get("tour", f.stem), "framework": m.get("framework"),
                      "steps": len(m.get("steps", [])), "commit": m.get("commit"),
                      "current": bool(commit) and m.get("commit") == commit})
    return {"dir": str(manual_dir), "tours": tours,
            "screenshots": sum(t["steps"] for t in tours)}


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--suite", action="append", help="run only this suite (repeatable)")
    ap.add_argument("--live", action="store_true", help="headed, slowed down, in front of the user")
    ap.add_argument("--slowmo", type=int, default=None, help="ms pause per action in live mode (default 400)")
    ap.add_argument("--tours", action="store_true", help="run only manual-tour specs (tours_cmd)")
    ap.add_argument("--label", default=None, help="label for the report (default: run id)")
    ap.add_argument("--no-server", action="store_true", help="do not start app.start_cmd")
    ap.add_argument("--collect-only", metavar="RUN_DIR", help="parse an existing run folder; run nothing")
    args = ap.parse_args()

    root = Path.cwd()
    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"ERROR: no test config at {cfg_path}. Copy .harness/templates/e2e/test-config.json "
              "and list the project's suites.")
        return 2
    cfg = json.loads(cfg_path.read_text())
    suites = cfg.get("suites") or []
    if args.suite:
        unknown = set(args.suite) - {s["name"] for s in suites}
        if unknown:
            print(f"ERROR: unknown suite(s): {', '.join(sorted(unknown))}")
            return 2
        suites = [s for s in suites if s["name"] in args.suite]
    if not suites:
        print("ERROR: the test config lists no suites.")
        return 2

    commit = os.environ.get("ASDR_COMMIT") or git("rev-parse", "--short", "HEAD")
    dirty = bool(git("status", "--porcelain")) if commit else None
    results_root = (root / cfg.get("results_dir", DEFAULT_RESULTS)).resolve()
    manual_dir = (root / cfg.get("manual_dir", DEFAULT_MANUAL)).resolve()
    started = dt.datetime.now(dt.timezone.utc)

    if args.collect_only:
        run_dir = Path(args.collect_only).resolve()
        run_id = run_dir.name
        mode = "collected"
    else:
        run_id = started.strftime("%Y%m%d-%H%M%S") + (f"-{commit}" if commit else "")
        run_dir = results_root / run_id
        mode = "ci"
        if args.live:
            mode = "live" if has_display() else "recorded"
            if mode == "recorded":
                print("[run_tests] no screen available here, so a headed browser cannot open. "
                      "Running headless with video recording; the videos are in the report.")
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    auth_dir = (root / cfg.get("auth_dir", DEFAULT_AUTH)).resolve()
    env = dict(os.environ)
    unset = []
    for k, v in (cfg.get("env") or {}).items():
        val = os.path.expandvars(str(v))
        if "$" in val:
            unset.append(k)
        env[k] = val
    if unset:
        print(f"[run_tests] WARN: config env {', '.join(unset)} refer to variables that are not set")
    env.update({
        "ASDR_RESULTS_DIR": str(run_dir),
        "ASDR_MANUAL_DIR": str(manual_dir),
        "ASDR_AUTH_DIR": str(auth_dir),
        "ASDR_COMMIT": commit or "",
    })
    app = cfg.get("app") or {}
    if app.get("url"):
        env["BASE_URL"] = app["url"]
    if mode == "live":
        env["ASDR_LIVE"] = "1"
        env["ASDR_SLOWMO"] = str(args.slowmo if args.slowmo is not None else 400)
    elif mode == "recorded":
        env["ASDR_RECORD"] = "1"

    results = []
    seed = None
    if not args.collect_only:
        if not args.suite:
            for sub in ("screens", "tours"):
                shutil.rmtree(manual_dir / sub, ignore_errors=True)
            shutil.rmtree(auth_dir, ignore_errors=True)
        auth_dir.mkdir(parents=True, exist_ok=True)
        (auth_dir / ".gitignore").write_text("*\n")
        server = None
        try:
            if not args.no_server:
                server = start_app(app, root, env, run_dir / "logs")
            if app.get("seed_cmd"):
                print(f"[run_tests] seeding test data: {app['seed_cmd']}", flush=True)
                with open(run_dir / "logs" / "seed.log", "w") as log:
                    rc = subprocess.run(app["seed_cmd"], shell=True, cwd=root / app.get("cwd", "."), env=env,
                                        stdout=log, stderr=subprocess.STDOUT, timeout=600).returncode
                seed = {"cmd": app["seed_cmd"], "exit_code": rc, "log": "logs/seed.log"}
                if rc != 0:
                    raise RuntimeError(f"seed_cmd failed with exit {rc} (see {run_dir / 'logs' / 'seed.log'})")
            for s in suites:
                if args.tours:
                    cmd = s.get("tours_cmd")
                    if not cmd:
                        print(f"[run_tests] {s['name']}: no tours_cmd, skipped")
                        continue
                elif mode == "live" and s.get("live_cmd"):
                    cmd = s["live_cmd"]
                else:
                    cmd = s["cmd"]
                cmd = cmd.format(results=run_dir, manual=manual_dir,
                                 base_url=app.get("url", ""), commit=commit or "")
                code, secs = run_suite(s, cmd, root, env, run_dir / "logs" / f"{s['name']}.log")
                results.append((s, cmd, code, secs))
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return 2
        finally:
            stop_app(server)
    else:
        results = [(s, None, None, None) for s in suites]

    suite_out = []
    for s, cmd, code, secs in results:
        files = []
        for pattern in s.get("junit", []):
            files += sorted(glob.glob(str(run_dir / pattern)))
        cases = parse_junit(files, run_dir, s.get("framework", ""))
        if not cases:
            cases = [{"suite": s["name"], "classname": "", "name": "suite produced no test results",
                      "file": None, "status": "error", "time": 0, "attachments": [],
                      "message": f"exit code {code}; no JUnit testcases matched {s.get('junit')}. "
                                 f"See logs/{s['name']}.log."}]
        elif code not in (0, None) and not any(c["status"] in ("failed", "error") for c in cases):
            cases.append({"suite": s["name"], "classname": "", "name": "suite exited with an error",
                          "file": None, "status": "error", "time": 0, "attachments": [],
                          "message": f"exit code {code} although every test passed. See logs/{s['name']}.log."})
        report = s.get("html_report")
        suite_out.append({
            "name": s["name"], "framework": s.get("framework"), "cmd": cmd, "exit_code": code,
            "duration_s": secs, "junit": [Path(f).relative_to(run_dir).as_posix() for f in files],
            "html_report": report if report and (run_dir / report).is_file() else None,
            "log": f"logs/{s['name']}.log" if (run_dir / "logs" / f"{s['name']}.log").is_file() else None,
            "totals": count(cases), "cases": cases,
        })

    all_cases = [c for s in suite_out for c in s["cases"]]
    totals = count(all_cases)
    status = "passed" if totals["failed"] == 0 and totals["error"] == 0 else "failed"
    finished = dt.datetime.now(dt.timezone.utc)
    summary = {
        "schema": 1,
        "product": cfg.get("product"),
        "run_id": run_id,
        "label": args.label or run_id,
        "mode": mode,
        "tours_only": bool(args.tours),
        "status": status,
        "commit": commit,
        "dirty": dirty,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "duration_s": round((finished - started).total_seconds(), 1),
        "environment": {"os": platform.platform(), "python": platform.python_version(),
                        "ci": bool(os.environ.get("CI")), "base_url": app.get("url")},
        "totals": totals,
        "suites": suite_out,
        "manual": manual_inventory(manual_dir, commit),
        "seed": seed,
        "a11y": a11y_summary(run_dir),
        "coverage": coverage_summary(run_dir),
        "saved_logins": sorted(f.stem for f in auth_dir.glob("*.json")) if auth_dir.is_dir() else [],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    results_root.mkdir(parents=True, exist_ok=True)
    (results_root / "latest.json").write_text(json.dumps(
        {"run_id": run_id, "path": str(run_dir), "status": status, "commit": commit,
         "finished_at": summary["finished_at"]}, indent=2))
    hist = results_root / "history.jsonl"
    lines = hist.read_text().splitlines() if hist.exists() else []
    lines.append(json.dumps({"run_id": run_id, "status": status, "mode": mode, "commit": commit,
                             "finished_at": summary["finished_at"], **totals}))
    hist.write_text("\n".join(lines[-HISTORY_KEEP:]) + "\n")

    print("\n[run_tests] ── summary ──")
    for s in suite_out:
        t = s["totals"]
        print(f"  {s['name']:<14} {t['passed']:>3} passed  {t['failed']:>3} failed  "
              f"{t['error']:>3} errors  {t['skipped']:>3} skipped")
    cov = summary["coverage"]
    if cov:
        print(f"  coverage markers: {len({x for v in cov['by_tc'].values() for x in v})} distinct items marked by "
              f"{len(cov['by_tc'])} test cases" + (f", {len(cov['metrics'])} measurements" if cov["metrics"] else "")
              + " (validate_product_map.py checks them against the documents)")
    a = summary["a11y"]
    if a:
        print(f"  accessibility: {a['checks']} checks — " +
              ", ".join(f"{a['by_impact'][k]} {k}" for k in IMPACT_ORDER))
    m = summary["manual"]
    print(f"  manual tours: {len(m['tours'])} ({m['screenshots']} screenshots)")
    print(f"  mode={mode} status={status.upper()} → {run_dir / 'summary.json'}")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
