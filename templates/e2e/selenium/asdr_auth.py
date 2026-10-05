"""ASDR saved logins for Selenium. Copy unchanged next to conftest.py.

    from asdr_auth import sign_in_as
    sign_in_as(driver, base_url, "admin")

Restores the browser state the Playwright auth setup saved in
<ASDR_AUTH_DIR>/<role>.json (cookies + localStorage, Playwright's storageState
format), so the three frameworks share one sign-in per role. Without that file
it calls login(driver, base_url, role) from the project's login.py. Journey
tests that walk the sign-in flow must not use it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def auth_file(role: str) -> Path:
    d = Path(os.environ.get("ASDR_AUTH_DIR", ".harness/auth"))
    d.mkdir(parents=True, exist_ok=True)
    ignore = d / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n")
    return d / f"{role}.json"


def apply_storage_state(driver, base_url: str, state: dict) -> None:
    parts = urlsplit(base_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    driver.get(origin + "/")                      # must be on the origin to set its storage
    for c in state.get("cookies", []):
        cookie = {"name": c["name"], "value": c["value"], "path": c.get("path", "/"),
                  "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly"))}
        if c.get("expires", -1) and c.get("expires", -1) > 0:
            cookie["expiry"] = int(c["expires"])
        try:
            driver.add_cookie(cookie)
        except Exception:  # noqa: BLE001 - a cookie for another domain; skip it
            pass
    for o in state.get("origins", []):
        if o.get("origin") == origin:
            for item in o.get("localStorage", []):
                driver.execute_script("localStorage.setItem(arguments[0], arguments[1]);",
                                      item["name"], item["value"])
    driver.get(base_url)


def sign_in_as(driver, base_url: str, role: str) -> str:
    """Returns 'restored' (saved state reused) or 'logged-in' (login.py ran)."""
    f = auth_file(role)
    if f.is_file():
        apply_storage_state(driver, base_url, json.loads(f.read_text()))
        return "restored"
    import login  # project-specific: login(driver, base_url, role)
    login.login(driver, base_url, role)
    return "logged-in"
