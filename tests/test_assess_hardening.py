#!/usr/bin/env python3
"""v3.7: what the first full /assess run (eShopOnWeb, Oct 2026) broke, pinned.

Each test names the defect the run exposed. None of these were caught by the
v3.6 tests because the v3.6 sample was small, single-reviewer and JavaScript."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
sys.path.insert(0, str(S))
import assess_scan as scan  # noqa: E402
import build_assess_report as bar  # noqa: E402
import validate_assessment as va  # noqa: E402


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=e, timeout=300)


def last_json(stdout, tag):
    line = [x for x in stdout.splitlines() if x.startswith(tag + ": ")][-1]
    return json.loads(line[len(tag) + 2:])


def finding(fid, title, evidence, sev="medium", area="code"):
    return {"id": fid, "area": area, "title": title, "severity": sev, "confidence": "confirmed",
            "evidence": evidence, "what": "w", "business_impact": "b", "fix": "f", "effort": "S"}


class Fixture(unittest.TestCase):
    """A tiny .NET-shaped source tree plus an assessment folder."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="asdr-hard-"))
        self.src = self.d / "source"            # named "source" on purpose: it broke osv-scanner's argument parsing
        (self.src / "src/Web/Views").mkdir(parents=True)
        (self.src / "src/Core").mkdir(parents=True)
        (self.src / "src/Core/Constants.cs").write_text(
            "namespace Core;\npublic static class Constants\n{\n"
            '    public const string DEFAULT_PASSWORD = "Zq7#notreal";\n'
            '    public const string JWT_SECRET_KEY = "LettersOnlySigningKeyThatIsLong";\n'
            '    public const string Role = "Administrators";\n}\n')
        (self.src / "src/Web/Views/_Layout.cshtml").write_text(
            "<html><head>\n"
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.3.6/css/bootstrap.min.css" />\n'
            "</head><body>\n"
            '<script src="https://ajax.aspnetcdn.com/ajax/jquery/jquery-2.2.0.min.js"></script>\n'
            '<script src="https://cdn.jsdelivr.net/npm/lodash@4.17.20/lodash.min.js"\n'
            '        integrity="sha384-abc" crossorigin="anonymous"></script>\n'
            "</body></html>\n")
        (self.src / "src/Web/libman.json").write_text(json.dumps(
            {"version": "1.0", "libraries": [{"library": "jquery-validate@1.19.5", "destination": "wwwroot/lib/v/"}]}, indent=2))
        (self.src / "src/Web/Web.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk.Web">\n  <ItemGroup>\n'
            '    <PackageReference Include="Azure.Identity" Version="1.10.4" />\n'
            '    <PackageReference Include="Serilog">\n      <Version>2.10.0</Version>\n    </PackageReference>\n'
            "  </ItemGroup>\n</Project>\n")
        (self.src / "Directory.Packages.props").write_text(
            '<Project><ItemGroup><PackageVersion Include="System.Text.Json" Version="8.0.0" /></ItemGroup></Project>\n')
        (self.src / "src/Web/Index.razor").write_text("@page \"/\"\n<h1>Hi</h1>\n")
        self.docs = self.d / "docs/assess"
        (self.docs / "evidence").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def validate(self, findings_by_file, extra=()):
        for name, items in findings_by_file.items():
            (self.docs / name).write_text(json.dumps(items))
        first = sorted(findings_by_file)[0]
        r = run([str(S / "validate_assessment.py"), "--root", str(self.src), "--as-is", str(self.docs / "as-is.json"),
                 "--findings", str(self.docs / first), "--strict", *extra], self.d)
        return r, last_json(r.stdout, "ASSESS-VALIDATE")


class TestEveryCitationResolves(Fixture):
    def test_a_wrong_line_next_to_a_right_one_fails(self):
        # v3.6 accepted a finding if ANY citation resolved; reviewers found wrong lines it let through
        r, res = self.validate({"findings-architecture.json": [
            finding("A-01", "Constants hold credentials", ["src/Core/Constants.cs:4", "src/Core/Constants.cs:400"])]})
        self.assertFalse(res["ok"])
        self.assertIn("citation does not resolve — src/Core/Constants.cs:400 (file has 7 lines)", r.stdout)

    def test_history_note_and_urls_are_not_path_checked(self):
        r, res = self.validate({"findings-security.json": [finding("S-01", "Key in history", [
            "src/Core/Constants.cs:5",
            "git: commit c783174 src/Web/key-old.xml:2 (file exists only in history)",
            "see https://github.com/org/repo/blob/main/src/Gone.cs:12 for the upstream fix"], area="security")]})
        self.assertTrue(res["ok"], r.stdout)

    def test_reversed_range_fails(self):
        r, res = self.validate({"findings-process.json": [finding("P-01", "x", ["src/Core/Constants.cs:6-2"], area="process")]})
        self.assertFalse(res["ok"])


