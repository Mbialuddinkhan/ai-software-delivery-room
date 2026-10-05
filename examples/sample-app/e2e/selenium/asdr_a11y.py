"""ASDR accessibility check for Selenium (axe-core). Copy unchanged.

    from asdr_a11y import check_a11y
    check_a11y(driver, "board")                      # whole page
    check_a11y(driver, "settings", include="#settings")

Injects axe-core (ASDR_AXE_JS, or node_modules/axe-core/axe.min.js found from
the working directory upwards), writes
<ASDR_RESULTS_DIR>/a11y/selenium--<test>--<label>.json and raises
AssertionError on violations whose impact is in ASDR_A11Y_FAIL_ON (default
"critical,serious"; "none" only records). Rules: ASDR_A11Y_TAGS.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

RUN_AXE = """
const done = arguments[arguments.length - 1];
const ctx = arguments[0] ? document.querySelector(arguments[0]) : document;
axe.run(ctx, { runOnly: { type: 'tag', values: arguments[1] } }).then((r) => done({
  passes: r.passes.length,
  violations: r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl,
    nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')) })),
})).catch((e) => done({ error: String(e) }));
"""


def _axe_source() -> str:
    env = os.environ.get("ASDR_AXE_JS")
    if env and Path(env).is_file():
        return Path(env).read_text()
    here = Path.cwd().resolve()
    for d in [here, *here.parents][:6]:
        f = d / "node_modules" / "axe-core" / "axe.min.js"
        if f.is_file():
            return f.read_text()
    raise RuntimeError("axe-core not found: npm i -D axe-core, or set ASDR_AXE_JS to axe.min.js")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:80]


def check_a11y(driver, label: str, include: str | None = None) -> dict:
    tags = [t.strip() for t in os.environ.get("ASDR_A11Y_TAGS", "wcag2a,wcag2aa,wcag21a,wcag21aa").split(",")]
    fail_on = [t.strip() for t in os.environ.get("ASDR_A11Y_FAIL_ON", "critical,serious").split(",")
               if t.strip() and t.strip() != "none"]
    if not driver.execute_script("return !!window.axe"):
        driver.execute_script(_axe_source())
    driver.set_script_timeout(30)
    r = driver.execute_async_script(RUN_AXE, include, tags)
    if r.get("error"):
        raise RuntimeError(f"axe failed: {r['error']}")
    test = (os.environ.get("PYTEST_CURRENT_TEST") or "selenium").split(" (")[0]
    record = {"schema": 1, "framework": "selenium", "test": test, "label": label,
              "url": driver.current_url, "fail_on": fail_on, "tags": tags,
              "violations": r["violations"], "passes": r["passes"]}
    out = Path(os.environ.get("ASDR_RESULTS_DIR", "test-results")) / "a11y"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"selenium--{_slug(test)}--{_slug(label)}.json").write_text(json.dumps(record, indent=2))
    blocking = [v for v in r["violations"] if v.get("impact") in fail_on]
    assert not blocking, f"accessibility ({label}): " + "; ".join(
        f"{v['impact']} {v['id']} — {v['help']} ({', '.join(v['targets'])})" for v in blocking)
    return record
