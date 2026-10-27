#!/usr/bin/env python3
"""Tests for the v3.9 MiroFish launcher (scripts/mirofish_stack.py).

Never touches the network or a real Docker: `docker`, `git` and `sysctl` are
replaced by stub scripts on PATH that log their arguments; a stub
`docker compose up` starts a tiny local /health server so the launcher's
wait loop is exercised for real.
"""
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PY = sys.executable
PIN = json.loads((SCRIPTS / "upstream.json").read_text())

DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  info*) [ -n "$STUB_DOCKER_DOWN" ] && exit 1; exit 0 ;;
  "compose version --short") echo "${STUB_COMPOSE_VERSION:-2.29.1}"; exit 0 ;;
esac
case "$*" in
  *" config -q"*) exit 0 ;;
  *" up -d --build"*)
     mkdir -p "$STUB_DIR/www"; echo '{"status": "ok"}' > "$STUB_DIR/www/health"
     nohup "$STUB_PY" -m http.server "$STUB_HEALTH_PORT" --bind 127.0.0.1 --directory "$STUB_DIR/www" >/dev/null 2>&1 &
     echo $! > "$STUB_DIR/server.pid"; exit 0 ;;
  *" down"*) [ -f "$STUB_DIR/server.pid" ] && kill "$(cat "$STUB_DIR/server.pid")" 2>/dev/null; rm -f "$STUB_DIR/server.pid"; exit 0 ;;
  *" ps "*) echo '[]'; exit 0 ;;
  *" logs "*) echo "log line"; exit 0 ;;