class TestPerReviewerFiles(Fixture):
    def test_merged_and_not_double_counted_when_named_directly(self):
        # v3.7 regression: --findings naming one of the merged files counted it twice → every id "used twice"
        r, res = self.validate({
            "findings-process.json": [finding("P-01", "Orders ship to one address", ["src/Core/Constants.cs:1"], area="process")],
            "findings-security.json": [finding("S-01", "Signing key in code", ["src/Core/Constants.cs:5"], area="security")]})
        self.assertTrue(res["ok"], r.stdout)
        self.assertEqual(res["counts"]["findings"], 2)
        self.assertNotIn("used twice", r.stdout)

    def test_same_id_in_two_files_is_an_error(self):
        r, res = self.validate({
            "findings-architecture.json": [finding("A-01", "One", ["src/Core/Constants.cs:1"])],
            "findings-operations.json": [finding("A-01", "Two", ["src/Core/Constants.cs:2"], area="operations")]})
        self.assertFalse(res["ok"])
        self.assertIn("finding id A-01 is used twice", r.stdout)


class TestDuplicates(unittest.TestCase):
    def test_same_issue_from_two_reviewers_is_flagged(self):
        a = finding("O-12", "Both production databases accept connections from almost every address",
                    ["infra/sql.bicep:33-42", "infra/sql.bicep:23"], area="operations")
        b = finding("S-02", "Both production databases accept connections from any internet address",
                    ["infra/sql.bicep:23", "infra/sql.bicep:33-42"], area="security")
        self.assertEqual(len(va.duplicates([a, b])), 1)

    def test_sharing_a_supporting_line_is_not_a_duplicate(self):
        # the first heuristic flagged 54 pairs on eShopOnWeb: reviewers cite Program.cs for everything
        a = finding("O-10", "CI only compiles and runs tests", ["ci.yml:11-16", "Program.cs:20"], area="operations")
        b = finding("S-12", "The build pipeline uses movable action tags", ["ci.yml:11-16"], area="security")
        self.assertEqual(va.duplicates([a, b]), [])

    def test_same_reviewer_is_never_compared(self):
        a = finding("A-01", "Same words here exactly", ["x.cs:1"])
        b = finding("A-02", "Same words here exactly", ["x.cs:1"])
        self.assertEqual(va.duplicates([a, b]), [])


class TestCredentialSweep(Fixture):
    def test_values_harvested_from_source(self):
        c = va.harvest_credentials(self.src)
        self.assertEqual(sorted(c.values()), ["src/Core/Constants.cs:4", "src/Core/Constants.cs:5"])  # not "Administrators"

    def test_value_in_evidence_fails_and_is_never_printed(self):
        # v3.6 leak: jscpd clone fragments carried the seeded password into evidence/
        (self.docs / "evidence/jscpd-report.json").write_text(json.dumps(
            {"duplicates": [{"fragment": 'DEFAULT_PASSWORD = "Zq7#notreal";'}]}))
        r, res = self.validate({"findings-security.json": [finding("S-01", "Default password", ["src/Core/Constants.cs:4"],
                                                                   area="security")]})
        self.assertFalse(res["ok"])
        self.assertGreaterEqual(res["secrets"], 1)
        self.assertIn("contains the credential value assigned at src/Core/Constants.cs:4", r.stdout)
        self.assertNotIn("Zq7#notreal", r.stdout + r.stderr)

    def test_letters_only_signing_key_is_caught_in_a_markdown_file(self):
        (self.docs / "technical-security.md").write_text("The key is LettersOnlySigningKeyThatIsLong, rotate it.\n")
        r, res = self.validate({"findings-security.json": [finding("S-01", "Key", ["src/Core/Constants.cs:5"], area="security")]})
        self.assertFalse(res["ok"])
        self.assertIn("Constants.cs:5", r.stdout)

    def test_pattern_inside_an_evidence_json_string(self):
        (self.docs / "evidence/semgrep.json").write_text(json.dumps(
            {"results": [{"extra": {"message": 'api_key = "' + "abcdef" + '123456"'}}]}))
        r, res = self.validate({"findings-security.json": [finding("S-01", "Key", ["src/Core/Constants.cs:5"], area="security")]})
        self.assertFalse(res["ok"])
        self.assertIn("looks like a key, token or password value", r.stdout)


