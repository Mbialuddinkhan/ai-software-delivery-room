"""ASDR Selenium (pytest) fixtures. devops copies this file and asdr_manual.py
into the project's Selenium test directory. run_tests.py drives it through
environment variables, so the same suite serves CI and live runs:

  ASDR_LIVE=1        headed browser, actions slowed by ASDR_SLOWMO ms (default 400)
  ASDR_SLOWMO        pause after each click / type / navigation, in ms
  ASDR_RESULTS_DIR   screenshots go to <dir>/selenium/screenshots/ (default test-results)
  BASE_URL           app under test (default http://localhost:4173)
  CHROME_BINARY      Chrome/Chromium to drive (optional)
  CHROMEDRIVER       explicit driver path (optional). When unset, Selenium Manager
                     picks a driver that matches the browser and ignores any stale
                     chromedriver on PATH.

Every test leaves a final screenshot (pass or fail); the path is recorded as
a JUnit property named "attachment" so publish_test_report.py shows it.
Run with:  pytest <dir> --junitxml=<results>/junit/selenium.xml -o junit_family=xunit1
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.events import AbstractEventListener, EventFiringWebDriver

LIVE = bool(os.environ.get("ASDR_LIVE"))
SLOWMO = int(os.environ.get("ASDR_SLOWMO") or (400 if LIVE else 0))
RESULTS = Path(os.environ.get("ASDR_RESULTS_DIR", "test-results"))


class _SlowMo(AbstractEventListener):
    """Pauses after each action so a person watching a live run can follow it."""

    def _pause(self, *_):
        time.sleep(SLOWMO / 1000)

    after_navigate_to = after_click = after_change_value_of = _pause


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("BASE_URL", "http://localhost:4173").rstrip("/")


@pytest.fixture
def driver(request):
    opts = Options()
    if not LIVE:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if os.environ.get("CHROME_BINARY"):
        opts.binary_location = os.environ["CHROME_BINARY"]
    if os.environ.get("CHROMEDRIVER"):
        drv = webdriver.Chrome(service=Service(os.environ["CHROMEDRIVER"]), options=opts)
    else:
        os.environ.setdefault("SE_SKIP_DRIVER_IN_PATH", "true")
        drv = webdriver.Chrome(options=opts)
    try:  # same 1280x800 viewport as the Playwright manual project
        drv.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                            {"width": 1280, "height": 800, "deviceScaleFactor": 1, "mobile": False})
    except Exception:
        pass
    drv.implicitly_wait(2)
    wrapped = EventFiringWebDriver(drv, _SlowMo()) if SLOWMO else drv
    request.node._asdr_driver = drv
    yield wrapped
    drv.quit()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    drv = getattr(item, "_asdr_driver", None)
    if report.when != "call" or drv is None:
        return
    shots = RESULTS / "selenium" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", item.nodeid)[-150:]
    path = shots / f"{name}{'--FAILED' if report.failed else ''}.png"
    try:
        drv.save_screenshot(str(path))
        item.user_properties.append(("attachment", str(path.resolve())))
    except Exception:  # browser already gone; the failure itself is the evidence
        pass
