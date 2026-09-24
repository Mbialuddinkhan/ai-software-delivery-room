#!/usr/bin/env python3
"""Tests for the v3.2 context-discipline scripts.

Run from the repo root:  python3 -m unittest discover tests -v

Every test builds a throwaway project (git repo, a few TS/Python files, tests,
a contract, sprint state) and runs the real scripts as subprocesses, so what is
tested is the shipped command-line behaviour, not an import of internals.
Zero dependencies beyond git and the standard library.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PY = sys.executable


def run(args, cwd):
    p = subprocess.run([PY, *args], cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip("\n"))


CONTRACT_HEAD = """
# CONTRACT · sprint-01 · booking

Negotiated by: generator + evaluator
Status: in-negotiation
Last edit: 2026-01-01T00:00:00Z

## Sprint goal

Callers can book a slot by phone

## Acceptance criteria

"""
CONTRACT_TAIL = """

## Test plan

- `npm test`

## Out of scope

- Payment capture

## Done definition

All acceptance criteria pass with recorded evidence.

## Revision notes
"""


def contract(criteria_md):
    return CONTRACT_HEAD + textwrap.dedent(criteria_md).strip("\n") + CONTRACT_TAIL


class Project:
    """A scratch project with a git history and the harness initialised."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="asdr-test-"))
        git(self.dir, "init", "-q", ".")
        git(self.dir, "config", "user.email", "t@t")
        git(self.dir, "config", "user.name", "t")
        code, out = run([SCRIPTS / "init_asdr.py", "--source", str(REPO)], self.dir)
        assert code == 0, out
        write(self.dir, "src/db/lead.ts", """
            // lead repository
            export function findLead(id: string) { return { id }; }
            """)
        write(self.dir, "src/voice/tools.ts", """
            import { findLead } from '../db/lead';
            // tools for the voice agent
            export function bookSlot(slotKey: string) {
              /* block comment */
              const lead = findLead('x');
              return { slotKey, lead };
            }
            """)
        write(self.dir, "src/voice/index.ts", """
            import { bookSlot } from './tools';
            export { bookSlot };
            """)
        write(self.dir, "tests/int/book.spec.ts", """
            import { bookSlot } from '../../src/voice/tools';
            const PhoneNumber = '+100';
            afterAll(() => { deleteMany(); });
            test('books', () => { expect(bookSlot('slotKey-1')).toBeTruthy(); expect(1).toBe(1); });
            """)
        write(self.dir, "tests/unit/lead.test.ts", """
            import { findLead } from '../../src/db/lead';
            test('finds', () => { expect(findLead('a').id).toBe('a'); });
            """)
        write(self.dir, "pkg/__init__.py", "")
        write(self.dir, "pkg/utils.py", "def helper():\n    return 1\n")
        write(self.dir, "pkg/sub/__init__.py", "")
        write(self.dir, "pkg/sub/main.py", """
            from ..utils import helper
            from pkg.utils import helper as h2
            import pkg.utils
            """)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-qm", "base")
        self.base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.dir,
                                   capture_output=True, text=True).stdout.strip()

    def script(self, name, *args):
        return run([self.dir / ".harness" / "scripts" / name, *args], self.dir)

    def read_json(self, rel):
        return json.loads((self.dir / rel).read_text())

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TestInit(unittest.TestCase):
    def test_init_seeds_packs_dir_and_base_ref(self):
        p = Project()
        try:
            self.assertTrue((p.dir / ".harness/packs").is_dir())
            prog = p.read_json(".harness/progress.json")
            self.assertIn("sprint_base_ref", prog)
            self.assertEqual(prog["rigor"], "standard")
            code, out = p.script("../scripts/init_asdr.py", "--source", str(REPO))
            self.assertEqual(code, 0, out)  # idempotent
        finally:
            p.cleanup()


