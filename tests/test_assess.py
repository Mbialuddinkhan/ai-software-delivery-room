#!/usr/bin/env python3
"""v3.6: /assess — evidence gate, scanner wrapper, two-part report.

The assessment describes a client's weaknesses, so the gates matter more than
the prose: nothing ships without evidence that resolves, no secret value ever
lands in a document, and the report states its rating rule and labels every
estimate."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
SAMPLE = REPO / "examples" / "sample-app"
ASSESS = SAMPLE / "docs" / "assess"
sys.path.insert(0, str(S))
import build_assess_report as bar  # noqa: E402


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last_json(stdout, tag):
    line = [x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1]
    return json.loads(line[len(tag) + 2:])


class TestValidateAssessment(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-va-"))
        self.findings = json.loads((ASSESS / "findings.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def validate(self, findings=None, strict=True):
        args = [str(S / "validate_assessment.py"), "--root", str(SAMPLE),
                "--as-is", str(ASSESS / "as-is.json")]
        if findings is not None:
            f = self.d / "findings.json"
            f.write_text(json.dumps(findings))
            args += ["--findings", str(f)]
        else:
            args += ["--findings", str(ASSESS / "findings.json")]
        if strict:
            args.append("--strict")
        r = run(args, self.d)
        return r, last_json(r.stdout, "ASSESS-VALIDATE")

    def test_sample_passes_strict(self):
        r, res = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(res["ok"])
        self.assertEqual(res["issues"], 0)
        self.assertGreater(res["counts"]["features"], 0)
        self.assertGreater(res["counts"]["flow_steps"], 0)

    def test_uncited_finding_fails(self):
        bad = self.findings + [{**self.findings[0], "id": "T-99", "evidence": ["trust me"]}]
        r, res = self.validate(bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERROR: finding T-99: no evidence resolves", r.stdout)
        # without --strict it is a warning, not a failure
        r, res = self.validate(bad, strict=False)
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN: finding T-99", r.stdout)

    def test_line_past_end_of_file_fails(self):
        bad = [{**self.findings[0], "evidence": ["app/app.js:99999"]}]
        r, _ = self.validate(bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("line 99999 >", r.stdout)

    def test_pasted_secret_always_fails(self):
        # assembled at run time so no secret-shaped literal sits in the repo
        for value in ['api_key = "' + "not-a-real-" + "value-42" + '"',
                      "-----BEGIN RSA " + "PRIVATE KEY-----",
                      ".".join(["eyJ" + "a" * 14, "b" * 14, "c" * 8])]:
            bad = [{**self.findings[0], "what": f"found {value} in config"}]
            r, res = self.validate(bad, strict=False)          # fails even without --strict
            self.assertEqual(r.returncode, 1, value)
            self.assertEqual(res["secrets"], 1, value)
            self.assertIn("SECRET:", r.stdout)

    def test_citation_anywhere_in_the_string(self):
        ok = [{**self.findings[0], "evidence": ["see app/app.js:7-13 and app/index.html:28 (role picker)"]}]
        r, res = self.validate(ok)
        self.assertEqual(r.returncode, 0, r.stdout)
        notes = [{**self.findings[0], "evidence": ["db: tasks table has no owner column"]}]
        r, res = self.validate(notes)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_vocabularies(self):
        for field, value in [("severity", "urgent"), ("confidence", "sure"), ("area", "vibes"), ("effort", "XL")]:
            bad = [{**self.findings[0], field: value}]
            r, _ = self.validate(bad)
            self.assertEqual(r.returncode, 1, field)
            self.assertIn(f"{field} '{value}'", r.stdout)

    def test_nothing_to_validate(self):
        r = run([str(S / "validate_assessment.py"), "--root", str(self.d)], self.d)
        self.assertEqual(r.returncode, 1)
        self.assertFalse(last_json(r.stdout, "ASSESS-VALIDATE")["ok"])


class TestAssessScan(unittest.TestCase):
    def test_no_tools_is_reported_not_fatal(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-scan-"))
        empty = d / "nobin"
        empty.mkdir()
        try:
            r = run([str(S / "assess_scan.py"), "--target", str(SAMPLE / "app"), "--out", str(d / "ev")], d,
                    env={"PATH": str(empty)})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            st = last_json(r.stdout, "ASSESS-SCAN")["status"]
            for t in ("osv-scanner", "trivy", "semgrep", "gitleaks", "lizard", "jscpd"):
                self.assertEqual(st[t], "missing", t)
            self.assertEqual(st["git"], "skipped")
            summary = json.loads((d / "ev/scan-summary.json").read_text())
            self.assertGreater(summary["inventory"]["total_files"], 0)
            self.assertEqual(summary["hotspots"], [])
            md = (d / "ev/scan-summary.md").read_text()
            self.assertIn("Not installed (not run)", md)
            self.assertIn("semgrep", md)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_bad_target(self):
        d = Path(tempfile.mkdtemp(prefix="asdr-scan-"))
        try:
            r = run([str(S / "assess_scan.py"), "--target", str(d / "nope")], d)
            self.assertEqual(r.returncode, 1)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestAssessReport(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-rep-"))
        self.home = self.d / "home"
        self.home.mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def build(self, *extra):
        r = run([str(S / "build_assess_report.py"), "--dir", str(ASSESS), "--out", str(self.d / "report"),
                 "--no-pdf", *extra], self.d, env={"HOME": str(self.home)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, (self.d / "report/index.html").read_text()

    def test_two_parts_rule_and_estimates(self):
        r, h = self.build()
        self.assertIn("Part A · Business report", h)
        self.assertIn("Part B · Technical appendix", h)
        self.assertIn('class="est">estimate', h)
        self.assertIn("Weak", h)                         # the sample has high findings
        self.assertIn("T-01", h)
        self.assertIn("app/app.js:7-13", h)              # evidence is shown
        self.assertIn("built-in neutral", r.stdout)      # no brand file anywhere → neutral
        self.assertIn(">AS<", h)
        self.assertIn("do not publish", r.stdout)
        self.assertFalse(any(p.name != "index.html" for p in (self.d / "report").iterdir()))  # no fragment, no pdf

    def test_brand_file_and_fragment(self):
        brand = self.d / "brand.json"
        brand.write_text(json.dumps({"monogram": "BK", "lockup": "Bilal Uddin Khan", "reference_prefix": "BK",
                                     "footer": "TEST FOOTER", "colors": {"blue": "#23408E"}}))
        frag = self.d / "frag.html"
        r, h = self.build("--brand", str(brand), "--fragment", str(frag))
        self.assertIn(">BK<", h)
        self.assertIn("Bilal Uddin Khan", h)
        self.assertIn("TEST FOOTER", h)
        self.assertTrue(frag.is_file())
        self.assertNotIn("<!doctype", frag.read_text().lower())

    def test_home_brand_is_used(self):
        (self.home / ".asdr").mkdir()
        (self.home / ".asdr/brand.json").write_text(json.dumps({"monogram": "ZZ"}))
        r, h = self.build()
        self.assertIn(">ZZ<", h)

    def test_rating_rule(self):
        self.assertEqual(bar.rating([{"area": "code", "severity": "critical"}], "code")[0], "Critical")
        self.assertEqual(bar.rating([{"area": "code", "severity": "high"}, {"area": "code", "severity": "low"}], "code")[0], "Weak")
        self.assertEqual(bar.rating([{"area": "code", "severity": "medium"}], "code")[0], "Fair")
        self.assertEqual(bar.rating([{"area": "code", "severity": "low"}], "code")[0], "Good")
        self.assertEqual(bar.rating([{"area": "data", "severity": "high"}], "code")[0], "Not assessed")
        self.assertEqual(bar.process_rating([1] * 10, [])[0], "Weak")
        self.assertEqual(bar.process_rating([1] * 4, [])[0], "Fair")
        self.assertEqual(bar.process_rating([1], [])[0], "Good")

    def test_markdown(self):
        h = bar.md_to_html("# Title\n\n**b** `c` <script>x</script>\n\n- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n"
                           "```mermaid\ngraph TD; A-->B\n```\n")
        self.assertIn("<h2>Title</h2>", h)                    # headings are demoted under the report's own
        self.assertIn("<b>b</b> <code>c</code>", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn("<ul><li>a</li><li>b</li></ul>", h)
        self.assertIn("<th>x</th>", h)
        self.assertIn('<pre class="mermaid">', h)

    def test_missing_inputs(self):
        r = run([str(S / "build_assess_report.py"), "--dir", str(self.d / "nothing"), "--no-pdf"], self.d)
        self.assertEqual(r.returncode, 1)


class TestAssessWiring(unittest.TestCase):
    def test_templates_ship(self):
        for f in ("intake.json", "as-is.json", "findings.json", "opportunities.json", "technical.md", "brand.json"):
            self.assertTrue((REPO / "templates/assess" / f).is_file(), f)
        for f in ("intake.json", "as-is.json", "findings.json", "opportunities.json"):
            json.loads((REPO / "templates/assess" / f).read_text())

    def test_skill_ground_rules(self):
        sk = (REPO / "skills/assess/SKILL.md").read_text()
        for needle in ("Authorisation first", "Defensive only", "Evidence or it does not ship",
                       "Never copy a secret", "Private.", "validate_assessment.py --root <source path> --strict",
                       "rea-agents@6.4.0", "rea_allowed", "Characterisation tests"):
            self.assertIn(needle, sk)

    def test_agents_have_assess_mode(self):
        for a in ("business-analyst", "solution-architect", "security-compliance", "devops", "product-owner"):
            self.assertIn("ASSESS", (REPO / "agents" / f"{a}.md").read_text(), a)
        self.assertIn("haracterisation", (REPO / "agents/generator.md").read_text())

    def test_brand_template_has_no_real_contact(self):
        b = json.loads((REPO / "templates/assess/brand.json").read_text())
        self.assertNotIn("@bilalkhan", json.dumps(b))


if __name__ == "__main__":
    unittest.main()
