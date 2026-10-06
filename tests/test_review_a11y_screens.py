#!/usr/bin/env python3
"""v3.5: manual wording checks + human review, accessibility aggregation,
saved logins / seeding in run_tests.py, and screenshot comparison."""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
sys.path.insert(0, str(S))
import compare_screens as cs  # noqa: E402


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.pop("ASDR_COMMIT", None)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=180)


def png_with_filters(path: Path, w: int, h: int, pixel):
    """Write an RGB PNG using filter types 0-4 in rotation, to exercise the decoder."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    rows = [bytes(v for x in range(w) for v in pixel(x, y)) for y in range(h)]
    out, prev = bytearray(), bytes(w * 3)
    for y, row in enumerate(rows):
        f = y % 5
        enc = bytearray()
        for i, v in enumerate(row):
            a = row[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            pred = {0: 0, 1: a, 2: b, 3: (a + b) >> 1, 4: cs._paeth(a, b, c)}[f]
            enc.append((v - pred) & 0xFF)
        out += bytes([f]) + enc
        prev = row
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cs.SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b""))
    return rows


def gradient(x, y):
    return ((x * 37 + y * 11) % 256, (x * 5 + y * 97) % 256, (x * y) % 256)


class TestCompareScreens(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-cs-"))

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_pure_python_decoder_handles_every_filter(self):
        rows = png_with_filters(self.d / "a.png", 23, 17, gradient)
        os.environ["ASDR_NO_PIL"] = "1"
        try:
            w, h, got = cs.read_png(self.d / "a.png")
        finally:
            del os.environ["ASDR_NO_PIL"]
        self.assertEqual((w, h), (23, 17))
        self.assertEqual(got, rows)

    def test_changed_unchanged_added_removed(self):
        base, cur = self.d / "base", self.d / "cur"
        png_with_filters(base / "same.png", 40, 40, gradient)
        shutil.copy(base / "same.png", cur.mkdir(parents=True) or cur / "same.png")
        png_with_filters(base / "moved.png", 40, 40, gradient)
        png_with_filters(cur / "moved.png", 40, 40,
                         lambda x, y: (255, 0, 0) if 5 <= x < 15 and 5 <= y < 15 else gradient(x, y))
        png_with_filters(base / "gone.png", 10, 10, gradient)
        png_with_filters(cur / "new.png", 10, 10, gradient)
        png_with_filters(base / "resized.png", 10, 10, gradient)
        png_with_filters(cur / "resized.png", 12, 10, gradient)
        os.environ["ASDR_NO_PIL"] = "1"
        try:
            rep = cs.compare_dirs(base, cur, self.d / "diffs")
        finally:
            del os.environ["ASDR_NO_PIL"]
        changed = {c["name"]: c for c in rep["changed"]}
        self.assertEqual(set(changed), {"moved.png", "resized.png"})
        self.assertAlmostEqual(changed["moved.png"]["pct"], 100 * 100 / 1600, places=2)
        self.assertIn("size changed", changed["resized.png"]["note"])
        self.assertEqual(rep["unchanged"], ["same.png"])
        self.assertEqual(rep["added"], ["new.png"])
        self.assertEqual(rep["removed"], ["gone.png"])
        w, h, rows = cs.read_png(self.d / "diffs" / "diff--moved.png")
        self.assertEqual(rows[10][30:33], cs.RED)                         # changed pixel marked red
        self.assertNotEqual(rows[30][90:93], cs.RED)


class TestManualWordingAndReview(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-rv-"))
        m = self.d / ".harness/manual"
        steps = []
        for i, (sid, text) in enumerate([("open", "Sign in\nYour name\nRole"), ("go", "Team board\nAdd task\nAll Active Done")], 1):
            png_with_filters(m / f"screens/t--{sid}.png", 8, 8, gradient)
            steps.append({"id": sid, "title": sid, "screenshot": f"screens/t--{sid}.png", "order": i,
                          "page_text": text, "target_text": "Sign in" if sid == "open" else None})
        (m / "tours").mkdir(parents=True, exist_ok=True)
        (m / "tours/t.json").write_text(json.dumps({"tour": "t", "commit": "abc1234", "steps": steps}))
        self.spec = {"product": "Demo", "version": "2.0.0",
                     "steps": {"t/open": "Type your name, then click **Sign in**.",
                               "t/go": "Click **Add task** or press **Enter**."},
                     "levels": [{"id": "beginner", "kind": "tier", "title": "Beginner",
                                 "sections": [{"title": "All", "steps": ["t/*"]}]}]}
        self.save()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def save(self):
        (self.d / "docs/manuals").mkdir(parents=True, exist_ok=True)
        (self.d / "docs/manuals/manual.json").write_text(json.dumps(self.spec))

    def bm(self, *a):
        return run([str(S / "build_manual.py"), "--commit", "abc1234", "--no-pdf", *a], self.d)

    def test_bold_names_must_be_on_screen(self):
        self.assertEqual(self.bm("--check").returncode, 0)                 # Enter is a key, Sign in on screen
        self.spec["steps"]["t/go"] = "Click **Save task**."
        self.save()
        r = self.bm("--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("names **Save task**, which is not on that screen", r.stdout)
        self.spec["steps"]["t/go"] = {"text": "Click **Save task**.", "offscreen": ["Save task"]}
        self.save()
        self.assertEqual(self.bm("--check").returncode, 0)                 # deliberate exception

    def test_whole_word_match(self):
        self.spec["steps"]["t/go"] = "Click **Add**."                      # "Add task" contains the word Add
        self.save()
        self.assertEqual(self.bm("--check").returncode, 0)
        self.spec["steps"]["t/go"] = "Click **Ad**."                       # not a word on screen
        self.save()
        self.assertEqual(self.bm("--check").returncode, 1)

    def test_review_cycle(self):
        r = self.bm("--require-review", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("'t/open' explanation is new", r.stdout)
        r = self.bm("--review-page", "review.html")
        self.assertEqual(r.returncode, 0, r.stdout)
        page = (self.d / "review.html").read_text()
        self.assertIn("Not reviewed yet", page)
        self.assertNotIn("<!doctype", page.lower())
        self.assertEqual(self.bm("--approve", "all", "--reviewer", "Bilal").returncode, 0)
        self.assertEqual(self.bm("--require-review", "--check").returncode, 0)
        self.bm("--require-review")
        html = (self.d / "docs/manuals/2.0.0/beginner.html").read_text()
        self.assertIn("Explanations reviewed by Bilal", html)
        # A changed explanation needs reading again; the other stays approved.
        self.spec["steps"]["t/go"] = "Click **Add task**."
        self.save()
        r = self.bm("--require-review", "--check")
        self.assertIn("'t/go' explanation is changed since it was approved", r.stdout)
        self.assertNotIn("'t/open'", r.stdout)
        r = self.bm("--flag", "t/go", "--note", "say where the button is", "--reviewer", "Bilal")
        self.assertEqual(r.returncode, 0)
        r = self.bm("--require-review", "--check")
        self.assertIn("flagged for fixing by Bilal: say where the button is", r.stdout)
        self.assertEqual(self.bm("--flag", "t/go").returncode, 1)          # a flag needs a note
        self.assertEqual(self.bm("--approve", "t/nope").returncode, 1)

    def test_compare_to_previous_version(self):
        self.assertEqual(self.bm().returncode, 0)                          # 2.0.0 baseline
        png_with_filters(self.d / ".harness/manual/screens/t--go.png", 8, 8, lambda x, y: (0, 0, 0))
        self.spec["version"] = "2.1.0"
        self.save()
        r = self.bm()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("compared with 2.0.0: 1 screens changed", r.stdout)
        out = self.d / "docs/manuals/2.1.0"
        self.assertTrue((out / "ui-changes.html").is_file())
        self.assertTrue((out / "changes/diff--t--go.png").is_file())
        self.assertTrue((out / "changes/before--t--go.png").is_file())
        self.assertIn("Screen changed since 2.0.0", (out / "beginner.html").read_text())
        b = json.loads((out / "build.json").read_text())
        self.assertEqual([c["name"] for c in b["ui_changes"]["changed"]], ["t--go.png"])
        r = self.bm("--compare-to", "none")
        self.assertNotIn("compared with", r.stdout)


class TestRunTestsAuthSeedA11y(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-ra-"))
        (self.d / ".harness").mkdir()
        (self.d / "suite.py").write_text(
            "import os, json, pathlib\n"
            "r = pathlib.Path(os.environ['ASDR_RESULTS_DIR'])\n"
            "(r/'junit').mkdir(parents=True, exist_ok=True); (r/'a11y').mkdir(exist_ok=True)\n"
            "auth = pathlib.Path(os.environ['ASDR_AUTH_DIR']); (auth/'admin.json').write_text('{}')\n"
            "assert os.environ.get('ASDR_USER_ADMIN') == 'admin@example.test', os.environ.get('ASDR_USER_ADMIN')\n"
            "assert pathlib.Path('seeded.txt').read_text() == 'ok'\n"
            "v = [{'id':'color-contrast','impact':'serious','help':'Contrast','helpUrl':'u','nodes':2,'targets':['p']}]\n"
            "(r/'a11y'/'playwright--t--board.json').write_text(json.dumps({'framework':'playwright','test':'t','label':'board','url':'/','violations':v,'passes':20}))\n"
            "(r/'a11y'/'cypress--t--home.json').write_text(json.dumps({'framework':'cypress','test':'t','label':'home','url':'/','violations':[],'passes':22}))\n"
            "(r/'junit'/'s.xml').write_text('<testsuite><testcase name=\"[TC-01] ok\" classname=\"c\"/></testsuite>')\n")
        self.cfg = {"schema": 1, "product": "Demo",
                    "app": {"seed_cmd": f"{sys.executable} -c \"open('seeded.txt','w').write('ok')\""},
                    "env": {"ASDR_USER_ADMIN": "admin@example.test", "ASDR_PASS_ADMIN": "${ASDR_TEST_SECRET_X}"},
                    "suites": [{"name": "s", "framework": "playwright", "cmd": f"{sys.executable} suite.py",
                                "junit": ["junit/s.xml"]}]}
        self.write()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self):
        (self.d / ".harness/test-config.json").write_text(json.dumps(self.cfg))

    def summary(self):
        p = json.loads((self.d / ".harness/test-results/latest.json").read_text())["path"]
        return json.loads((Path(p) / "summary.json").read_text())

    def test_seed_env_auth_and_a11y(self):
        stale = self.d / ".harness/auth/old.json"
        stale.parent.mkdir(parents=True)
        stale.write_text("{}")
        r = run([str(S / "run_tests.py")], self.d, {"ASDR_COMMIT": "abc1234"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ASDR_PASS_ADMIN refer to variables that are not set", r.stdout)
        s = self.summary()
        self.assertEqual(s["seed"]["exit_code"], 0)
        self.assertEqual(s["saved_logins"], ["admin"])                    # stale file cleared first
        self.assertEqual((self.d / ".harness/auth/.gitignore").read_text(), "*\n")
        a = s["a11y"]
        self.assertEqual(a["checks"], 2)
        self.assertEqual(a["by_impact"]["serious"], 1)
        self.assertEqual(a["rules"][0]["where"], ["board (playwright)"])
        self.assertIn("accessibility: 2 checks", r.stdout)
        run([str(S / "publish_test_report.py"), "--label", "x"], self.d)
        html = (self.d / "docs/test-reports/x/index.html").read_text()
        self.assertIn("<h2>Accessibility</h2>", html)
        self.assertIn("color-contrast", html)
        run([str(S / "emit_facts.py"), "--no-tests", "--out", ".harness/facts.json"], self.d)
        f = json.loads((self.d / ".harness/facts.json").read_text())
        self.assertEqual(f["test_runs"]["a11y"]["serious"], 1)

    def test_seed_failure_stops_the_run(self):
        self.cfg["app"]["seed_cmd"] = f"{sys.executable} -c \"raise SystemExit(3)\""
        self.write()
        r = run([str(S / "run_tests.py")], self.d)
        self.assertEqual(r.returncode, 2)
        self.assertIn("seed_cmd failed with exit 3", r.stdout)


class TestTemplateCopies(unittest.TestCase):
    def test_sample_uses_the_new_helpers_unchanged(self):
        pairs = [
            ("templates/e2e/playwright/asdr-auth.ts", "examples/sample-app/e2e/playwright/asdr-auth.ts"),
            ("templates/e2e/playwright/auth.setup.ts", "examples/sample-app/e2e/playwright/auth.setup.ts"),
            ("templates/e2e/playwright/asdr-a11y.ts", "examples/sample-app/e2e/playwright/asdr-a11y.ts"),
            ("templates/e2e/cypress/asdr-auth.js", "examples/sample-app/cypress/support/asdr-auth.js"),
            ("templates/e2e/cypress/asdr-a11y.js", "examples/sample-app/cypress/support/asdr-a11y.js"),
            ("templates/e2e/cypress/asdr-a11y-plugin.js", "examples/sample-app/cypress/plugins/asdr-a11y-plugin.js"),
            ("templates/e2e/selenium/asdr_auth.py", "examples/sample-app/e2e/selenium/asdr_auth.py"),
            ("templates/e2e/selenium/asdr_a11y.py", "examples/sample-app/e2e/selenium/asdr_a11y.py"),
            ("templates/e2e/playwright/asdr-cover.ts", "examples/sample-app/e2e/playwright/asdr-cover.ts"),
            ("templates/e2e/cypress/asdr-cover.js", "examples/sample-app/cypress/support/asdr-cover.js"),
            ("templates/e2e/cypress/asdr-cover-plugin.js", "examples/sample-app/cypress/plugins/asdr-cover-plugin.js"),
            ("templates/e2e/selenium/asdr_cover.py", "examples/sample-app/e2e/selenium/asdr_cover.py"),
            ("templates/e2e/cypress/cypress.config.js", "examples/sample-app/cypress.config.js"),
        ]
        for a, b in pairs:
            self.assertEqual((REPO / a).read_text(), (REPO / b).read_text(), f"{b} drifted from {a}")
        norm = lambda t: re.sub(r"^const startCmd = .*$", "", t, flags=re.MULTILINE)
        self.assertEqual(norm((REPO / "templates/e2e/playwright/playwright.config.ts").read_text()),
                         norm((REPO / "examples/sample-app/playwright.config.ts").read_text()))

    def test_tour_helpers_record_on_screen_text(self):
        for f in ("templates/e2e/playwright/asdr-manual.ts", "templates/e2e/cypress/asdr-manual.js",
                  "templates/e2e/cypress/asdr-manual-plugin.js", "templates/e2e/selenium/asdr_manual.py"):
            self.assertIn("page_text", (REPO / f).read_text(), f)


if __name__ == "__main__":
    unittest.main()
