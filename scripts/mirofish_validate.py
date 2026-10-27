#!/usr/bin/env python3
"""Run an idea-validation simulation on a MiroFish instance (the `validate` skill).

Usage:
  python3 mirofish_validate.py --check [--url URL]
  python3 mirofish_validate.py --seed docs/validation/seed.md \
      --requirement-file docs/validation/requirement.md \
      [--max-rounds 20] [--runs 1] [--interview-sample 10] [--resume]

MiroFish (github.com/666ghj/MiroFish, AGPL-3.0) is a swarm simulation engine:
it builds a knowledge graph from seed documents, generates agent personas,
runs a Twitter/Reddit-style social simulation and writes a prediction report.
ASDR never bundles or modifies it. This script only talks to an instance the
user runs themselves, over its HTTP API (default http://localhost:5001, or
$MIROFISH_URL).

Pipeline per run. Every id and step is saved to run-<n>.json as it happens,
so --resume continues a run that hit the time limit instead of paying again:
  1. POST /api/graph/ontology/generate   seed copy (hypotheses stripped) + requirement
  2. POST /api/graph/build               -> poll /api/graph/task/<id>
                                            (project status if the task is gone)
  3. POST /api/simulation/create
  4. POST /api/simulation/prepare        -> poll /api/simulation/prepare/status
  5. POST /api/simulation/start          (max_rounds capped: cost control)
     poll /api/simulation/<id>/run-status until every enabled platform has
     finished its rounds. MiroFish then keeps the environment alive, waiting
     for interview commands; the run is not "completed" yet.
  6. POST /api/simulation/interview/batch  fixed validation questions to an
     evenly spread sample of agents (a failed batch is recorded, not fatal)
  7. POST /api/simulation/close-env      -> poll until the run is terminal
     (POST /api/simulation/stop if it does not close in time). MiroFish only
     writes a report for a terminal run.
  8. POST /api/report/generate           -> poll /api/report/generate/status
     GET  /api/report/<id>

Outputs (in --out, default docs/validation/mirofish/):
  run-<n>.json          ids, timings, final run status, action counts
  report-<n>.md         MiroFish's report, verbatim
  interviews-<n>.json   the validation questions and every agent's answer
  uploaded-<seed>       exactly what was uploaded
and the measured summary under the "mirofish" key of --facts (default
.harness/validation.json, shared with the panel), written "incomplete" at
the start and "complete" at the end. The synthesis may cite numbers only
from that file (`validation:mirofish.<dotted.key>`).

Every request carries Accept-Language: en (--language) — the original
MiroFish answers in Chinese by default; the offline fork is English-only.

Exit codes: 0 done · 1 usage/input error · 2 MiroFish unreachable ·
3 a MiroFish step failed or answered unexpectedly · 4 time limit reached
(re-run the same command with --resume).

Zero dependencies (urllib only) so it runs anywhere the harness runs.
"""
import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validation_questions as vq  # noqa: E402

DEFAULT_URL = "http://localhost:5001"
LAUNCHER_HOME = Path(os.environ.get("ASDR_MIROFISH_HOME", Path.home() / ".asdr" / "mirofish"))

# What differs between the two upstreams the launcher can run, verified
# against their source at the commits pinned in upstream.json. The call
# sequence is the same for both; the differences are recorded in the facts
# and decide the language header.
CAPABILITIES = {
    "cloud": {   # 666ghj/MiroFish
        "graph_store": "zep-cloud", "llm": "any OpenAI-format API",
        "report_requires_terminal_run": True,      # /report/generate answers 409 before
        "language": "Accept-Language header (default zh); ASDR sends 'en'",
    },
    "offline": {  # nikmcfly/MiroFish-Offline
        "graph_store": "neo4j (local)", "llm": "ollama (local) or any OpenAI-format API",
        "report_requires_terminal_run": False,     # no 409; ASDR closes first anyway
        "language": "English only",
    },
}