esac
exit 0
"""

GIT = r"""#!/bin/sh
echo "git $*" >> "$STUB_LOG"
if [ "$1" = "clone" ]; then mkdir -p "$4"; echo "services: {}" > "$4/docker-compose.yml"; exit 0; fi
if [ "$1" = "-C" ] && [ "$3" = "checkout" ]; then echo "$5" > "$2/.head"; exit 0; fi
if [ "$1" = "-C" ] && [ "$3" = "rev-parse" ]; then cat "$2/.head"; exit 0; fi
exit 0
"""


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class FakeOllama:
    def __init__(self, models):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"models": [{"name": m} for m in models]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class StackBase(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.bin = self.d / "bin"
        self.bin.mkdir()
        for name, body in (("docker", DOCKER), ("git", GIT)):
            p = self.bin / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        self.home = self.d / "asdr-home"
        self.log = self.d / "stub.log"
        self.port, self.ui = free_port(), free_port()
        self.env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.d),
                    "ASDR_MIROFISH_HOME": str(self.home), "STUB_LOG": str(self.log),
                    "STUB_DIR": str(self.d), "STUB_PY": PY,
                    "STUB_HEALTH_PORT": str(self.port), "ASDR_MIROFISH_RAM_GB": "32"}

    def tearDown(self):
        pid = self.d / "server.pid"
        if pid.exists():
            try:
                os.kill(int(pid.read_text()), 15)
            except (OSError, ValueError):
                pass
        shutil.rmtree(self.d)

    def stack(self, *args, env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("MIROFISH_", "STUB_"))}
        e.update(self.env)
        e.update(env or {})
        p = subprocess.run([PY, SCRIPTS / "mirofish_stack.py", *map(str, args)], cwd=self.d,
                           capture_output=True, text=True, env=e, timeout=120)
        return p.returncode, p.stdout, p.stderr

    def ports(self):
        return ["--port", self.port, "--ui-port", self.ui]


class TestDoctor(StackBase):
    def test_docker_missing(self):
        (self.bin / "docker").unlink()
        code, out, _ = self.stack("doctor", "--flavor", "cloud", *self.ports(),
                                  env={"PATH": str(self.bin)})
        self.assertEqual(code, 2)
        self.assertIn("FAIL  docker not found", out)

    def test_daemon_down_and_old_compose(self):
        code, out, _ = self.stack("doctor", "--flavor", "cloud", *self.ports(),
                                  env={"STUB_DOCKER_DOWN": "1", "STUB_COMPOSE_VERSION": "2.20.0"})
        self.assertEqual(code, 2)
        self.assertIn("daemon is not answering", out)
        self.assertIn("older than 2.24.4", out)

    def test_busy_port_low_ram_missing_keys(self):
        s = socket.socket()
        s.bind(("127.0.0.1", self.port))
        s.listen()
        try:
            code, out, _ = self.stack("doctor", "--flavor", "cloud", *self.ports(),
                                      env={"ASDR_MIROFISH_RAM_GB": "4"})
        finally:
            s.close()
        self.assertEqual(code, 2)
        self.assertIn(f"port {self.port} is in use", out)
        self.assertIn("WARN  4 GB RAM", out)
        self.assertIn("MIROFISH_LLM_API_KEY", out)

    def test_offline_checks_ollama_and_models(self):
        oll = FakeOllama(["qwen2.5:14b"])
        try:
            code, out, _ = self.stack("doctor", "--flavor", "offline", *self.ports(),
                                      "--ollama-url", oll.url, "--json",
                                      env={"ASDR_MIROFISH_RAM_GB": "16"})
        finally:
            oll.close()
        checks = json.loads(out)
        text = json.dumps(checks)
        self.assertIn("model qwen2.5:14b present", text)
        self.assertIn("model nomic-embed-text not pulled", text)
        self.assertTrue(any(c["level"] == "WARN" and "16 GB RAM" in c["check"] for c in checks))
        code, out, _ = self.stack("doctor", "--flavor", "offline", *self.ports(),
                                  "--ollama-url", "http://127.0.0.1:9")
        self.assertEqual(code, 2)
        self.assertIn("Ollama not answering", out)


class TestUpDown(StackBase):
    KEYS = {"MIROFISH_LLM_API_KEY": "sk-SECRET-123456", "MIROFISH_LLM_BASE_URL": "https://llm.example/v1",
            "MIROFISH_LLM_MODEL": "some-model", "MIROFISH_ZEP_API_KEY": "zep-SECRET-abcdef"}

    def test_up_needs_consent(self):
        code, out, _ = self.stack("up", "--flavor", "cloud", *self.ports(), env=self.KEYS)
        self.assertEqual(code, 1)
        info = json.loads(out)
        self.assertTrue(info["consent_required"])
        self.assertIn("Zep Cloud", info["data_goes_to"])
        self.assertFalse(self.log.exists() and "clone" in self.log.read_text())

    def test_cloud_up_status_down_purge(self):
        code, out, err = self.stack("up", "--flavor", "cloud", "--yes", "--wait-seconds", "20",
                                    *self.ports(), env=self.KEYS)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("SECRET", out + err)
        sha = PIN["mirofish"]["commit"]
        d = self.home / f"cloud-{sha[:7]}"
        log = self.log.read_text()
        self.assertIn(f"checkout --detach {sha}", log)          # the pin, never latest
        self.assertIn("config -q", log)
        env = d / ".env"
        self.assertEqual(stat.S_IMODE(env.stat().st_mode), 0o600)
        self.assertIn("ZEP_API_KEY=zep-SECRET-abcdef", env.read_text())
        ov = (d / "docker-compose.asdr.yml").read_text()
        self.assertIn(f'"127.0.0.1:{self.port}:5001"', ov)
        self.assertIn(f'"127.0.0.1:{self.ui}:3000"', ov)
        self.assertIn("ports: !override", ov)
        self.assertIn("build: .", ov)
        st = json.loads((self.home / "state.json").read_text())
        self.assertEqual((st["flavor"], st["commit"], st["running"]), ("cloud", sha, True))
        code, out, _ = self.stack("status")
        self.assertTrue(json.loads(out)["healthy"])
        for _ in range(2):                                      # idempotent
            self.assertEqual(self.stack("down")[0], 0)
        self.assertFalse(json.loads((self.home / "state.json").read_text())["running"])
        self.assertEqual(self.stack("purge")[0], 1)             # needs --yes
        for _ in range(2):
            self.assertEqual(self.stack("purge", "--yes")[0], 0)
        self.assertFalse(d.exists())
        self.assertFalse((self.home / "state.json").exists())

    def test_container_ollama_without_models_is_not_reported_as_up(self):
        # /health answers before any model call; an empty Ollama container
        # used to pass as "up".
        try:
            code, out, err = self.stack("up", "--flavor", "offline", "--ollama", "container",
                                        "--yes", "--wait-seconds", "20", *self.ports())
            self.assertEqual(code, 3, out + err)
            self.assertIn("has no qwen2.5:14b, nomic-embed-text", out)
            self.assertIn("--pull-models", out)
            log = Path(self.env["STUB_LOG"]).read_text()
            self.assertIn("exec -T ollama ollama list", log)
        finally:
            self.stack("down")

    def test_offline_host_ollama_override_and_neo4j_password_reuse(self):
        oll = FakeOllama(["qwen2.5:14b", "nomic-embed-text:latest"])
        try:
            args = ["up", "--flavor", "offline", "--yes", "--wait-seconds", "20",
                    "--ollama-url", oll.url, *self.ports()]
            code, out, err = self.stack(*args)
            self.assertEqual(code, 0, out + err)
            d = self.home / f"offline-{PIN['mirofish-offline']['commit'][:7]}"
            env1 = (d / ".env").read_text()
            self.assertIn("LLM_BASE_URL=http://host.docker.internal:11434/v1", env1)
            self.assertIn("NEO4J_URI=bolt://neo4j:7687", env1)
            ov = (d / "docker-compose.asdr.yml").read_text()
            self.assertIn('profiles: ["asdr-container-ollama"]', ov)
            self.assertIn("depends_on: !override", ov)
            self.assertIn('"127.0.0.1:7687:7687"', ov)
            self.assertIn("host.docker.internal:host-gateway", ov)
            self.stack("down")
            time.sleep(0.5)
            code, out, err = self.stack(*args)                   # restart: same password
            self.assertEqual(code, 0, out + err)
            pw = lambda t: [l for l in t.splitlines() if l.startswith("NEO4J_PASSWORD=")][0]  # noqa: E731
            self.assertEqual(pw(env1), pw((d / ".env").read_text()))
            self.assertNotIn(pw(env1).split("=", 1)[1], out + err)
        finally:
            self.stack("down")
            oll.close()

    def test_wrong_checkout_is_moved_to_the_pin(self):
        # A folder at another commit used to be refused with advice (`purge`)
        # that could not fix it; now it is fetched and checked out at the pin.
        sha = PIN["mirofish"]["commit"]
        d = self.home / f"cloud-{sha[:7]}"
        d.mkdir(parents=True)
        (d / "docker-compose.yml").write_text("services: {}")
        (d / ".head").write_text("0" * 40)
        try:
            code, out, err = self.stack("up", "--flavor", "cloud", "--yes", *self.ports(),
                                        env=self.KEYS)
            self.assertEqual(code, 0, out + err)
            self.assertEqual((d / ".head").read_text().strip(), sha)
            log = Path(self.env["STUB_LOG"]).read_text()
            self.assertIn(f"fetch origin {sha}", log)
        finally:
            self.stack("down")

    def test_purge_cleans_up_a_failed_install_without_state(self):
        sha = PIN["mirofish-offline"]["commit"]
        d = self.home / f"offline-{sha[:7]}"
        d.mkdir(parents=True)
        (d / "docker-compose.yml").write_text("services: {}")
        code, out, _ = self.stack("purge", "--yes")
        self.assertEqual(code, 0, out)
        self.assertFalse(d.exists())
        log = Path(self.env["STUB_LOG"]).read_text()
        self.assertIn("-p asdr-mirofish-offline", log)
        self.assertIn("down -v --rmi local", log)
        self.assertIn(f"image rm -f asdr-mirofish-offline:{sha[:7]}", log)


class TestGeneratedOverride(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("ms", SCRIPTS / "mirofish_stack.py")
        self.ms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ms)

    def test_every_published_port_is_loopback(self):
        for flavor, oll in (("cloud", "host"), ("offline", "host"), ("offline", "container")):
            a = types.SimpleNamespace(flavor=flavor, port=5001, ui_port=3000, ollama=oll)
            y = self.ms.override_yaml(a, "abc1234")
            ports = [l.strip() for l in y.splitlines() if l.strip().startswith('- "') and ":" in l
                     and "host-gateway" not in l]
            self.assertTrue(ports)
            self.assertTrue(all(p.startswith('- "127.0.0.1:') for p in ports), (flavor, ports))

    def test_gpu_reservation_is_dropped_without_nvidia(self):
        a = types.SimpleNamespace(flavor="offline", port=5001, ui_port=3000, ollama="container")
        self.assertIn("deploy: !reset {}", self.ms.override_yaml(a, "abc1234", nvidia=False))
        self.assertNotIn("deploy: !reset", self.ms.override_yaml(a, "abc1234", nvidia=True))

    def test_pins_are_full_commits(self):
        for k in ("mirofish", "mirofish-offline"):
            self.assertRegex(PIN[k]["commit"], r"^[0-9a-f]{40}$")
            self.assertEqual(PIN[k]["kind"], "git-commit")


class TestUpdateCheckForPins(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("cu", SCRIPTS / "check_updates.py")
        self.cu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cu)

    def test_commit_pin_statuses(self):
        spec = PIN["mirofish"]
        self.assertEqual(self.cu.git_commit_status("mirofish", spec, None)[0], "skipped")
        fake = lambda url: json.dumps({"ahead_by": 2, "commits": [  # noqa: E731
            {"commit": {"message": "fix report\n\nbody"}}, {"commit": {"message": "add es locale"}}]})
        kind, entry = self.cu.git_commit_status("mirofish", spec, spec["commit"], fake)
        self.assertEqual(kind, "update")
        self.assertIn("2 commit(s) newer", entry["latest"])
        self.assertIn("- fix report", entry["benefits"])
        kind, _ = self.cu.git_commit_status("mirofish", spec, spec["commit"],
                                            lambda url: json.dumps({"ahead_by": 0}))
        self.assertEqual(kind, "up_to_date")

        def boom(url):
            raise OSError("offline")
        self.assertIn("unreachable", self.cu.git_commit_status("mirofish", spec, spec["commit"], boom)[1])


if __name__ == "__main__":
    unittest.main()
