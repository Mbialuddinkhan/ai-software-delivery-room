#!/usr/bin/env python3
"""Tests for the v3.8 idea-validation pieces.

Deterministic and offline: mirofish_validate.py runs against an in-process
fake of the MiroFish HTTP API on 127.0.0.1; no LLM, no Zep, no network.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PY = sys.executable


class FakeMiroFish:
    """Just enough of MiroFish's API. Async tasks finish on the 2nd poll."""

    def __init__(self, fail=None, env_alive=True, agents=25, run_polls=2,
                 close_ignored=False, task_lost=False, interview_fails=False):
        self.fail = fail                 # "graph" | "run" | None
        self.env_alive = env_alive       # False: process exited after its rounds
        self.agents = agents
        self.run_polls = run_polls       # polls before every platform finishes its rounds
        self.close_ignored = close_ignored
        self.task_lost = task_lost       # MiroFish restarted: in-memory tasks gone
        self.interview_fails = interview_fails
        self.started = False
        self.closed = False
        self.stopped = False
        self.calls = []
        self.languages = []
        self.uploads = []
        self.polls = {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, data, code=200):
                body = json.dumps({"success": code == 200, "data": data}
                                  if code == 200 else {"success": False, "error": data}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def do_GET(self):
                fake.languages.append(self.headers.get("Accept-Language"))
                p = self.path.split("?")[0]
                fake.calls.append(("GET", p))
                if p == "/health":
                    body = b'{"status": "ok", "service": "MiroFish Backend"}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if p.startswith("/api/graph/task/"):
                    if fake.task_lost:
                        return self._json("task not found", 404)
                    n = fake._tick("graph")
                    st = "failed" if fake.fail == "graph" else (
                        "completed" if n >= 2 else "processing")
                    return self._json({"task_id": "t_g", "status": st, "progress": 50 * n})
                if p.startswith("/api/graph/project/"):
                    return self._json({"project_id": "proj_1", "status": "graph_completed"})
                if p.endswith("/run-status"):
                    if not fake.started:
                        return self._json({"runner_status": "idle"})
                    n = fake._tick("run")
                    done = n >= fake.run_polls
                    if fake.fail == "run":
                        st = "failed"
                    elif fake.stopped:
                        st = "stopped"
                    elif done and (fake.closed or not fake.env_alive):
                        st = "completed"
                    else:
                        st = "running"   # real MiroFish: alive, waiting for interviews
                    return self._json({"runner_status": st, "current_round": min(n, 20),
                                       "total_rounds": 20, "total_actions_count": 340,
                                       "twitter_completed": done, "reddit_completed": done,
                                       "twitter_actions_count": 200,
                                       "reddit_actions_count": 140})
                if p.endswith("/profiles"):
                    return self._json({"platform": "reddit", "count": fake.agents,
                                       "profiles": [{"user_id": i, "name": f"A{i}"}
                                                    for i in range(fake.agents)]})
                if p == "/api/report/rep_1":
                    return self._json({"report_id": "rep_1", "status": "completed",
                                       "markdown_content": "# Report\n\nObjection: price."})
                if p.startswith("/api/report/by-simulation/"):
                    return self._json({"report_id": "rep_1"})
                return self._json(f"unknown {p}", 404)

            def do_POST(self):
                fake.languages.append(self.headers.get("Accept-Language"))
                p = self.path
                raw = self._body()
                fake.calls.append(("POST", p))
                if p == "/api/graph/ontology/generate":
                    fake.uploads.append(raw.decode("utf-8", "replace"))
                    return self._json({"project_id": "proj_1",
                                       "ontology": {"entity_types": [1, 2, 3]}})
                data = json.loads(raw or b"{}")
                if p == "/api/graph/build":
                    return self._json({"project_id": data["project_id"], "task_id": "t_g"})
                if p == "/api/simulation/create":
                    return self._json({"simulation_id": "sim_1", "status": "created"})
                if p == "/api/simulation/prepare":
                    return self._json({"simulation_id": "sim_1", "task_id": "t_p",
                                       "status": "preparing"})
                if p == "/api/simulation/prepare/status":
                    n = fake._tick("prepare")
                    return self._json({"status": "completed" if n >= 2 else "processing"})
                if p == "/api/simulation/start":
                    if fake.started:
                        return self._json("already running", 400)
                    fake.started = True
                    fake.start_payload = data
                    return self._json({"runner_status": "running"})
                if p == "/api/simulation/env-status":
                    return self._json({"env_alive": fake.env_alive and not fake.closed})
                if p == "/api/simulation/interview/batch":
                    if fake.interview_fails:
                        return self._json("all interviews failed", 500)
                    fake.interview_payloads = getattr(fake, "interview_payloads", []) + [data]
                    res = {f"reddit_{i['agent_id']}": {"agent_id": i["agent_id"],
                                                       "platform": "reddit",
                                                       "response": "maybe, too pricey"}
                           for i in data["interviews"]}
                    return self._json({"result": {"results": res}})
                if p == "/api/report/generate":
                    if not (fake.closed or fake.stopped or not fake.env_alive):
                        return self._json("simulation still active", 409)
                    return self._json({"simulation_id": "sim_1", "task_id": "t_r",
                                       "report_id": "rep_1", "status": "generating",
                                       "already_generated": False})
                if p == "/api/report/generate/status":
                    n = fake._tick("report")
                    return self._json({"status": "completed" if n >= 2 else "processing",
                                       **({"report_id": "rep_1"} if n >= 2 else {})})
                if p == "/api/simulation/close-env":
                    if not fake.close_ignored:
                        fake.closed = True
                    return self._json({"closed": True})
                if p == "/api/simulation/stop":
                    fake.stopped = True
                    return self._json({"runner_status": "stopped"})
                return self._json(f"unknown {p}", 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _tick(self, key):
        self.polls[key] = self.polls.get(key, 0) + 1
        return self.polls[key]

    def count(self, method, path):
        return sum(1 for c in self.calls if c == (method, path))

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def run(args, cwd, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([PY, *map(str, args)], cwd=cwd, capture_output=True, text=True, env=e)
    return p.returncode, p.stdout, p.stderr


class ValidateBase(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "docs/validation").mkdir(parents=True)
        (self.d / "docs/validation/seed.md").write_text(
            "# Validation Seed\n\n## 3. Segments\nagency owners\n\n"
            "## 6. Hypotheses to test\n| H-01 | SECRET-CRITERION |\n")
        (self.d / "docs/validation/requirement.md").write_text(
            "Simulate agency owners reacting to a $29/month lead-response tool.")

    def tearDown(self):
        shutil.rmtree(self.d)

    def validate(self, url, *extra):
        return run([SCRIPTS / "mirofish_validate.py", "--url", url,
                    "--seed", "docs/validation/seed.md",
                    "--requirement-file", "docs/validation/requirement.md",
                    "--poll-seconds", "0.01", *extra], self.d)


class TestMiroFishValidate(ValidateBase):
    def test_full_run_writes_outputs_and_facts(self):
        fake = FakeMiroFish()
        try:
            code, out, err = self.validate(fake.url, "--interview-sample", "5",
                                           "--max-rounds", "12")
            self.assertEqual(code, 0, out + err)
            o = self.d / "docs/validation/mirofish"
            self.assertIn("Objection: price", (o / "report-1.md").read_text())
            iv = json.loads((o / "interviews-1.json").read_text())
            self.assertEqual(iv["agent_ids"], [0, 5, 10, 15, 20])
            self.assertEqual(len(iv["answers"]), 5 * len(iv["questions"]))
            facts = json.loads((self.d / ".harness/validation.json").read_text())["mirofish"]
            self.assertEqual(facts["evidence_class"], "simulated")
            self.assertEqual(facts["per_run"][0]["actions_total"], 340)
            self.assertEqual(facts["per_run"][0]["agents_total"], 25)
            self.assertEqual(fake.start_payload["max_rounds"], 12)
            self.assertIn('filename="seed.md"', fake.uploads[0])
            self.assertIn("$29/month", fake.uploads[0])
            self.assertEqual(fake.count("POST", "/api/simulation/close-env"), 1)
            self.assertEqual(facts["status"], "complete")
            self.assertTrue(all(h == "en" for h in fake.languages), fake.languages[:3])
            # hypotheses never reach MiroFish; what was sent is kept
            self.assertNotIn("SECRET-CRITERION", fake.uploads[0])
            self.assertIn("agency owners", fake.uploads[0])
            self.assertEqual(facts["seed_sections_not_uploaded"], ["seed.md: 6. Hypotheses to test"])
            self.assertTrue((o / "uploaded-seed.md").is_file())
            # one platform for interviews in a parallel run
            self.assertEqual(fake.interview_payloads[0]["platform"], "reddit")
            # close-env strictly before the report is requested
            order = [c[1] for c in fake.calls if c[0] == "POST"]
            self.assertLess(order.index("/api/simulation/close-env"),
                            order.index("/api/report/generate"))
        finally:
            fake.close()

    def test_environment_that_will_not_close_is_stopped(self):
        fake = FakeMiroFish(close_ignored=True)
        try:
            code, out, err = self.validate(fake.url, "--close-grace-seconds", "0.05")
            self.assertEqual(code, 0, out + err)
            self.assertEqual(fake.count("POST", "/api/simulation/stop"), 1)
            self.assertTrue((self.d / "docs/validation/mirofish/report-1.md").is_file())
        finally:
            fake.close()

    def test_restart_lost_task_falls_back_to_project_status(self):
        fake = FakeMiroFish(task_lost=True)
        try:
            code, out, err = self.validate(fake.url)
            self.assertEqual(code, 0, out + err)
            self.assertGreaterEqual(fake.count("GET", "/api/graph/project/proj_1"), 1)
        finally:
            fake.close()

    def test_failed_interviews_are_recorded_not_fatal(self):
        fake = FakeMiroFish(interview_fails=True)
        try:
            code, out, err = self.validate(fake.url)
            self.assertEqual(code, 0, out + err)
            facts = json.loads((self.d / ".harness/validation.json").read_text())["mirofish"]
            self.assertEqual(facts["per_run"][0]["interviews"]["failed_batches"], 5)
            self.assertEqual(facts["per_run"][0]["interviews"]["answers"], 0)
        finally:
            fake.close()

    def test_unreachable_exits_2(self):
        code, out, err = run([SCRIPTS / "mirofish_validate.py", "--check",
                              "--url", "http://127.0.0.1:9"], self.d)
        self.assertEqual(code, 2)
        code, out, err = self.validate("http://127.0.0.1:9")
        self.assertEqual(code, 2)
        self.assertIn("desk validation", out)

    def test_failed_step_exits_3(self):
        fake = FakeMiroFish(fail="graph")
        try:
            code, out, err = self.validate(fake.url)
            self.assertEqual(code, 3, out + err)
            self.assertIn("graph build failed", out)
            facts = json.loads((self.d / ".harness/validation.json").read_text())["mirofish"]
            self.assertEqual(facts["status"], "incomplete")
            self.assertEqual(facts["runs_complete"], 0)
        finally:
            fake.close()

    def test_timeout_then_resume_does_not_repay(self):
        fake = FakeMiroFish(run_polls=10_000)
        try:
            code, out, err = self.validate(fake.url, "--timeout-minutes", "0.002")
            self.assertEqual(code, 4, out + err)
            state = json.loads((self.d / "docs/validation/mirofish/run-1.json").read_text())
            self.assertTrue(state["run_started"])
            fake.run_polls = 0
            code, out, err = self.validate(fake.url, "--resume")
            self.assertEqual(code, 0, out + err)
            self.assertEqual(fake.count("POST", "/api/graph/ontology/generate"), 1)
            self.assertEqual(fake.count("POST", "/api/simulation/start"), 1)
        finally:
            fake.close()

    def test_dead_environment_skips_interviews(self):
        fake = FakeMiroFish(env_alive=False)
        try:
            code, out, err = self.validate(fake.url)
            self.assertEqual(code, 0, out + err)
            facts = json.loads((self.d / ".harness/validation.json").read_text())["mirofish"]
            self.assertIn("skipped", facts["per_run"][0]["interviews"])
            self.assertEqual(fake.count("POST", "/api/simulation/interview/batch"), 0)
        finally:
            fake.close()

    def test_missing_inputs_exit_1(self):
        code, out, err = run([SCRIPTS / "mirofish_validate.py", "--url", "http://x"], self.d)
        self.assertEqual(code, 1)

    def test_sample_ids_are_spread_and_bounded(self):
        spec = importlib.util.spec_from_file_location("mv", SCRIPTS / "mirofish_validate.py")
        mv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mv)
        self.assertEqual(mv.sample_ids(0, 10), [])
        self.assertEqual(mv.sample_ids(3, 10), [0, 1, 2])
        self.assertEqual(mv.sample_ids(100, 4), [0, 25, 50, 75])


class TestFactsMerge(ValidateBase):
    def test_mirofish_lane_keeps_panel_facts(self):
        (self.d / ".harness").mkdir()
        (self.d / ".harness/validation.json").write_text(json.dumps({"panel": {"status": "complete"}}))
        fake = FakeMiroFish()
        try:
            code, out, err = self.validate(fake.url)
            self.assertEqual(code, 0, out + err)
            allf = json.loads((self.d / ".harness/validation.json").read_text())
            self.assertEqual(allf["panel"], {"status": "complete"})
            self.assertEqual(allf["mirofish"]["status"], "complete")
            self.assertIn("unknown", allf["mirofish"]["flavor"])
        finally:
            fake.close()

    def test_flavor_from_launcher_state(self):
        home = self.d / "asdr-home"
        home.mkdir()
        fake = FakeMiroFish()
        try:
            (home / "state.json").write_text(json.dumps({"flavor": "offline", "url": fake.url}))
            code, out, err = run([SCRIPTS / "mirofish_validate.py", "--url", fake.url,
                                  "--seed", "docs/validation/seed.md",
                                  "--requirement-file", "docs/validation/requirement.md",
                                  "--poll-seconds", "0.01"], self.d,
                                 {"ASDR_MIROFISH_HOME": str(home)})
            self.assertEqual(code, 0, out + err)
            m = json.loads((self.d / ".harness/validation.json").read_text())["mirofish"]
            self.assertEqual(m["flavor"], "offline")
            self.assertFalse(m["capabilities"]["report_requires_terminal_run"])
        finally:
            fake.close()


class TestDetectMiroFish(unittest.TestCase):
    def test_detects_running_instance_and_honours_off(self):
        d = Path(tempfile.mkdtemp())
        fake = FakeMiroFish()
        try:
            run([SCRIPTS / "detect_companions.py"], d,
                {"HOME": str(d), "MIROFISH_URL": fake.url})
            data = json.loads((d / ".harness/companions.json").read_text())
            self.assertTrue(data["mirofish"]["installed"])
            run([SCRIPTS / "detect_companions.py"], d, {"HOME": str(d), "MIROFISH_URL": "off"})
            data = json.loads((d / ".harness/companions.json").read_text())
            self.assertFalse(data["mirofish"]["installed"])
            self.assertEqual(fake.count("GET", "/health"), 1)
            home = d / "asdr-home"
            home.mkdir()
            (home / "state.json").write_text(json.dumps(
                {"flavor": "offline", "commit": "313fe64", "url": fake.url, "running": True}))
            run([SCRIPTS / "detect_companions.py"], d,
                {"HOME": str(d), "MIROFISH_URL": fake.url, "ASDR_MIROFISH_HOME": str(home)})
            data = json.loads((d / ".harness/companions.json").read_text())
            self.assertEqual(data["mirofish"]["flavor"], "offline")
            self.assertEqual(data["mirofish"]["launcher"]["commit"], "313fe64")
        finally:
            fake.close()
            shutil.rmtree(d)


class TestValidationVerdict(unittest.TestCase):
    def check(self, block, *extra):
        d = Path(tempfile.mkdtemp())
        try:
            f = d / "v.md"
            f.write_text(f"# Idea Validation\n\n```yaml\n{block}\n```\n")
            return run([SCRIPTS / "validate_verdict.py", f, *extra], d)
        finally:
            shutil.rmtree(d)

    def test_template_placeholder_is_rejected(self):
        tpl = (REPO / "templates/idea-validation.md").read_text()
        block = tpl.rsplit("```yaml\n", 1)[1].split("```")[0]
        code, out, _ = self.check(block, "--type", "validation")
        self.assertEqual(code, 1)
        self.assertIn("recommendation", out)

    def test_filled_block_passes_and_type_is_inferred(self):
        block = ("recommendation: pivot\nevidence_class: panel+desk\n"
                 "hypotheses_supported: [H-02]\nhypotheses_refuted: [H-01]\n"
                 'top_objections: ["price", "setup time"]\nreal_world_tests: [RW-01]\n'
                 'reason: "Segment S-02 responds; S-01 does not."')
        code, out, _ = self.check(block)
        self.assertEqual(code, 0, out)
        self.assertIn("validation", out)


class TestEvidenceClass(unittest.TestCase):
    check = TestValidationVerdict.check

    def test_unknown_evidence_class_is_rejected(self):
        block = ("recommendation: proceed\nevidence_class: simulated+desk\n"
                 "hypotheses_supported: []\nhypotheses_refuted: []\n"
                 'top_objections: ["x"]\nreal_world_tests: [RW-01]\nreason: "r"')
        code, out, _ = self.check(block, "--type", "validation")
        self.assertEqual(code, 1)
        self.assertIn("evidence_class", out)


class TestWiring(unittest.TestCase):
    def test_skill_templates_and_hooks_exist(self):
        skill = (REPO / "skills/validate/SKILL.md").read_text()
        for t in ("validation-seed.md", "validation-desk-evidence.md", "idea-validation.md"):
            self.assertTrue((REPO / "templates" / t).is_file(), t)
            self.assertIn(t, skill)
        self.assertIn("mirofish_validate.py", skill)
        self.assertIn("Idea validation (optional)", (REPO / "skills/asdr/SKILL.md").read_text())
        self.assertIn("Idea validation (optional)", (REPO / "skills/discover/SKILL.md").read_text())
        self.assertIn("docs/00a-idea-validation.md",
                      (REPO / "skills/asdr/references/file-map.md").read_text())
        self.assertIn("MiroFish", (REPO / "THIRD_PARTY_NOTICES.md").read_text())


if __name__ == "__main__":
    unittest.main()