class TestEmitFacts(unittest.TestCase):
    def test_diff_is_a_change_measure_and_sees_untracked_files(self):
        p = Project()
        try:
            with open(p.dir / "src/voice/tools.ts", "a") as f:
                f.write("export function cancelSlot(k: string) { return k; }\n"
                        "// trailing comment\n")
            write(p.dir, "src/voice/new.ts", "export const x = 1;\n// c\nexport const y = 2;\n")
            code, out = p.script("emit_facts.py", "--base", p.base, "--test-cmd",
                                 "echo 'Tests: 3 passed, 0 failed'")
            self.assertEqual(code, 0, out)
            facts = p.read_json(".harness/facts.json")
            d = facts["diff"]["src/voice/tools.ts"]
            self.assertEqual(d["added"], 2)
            self.assertEqual(d["added_nonblank"], 1)   # comment line excluded
            self.assertEqual(d["net_nonblank"], 1)     # the CHANGE, not the file
            self.assertEqual(d["file_nonblank"], 6)    # whole file, separately
            n = facts["diff"]["src/voice/new.ts"]
            self.assertTrue(n["untracked"])
            self.assertEqual(n["net_nonblank"], 2)
            self.assertEqual(facts["tests"]["passed"], 3)
            self.assertEqual(facts["tests"]["failed"], 0)
            self.assertEqual(facts["census"]["unit"], 1)
            self.assertEqual(facts["census"]["e2e"], 0)
            self.assertNotIn(".harness/facts.json", facts["diff"])
        finally:
            p.cleanup()

    def test_base_ref_from_progress_survives_generator_commit(self):
        p = Project()
        try:
            prog = p.read_json(".harness/progress.json")
            prog["sprint_base_ref"] = p.base
            (p.dir / ".harness/progress.json").write_text(json.dumps(prog))
            with open(p.dir / "src/voice/tools.ts", "a") as f:
                f.write("export const z = 1;\n")
            git(p.dir, "add", "-A")
            git(p.dir, "commit", "-qm", "generator commits its own work")
            code, out = p.script("emit_facts.py", "--no-tests")
            self.assertEqual(code, 0, out)
            facts = p.read_json(".harness/facts.json")
            self.assertEqual(facts["diff_base"], p.base)
            self.assertIn("src/voice/tools.ts", facts["diff"])
        finally:
            p.cleanup()

    def test_degrades_outside_git(self):
        d = tempfile.mkdtemp()
        try:
            code, out = run([SCRIPTS / "emit_facts.py", "--no-tests", "--out", "f.json"], d)
            self.assertEqual(code, 0, out)
            self.assertIn("not a git work tree", out)
        finally:
            shutil.rmtree(d)


class TestBuildGraph(unittest.TestCase):
    def test_resolves_parent_dir_same_dir_and_python_imports(self):
        p = Project()
        try:
            code, out = p.script("build_graph.py")
            self.assertEqual(code, 0, out)
            g = p.read_json(".harness/traceability.json")["graph"]
            self.assertIn("src/db/lead.ts", g["imports"]["src/voice/tools.ts"])       # ../
            self.assertIn("src/voice/tools.ts", g["imports"]["src/voice/index.ts"])   # ./
            self.assertIn("src/voice/tools.ts", g["imports"]["tests/int/book.spec.ts"])  # ../../
            self.assertIn("pkg/utils.py", g["imports"]["pkg/sub/main.py"])            # python
            blast = g["dependents"]["src/voice/tools.ts"]
            self.assertIn("src/voice/index.ts", blast)
            self.assertIn("tests/int/book.spec.ts", blast)
            self.assertEqual(sorted(g["fixture_risk"]["tests/int/book.spec.ts"]),
                             ["afterAll-cleanup", "contended-key", "fk-order", "global-unique"])
        finally:
            p.cleanup()

    def test_fact_citations_do_not_become_phantom_files(self):
        p = Project()
        try:
            write(p.dir, ".harness/contracts/contract-sprint-01.md", contract("""
                ### Happy path
                1. facts:diff.src/voice/tools.ts.net_nonblank <= 120
                2. src/voice/tools.ts exports bookSlot.
                """))
            code, out = p.script("build_graph.py")
            self.assertEqual(code, 0, out)
            f2c = p.read_json(".harness/traceability.json")["graph"]["file_to_criteria"]
            self.assertIn("src/voice/tools.ts", f2c)
            self.assertFalse([k for k in f2c if k.startswith("diff.")], f2c)
        finally:
            p.cleanup()


