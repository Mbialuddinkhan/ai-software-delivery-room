#!/usr/bin/env python3
"""Install, start, check and stop a pinned MiroFish for the `validate` skill.

Usage:
  python3 mirofish_stack.py doctor  --flavor cloud|offline [--json]
  python3 mirofish_stack.py up      --flavor cloud|offline --yes [--port 5001] [--ui-port 3000]
                                    [--ollama host|container] [--model qwen2.5:14b] [--pull-models]
  python3 mirofish_stack.py status | logs [--tail 200] | down | purge --yes

Why a launcher and not a copy: MiroFish is a whole application (Python
backend, Vue frontend, Docker, a graph store) under AGPL-3.0. ASDR stays MIT
and contains none of its code. This script downloads the upstream source at
the commit pinned in scripts/upstream.json, into ~/.asdr/mirofish/ (outside
any project), builds it locally with Docker Compose and runs it. It never
patches MiroFish. If MiroFish needs a change to work, it stops and says so.

Flavours:
  cloud    666ghj/MiroFish — needs an OpenAI-format LLM key and a Zep Cloud
           key, read from the environment (MIROFISH_LLM_API_KEY,
           MIROFISH_LLM_BASE_URL, MIROFISH_LLM_MODEL, MIROFISH_ZEP_API_KEY).
           Seed text goes to that LLM provider and to Zep Cloud. Reports
           default to Chinese; mirofish_validate.py asks for English.
  offline  nikmcfly/MiroFish-Offline — Neo4j + Ollama, English, no cloud
           keys. Default --ollama host: the user's own Ollama, because Docker
           on macOS cannot use the Apple GPU. --ollama container runs the
           fork's Ollama container (Linux + NVIDIA makes sense; a Mac would
           run the model on CPU, very slowly).

Safety:
  - Keys only from environment variables; never asked for, never printed.
    The generated .env is mode 600. Command output is redacted.
  - Every published port is bound to 127.0.0.1 (MiroFish's API has no
    authentication) via a compose override (needs Compose >= 2.24.4 for
    `!override`).
  - `up` and `purge` refuse without --yes: the orchestrator asks the user
    first (downloads, disk, and for cloud, where the data goes).

State: ~/.asdr/mirofish/state.json (override the folder with
ASDR_MIROFISH_HOME). mirofish_validate.py and detect_companions.py read it.
Exit codes: 0 ok · 1 usage / consent missing · 2 a prerequisite missing ·
3 an upstream step failed.
"""
import argparse
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import request

HERE = Path(__file__).resolve().parent
HOME = Path(os.environ.get("ASDR_MIROFISH_HOME", Path.home() / ".asdr" / "mirofish"))
STATE = HOME / "state.json"
UPSTREAM_KEY = {"cloud": "mirofish", "offline": "mirofish-offline"}
CLOUD_ENV = ("MIROFISH_LLM_API_KEY", "MIROFISH_LLM_BASE_URL", "MIROFISH_LLM_MODEL",
             "MIROFISH_ZEP_API_KEY")
SECRET_ENV = ("MIROFISH_LLM_API_KEY", "MIROFISH_ZEP_API_KEY")
EMBED_MODEL = "nomic-embed-text"
MIN_COMPOSE = (2, 24, 4)
NEO4J_PORTS = (7474, 7687)


# ── small helpers ────────────────────────────────────────────────────────────

def pin(flavor):
    up = json.loads((HERE / "upstream.json").read_text())
    spec = up[UPSTREAM_KEY[flavor]]
    if not re.fullmatch(r"[0-9a-f]{40}", spec.get("commit", "")):
        raise SystemExit(f"ERROR: upstream.json → {UPSTREAM_KEY[flavor]} has no full commit pin")
    return spec


def redact(text):
    for k in SECRET_ENV:
        v = os.environ.get(k)
        if v and len(v) >= 4:
            text = text.replace(v, "***")
    for m in re.findall(r"NEO4J_PASSWORD=(\S+)", text):
        text = text.replace(m, "***")
    return text


