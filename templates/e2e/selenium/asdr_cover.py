"""ASDR coverage markers for Selenium (pytest). Copy unchanged.

    from asdr_cover import flow_step, covers, metric
    flow_step("PF-02.3")              # a journey test reached this flow step
    covers("AC-03.2", "BR-02")        # right where the test asserts them
    metric("board-render-500", ms, "ms", budget=1000)

The test function name must carry its test-case id: def test_tc_03_…().
Markers go to <ASDR_RESULTS_DIR>/coverage/selenium.jsonl.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_TC = re.compile(r"\[TC-(\d+)\]|(?<![A-Za-z0-9])[Tt][Cc][_-](\d+)(?![0-9])")


def _write(kind: str, **extra) -> None:
    test = (os.environ.get("PYTEST_CURRENT_TEST") or "selenium").split(" (")[0]
    tcs = sorted({f"TC-{a or b}" for a, b in _TC.findall(test)})
    d = Path(os.environ.get("ASDR_RESULTS_DIR", "test-results")) / "coverage"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "selenium.jsonl", "a") as f:
        f.write(json.dumps({"framework": "selenium", "test": test, "tc": tcs, "kind": kind, **extra}) + "\n")


def flow_step(step_id: str) -> None:
    _write("step", items=[step_id])


def covers(*items: str) -> None:
    _write("covers", items=list(items))


def metric(name: str, value: float, unit: str, budget: float | None = None) -> None:
    _write("metric", name=name, value=value, unit=unit, budget=budget)
