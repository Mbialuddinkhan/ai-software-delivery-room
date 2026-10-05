"""ASDR manual-tour helper for Selenium (Python).

A tour is an ordinary pytest test that walks one user task and calls
manual_step() at every moment a user manual should show. Each call outlines
the element the user acts on (red, 3px), saves a viewport screenshot to
<ASDR_MANUAL_DIR>/screens/<tour>--<id>.png and records the step in
<ASDR_MANUAL_DIR>/tours/<tour>.json. The manifest format is the same one the
Playwright and Cypress helpers write, so build_manual.py treats all three
alike.

Copy unchanged next to conftest.py. Environment, set by run_tests.py:
  ASDR_MANUAL_DIR  where screens/ and tours/ go (default .harness/manual)
  ASDR_COMMIT      commit the screenshots were taken from
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from selenium.webdriver.common.by import By

HIGHLIGHT = "3px solid #e5484d"


def _resolve(driver, element):
    """Accept a WebElement, a CSS selector string, or a (By, value) tuple."""
    if element is None:
        return None, None
    if isinstance(element, str):
        return driver.find_element(By.CSS_SELECTOR, element), element
    if isinstance(element, tuple):
        return driver.find_element(*element), f"{element[0]}={element[1]}"
    desc = driver.execute_script(
        "const e=arguments[0];return e.tagName.toLowerCase()+(e.id?'#'+e.id:'')"
        "+(e.getAttribute('aria-label')?'[aria-label=\"'+e.getAttribute('aria-label')+'\"]':'');",
        element,
    )
    return element, desc


def manual_step(driver, tour: str, step_id: str, title: str, element=None, note: str | None = None) -> str:
    """Capture one manual step. Returns the screenshot path (relative to the manual dir)."""
    base = Path(os.environ.get("ASDR_MANUAL_DIR", ".harness/manual"))
    (base / "screens").mkdir(parents=True, exist_ok=True)
    (base / "tours").mkdir(parents=True, exist_ok=True)

    el, target = _resolve(driver, element)
    if el is not None:
        driver.execute_script(
            "const e=arguments[0];e.scrollIntoView({block:'center'});"
            "e.setAttribute('data-asdr-prev-outline', e.style.outline||'');"
            "e.style.outline=arguments[1];e.style.outlineOffset='3px';",
            el, HIGHLIGHT,
        )
    rel = f"screens/{tour}--{step_id}.png"
    driver.save_screenshot(str(base / rel))
    if el is not None:
        driver.execute_script(
            "const e=arguments[0];e.style.outline=e.getAttribute('data-asdr-prev-outline')||'';"
            "e.style.outlineOffset='';e.removeAttribute('data-asdr-prev-outline');",
            el,
        )

    file = base / "tours" / f"{tour}.json"
    manifest = (json.loads(file.read_text()) if file.exists()
                else {"schema": 1, "tour": tour, "framework": "selenium", "steps": []})
    manifest["commit"] = os.environ.get("ASDR_COMMIT") or None
    manifest["captured_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    vp = driver.execute_script("return {width: window.innerWidth, height: window.innerHeight};")
    manifest["steps"] = [s for s in manifest["steps"] if s["id"] != step_id]
    manifest["steps"].append({
        "id": step_id, "title": title, "url": driver.current_url, "screenshot": rel,
        "target": target, "note": note, "viewport": vp,
    })
    for i, s in enumerate(manifest["steps"], 1):
        s["order"] = i
    file.write_text(json.dumps(manifest, indent=2))
    return rel