def sh(cmd, check=False, capture=True, timeout=None):
    try:
        p = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{' '.join(cmd[:3])}: timed out"
    out, err = redact(p.stdout or ""), redact(p.stderr or "")
    if check and p.returncode != 0:
        raise StackError(f"`{' '.join(cmd[:4])} …` failed: {(err or out).strip()[:600]}")
    return p.returncode, out, err


class StackError(Exception):
    pass


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # A port in TIME_WAIT after a stop is free for a new listener; only a
    # live listener should count as busy.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def mem_gb():
    override = os.environ.get("ASDR_MIROFISH_RAM_GB")   # for tests / unusual hosts
    if override:
        return float(override)
    try:
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                      text=True).stdout.strip()) / 2 ** 30
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 2 ** 20
    except Exception:
        pass
    return None


def http_json(url, timeout=3):
    with request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def healthy(url):
    try:
        with request.urlopen(url.rstrip("/") + "/health", timeout=3) as r:
            return r.status == 200 and b"ok" in r.read(200).lower()
    except Exception:
        return False


def has_nvidia_runtime():
    code, out, _ = sh(["docker", "info", "--format", "{{json .Runtimes}}"], timeout=20)
    return code == 0 and "nvidia" in (out or "").lower()


def compose_version():
    code, out, _ = sh(["docker", "compose", "version", "--short"])
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
    return tuple(int(x) for x in m.groups()) if code == 0 and m else None


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def save_state(st):
    HOME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2))


# ── doctor ───────────────────────────────────────────────────────────────────

