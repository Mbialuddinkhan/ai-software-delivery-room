#!/usr/bin/env python3
"""Generate a scoped context pack for one agent task.

Usage:
  python3 make_context_pack.py --sprint sprint-07 --role generator
        [--budget 12000] [--out .harness/packs/pack-sprint-07-generator.md]
        [--stop "hand off after the contract is written"]

Why
---
The dominant context cost is re-derivation: every agent re-reads the contract,
the prior eval reports and large parts of the repository before writing
anything, and wide briefs exhaust budgets mid-task while narrow ones finish.

This assembles ONE small brief from the graph and the measured facts — file
paths and fact keys, never file contents — so the agent starts with the answer
to "what is relevant?" instead of paying to rediscover it.

The budget is the point
-----------------------
If the pack exceeds --budget, this EXITS 1 and tells you to split the task.
That converts context overflow from a silent, expensive mid-task failure into a
cheap planning-time signal. Budget is measured in characters and reported as an
approximate token count (~4 chars/token); it bounds the brief, not the agent's
own reasoning.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CHARS_PER_TOKEN = 4


def load(p, default=None):
    q = Path(p)
    if not q.exists():
        return default
    try:
        return json.loads(q.read_text())
    except ValueError:
        return default


def contract_files(contract_path):
    """Files named by the contract.

    `facts:<dotted.key>` citations are stripped first: a key such as
    `facts:diff.src/pay.ts.net_nonblank` otherwise looks like a file path and
    would be listed as a file in scope (and would break the facts slice).
    """
    if not Path(contract_path).exists():
        return [], 0
    body = re.sub(r"<!--.*?-->", "", Path(contract_path).read_text(), flags=re.DOTALL)
    n = len(re.findall(r"^\s*\d+\.\s+\S", body, re.M))

    # A criterion may name a file ONLY through a fact citation, e.g.
    # `facts:diff.src/pay.ts.net_nonblank`. Those files are in scope too — the
    # citations are the most precise statement of what the sprint touches.
    from_facts = set()
    for key in re.findall(r"facts:([A-Za-z0-9_./\[\]-]+)", body):
        m = re.match(r"diff\.(.+?)\.(?:added|removed|net_nonblank)$", key)
        if m:
            from_facts.add(m.group(1))

    body = re.sub(r"facts:[A-Za-z0-9_./\[\]-]+", " ", body)
    files = set(re.findall(
        r"([\w./-]+\.(?:ts|tsx|js|jsx|py|go|rb|java|rs|sql))", body))
    return sorted(files | from_facts), n


def last_verdict(evaldir, sprint):
    d = Path(evaldir)
    if not d.is_dir():
        return None
    reports = sorted(d.glob(f"eval-report-{sprint}-attempt-*.md"))
    if not reports:
        return None
    text = reports[-1].read_text(errors="ignore")
    blocks = re.findall(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    return {"report": str(reports[-1]),
            "verdict_block": blocks[-1].strip() if blocks else "(no verdict block)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sprint", required=True)
    ap.add_argument("--role", required=True,
                    help="generator | evaluator | stage-qa | product-integrity-qa | …")
    ap.add_argument("--budget", type=int, default=12000, help="max characters")
    ap.add_argument("--matrix", default=".harness/traceability.json")
    ap.add_argument("--facts", default=".harness/facts.json")
    ap.add_argument("--contracts", default=".harness/contracts")
    ap.add_argument("--evals", default=".harness/eval-reports")
    ap.add_argument("--digest", default=".harness/state-digest.md")
    ap.add_argument("--stop", default=None, help="explicit stopping point")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    matrix = load(args.matrix, {}) or {}
    facts = load(args.facts, None)
    graph = matrix.get("graph", {})
    contract = f"{args.contracts}/contract-{args.sprint}.md"

    # Scope is whatever the contract names. The graph enriches that scope
    # (blast radius, requirements, fixture risk); it must never gatekeep it, or
    # a newly-created file the graph hasn't seen would silently drop out.
    in_scope, n_criteria = contract_files(contract)

    # Blast radius: everything that imports an in-scope file.
    dependents = graph.get("dependents", {})
    blast = sorted({d for f in in_scope for d in dependents.get(f, [])} - set(in_scope))

    reqs = sorted({r for f in in_scope
                   for r in graph.get("file_to_requirements", {}).get(f, [])})
    risk = {f: graph["fixture_risk"][f] for f in graph.get("fixture_risk", {})
            if f in in_scope or f in blast}

    fact_slice = {}
    if facts:
        fact_slice["commit"] = facts.get("commit")
        fact_slice["census"] = facts.get("census")
        if facts.get("diff"):
            fact_slice["diff"] = {f: v for f, v in facts["diff"].items() if f in in_scope}
        if facts.get("tests"):
            fact_slice["tests"] = {k: facts["tests"].get(k)
                                   for k in ("exit_ok", "passed", "failed")}

    verdict = last_verdict(args.evals, args.sprint)
    digest = Path(args.digest).read_text() if Path(args.digest).exists() else None

    L = []
    L.append(f"# Context pack · {args.sprint} · {args.role}")
    L.append("")
    L.append("Everything you need is below or named below. Read the named files only "
             "if a task step requires their contents — do not scan the repository, "
             "and do not derive any number that already appears here.")
    L.append("")
    L.append("## Your task")
    L.append(f"- Role: **{args.role}**  ·  Sprint: **{args.sprint}**")
    L.append(f"- Contract: `{contract}` ({n_criteria} criteria)")
    if args.stop:
        L.append(f"- **Stop when:** {args.stop}")
    L.append("")
    if digest:
        L.append("## Project state (authoritative digest)")
        L.append(digest.strip())
        L.append("")
    L.append("## Files in scope")
    if in_scope:
        L.extend(f"- `{f}`" for f in in_scope)
    else:
        L.append("- (none named by the contract)")
    if blast:
        L.append("")
        L.append("## Blast radius — these import a file in scope")
        L.extend(f"- `{f}`" for f in blast[:25])
        if len(blast) > 25:
            L.append(f"- …and {len(blast) - 25} more")
    if reqs:
        L.append("")
        L.append("## Requirements these files serve")
        L.append(", ".join(reqs))
    if risk:
        L.append("")
        L.append("## Fixture-isolation risk (clean in `beforeAll`, never `afterAll`)")
        for f, tags in sorted(risk.items()):
            L.append(f"- `{f}` — {', '.join(tags)}")
    if fact_slice:
        L.append("")
        L.append("## Measured facts (cite these; never re-derive)")
        L.append("```json")
        L.append(json.dumps(fact_slice, indent=2, sort_keys=True))
        L.append("```")
        L.append("Cite as `facts:<dotted.key>`. A number not in facts.json is not "
                 "measured and may not be asserted.")
    else:
        L.append("")
        L.append("## Measured facts")
        L.append("**None available.** `facts.json` is missing — run "
                 "`emit_facts.py` first. Do not assert numeric claims until it exists.")
    if verdict:
        L.append("")
        L.append(f"## Last verdict for this sprint (`{verdict['report']}`)")
        L.append("```yaml")
        L.append(verdict["verdict_block"])
        L.append("```")
        L.append("Fix only what failed. Rewriting passing work risks breaking it "
                 "and burns an attempt.")

    text = "\n".join(L) + "\n"
    size = len(text)
    approx_tokens = size // CHARS_PER_TOKEN

    out = Path(args.out or f".harness/packs/pack-{args.sprint}-{args.role}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)

    print(f"OK: wrote {out}")
    print(f"  files_in_scope={len(in_scope)} blast_radius={len(blast)} "
          f"requirements={len(reqs)} risk_files={len(risk)}")
    print(f"  size={size} chars (~{approx_tokens} tokens), budget={args.budget}")

    if size > args.budget:
        print()
        print(f"ERROR: pack is {size} chars, over the {args.budget} budget.")
        print("The TASK is too big, not the budget. Split it before dispatching:")
        print("  - fewer files per task (split the contract by category or module)")
        print("  - one stopping point per agent, not a whole sprint")
        print("Failing now is far cheaper than an agent exhausting context mid-task "
              "and returning uncommitted partial work.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
