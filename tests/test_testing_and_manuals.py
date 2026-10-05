#!/usr/bin/env python3
"""v3.4 testing pipeline: run_tests.py → publish_test_report.py → build_manual.py,
plus run_metrics.py, init seeding and template copies. No browser needed: the
suites here are tiny commands that write JUnit the way each framework does."""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
SAMPLE = REPO / "examples" / "sample-app"


def png(path: Path):
    """Write a valid 2x2 PNG without Pillow."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.pop("ASDR_COMMIT", None)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=120)


PW_JUNIT = """<testsuites><testsuite name="a.spec.ts" tests="2" failures="1">
<testcase name="[TC-01] journey works" classname="a.spec.ts" time="1.2"><system-out>[[ATTACHMENT|../shots/ok.png]]</system-out></testcase>
<testcase name="[TC-02] error path" classname="a.spec.ts" time="0.4"><failure message="expected Saved">Error: expected Saved</failure>
<system-out>[[ATTACHMENT|../shots/fail.png]]</system-out></testcase></testsuite></testsuites>"""
CY_JUNIT = """<testsuites name="Cypress"><testsuite name="Root Suite" file="cypress/e2e/board.cy.js" tests="0"/>
<testsuite name="Board" tests="1"><testcase name="Board [TC-03] adds" classname="[TC-03] adds" time="0.9"/></testsuite></testsuites>"""
PY_JUNIT = """<testsuites><testsuite name="pytest" tests="1"><testcase classname="test_board" name="test_tc_04_counter" time="0.3">
<properties><property name="attachment" value="{shot}"/></properties></testcase></testsuite></testsuites>"""


class Project:
    """A throwaway project with three fake suites, one of them failing."""

    def __init__(self, fail=True, silent_suite=False):
        self.dir = Path(tempfile.mkdtemp(prefix="asdr-t-"))
        (self.dir / ".harness").mkdir()
        w = lambda name, body: (self.dir / name).write_text(textwrap.dedent(body))
        w("pw.py", f"""
            import os, pathlib
            r = pathlib.Path(os.environ['ASDR_RESULTS_DIR'])
            (r/'junit').mkdir(parents=True, exist_ok=True); (r/'shots').mkdir(exist_ok=True)
            for n in ('ok','fail'): (r/'shots'/(n+'.png')).write_bytes(b'png')
            xml = {PW_JUNIT!r}
            if not {fail!r}: xml = xml.replace('<failure message="expected Saved">Error: expected Saved</failure>', '')
            (r/'junit'/'playwright.xml').write_text(xml)
            m = pathlib.Path(os.environ['ASDR_MANUAL_DIR'])
            (m/'tours').mkdir(parents=True, exist_ok=True)
            (m/'tours'/'t.json').write_text('{{"tour":"t","framework":"playwright","commit":"'+os.environ['ASDR_COMMIT']+'","steps":[{{"id":"a","screenshot":"screens/t--a.png"}}]}}')
            raise SystemExit(1 if {fail!r} else 0)
        """)
        w("cy.py", f"""
            import os, pathlib
            r = pathlib.Path(os.environ['ASDR_RESULTS_DIR'])
            (r/'junit').mkdir(parents=True, exist_ok=True)
            (r/'cypress'/'videos').mkdir(parents=True, exist_ok=True)
            (r/'cypress'/'videos'/'board.cy.js.mp4').write_bytes(b'mp4')
            (r/'junit'/'cypress-abc.xml').write_text({CY_JUNIT!r})
        """)
        w("py.py", f"""
            import os, pathlib
            r = pathlib.Path(os.environ['ASDR_RESULTS_DIR'])
            (r/'junit').mkdir(parents=True, exist_ok=True)
            shot = pathlib.Path(os.environ['ASDR_RESULTS_DIR']).parent.parent / 'outside.png'
            shot.write_bytes(b'png')
            (r/'junit'/'selenium.xml').write_text({PY_JUNIT!r}.replace('{{shot}}', str(shot)))
        """)
        suites = [
            {"name": "playwright", "framework": "playwright", "cmd": f"{sys.executable} pw.py",
             "junit": ["junit/playwright.xml"]},
            {"name": "cypress", "framework": "cypress", "cmd": f"{sys.executable} cy.py",
             "junit": ["junit/cypress-*.xml"]},
            {"name": "selenium", "framework": "selenium", "cmd": f"{sys.executable} py.py",
             "junit": ["junit/selenium.xml"]},
        ]
        if silent_suite:
            suites.append({"name": "silent", "framework": "x", "cmd": "true", "junit": ["junit/none.xml"]})
        (self.dir / ".harness" / "test-config.json").write_text(json.dumps(
            {"schema": 1, "product": "Demo", "suites": suites}))

    def run_tests(self, *extra, env=None):
        return run([str(S / "run_tests.py"), *extra], self.dir, {"ASDR_COMMIT": "abc1234", **(env or {})})

    def summary(self):
        latest = json.loads((self.dir / ".harness/test-results/latest.json").read_text())
        return json.loads((Path(latest["path"]) / "summary.json").read_text())

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestRunTests(unittest.TestCase):
    def test_collects_three_frameworks_and_fails_on_a_failure(self):
        p = Project(fail=True)
        try:
            r = p.run_tests()
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            s = p.summary()
            self.assertEqual(s["status"], "failed")
            self.assertEqual(s["totals"]["tests"], 4)
            self.assertEqual(s["totals"]["failed"], 1)
            cases = {c["name"]: c for su in s["suites"] for c in su["cases"]}
            fail = cases["[TC-02] error path"]
            self.assertIn("expected Saved", fail["message"])
            self.assertEqual(fail["attachments"], ["shots/fail.png"])        # Playwright [[ATTACHMENT|]]
            self.assertEqual(cases["Board [TC-03] adds"]["attachments"],
                             ["cypress/videos/board.cy.js.mp4"])             # Cypress video by spec file
            sel = cases["test_tc_04_counter"]["attachments"]
            self.assertEqual(len(sel), 1)
            self.assertTrue(sel[0].startswith("attachments/"))                 # copied in from outside
            self.assertEqual(s["commit"], "abc1234")
            self.assertEqual(s["manual"]["tours"][0]["current"], True)
        finally:
            p.close()

    def test_passing_run_exits_zero(self):
        p = Project(fail=False)
        try:
            r = p.run_tests("--label", "sprint-01")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(p.summary()["label"], "sprint-01")
            hist = (p.dir / ".harness/test-results/history.jsonl").read_text().splitlines()
            self.assertEqual(len(hist), 1)
        finally:
            p.close()

    def test_silent_suite_is_an_error(self):
        p = Project(fail=False, silent_suite=True)
        try:
            r = p.run_tests()
            self.assertEqual(r.returncode, 1)
            silent = next(x for x in p.summary()["suites"] if x["name"] == "silent")
            self.assertEqual(silent["totals"]["error"], 1)
        finally:
            p.close()

    def test_live_without_a_screen_records_instead(self):
        p = Project(fail=False)
        try:
            env = {"DISPLAY": "", "WAYLAND_DISPLAY": "", "CI": "1"}
            r = p.run_tests("--live", env=env)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(p.summary()["mode"], "recorded")
            self.assertIn("no screen", r.stdout)
        finally:
            p.close()

    def test_missing_config_and_unknown_suite(self):
        d = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(run([str(S / "run_tests.py")], d).returncode, 2)
        finally:
            shutil.rmtree(d)
        p = Project()
        try:
            self.assertEqual(p.run_tests("--suite", "nope").returncode, 2)
        finally:
            p.close()

    def test_emit_facts_reads_the_latest_run(self):
        p = Project(fail=False)
        try:
            p.run_tests()
            r = run([str(S / "emit_facts.py"), "--no-tests", "--out", ".harness/facts.json"], p.dir)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = json.loads((p.dir / ".harness/facts.json").read_text())
            self.assertEqual(f["test_runs"]["status"], "passed")
            self.assertEqual(f["test_runs"]["suites"]["cypress"]["passed"], 1)
        finally:
            p.close()


class TestPublishReport(unittest.TestCase):
    def test_repo_and_private_single_file(self):
        p = Project(fail=True)
        try:
            p.run_tests()
            r = run([str(S / "publish_test_report.py"), "--label", "sprint-02 attempt-1"], p.dir)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = p.dir / "docs/test-reports/sprint-02-attempt-1"
            html = (out / "index.html").read_text()
            self.assertTrue(html.startswith("<!doctype html>"))
            self.assertIn("[TC-02] error path", html)
            self.assertIn("Tests failed", html)
            self.assertTrue((out / "assets/shots/fail.png").is_file())
            self.assertTrue((p.dir / "docs/test-reports/index.html").is_file())
            line = next(x for x in r.stdout.splitlines() if x.startswith("PUBLISH: "))
            pub = json.loads(line[len("PUBLISH: "):])
            self.assertNotIn("github_pages", pub["outputs"])          # private by default
            art = Path(pub["outputs"]["claude_artifact"]).read_text()
            self.assertNotIn("<!doctype", art.lower())                # Artifact-tool format
            self.assertIn("<title>", art[:8000])
            self.assertIn("data:image/png;base64,", art)
            self.assertIn("prefers-color-scheme: dark", art)
        finally:
            p.close()

    def test_publish_json_switches_targets(self):
        p = Project(fail=False)
        try:
            p.run_tests()
            (p.dir / ".harness/publish.json").write_text(json.dumps(
                {"repo": False, "ci_artifacts": False, "claude_artifact": False, "github_pages": True}))
            r = run([str(S / "publish_test_report.py")], p.dir)
            pub = json.loads(r.stdout.splitlines()[-1][len("PUBLISH: "):])
            self.assertEqual(set(pub["outputs"]), {"github_pages"})
            self.assertFalse((p.dir / "docs/test-reports").exists())
        finally:
            p.close()


class TestBuildManual(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-m-"))
        m = self.d / ".harness/manual"
        steps = []
        for i, sid in enumerate(["open", "name", "go", "board"], 1):
            png(m / f"screens/basics--{sid}.png")
            steps.append({"id": sid, "title": sid.title(), "screenshot": f"screens/basics--{sid}.png", "order": i})
        (m / "tours").mkdir(parents=True, exist_ok=True)
        (m / "tours/basics.json").write_text(json.dumps(
            {"schema": 1, "tour": "basics", "framework": "playwright", "commit": "abc1234", "steps": steps}))
        self.spec = {
            "schema": 1, "product": "Demo", "version": "1.2.0",
            "steps": {"basics/open": {"text": "Open it.", "levels": {"beginner": "Open the link."}},
                      "basics/name": "Type your **name**.", "basics/go": {"text": "Click **Go**."},
                      "basics/board": {"text": "Your board."}},
            "levels": [
                {"id": "member-getting-started", "kind": "persona", "persona": "Member", "part": "Getting started",
                 "sections": [{"title": "Sign in", "steps": ["basics/open..go"]}, {"title": "Board", "steps": ["basics/board"]}]},
                {"id": "beginner", "kind": "tier", "title": "Beginner", "sections": [{"title": "All", "steps": ["basics/*"]}]},
            ]}
        self.write_spec()
        (self.d / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.0] - 2026-10-01\n- Faster board\n\n## [1.1.0]\n- Old\n")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write_spec(self):
        (self.d / "docs/manuals").mkdir(parents=True, exist_ok=True)
        (self.d / "docs/manuals/manual.json").write_text(json.dumps(self.spec))

    def build(self, *extra):
        return run([str(S / "build_manual.py"), "--commit", "abc1234", "--no-pdf", *extra], self.d)

    def test_builds_every_level_with_version_banner(self):
        r = self.build("--artifact", "art.html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.d / "docs/manuals/1.2.0"
        beginner = (out / "beginner.html").read_text()
        self.assertIn("Open the link.", beginner)                      # per-level wording
        self.assertIn("Demo 1.2.0", beginner)
        self.assertIn("commit abc1234", beginner)
        self.assertIn("Faster board", beginner)                        # What's new from CHANGELOG
        self.assertNotIn("Old", beginner.split("What is new")[1].split("</section>")[0])
        gs = (out / "member-getting-started.html").read_text()
        self.assertEqual(gs.count('class="step"'), 4)                   # range open..go + board
        self.assertIn("<strong>name</strong>", gs)
        self.assertTrue((out / "screens/basics--open.png").is_file())
        b = json.loads((out / "build.json").read_text())
        self.assertEqual([lv["id"] for lv in b["levels"]], ["member-getting-started", "beginner"])
        art = (self.d / "art.html").read_text()
        self.assertNotIn("<!doctype", art.lower())
        self.assertIn('id="beginner"', art)
        self.assertTrue((self.d / "docs/manuals/index.html").is_file())

    def test_stale_screenshots_block_the_build(self):
        r = run([str(S / "build_manual.py"), "--commit", "fff0000", "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not fff0000", r.stdout)
        r = run([str(S / "build_manual.py"), "--commit", "fff0000", "--no-pdf", "--allow-stale"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_explanation_and_unknown_step(self):
        del self.spec["steps"]["basics/go"]
        self.spec["levels"][1]["sections"].append({"title": "X", "steps": ["basics/nope", "other/*"]})
        self.write_spec()
        r = self.build("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("'basics/go' has no explanation", r.stdout)
        self.assertIn("step 'nope' not in tour 'basics'", r.stdout)
        self.assertIn("tour 'other' was not captured", r.stdout)

    def test_warns_when_no_tier_manuals(self):
        self.spec["levels"] = self.spec["levels"][:1]
        self.write_spec()
        r = self.build("--check")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no experience-tier manuals", r.stdout)


class TestSupportingPieces(unittest.TestCase):
    def test_run_metrics_on_an_empty_project(self):
        d = Path(tempfile.mkdtemp())
        try:
            r = run([str(S / "run_metrics.py")], d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("# Run metrics", (d / "docs/run-metrics.md").read_text())
        finally:
            shutil.rmtree(d)

    def test_init_copies_e2e_templates_and_seeds_private_publish(self):
        d = Path(tempfile.mkdtemp())
        try:
            r = run([str(S / "init_asdr.py"), "--source", str(REPO)], d)
            self.assertEqual(r.returncode, 0, r.stdout)
            for f in ("e2e/playwright/asdr-manual.ts", "e2e/cypress/asdr-manual-plugin.js",
                      "e2e/selenium/conftest.py", "e2e/test-config.json", "e2e/manual.json",
                      "feature-list.md", "process-flows.md", "test-cases.md", "ci-asdr.yml"):
                self.assertTrue((d / ".harness/templates" / f).is_file(), f)
            pub = json.loads((d / ".harness/publish.json").read_text())
            self.assertEqual(pub["github_pages"], False)
            self.assertTrue((d / ".harness/scripts/report_style.py").is_file())
        finally:
            shutil.rmtree(d)

    def test_sample_app_uses_the_templates_unchanged(self):
        pairs = [
            ("templates/e2e/playwright/asdr-manual.ts", "examples/sample-app/e2e/playwright/asdr-manual.ts"),
            ("templates/e2e/cypress/asdr-manual.js", "examples/sample-app/cypress/support/asdr-manual.js"),
            ("templates/e2e/cypress/asdr-manual-plugin.js", "examples/sample-app/cypress/plugins/asdr-manual-plugin.js"),
            ("templates/e2e/cypress/cypress.config.js", "examples/sample-app/cypress.config.js"),
            ("templates/e2e/selenium/conftest.py", "examples/sample-app/e2e/selenium/conftest.py"),
            ("templates/e2e/selenium/asdr_manual.py", "examples/sample-app/e2e/selenium/asdr_manual.py"),
            ("templates/e2e/selenium/pytest.ini", "examples/sample-app/e2e/selenium/pytest.ini"),
        ]
        for a, b in pairs:
            self.assertEqual((REPO / a).read_text(), (REPO / b).read_text(), f"{b} drifted from {a}")

    def test_sample_manual_spec_is_valid(self):
        spec = json.loads((SAMPLE / "docs/manuals/manual.json").read_text())
        kinds = [lv["kind"] for lv in spec["levels"]]
        self.assertGreaterEqual(kinds.count("persona"), 4)
        self.assertEqual(sorted(lv["id"] for lv in spec["levels"] if lv["kind"] == "tier"),
                         ["administrator", "beginner", "everyday", "power"])


if __name__ == "__main__":
    unittest.main()