def doctor(a):
    checks = []

    def add(level, msg, fix=None):
        checks.append({"level": level, "check": msg, **({"fix": fix} if fix else {})})

    darwin = sys.platform == "darwin"
    add("INFO", f"host: {platform.system()} {platform.machine()}")
    if not shutil.which("docker"):
        add("FAIL", "docker not found", "install Docker Desktop (macOS/Windows) or Docker Engine")
    else:
        code, _, err = sh(["docker", "info"], timeout=20)
        if code != 0:
            add("FAIL", "Docker is installed but the daemon is not answering",
                ("start Docker Desktop, wait until it says running, and retry" if sys.platform == "darwin" or os.name == "nt" else "start the Docker daemon (e.g. `sudo systemctl start docker`) and retry"))
        else:
            add("PASS", "Docker daemon answering")
        cv = compose_version()
        if not cv:
            add("FAIL", "docker compose (v2) not available", "update Docker Desktop / install the compose plugin")
        elif cv < MIN_COMPOSE:
            add("FAIL", f"docker compose {'.'.join(map(str, cv))} is older than "
                f"{'.'.join(map(str, MIN_COMPOSE))} (needed for the 127.0.0.1 port override)",
                "update Docker Desktop")
        else:
            add("PASS", f"docker compose {'.'.join(map(str, cv))}")
    add("PASS" if shutil.which("git") else "FAIL", "git available",
        None if shutil.which("git") else "install git (xcode-select --install on macOS)")

    st = load_state()
    ours = set(st.get("ports", [])) if st and st.get("running") else set()
    ports = [a.port, a.ui_port]
    if a.flavor == "offline":
        ports += list(NEO4J_PORTS)
        if a.ollama == "container":
            ports.append(11434)
    for p in ports:
        if port_free(p) or p in ours:
            add("PASS", f"port {p} free" + (" (used by the ASDR stack)" if p in ours else ""))
        else:
            add("FAIL", f"port {p} is in use", "stop what uses it or choose another --port/--ui-port")

    HOME.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(HOME).free / 2 ** 30
    need, rec = (10, 20) if a.flavor == "cloud" else (20, 50)   # offline: the fork's README
    add("FAIL" if free < need else "WARN" if free < rec else "PASS",
        f"{free:.0f} GB free disk (need {need}, recommended {rec})",
        "free some disk space" if free < rec else None)
    ram = mem_gb()
    if ram is None:
        add("WARN", "could not read RAM size")
    elif a.flavor == "offline":
        add("FAIL" if ram < 16 else "WARN" if ram < 32 else "PASS",
            f"{ram:.0f} GB RAM (the offline fork states 16 GB minimum, 32 GB recommended)",
            "use a smaller model (qwen2.5:7b) or the cloud flavour" if ram < 32 else None)
    else:
        add("WARN" if ram < 8 else "PASS", f"{ram:.0f} GB RAM")

    if a.flavor == "cloud":
        missing = [k for k in CLOUD_ENV if not os.environ.get(k)]
        if missing:
            add("FAIL", f"environment variables not set: {', '.join(missing)}",
                "export them in the shell that runs ASDR (never paste keys into the chat)")
        else:
            add("PASS", "LLM and Zep settings present in the environment (values not shown)")
        add("INFO", "cloud flavour: the seed is sent to your LLM provider and to Zep Cloud")
    else:
        if a.ollama == "container":
            if darwin:
                add("WARN", "Ollama in a container on macOS runs on CPU (no Apple GPU in Docker)",
                    "prefer --ollama host with the Ollama app")
        else:
            try:
                tags = http_json(a.ollama_url.rstrip("/") + "/api/tags")
                names = {m.get("name", "") for m in tags.get("models", [])}
                add("PASS", f"Ollama answering at {a.ollama_url}")
                for mdl in (a.model, EMBED_MODEL):
                    have = any(n == mdl or n.startswith(mdl + ":") or n == mdl + ":latest"
                               for n in names)
                    add("PASS" if have else "WARN", f"model {mdl} " + ("present" if have else "not pulled"),
                        None if have else f"`ollama pull {mdl}` (check its size on "
                        "ollama.com/library first) or pass --pull-models after the user agrees")
            except Exception:
                add("FAIL", f"Ollama not answering at {a.ollama_url}",
                    "install and start Ollama (the app, or `ollama serve`)")
            if not darwin and os.name != "nt":
                add("WARN", "Linux: Ollama listens on 127.0.0.1 by default, which containers "
                    "cannot reach through host.docker.internal",
                    "make it also listen on the Docker bridge address, e.g. "
                    "`sudo systemctl edit ollama` → Environment=\"OLLAMA_HOST=172.17.0.1:11434\" "
                    "(the docker0 address — not 0.0.0.0, which exposes it to your network); "
                    "`up` checks this from inside the container")
    fails = [c for c in checks if c["level"] == "FAIL"]
    return checks, not fails


def print_checks(checks, as_json):
    if as_json:
        print(json.dumps(checks, indent=2))
        return
    for c in checks:
        print(f"{c['level']:<5} {c['check']}" + (f"  → {c['fix']}" if c.get("fix") else ""))


# ── generated files ──────────────────────────────────────────────────────────

def env_file(a, existing):
    if a.flavor == "cloud":
        return {
            "LLM_API_KEY": os.environ["MIROFISH_LLM_API_KEY"],
            "LLM_BASE_URL": os.environ["MIROFISH_LLM_BASE_URL"],
            "LLM_MODEL_NAME": os.environ["MIROFISH_LLM_MODEL"],
            "ZEP_API_KEY": os.environ["MIROFISH_ZEP_API_KEY"],
        }
    llm = ("http://ollama:11434" if a.ollama == "container"
           else "http://host.docker.internal:11434")
    # Neo4j fixes its password when its data volume is first created: reuse it.
    pw = existing.get("NEO4J_PASSWORD") or secrets.token_urlsafe(18)
    return {
        "LLM_API_KEY": "ollama", "LLM_BASE_URL": f"{llm}/v1", "LLM_MODEL_NAME": a.model,
        "NEO4J_URI": "bolt://neo4j:7687", "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": pw,
        "EMBEDDING_MODEL": EMBED_MODEL, "EMBEDDING_BASE_URL": llm,
        "OPENAI_API_KEY": "ollama", "OPENAI_API_BASE_URL": f"{llm}/v1",
    }