ONTOLOGY_TIMEOUT = 900       # synchronous LLM call in MiroFish
DEFAULT_TIMEOUT = 60


class MiroFishError(Exception):
    def __init__(self, msg, code=3, status=None):
        super().__init__(msg)
        self.code = code
        self.status = status


class Client:
    def __init__(self, base, language="en"):
        self.base = base.rstrip("/")
        self.language = language

    def _send(self, req, timeout):
        if self.language:
            req.add_header("Accept-Language", self.language)
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(body).get("error") or body
            except ValueError:
                msg = body
            raise MiroFishError(f"{req.get_method()} {req.full_url} -> HTTP {e.code}: "
                                f"{str(msg)[:400]}", status=e.code)
        except (TimeoutError, error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(e, TimeoutError) or isinstance(reason, TimeoutError):
                raise MiroFishError(f"{req.get_method()} {req.full_url}: no answer within "
                                    f"{timeout}s (MiroFish is up but slow; re-run with "
                                    "--resume)", code=4)
            raise MiroFishError(f"cannot reach MiroFish at {self.base}: {reason}", code=2)
        try:
            data = json.loads(body)
        except ValueError:
            raise MiroFishError(f"{req.full_url} returned non-JSON: {body[:200]}")
        if isinstance(data, dict) and data.get("success") is False:
            raise MiroFishError(f"{req.full_url}: {str(data.get('error'))[:400]}")
        return data.get("data", data) if isinstance(data, dict) else data

    def get(self, path, timeout=DEFAULT_TIMEOUT):
        return self._send(request.Request(self.base + path, method="GET"), timeout)

    def post(self, path, payload, timeout=DEFAULT_TIMEOUT):
        req = request.Request(self.base + path, method="POST",
                              data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
        return self._send(req, timeout)

    def post_multipart(self, path, fields, files, timeout=DEFAULT_TIMEOUT):
        boundary = "----asdr" + uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"'
                          f"\r\n\r\n{v}\r\n").encode("utf-8"))
        for name, content in files:
            ctype = mimetypes.guess_type(name)[0] or "text/plain"
            parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
                          f'filename="{name}"\r\nContent-Type: {ctype}\r\n\r\n')
                         .encode("utf-8") + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        req = request.Request(self.base + path, method="POST", data=b"".join(parts),
                              headers={"Content-Type":
                                       f"multipart/form-data; boundary={boundary}"})
        return self._send(req, timeout)


def health(client):
    try:
        client.get("/health", timeout=5)
        return True
    except MiroFishError:
        return False



def prepare_uploads(seeds, out):
    """Seed files as uploaded, with hypothesis sections removed from text seeds."""
    files, removed = [], []
    for p in seeds:
        raw = p.read_bytes()
        if p.suffix.lower() in (".md", ".txt", ".markdown"):
            text, gone = vq.strip_sections(raw.decode("utf-8", "replace"))
            removed += [f"{p.name}: {h}" for h in gone]
            raw = text.encode("utf-8")
        (out / f"uploaded-{p.name}").write_bytes(raw)
        files.append((p.name, raw))
    return files, removed


def poll(fn, done, failed, deadline, interval, what):
    """Call fn() until done(result) or failed(result); raise on time limit."""
    while True:
        res = fn()
        if failed(res):
            raise MiroFishError(f"{what} failed: {json.dumps(res)[:400]}")
        if done(res):
            return res
        if time.time() > deadline:
            raise MiroFishError(f"{what} still running at the time limit; "
                                "re-run with --resume to continue", code=4)
        time.sleep(interval)


def sample_ids(n_agents, k):
    """k agent ids spread evenly over 0..n_agents-1 (deterministic)."""
    if n_agents <= 0 or k <= 0:
        return []
    k = min(k, n_agents)
    step = n_agents / k
    return sorted({int(i * step) for i in range(k)})


def _status(res, *keys):
    for k in keys:
        if isinstance(res, dict) and res.get(k):
            return str(res[k]).lower()
    return ""


