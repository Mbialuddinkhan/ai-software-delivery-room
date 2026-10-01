#!/usr/bin/env python3
"""Check whether ASDR or any companion has a newer version available.

Usage:
  python3 check_updates.py [--plugin-root DIR] [--force] [--json]
  python3 check_updates.py --hook --plugin-root "$CLAUDE_PLUGIN_ROOT"   # optional
                                       # SessionStart notice; ASDR does not wire it

What it does:
  1. Reads scripts/upstream.json (next to this file) for where each item's
     latest version lives (raw plugin.json on GitHub, or PyPI).
  2. Finds the installed version: ASDR from --plugin-root/.claude-plugin/
     plugin.json; other Claude plugins from `claude plugin list --json`, then
     from ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/; graphify
     from the Python module.
  3. Compares semver, pulls the top section of the upstream CHANGELOG as
     the "why update" text, and reports.

Outputs:
  default  human-readable report
  --json   {"checked_at", "updates": [{name, installed, latest, optional,
            benefits, update_command}], "up_to_date": [...], "skipped": [...]}
  --hook   prints a 3-5 line notice ONLY when an update exists (SessionStart
           stdout becomes session context); prints nothing otherwise.

Never installs anything. Network is best-effort: any failure = "skipped".
Results are cached for 24h in ~/.claude/asdr-update-check.json (--force
bypasses). Honors CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 by doing
nothing. Exit code is always 0.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / ".claude" / "asdr-update-check.json"
TTL = 24 * 3600
UA = "asdr-check-updates/1.0"


def fetch(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def semver(s):
    if not s:
        return None
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(s))
    return tuple(int(x) for x in m.groups()) if m else None


def changelog_top(text, max_lines=12):
    """First '## ' section of a changelog, trimmed to a few lines."""
    lines = text.splitlines()
    out, started = [], False
    for ln in lines:
        if ln.startswith("## "):
            if started:
                break
            started = True
            out.append(ln.lstrip("# ").strip())
            continue
        if started and ln.strip():
            out.append(ln.rstrip())
            if len(out) >= max_lines:
                break
    return "\n".join(out)


def installed_claude_plugins():
    """{name: version} from `claude plugin list --json`, then cache dirs."""
    found = {}
    try:
        r = subprocess.run(["claude", "plugin", "list", "--json"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            items = data if isinstance(data, list) else data.get("plugins", [])
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = str(it.get("name") or it.get("id") or "").split("@")[0]
                ver = it.get("version") or it.get("installedVersion")
                if name and ver:
                    found[name] = str(ver)
    except Exception:
        pass
    cache = Path.home() / ".claude" / "plugins" / "cache"
    if cache.is_dir():
        for mp in cache.iterdir():
            for plug in (mp.iterdir() if mp.is_dir() else []):
                if plug.name in found or not plug.is_dir():
                    continue
                vers = [semver(v.name) for v in plug.iterdir() if v.is_dir()]
                vers = [v for v in vers if v]
                if vers:
                    found[plug.name] = ".".join(map(str, max(vers)))
    return found


def installed_pypi(pkg_import):
    try:
        r = subprocess.run([sys.executable, "-c",
                            f"import importlib.metadata as m;print(m.version('{pkg_import}'))"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def run(plugin_root):
    upstream = json.loads((HERE / "upstream.json").read_text())
    upstream.pop("_comment", None)
    plugins = installed_claude_plugins()
    report = {"checked_at": int(time.time()), "updates": [], "up_to_date": [], "skipped": []}

    for name, spec in upstream.items():
        # installed
        if name == "ai-software-delivery-room" and plugin_root:
            try:
                inst = json.loads((Path(plugin_root) / ".claude-plugin" / "plugin.json").read_text()).get("version")
            except Exception:
                inst = plugins.get(name)
        elif spec["kind"] == "pypi":
            inst = installed_pypi(spec["package"])
        else:
            inst = plugins.get(name)
        if not inst:
            report["skipped"].append({"name": name, "reason": "not installed"})
            continue
        # latest
        try:
            raw = fetch(spec["manifest_url"])
            latest = (json.loads(raw)["info"]["version"] if spec["kind"] == "pypi"
                      else json.loads(raw).get("version"))
        except Exception as e:
            report["skipped"].append({"name": name, "reason": f"upstream unreachable: {e.__class__.__name__}"})
            continue
        si, sl = semver(inst), semver(latest)
        if not si or not sl:
            report["skipped"].append({"name": name, "reason": f"unparseable version {inst!r}/{latest!r}"})
            continue
        if sl <= si:
            report["up_to_date"].append({"name": name, "installed": inst})
            continue
        benefits = ""
        try:
            benefits = changelog_top(fetch(spec["changelog_url"]))
        except Exception:
            benefits = "(changelog unavailable — see the repository release notes)"
        report["updates"].append({
            "name": name, "installed": inst, "latest": latest,
            "optional": bool(spec.get("optional")),
            "benefits": benefits,
            "update_command": spec["update_command"],
            "pinned_note": spec.get("pinned_note"),
        })
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-root", default=os.environ.get("CLAUDE_PLUGIN_ROOT"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", action="store_true")
    a = ap.parse_args()

    if os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC") == "1":
        return 0

    report = None
    if not a.force and CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text())
            if time.time() - cached.get("checked_at", 0) < TTL:
                report = cached
        except Exception:
            report = None
    if report is None:
        report = run(a.plugin_root)
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(report, indent=2))
        except Exception:
            pass

    if a.json:
        print(json.dumps(report, indent=2))
        return 0

    ups = report["updates"]
    if a.hook:
        if ups:
            names = ", ".join(f"{u['name']} {u['installed']}→{u['latest']}" for u in ups)
            print(f"ASDR update check: newer versions available for {names}. "
                  f"When /asdr runs, it will show what each update adds and ask before "
                  f"installing. To see now: python3 .harness/scripts/check_updates.py")
        return 0

    if not ups:
        print("ASDR and companions are up to date." if report["up_to_date"] else "Nothing to check.")
    for u in ups:
        tag = " (optional companion)" if u["optional"] else ""
        print(f"\n== {u['name']}{tag}: {u['installed']} -> {u['latest']}")
        print("   What it adds:")
        for ln in u["benefits"].splitlines():
            print("   " + ln)
        if u.get("pinned_note"):
            print("   Note: " + u["pinned_note"])
        print(f"   Update: {u['update_command']}   then /reload-plugins")
    for s in report["skipped"]:
        print(f"   skipped {s['name']}: {s['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