def read_env(path):
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_env(path, values):
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("# Written by ASDR mirofish_stack.py — values come from your environment.\n")
        for k, v in values.items():
            f.write(f"{k}={v}\n")
    os.chmod(path, 0o600)


def override_yaml(a, short, nvidia=False):
    lines = ["# Written by ASDR mirofish_stack.py. Binds every port to 127.0.0.1 and builds",
             "# the pinned source locally instead of pulling a moving :latest image.",
             "services:", "  mirofish:", "    build: .",
             f"    image: asdr-mirofish-{a.flavor}:{short}",
             "    ports: !override",
             f'      - "127.0.0.1:{a.ui_port}:3000"',
             f'      - "127.0.0.1:{a.port}:5001"']
    if a.flavor == "offline":
        lines += ["    extra_hosts:", '      - "host.docker.internal:host-gateway"']
        if a.ollama == "host":
            lines += ["    depends_on: !override", "      neo4j:",
                      "        condition: service_healthy"]
        lines += ["  neo4j:", "    ports: !override"]
        lines += [f'      - "127.0.0.1:{p}:{p}"' for p in NEO4J_PORTS]
        lines += ["  ollama:"]
        if a.ollama == "host":
            lines += ['    profiles: ["asdr-container-ollama"]']
        else:
            lines += ["    ports: !override", '      - "127.0.0.1:11434:11434"']
            if not nvidia:
                # The fork reserves an NVIDIA GPU; without that runtime the
                # container would not start.
                lines += ["    deploy: !reset {}"]
    return "\n".join(lines) + "\n"