def platforms(args):
    return ["twitter", "reddit"] if args.platform == "parallel" else [args.platform]


def rounds_finished(r, plats):
    """Every enabled platform has emitted simulation_end, or the run is terminal."""
    if _status(r, "runner_status") in ("completed", "stopped"):
        return True
    return all(r.get(f"{p}_completed") for p in plats)


def terminal(r):
    return _status(r, "runner_status") in ("completed", "stopped")


def graph_status(client, st):
    """Graph task status; MiroFish keeps tasks in memory, so after a restart
    fall back to the project's own status."""
    try:
        return client.get(f"/api/graph/task/{st['graph_task_id']}")
    except MiroFishError as e:
        if e.status != 404:
            raise
        proj = client.get(f"/api/graph/project/{st['project_id']}")
        s = _status(proj, "status")
        return {"status": "completed" if s == "graph_completed"
                else "failed" if s == "failed" else "processing"}


def run_once(client, n, args, uploads, requirement, questions, out, log):
    state_path = out / f"run-{n}.json"
    st = json.loads(state_path.read_text()) if (args.resume and state_path.exists()) else {}
    st.setdefault("run", n)
    st.setdefault("started_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    st["max_rounds"] = args.max_rounds
    st["platform"] = args.platform

    def save():
        state_path.write_text(json.dumps(st, indent=2, ensure_ascii=False))

    deadline = time.time() + args.timeout_minutes * 60
    iv = args.poll_seconds
    plats = platforms(args)

    if not st.get("project_id"):
        log(f"[run {n}] 1/8 ontology from {len(uploads)} seed file(s)")
        r = client.post_multipart("/api/graph/ontology/generate", {
            "simulation_requirement": requirement,
            "project_name": args.project_name,
            "additional_context": args.additional_context or "",
        }, uploads, timeout=ONTOLOGY_TIMEOUT)
        st["project_id"] = r["project_id"]
        st["ontology_entity_types"] = len((r.get("ontology") or {}).get("entity_types") or [])
        save()

    if not st.get("graph_done"):
        if not st.get("graph_task_id"):
            log(f"[run {n}] 2/8 building the knowledge graph")
            r = client.post("/api/graph/build", {"project_id": st["project_id"]})
            st["graph_task_id"] = r["task_id"]
            save()
        poll(lambda: graph_status(client, st),
             lambda r: _status(r, "status") == "completed",
             lambda r: _status(r, "status") == "failed",
             deadline, iv, "graph build")
        st["graph_done"] = True
        save()

    if not st.get("simulation_id"):
        log(f"[run {n}] 3/8 creating the simulation")
        r = client.post("/api/simulation/create", {
            "project_id": st["project_id"],
            "enable_twitter": "twitter" in plats,
            "enable_reddit": "reddit" in plats,
        })
        st["simulation_id"] = r["simulation_id"]
        save()
    sim = st["simulation_id"]

    if not st.get("prepared"):
        log(f"[run {n}] 4/8 generating personas and the simulation config")
        if not st.get("prepare_task_id"):
            r = client.post("/api/simulation/prepare", {"simulation_id": sim})
            st["prepare_task_id"] = r.get("task_id")
            save()
        poll(lambda: client.post("/api/simulation/prepare/status",
                                 {"task_id": st.get("prepare_task_id"), "simulation_id": sim}),
             lambda r: (r.get("already_prepared") is True
                        or _status(r, "status") in ("completed", "ready")),
             lambda r: _status(r, "status") == "failed",
             deadline, iv, "simulation prepare")
        st["prepared"] = True
        save()

    run_status = lambda: client.get(f"/api/simulation/{sim}/run-status")  # noqa: E731
    if not st.get("rounds_done"):
        if not st.get("run_started"):
            # A crash between /start and save() leaves a live run behind;
            # starting it again is a 400, so look first.
            now = run_status()
            if _status(now, "runner_status") in ("", "idle"):
                log(f"[run {n}] 5/8 running the simulation (max {args.max_rounds} rounds)")
                client.post("/api/simulation/start", {
                    "simulation_id": sim, "platform": args.platform,
                    "max_rounds": args.max_rounds, "enable_graph_memory_update": False})
            st["run_started"] = True
            save()
        final = poll(run_status,
                     lambda r: rounds_finished(r, plats),
                     lambda r: _status(r, "runner_status") == "failed",
                     deadline, iv, "simulation run")
        st["run_status"] = {k: final.get(k) for k in (
            "runner_status", "current_round", "total_rounds", "simulated_hours",
            "twitter_actions_count", "reddit_actions_count", "total_actions_count")}
        st["rounds_done"] = True
        save()

    if "interviews" not in st:
        log(f"[run {n}] 6/8 interviewing a sample of agents")
        alive = client.post("/api/simulation/env-status", {"simulation_id": sim})
        if not alive.get("env_alive"):
            st["interviews"] = {"skipped": "simulation environment no longer alive"}
        else:
            # One platform by default: in a parallel run each agent would
            # otherwise answer twice (twice the cost, the same persona).
            iplat = args.interview_platform
            if iplat == "auto":
                iplat = "reddit" if args.platform == "parallel" else args.platform
            prof = client.get(f"/api/simulation/{sim}/profiles?platform="
                              f"{'reddit' if iplat == 'both' else iplat}")
            profiles = prof.get("profiles") or []
            st["agents_total"] = len(profiles)
            ids = sample_ids(len(profiles), args.interview_sample)
            answers, failures = [], []
            for q_i, q in enumerate(questions):
                if not ids:
                    break
                try:
                    r = client.post("/api/simulation/interview/batch", {
                        "simulation_id": sim, "timeout": args.interview_timeout,
                        "interviews": [{"agent_id": a, "prompt": q} for a in ids],
                        **({} if iplat == "both" else {"platform": iplat})},
                        timeout=args.interview_timeout + 60)
                except MiroFishError as e:
                    if e.code == 2:
                        raise
                    failures.append({"question_index": q_i, "error": str(e)[:300]})
                    continue
                results = ((r.get("result") or {}).get("results")) or {}
                for key, v in results.items():
                    answers.append({"question_index": q_i, "key": key,
                                    "agent_id": v.get("agent_id"),
                                    "platform": v.get("platform"),
                                    "response": v.get("response")})

            def _uid(p):
                try:
                    return int(p.get("user_id"))
                except (TypeError, ValueError):
                    return None
            (out / f"interviews-{n}.json").write_text(json.dumps({
                "simulation_id": sim, "platform": iplat, "agent_ids": ids,
                "questions": questions,
                "personas": [p for p in profiles if _uid(p) in ids],
                "answers": answers, "failed_batches": failures},
                indent=2, ensure_ascii=False))
            st["interviews"] = {"agents": len(ids), "questions": len(questions),
                                "answers": len(answers), "failed_batches": len(failures)}
        save()

    if not st.get("terminal"):
        log(f"[run {n}] 7/8 closing the simulation environment")
        if not st.get("close_requested"):
            try:
                client.post("/api/simulation/close-env", {"simulation_id": sim})
            except MiroFishError as e:
                if e.code == 2:
                    raise
                st["close_env_error"] = str(e)[:300]
            st["close_requested"] = time.time()
            save()
        grace = min(deadline, st["close_requested"] + args.close_grace_seconds)
        try:
            poll(run_status, terminal, lambda r: False, grace, iv, "close-env")
        except MiroFishError as e:
            if e.code != 4 or time.time() > deadline:
                raise
            log(f"[run {n}] environment did not close in time; stopping it")
            client.post("/api/simulation/stop", {"simulation_id": sim})
            poll(run_status, terminal, lambda r: False, deadline, iv, "stop")
        st["terminal"] = True
        save()

    if not st.get("report_id"):
        log(f"[run {n}] 8/8 generating the MiroFish report")
        if not st.get("report_task_id"):
            r = client.post("/api/report/generate", {"simulation_id": sim})
            st["report_task_id"] = r.get("task_id")
            st["report_id_pending"] = r.get("report_id")
            if r.get("already_generated"):
                st["report_id"] = r.get("report_id")
            save()
        if not st.get("report_id"):
            r = poll(lambda: client.post("/api/report/generate/status",
                                         {"task_id": st.get("report_task_id"),
                                          "simulation_id": sim}),
                     lambda r: _status(r, "status") == "completed",
                     lambda r: _status(r, "status") == "failed",
                     deadline, iv, "report generation")
            st["report_id"] = (r.get("report_id") or st.get("report_id_pending")
                               or client.get(f"/api/report/by-simulation/{sim}")
                               .get("report_id"))
        save()
    rep = client.get(f"/api/report/{st['report_id']}")
    md = rep.get("markdown_content") or ""
    (out / f"report-{n}.md").write_text(md)
    st["report_chars"] = len(md)
    st["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    st["complete"] = True
    save()
    return st


def launcher_flavor(url):
    """The flavour the ASDR launcher started at this URL, if it did."""
    try:
        st = json.loads((LAUNCHER_HOME / "state.json").read_text())
    except (OSError, ValueError):
        return None
    return st.get("flavor") if vq.same_endpoint(st.get("url"), url) else None


def default_url():
    """$MIROFISH_URL, else the stack the ASDR launcher is running, else localhost."""
    if os.environ.get("MIROFISH_URL"):
        return os.environ["MIROFISH_URL"]
    try:
        st = json.loads((LAUNCHER_HOME / "state.json").read_text())
        if st.get("running") and st.get("url"):
            return st["url"]
    except (OSError, ValueError):
        pass
    return DEFAULT_URL


def write_facts(path, url, out, n_runs, status, stripped=None, error_msg=None):
    runs = []
    for n in range(1, n_runs + 1):
        f = out / f"run-{n}.json"
        if f.exists():
            runs.append(json.loads(f.read_text()))
    flavor = launcher_flavor(url)
    facts = {
        "source": "mirofish",
        "flavor": flavor or "unknown (not started by the ASDR launcher)",
        "capabilities": CAPABILITIES.get(flavor),
        "status": status,
        "evidence_class": "simulated",
        "note": ("Synthetic opinion from LLM personas seeded by our own documents. "
                 "It surfaces objections and arguments; it does not measure demand."),
        "mirofish_url": url,
        "runs_planned": n_runs,
        "runs_complete": sum(1 for r in runs if r.get("complete")),
        "seed_sections_not_uploaded": stripped or [],
        "output_dir": str(out),
        "per_run": [{
            "run": r["run"], "complete": bool(r.get("complete")),
            "simulation_id": r.get("simulation_id"),
            "rounds_completed": (r.get("run_status") or {}).get("current_round"),
            "rounds_cap": r.get("max_rounds"),
            "actions_total": (r.get("run_status") or {}).get("total_actions_count"),
            "agents_total": r.get("agents_total"),
            "interviews": r.get("interviews"),
            "report_file": f"report-{r['run']}.md" if r.get("complete") else None,
        } for r in runs],
    }
    if error_msg:
        facts["error"] = error_msg
    # .harness/validation.json holds every lane (mirofish, panel, …); replace
    # only this lane's key.
    p = Path(path)
    try:
        allf = json.loads(p.read_text())
        if not isinstance(allf, dict) or "per_run" in allf:   # pre-3.9 flat file
            allf = {}
    except (OSError, ValueError):
        allf = {}
    allf["mirofish"] = facts
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(allf, indent=2, ensure_ascii=False))
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=default_url())
    ap.add_argument("--check", action="store_true", help="health check only")
    ap.add_argument("--language", default="en",
                    help="Accept-Language sent to MiroFish (the original defaults to Chinese); "
                         "'' sends none")
    ap.add_argument("--seed", nargs="+", help="seed documents (.md/.txt/.pdf)")
    ap.add_argument("--requirement-file", help="the simulation requirement, plain text")
    ap.add_argument("--project-name", default="ASDR idea validation")
    ap.add_argument("--additional-context")
    ap.add_argument("--platform", choices=["parallel", "twitter", "reddit"], default="parallel")
    ap.add_argument("--max-rounds", type=int, default=20,
                    help="cap on simulation rounds (cost control; MiroFish advises <40 first)")
    ap.add_argument("--runs", type=int, default=1, help="independent runs, for variance")
    ap.add_argument("--interview-sample", type=int, default=10)
    ap.add_argument("--interview-platform", choices=["auto", "twitter", "reddit", "both"],
                    default="auto", help="auto = one platform (reddit in a parallel run)")
    ap.add_argument("--interview-timeout", type=int, default=180)
    ap.add_argument("--questions-file", help="one question per line; replaces the defaults")
    ap.add_argument("--keep-hypotheses", action="store_true",
                    help="upload seed sections about hypotheses too (not recommended)")
    ap.add_argument("--close-grace-seconds", type=float, default=180,
                    help="wait this long after close-env before stopping the run")
    ap.add_argument("--timeout-minutes", type=float, default=120, help="per invocation, per run")
    ap.add_argument("--poll-seconds", type=float, default=10)
    ap.add_argument("--out", default="docs/validation/mirofish")
    ap.add_argument("--facts", default=".harness/validation.json")
    ap.add_argument("--resume", action="store_true", help="continue runs from run-<n>.json")
    args = ap.parse_args()

    client = Client(args.url, args.language)
    if args.check:
        ok = health(client)
        print(f"{'OK' if ok else 'UNREACHABLE'}: MiroFish at {args.url}")
        return 0 if ok else 2

    if not args.seed or not args.requirement_file:
        print("ERROR: --seed and --requirement-file are required (or use --check)")
        return 1
    seeds = [Path(s) for s in args.seed]
    missing = [str(s) for s in seeds if not s.is_file()]
    if missing or not Path(args.requirement_file).is_file():
        print(f"ERROR: missing input file(s): {missing or [args.requirement_file]}")
        return 1
    requirement = Path(args.requirement_file).read_text().strip()
    if not requirement:
        print("ERROR: the simulation requirement is empty")
        return 1
    questions = vq.DEFAULT_QUESTIONS
    if args.questions_file:
        questions = [q.strip() for q in Path(args.questions_file).read_text().splitlines()
                     if q.strip()]
    if args.max_rounds < 1 or args.runs < 1:
        print("ERROR: --max-rounds and --runs must be >= 1")
        return 1

    if not health(client):
        print(f"UNREACHABLE: MiroFish at {args.url}. Start it (docs/COMPANIONS.md → "
              "MiroFish) or set MIROFISH_URL; the validate skill then falls back to "
              "desk validation.")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.keep_hypotheses:
        uploads = [(p.name, p.read_bytes()) for p in seeds]
        stripped = []
    else:
        uploads, stripped = prepare_uploads(seeds, out)
    # Overwrite any stale facts before spending anything.
    write_facts(args.facts, args.url, out, args.runs, "incomplete", stripped)

    def log(msg):
        print(msg, file=sys.stderr, flush=True)

    try:
        for n in range(1, args.runs + 1):
            run_once(client, n, args, uploads, requirement, questions, out, log)
    except MiroFishError as e:
        print(f"ERROR: {e}")
        write_facts(args.facts, args.url, out, args.runs, "incomplete", stripped, str(e))
        return e.code
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        msg = f"unexpected MiroFish response ({type(e).__name__}: {e}); check its version"
        print(f"ERROR: {msg}")
        write_facts(args.facts, args.url, out, args.runs, "incomplete", stripped, msg)
        return 3
    facts = write_facts(args.facts, args.url, out, args.runs, "complete", stripped)
    print(json.dumps(facts, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