class TestContextPack(unittest.TestCase):
    def test_pack_scope_blast_radius_and_budget(self):
        p = Project()
        try:
            write(p.dir, "sprints.json", json.dumps(
                [{"id": "sprint-01", "goal": "Callers can book", "status": "active"}]))
            write(p.dir, ".harness/contracts/contract-sprint-01.md", contract("""
                ### Happy path
                1. facts:diff.src/voice/tools.ts.net_nonblank <= 120
                """))
            p.script("emit_facts.py", "--no-tests", "--base", p.base)
            p.script("build_graph.py")
            code, out = p.script("build_digest.py")
            self.assertEqual(code, 0, out)
            code, out = p.script("make_context_pack.py", "--sprint", "sprint-01",
                                 "--role", "generator")
            self.assertEqual(code, 0, out)
            pack = (p.dir / ".harness/packs/pack-sprint-01-generator.md").read_text()
            self.assertIn("- `src/voice/tools.ts`", pack)
            self.assertIn("tests/int/book.spec.ts", pack)   # blast radius via ../../
            self.assertIn("Project state digest", pack)
            code, out = p.script("make_context_pack.py", "--sprint", "sprint-01",
                                 "--role", "evaluator", "--budget", "200")
            self.assertEqual(code, 1)
            self.assertIn("over the 200 budget", out)
        finally:
            p.cleanup()


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        # A real change and a test run, so `facts:diff.src/voice/tools.ts.*`
        # and `facts:tests.*` exist to be cited.
        with open(self.p.dir / "src/voice/tools.ts", "a") as f:
            f.write("export const z = 1;\n")
        self.p.script("emit_facts.py", "--base", self.p.base,
                      "--test-cmd", "echo 'Tests: 3 passed, 0 failed'")

    def tearDown(self):
        self.p.cleanup()

    def lint(self, criteria_md):
        write(self.p.dir, ".harness/contracts/c.md", contract(criteria_md))
        return self.p.script("preflight_contract.py", ".harness/contracts/c.md")

    def assertBlocks(self, code_tag, criteria_md):
        code, out = self.lint(criteria_md)
        self.assertEqual(code, 1, out)
        self.assertIn(code_tag, out)

    def assertPasses(self, criteria_md):
        code, out = self.lint(criteria_md)
        self.assertEqual(code, 0, out)

    # true positives — every check must still fire
    def test_p01_unmeasurable(self):
        self.assertBlocks("P01", "### Happy path\n1. The endpoint returns at most 5 rows.")

    def test_p01_under_and_within_are_bounds(self):
        self.assertBlocks("P01", "### Happy path\n1. The first page returns in under 300ms.")
        self.assertBlocks("P01", "### Happy path\n1. The response arrives within 500ms.")

    def test_p01_unknown_fact_key(self):
        self.assertBlocks("P01", "### Happy path\n1. facts:diff.src/nope.ts.net_nonblank <= 5")

    def test_p02_beyond_eof(self):
        self.assertBlocks("P02", "### Happy path\n1. The guard at src/voice/tools.ts:400 rejects empty keys.")

    def test_p03_zero_delta(self):
        self.assertBlocks("P03", "### Happy path\n1. Add the retry helper to src/voice/tools.ts "
                                 "with zero added exports in src/voice/tools.ts.")

    def test_p04_self_report(self):
        self.assertBlocks("P04", "### Happy path\n1. The generator must report that git diff --stat shows 112 lines.")

    def test_p05_regex_conflict(self):
        self.assertBlocks("P05", "### Happy path\n1. The response payload must contain the value 404.\n"
                                 "2. The response body must not match /40\\d/.")

    def test_p06_cost_floor(self):
        self.assertBlocks("P06", "### Happy path\n1. Loading the page performs at least 3 database reads.")

    def test_p08_file_overload(self):
        rows = "\n".join(f"{i}. tests/int/book.spec.ts covers case {chr(96 + i)}" for i in range(1, 9))
        self.assertBlocks("P08", "### Happy path\n" + rows)

    def test_p09_new_file_budget(self):
        files = " ".join(f"src/a{i}.ts" for i in range(13))
        self.assertBlocks("P09", f"### Happy path\n1. Create {files}")

    # false positives — none of these may block a valid contract
    def test_word_boundaries_already_and_called(self):
        self.assertPasses("### Happy path\n1. At least 2 of the fields are already populated "
                          "when the form loads (facts:tests.exit_ok is true).\n"
                          "2. The webhook handler is called at least 1 time per event "
                          "(facts:tests.exit_ok is true).")

    def test_http_status_is_not_a_measurement(self):
        self.assertPasses("### Happy path\n1. An unknown id returns exactly HTTP 404.\n"
                          "2. Creating a lead returns status code 201.")

    def test_docs_json_and_urls_are_not_new_source_files(self):
        adrs = " ".join(f"docs/adr/00{i}.md" for i in range(1, 10))
        self.assertPasses(f"### Happy path\n1. README.md and CHANGELOG.md gain an entry; package.json "
                          f"gains a script; {adrs} record decisions; the client fetches "
                          f"https://api.example.com/v1/users.json.")

    def test_path_segment_is_not_a_regex(self):
        self.assertPasses("### Happy path\n1. The payload must contain the value 42.\n"
                          "2. Requests must not be routed through src/4/legacy.ts.")

    def test_clean_contract_passes_both_validators(self):
        md = contract("""
            ### Happy path
            1. Calling bookSlot in src/voice/tools.ts returns an object containing the slotKey.
            2. facts:diff.src/voice/tools.ts.net_nonblank <= 120
            3. tests/int/book.spec.ts passes (facts:tests.exit_ok is true).
            ### Failure & error handling
            1. Booking an unknown slot returns HTTP 404 with body {"error":"not found"}.
            2. POSTing malformed JSON returns HTTP 400 and writes no row to leads.
            3. A timeout from the carrier is logged with the slotKey and retried once.
            ### Security
            1. The booking endpoint rejects requests without a bearer token with HTTP 401.
            2. slotKey is validated against ^[a-z0-9-]+$ before any database access.
            3. No secret appears in any log line written by src/voice/tools.ts.
            ### Accessibility
            1. The confirmation SMS fits one segment (facts:tests.exit_ok is true).
            2. The voice prompt is spoken at the configured rate.
            3. The IVR menu can be navigated with keypad only.
            ### Data persistence
            1. A successful booking writes one row to bookings (facts:tests.exit_ok is true).
            2. A cancelled booking sets status to cancelled and keeps the row.
            3. Restarting the service preserves all bookings.
            ### Performance
            1. facts:tests.exit_ok is true.
            2. The full suite runs green (facts:tests.exit_ok is true).
            ### Edge cases
            1. Booking the same slotKey twice returns the original booking.
            2. A slotKey with surrounding whitespace is trimmed before lookup.
            3. Cancelling an already-cancelled booking is a no-op.
            """)
        write(self.p.dir, ".harness/contracts/contract-sprint-01.md", md)
        code, out = self.p.script("validate_contract.py", ".harness/contracts/contract-sprint-01.md")
        self.assertEqual(code, 0, out)
        code, out = self.p.script("preflight_contract.py", ".harness/contracts/contract-sprint-01.md")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