def compose_cmd(st):
    d = Path(st["dir"])
    return ["docker", "compose", "-p", st["project"], "--project-directory", str(d),
            "-f", str(d / "docker-compose.yml"), "-f", str(d / "docker-compose.asdr.yml")]


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_up(a):
    spec = pin(a.flavor)
    commit, short = spec["commit"], spec["commit"][:7]
    if not a.yes:
        print(json.dumps({"consent_required": True, "flavor": a.flavor,
                          "will_download": [f"{spec['repo']} at {short} (source, into {HOME})",
                                            "Docker base images to build it locally"]
                          + (["neo4j image"] if a.flavor == "offline" else [])
                          + ([f"Ollama models {a.model}, {EMBED_MODEL} (--pull-models)"]
                             if a.pull_models else []),
                          "data_goes_to": ("your LLM provider and Zep Cloud" if a.flavor == "cloud"
                                           else "this machine only"),
                          "licence": spec.get("license", "AGPL-3.0"),
                          "next": "ask the user; re-run with --yes"}, indent=2))
        return 1
    checks, ok = doctor(a)
    if not ok:
        print_checks(checks, False)
        return 2
    d = HOME / f"{a.flavor}-{short}"
    st = {"flavor": a.flavor, "commit": commit, "dir": str(d),
          "project": f"asdr-mirofish-{a.flavor}",
          "url": f"http://127.0.0.1:{a.port}", "ui_url": f"http://127.0.0.1:{a.ui_port}",
          "ports": [a.port, a.ui_port] + (list(NEO4J_PORTS) if a.flavor == "offline" else []),
          "ollama": a.ollama if a.flavor == "offline" else None,
          "model": a.model if a.flavor == "offline" else os.environ.get("MIROFISH_LLM_MODEL"),
          "running": False, "installing": True}
    save_state(st)          # before anything can fail, so `purge` can always clean up
    try:
        if not (d / ".git").exists() and not (d / "docker-compose.yml").exists():
            HOME.mkdir(parents=True, exist_ok=True)
            print(f"downloading {spec['repo']} → {d}", file=sys.stderr)
            sh(["git", "clone", "--no-checkout", spec["repo"], str(d)], check=True, timeout=900)
            sh(["git", "-C", str(d), "checkout", "--detach", commit], check=True, timeout=300)
        _, head, _ = sh(["git", "-C", str(d), "rev-parse", "HEAD"])
        if head.strip() != commit:
            print(f"{d} is at {head.strip()[:12]}; moving it to the pinned {short}", file=sys.stderr)
            sh(["git", "-C", str(d), "fetch", "origin", commit], timeout=900)
            sh(["git", "-C", str(d), "checkout", "--detach", commit], check=True, timeout=300)
            _, head, _ = sh(["git", "-C", str(d), "rev-parse", "HEAD"])
            if head.strip() != commit:
                raise StackError(f"{d} could not be moved to the pinned {short} "
                                 f"(it is at {head.strip()[:12]}); `purge --yes`, then `up`")
        if a.flavor == "offline" and a.ollama == "host" and a.pull_models:
            for mdl in (a.model, EMBED_MODEL):
                print(f"ollama pull {mdl}", file=sys.stderr)
                sh(["ollama", "pull", mdl], check=True, capture=False)
        write_env(d / ".env", env_file(a, read_env(d / ".env")))
        nvidia = (a.flavor == "offline" and a.ollama == "container"
                  and sys.platform != "darwin" and has_nvidia_runtime())
        (d / "docker-compose.asdr.yml").write_text(override_yaml(a, short, nvidia))
        cc = compose_cmd(st)
        sh(cc + ["config", "-q"], check=True, timeout=120)
        print("building and starting (the first build takes several minutes)…", file=sys.stderr)
        sh(cc + ["up", "-d", "--build"], check=True, timeout=3600)
        st["running"] = True
        st["installing"] = False
        st["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        save_state(st)
        if a.flavor == "offline" and a.ollama == "container" and a.pull_models:
            for mdl in (a.model, EMBED_MODEL):
                print(f"ollama pull {mdl} (inside the container)", file=sys.stderr)
                sh(cc + ["exec", "-T", "ollama", "ollama", "pull", mdl], check=True,
                   capture=False, timeout=7200)
        if a.flavor == "offline" and a.ollama == "container":
            _, listed, _ = sh(cc + ["exec", "-T", "ollama", "ollama", "list"], timeout=60)
            have = {ln.split()[0] for ln in listed.splitlines()[1:] if ln.strip()}
            missing = [mdl for mdl in (a.model, EMBED_MODEL)
                       if not any(n == mdl or n == mdl + ":latest" or n.startswith(mdl + ":")
                                  for n in have)]
            if missing:
                raise StackError(f"the Ollama container has no {', '.join(missing)}; MiroFish "
                                 "would fail at its first model call. After the user agrees to "
                                 "the download, run `up --yes --pull-models` again.")
        deadline = time.time() + a.wait_seconds
        while time.time() < deadline and not healthy(st["url"]):
            time.sleep(3)
        if not healthy(st["url"]):
            raise StackError(f"started, but {st['url']}/health did not answer within "
                             f"{a.wait_seconds:.0f}s — see `mirofish_stack.py logs`")
        if a.flavor == "offline":
            # /health answers before any model call; check the backend can
            # actually reach Ollama from inside its container.
            target = ("http://ollama:11434" if a.ollama == "container"
                      else "http://host.docker.internal:11434") + "/api/tags"
            code, _, err = sh(cc + ["exec", "-T", "mirofish", "python3", "-c",
                                    "import sys,urllib.request;urllib.request.urlopen("
                                    "sys.argv[1],timeout=8)", target], timeout=60)
            if code != 0:
                raise StackError(
                    f"MiroFish is up but cannot reach Ollama at {target} from its container. "
                    + ("On Linux, Ollama must listen on the Docker bridge address — see "
                       "`doctor`. " if sys.platform != "darwin" else "Is the Ollama app running? ")
                    + "Then `down` and `up --yes` again.")
    except StackError as e:
        print(f"ERROR: {e}")
        return 3
    print(json.dumps({"up": True, "flavor": a.flavor, "commit": short, "url": st["url"],
                      "ui": st["ui_url"], "set": f"MIROFISH_URL={st['url']}"}, indent=2))
    return 0


def cmd_status(a):
    st = load_state()
    if not st:
        print(json.dumps({"installed": False}))
        return 0
    _, ps, _ = sh(compose_cmd(st) + ["ps", "--format", "json"], timeout=30) \
        if Path(st["dir"]).exists() else (1, "", "")
    print(json.dumps({**{k: st.get(k) for k in ("flavor", "commit", "url", "ui_url", "running")},
                      "healthy": healthy(st["url"]), "containers": ps.strip()[:2000]}, indent=2))
    return 0


def cmd_logs(a):
    st = load_state()
    if not st:
        print("nothing installed")
        return 0
    _, out, err = sh(compose_cmd(st) + ["logs", "--tail", str(a.tail)], timeout=60)
    print(out or err)
    return 0


def cmd_down(a):
    st = load_state()
    if not st or not st.get("running"):
        print("nothing running")
        return 0
    if Path(st["dir"]).exists():
        code, out, err = sh(compose_cmd(st) + ["down"], timeout=300)
        if code != 0:
            print(f"ERROR: compose down failed: {(err or out).strip()[:400]}")
            return 3
    st["running"] = False
    save_state(st)
    print("stopped (data kept; `purge --yes` removes it)")
    return 0


def cmd_purge(a):
    if not a.yes:
        print("purge deletes the downloaded source, its containers and volumes "
              "(including the Neo4j data). Ask the user, then re-run with --yes.")
        return 1
    removed = []
    dirs = sorted(x for x in HOME.glob("*-*") if x.is_dir()
                  and re.fullmatch(r"(cloud|offline)-[0-9a-f]{7}", x.name)) if HOME.exists() else []
    st = load_state()
    if st and Path(st["dir"]).exists() and Path(st["dir"]) not in dirs:
        dirs.append(Path(st["dir"]))
    for x in dirs:
        flavor = x.name.split("-")[0]
        project = f"asdr-mirofish-{flavor}"
        files = [f for f in ("docker-compose.yml", "docker-compose.asdr.yml") if (x / f).exists()]
        cmd = ["docker", "compose", "-p", project]
        if files:
            cmd += ["--project-directory", str(x)] + sum((["-f", str(x / f)] for f in files), [])
        sh(cmd + ["down", "-v", "--rmi", "local"], timeout=600)
        # --rmi local skips images with a custom tag, which ours have.
        flavor_, short_ = x.name.split("-", 1)
        sh(["docker", "image", "rm", "-f", f"asdr-mirofish-{flavor_}:{short_}"], timeout=120)
        shutil.rmtree(x, ignore_errors=True)
        removed.append(str(x))
    if STATE.exists():
        STATE.unlink()
    print(json.dumps({"purged": removed or "nothing installed"}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--flavor", choices=["cloud", "offline"], default="offline")
        p.add_argument("--port", type=int, default=5001)
        p.add_argument("--ui-port", type=int, default=3000)
        p.add_argument("--ollama", choices=["host", "container"], default="host")
        p.add_argument("--ollama-url", default=os.environ.get("ASDR_OLLAMA_URL",
                                                              "http://127.0.0.1:11434"))
        p.add_argument("--model", default="qwen2.5:14b")
    d = sub.add_parser("doctor")
    common(d)
    d.add_argument("--json", action="store_true")
    u = sub.add_parser("up")
    common(u)
    u.add_argument("--yes", action="store_true")
    u.add_argument("--pull-models", action="store_true")
    u.add_argument("--wait-seconds", type=float, default=600)
    sub.add_parser("status")
    lg = sub.add_parser("logs")
    lg.add_argument("--tail", type=int, default=200)
    sub.add_parser("down")
    pg = sub.add_parser("purge")
    pg.add_argument("--yes", action="store_true")
    a = ap.parse_args()

    if a.cmd == "doctor":
        checks, ok = doctor(a)
        print_checks(checks, a.json)
        return 0 if ok else 2
    return {"up": cmd_up, "status": cmd_status, "logs": cmd_logs,
            "down": cmd_down, "purge": cmd_purge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