class TestScanner(Fixture):
    def test_scrub_removes_copied_code(self):
        f = self.d / "x.json"
        f.write_text(json.dumps({"duplicates": [{"fragment": "secret code", "firstFile": {"name": "a.cs", "start": 1}}],
                                 "results": [{"extra": {"lines": "code line", "severity": "WARNING"}}],
                                 "leaks": [{"Secret": "REDACTED", "Match": "REDACTED", "Line": "pwd = x", "StartLine": 3}]}))
        self.assertEqual(scan.scrub_code(f), 5)
        d = json.loads(f.read_text())
        self.assertNotIn("fragment", d["duplicates"][0])
        self.assertEqual(d["leaks"][0]["StartLine"], 3)
        self.assertEqual(d["results"][0]["extra"]["severity"], "WARNING")

    def test_inventory_counts_razor_and_cshtml(self):
        inv = scan.inventory(self.src)
        self.assertIn(".cshtml", inv["lines_by_ext"])
        self.assertIn(".razor", inv["lines_by_ext"])

    def test_nuget_packages_from_projects(self):
        pk = scan.nuget_packages(self.src)
        self.assertEqual(pk, {"Azure.Identity": "1.10.4", "Serilog": "2.10.0", "System.Text.Json": "8.0.0"})

    def test_frontend_libraries_offline(self):
        import urllib.request
        real = urllib.request.urlopen

        def offline(*a, **k):
            raise OSError("no network in this test")
        urllib.request.urlopen = offline
        try:
            out = self.d / "ev"
            out.mkdir()
            res = scan.frontend(self.src, out, 10)
        finally:
            urllib.request.urlopen = real
        self.assertEqual(res["status"], "listed-unchecked")
        libs = json.loads((out / "osv-frontend.json").read_text())["libraries"]
        got = {(x["name"], x["version"], x["source"], x["integrity"]) for x in libs}
        self.assertEqual(got, {("bootstrap", "3.3.6", "cdn", False), ("jquery", "2.2.0", "cdn", False),
                               ("lodash", "4.17.20", "cdn", True), ("jquery-validation", "1.19.5", "libman", None)})
        self.assertEqual(res["cdn_without_integrity"], 2)
        lodash = next(x for x in libs if x["name"] == "lodash")
        self.assertEqual(lodash["location"], "src/Web/Views/_Layout.cshtml:5")   # multi-line tag: line of its start

    def test_hotspot_needs_two_changes(self):
        cx = {"_by_file": {"a.cs": {"ccn_total": 77, "ccn_max": 7, "nloc": 300},
                           "b.cs": {"ccn_total": 5, "ccn_max": 2, "nloc": 40}}}
        ch = {"_changes": {"a.cs": 1, "b.cs": 9}}
        self.assertEqual([h["file"] for h in scan.hotspots(cx, ch)], ["b.cs"])

    def test_dotnet_repo_without_lockfile_is_never_reported_clean(self):
        # osv-scanner exits 128 "No package sources found" on a .NET repo: v3.6 recorded that as 0 vulnerable
        bin_ = self.d / ".harness/bin"
        bin_.mkdir(parents=True)
        fake = bin_ / "osv-scanner"
        fake.write_text("#!/bin/sh\n"
                        "case \"$*\" in *-L*) echo '{\"results\":[{\"packages\":[{\"package\":{\"name\":\"Azure.Identity\","
                        "\"version\":\"1.10.4\"},\"groups\":[{\"max_severity\":\"5.5\"}],\"vulnerabilities\":[{\"id\":\"X\"}]}]}]}';;\n"
                        "*) echo 'No package sources found' >&2; exit 128;; esac\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        r = run([str(S / "assess_scan.py"), "--target", str(self.src), "--out", "ev",
                 "--skip", "semgrep,secrets,complexity,duplication,churn,frontend"], self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        o = json.loads((self.d / "ev/scan-summary.json").read_text())["tools"]["deps"]["osv-scanner"]
        self.assertEqual(o["status"], "ran")
        self.assertEqual(o["vulnerable_packages"], 1)
        self.assertEqual(o["packages_scanned"], 3)
        self.assertIn("direct packages only", (self.d / "ev/scan-summary.md").read_text())

    def test_summary_states_what_scanners_miss(self):
        r = run([str(S / "assess_scan.py"), "--target", str(self.src), "--out", "ev2",
                 "--skip", "deps,semgrep,secrets,complexity,duplication,churn,frontend"], self.d, env={"PATH": "/nonexistent"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("## What these scanners do not cover", (self.d / "ev2/scan-summary.md").read_text())


class TestReport(Fixture):
    def setUp(self):
        super().setUp()
        (self.docs / "intake.json").write_text(json.dumps({"client": "C", "system": "Shop", "reference": "BK-2026-T99",
                                                          "scope": {"access": ["source code", "git history"]}}))
        (self.docs / "as-is.json").write_text(json.dumps({"unknowns": [
            {"id": "U-01", "question": "Is it live?", "why": "urgency"},
            {"id": "U-02", "question": "Who uses the API?", "why": "route"}]}))
        (self.docs / "findings-security.json").write_text(json.dumps([finding("S-01", "Key", ["src/Core/Constants.cs:5"], "critical", "security")]))
        (self.docs / "findings-process.json").write_text(json.dumps([finding("P-01", "No payment", ["src/Core/Constants.cs:1"], "high", "process")]))
        (self.docs / "technical-architecture.md").write_text("# Technical assessment — Shop\n\n## 01 Architecture\n\nArchitecture words.\n")
        (self.docs / "technical-security.md").write_text("## 03 Security\n\nSecurity words.\n")
        (self.docs / "evidence/triage.json").write_text(json.dumps([
            {"tool": "semgrep", "verdict": "confirmed"}, {"tool": "semgrep", "verdict": "false-alarm"},
            {"tool": "osv-frontend", "verdict": "not-applicable"}]))

    def build(self):
        r = run([str(S / "build_assess_report.py"), "--dir", str(self.docs), "--out", str(self.d / "rep"), "--no-pdf"],
                self.d, env={"HOME": str(self.d)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return (self.d / "rep/index.html").read_text()

    def test_curated_questions_numbered_and_unknowns_in_part_b(self):
        # v3.6 bug: Part A said "answer question 2" but showed the raw unknowns, never the curated list
        (self.docs / "opportunities.json").write_text(json.dumps({"questions": [
            {"ids": ["U-01"], "question": "Is this a live shop?", "why": "Decides urgency"},
            "Who else reads the database?"]}))
        h = self.build()
        self.assertIn(">Q1<", h)
        self.assertIn(">Q2<", h)
        self.assertIn("Is this a live shop?", h)
        self.assertIn("Every open point", h)
        self.assertIn("Who uses the API?", h)

    def test_without_curated_questions_the_unknowns_are_asked(self):
        h = self.build()
        self.assertNotIn(">Q1<", h)
        self.assertIn("Who uses the API?", h)

    def test_merges_reviewer_files_and_triage(self):
        h = self.build()
        self.assertIn("S-01", h)
        self.assertIn("P-01", h)
        self.assertIn("Security words.", h)
        self.assertIn("Architecture words.", h)
        self.assertIn("How the scanner hits were triaged", h)

    def test_method_never_claims_access_that_was_not_given(self):
        t = bar.method_text({"access": ["source code", "git history"]}, {"status": {"semgrep": "ran", "trivy": "missing"}})
        self.assertIn("The running system was not used", t)
        self.assertIn("No production data was available", t)
        self.assertIn("semgrep", t)
        self.assertNotIn("trivy", t)
        t = bar.method_text({"access": ["source code", "test environment, one login per role", "anonymised database"]}, {})
        self.assertNotIn("not used", t)
        self.assertNotIn("No production data", t)


if __name__ == "__main__":
    unittest.main()
