#!/usr/bin/env python3
"""Cross-family second opinion on an artifact, via the Codex or Gemini CLI.

Usage:
  python3 second_opinion.py --artifact <file> [--artifact <file> …]
         [--stage <id>] [--role evaluator] [--provider auto|gemini|codex]
         [--checklist <file>] [--out .harness/second-opinions/so-<stage>.md]
         [--max-chars 24000] [--timeout 180]

v4.3 (brief 3.2, scoped honestly). "No agent signs off its own work" is
strongest when the checker does not share the author's blind spots — a
different model FAMILY, not just a different role. Inside Claude Code a
subagent cannot BE another family, so this script shells out to a locally
installed Gemini CLI or Codex CLI (the 4.1 exports mean many users have one)
and captures its review as ADVISORY EVIDENCE.

Role boundaries are unchanged — by design, recorded here and in
docs/VERIFICATION-MODEL.md: the evaluator remains the only role that can
pass a sprint, the judge the only one that resolves phases. The second
opinion is one more exhibit the deciding reviewer must address (agree or
rebut, in writing), never a vote it must obey. A second family that is wrong
stays wrong in the file, visibly.

Default provider order: gemini, then codex (decision 10.2: the Gemini export
verified all 19 roles load). When NEITHER is installed, this prints the
`SINGLE_PROVIDER` warning, appends it to `.harness/run-warnings.jsonl`, and
exits 0 — the run proceeds, honestly labelled as reviewed within one family.
Failures (timeout, non-zero exit) degrade the same way. Exit is 0 in every
outcome except bad arguments; this script never gates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

WARNINGS = Path(".harness/run-warnings.jsonl")

PROMPT = """You are an independent reviewer from a different model family, \
giving a second opinion on work produced by another AI system. Review ONLY \
what is below. Be specific and adversarial: name defects, contradictions, \
security risks and unsupported claims, each with the line or quote that \
shows it. Do not restate the content. Do not soften findings.
{checklist}
End with exactly one line:
SECOND-OPINION: concerns
or
SECOND-OPINION: no-concerns

=== ARTIFACT(S) UNDER REVIEW ===
{body}
"""


def detect(provider: str):
    order = {"auto": ["gemini", "codex"], "gemini": ["gemini"],
             "codex": ["codex"]}[provider]
    for name in order:
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def invoke(name: str, prompt: str, timeout: int):
    argv = {"gemini": ["gemini", "-p", prompt],
            "codex": ["codex", "exec", prompt]}[name]
    t0 = dt.datetime.now()
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    secs = (dt.datetime.now() - t0).total_seconds()
    return r.returncode, (r.stdout or "") + ("\n" + r.stderr if r.stderr else ""), secs


def warn(stage: str, message: str):
    print(message)
    try:
        WARNINGS.parent.mkdir(parents=True, exist_ok=True)
        with WARNINGS.open("a") as f:
            f.write(json.dumps({
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "stage": stage, "warning": message.split(":")[0],
                "message": message}) + "\n")
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", action="append", required=True)
    ap.add_argument("--stage", default="stage")
    ap.add_argument("--role", default="evaluator",
                    help="the deciding reviewer this opinion is addressed to")
    ap.add_argument("--provider", choices=["auto", "gemini", "codex"], default="auto")
    ap.add_argument("--checklist", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-chars", type=int, default=24000)
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    out = Path(args.out or f".harness/second-opinions/so-{args.stage}.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    parts, missing = [], []
    for a in args.artifact:
        p = Path(a)
        if p.exists():
            parts.append(f"--- {p} ---\n{p.read_text(errors='ignore')}")
        else:
            missing.append(str(p))
    if not parts:
        print(f"ERROR: none of the artifacts exist: {', '.join(missing)}")
        return 1
    body = "\n\n".join(parts)
    truncated = len(body) > args.max_chars
    if truncated:
        body = body[:args.max_chars] + "\n[... truncated for the second opinion ...]"

    checklist = ""
    if args.checklist and Path(args.checklist).exists():
        checklist = ("\nCheck specifically against this checklist:\n"
                     + Path(args.checklist).read_text(errors="ignore")[:4000])

    name, path = detect(args.provider)
    header = [f"# Second opinion · {args.stage}",
              f"_Requested {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} "
              f"for the {args.role}. ADVISORY EVIDENCE from a different model "
              "family — the deciding reviewer must address it (agree or rebut) "
              "but is never bound by it. Role boundaries unchanged._", ""]

    if not name:
        msg = ("SINGLE_PROVIDER: no second model family available (neither the "
               "gemini nor the codex CLI is installed) — this run's reviews stay "
               "within one model family. Install either CLI (see "
               "scripts/export_targets.py) to add cross-family review on "
               "high-radius stages.")
        warn(args.stage, msg)
        out.write_text("\n".join(header + ["## Unavailable", "", msg, ""]))
        print(f"-> {out}")
        return 0

    prompt = PROMPT.format(checklist=checklist, body=body)
    try:
        code, text, secs = invoke(name, prompt, args.timeout)
    except subprocess.TimeoutExpired:
        msg = (f"SECOND_OPINION_UNAVAILABLE: {name} timed out after "
               f"{args.timeout}s — proceeding single-family for this stage.")
        warn(args.stage, msg)
        out.write_text("\n".join(header + ["## Unavailable", "", msg, ""]))
        return 0
    except OSError as ex:
        msg = f"SECOND_OPINION_UNAVAILABLE: {name} failed to start ({ex})."
        warn(args.stage, msg)
        out.write_text("\n".join(header + ["## Unavailable", "", msg, ""]))
        return 0

    if code != 0:
        msg = (f"SECOND_OPINION_UNAVAILABLE: {name} exited {code} — "
               "proceeding single-family for this stage.")
        warn(args.stage, msg)
        out.write_text("\n".join(header + ["## Unavailable", "", msg,
                                           "", "```", text[-2000:], "```", ""]))
        return 0

    verdict = "unstated"
    for line in reversed(text.strip().splitlines()):
        if line.strip().startswith("SECOND-OPINION:"):
            verdict = line.split(":", 1)[1].strip()
            break
    out.write_text("\n".join(header + [
        f"- Provider: **{name}** (`{path}`), {secs:.0f}s",
        f"- Verdict line: **{verdict}**",
        f"- Input: {len(args.artifact)} artifact(s)"
        + (", truncated" if truncated else "")
        + (f"; missing: {', '.join(missing)}" if missing else ""),
        "", "## Opinion", "", text.strip(), ""]))
    print(f"OK: second opinion from {name} — {verdict} ({secs:.0f}s) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
