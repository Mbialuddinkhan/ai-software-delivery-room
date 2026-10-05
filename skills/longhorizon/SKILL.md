---
name: longhorizon
description: >
  Use this skill when the user wants to run only the long-horizon Planner → Generator → Evaluator
  coding harness without the full strategic discovery phase. Best for when architecture docs already
  exist or the user wants to jump straight to building. Trigger phrases: "long horizon", "start coding",
  "run the harness", "planner generator evaluator", "build with sprints", "just start building".
metadata:
  version: "3.3.2"
---

# Long Horizon — Execution Harness Orchestrator

Ask the user for a one-line build prompt if not provided.

You are the orchestrator. The state machine lives in scripts, not in your
memory: when unsure what to do next, run
`python3 .harness/scripts/next_action.py` and do exactly what it says.

## Context discipline (v3.2)

Before dispatching ANY agent in the sprint loop, run these in order:

    python3 .harness/scripts/emit_facts.py        # -> .harness/facts.json (diffs against
                                                  #    progress.json -> sprint_base_ref)
    python3 .harness/scripts/build_graph.py       # -> graph in .harness/traceability.json
    python3 .harness/scripts/build_digest.py      # -> .harness/state-digest.md
    python3 .harness/scripts/make_context_pack.py --sprint <id> --role <role>

Then pass the pack path (`.harness/packs/pack-<id>-<role>.md`) in the
invocation. If `make_context_pack.py` exits 1, the pack exceeded its budget:
the TASK is too big. Split the sprint or the contract and rebuild the pack.
Never raise the budget — the budget is the measurement, not the obstacle.

When you activate a sprint, record its starting commit in
`.harness/progress.json` as `"sprint_base_ref"` (`git rev-parse HEAD`).
`emit_facts.py` diffs against that ref, so the measured diff survives the
generator committing its own work; a diff against HEAD after that commit is
empty. Diff budgets cite `facts:diff.<file>.net_nonblank` (non-blank,
non-comment lines added minus removed) — `file_nonblank` is the whole file.

`facts.json` is the only source of measured numbers: **a number not in
facts.json is not measured and may not be asserted; cite it as
`facts:<dotted.key>`.**

After the generator writes a contract, run
`python3 .harness/scripts/preflight_contract.py <contract path>` and return
its ERROR lines to the generator BEFORE the evaluator is invoked. Catching an
unsatisfiable contract here is what removes negotiation rounds.

## 1. Initialize

1. Resolve PLUGIN_ROOT: the directory two levels above this skill's base
   directory (stated at the top of this invocation; it contains `scripts/`
   and `templates/`).
2. From the project root, run:
   `python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`
3. Fallback if the script cannot run: create
   `.harness/{contracts,eval-reports,traces,tests,scripts,templates}`,
   `docs/`, `evals/`; copy PLUGIN_ROOT/scripts and PLUGIN_ROOT/templates
   into `.harness/scripts/` and `.harness/templates/`; seed
   `.harness/progress.json` and `CLAUDE.md` from the templates.
4. No blueprint docs exist in this mode, so write a minimal
   `docs/00-blueprint-summary.md` from the template yourself: what we're
   building, the stack you'll use, and conventions. Fill CLAUDE.md's
   "Project facts". The generator and evaluator depend on this page —
   without it they each invent their own conventions and the codebase
   diverges sprint by sprint.

### Resume protocol

If `.harness/progress.json` already exists with a non-null sprint, this is
a resumed run: report phase/sprint/attempt to the user, run
`next_action.py`, continue from there. Never re-plan sprints that exist.

## 2. Plan

1. Set progress phase to `planning`.
2. Invoke **planner** with the build prompt verbatim + the path
   `docs/00-blueprint-summary.md`.
3. Run `python3 .harness/scripts/validate_sprints.py`. On ERROR lines,
   re-invoke the planner with those exact lines. Max 3 rounds, then ask the user.

## 3. Sprint loop

After every agent invocation, run
`python3 .harness/scripts/next_action.py` and do exactly what its JSON
says. When invoking generator/evaluator, pass sprint id, mode, and attempt.

The script encodes the rules — contract before build, evaluator-only
ratification (`Status: ratified`), max 4 negotiation rounds then
force-ratify, attempt > 5 forces a planner split, two teardowns stops for
the human. If state looks wrong, fix the state files and rerun the script;
do not improvise the sequence.

State field reference:

- `sprints.json` status: `pending | active | done | torn-down`
- Contract status: `in-negotiation | revision-requested | ratified`
- `progress.json` awaiting: `null | negotiate | ratify | build | evaluate`

## 4. Completion

When `next_action.py` reports `final-gates` (all sprints done), set phase
to `done` and write `.harness/done.md`:

- Sprint summary table from `sprints.json`
- Eval verdicts per sprint from `.harness/eval-reports/`
- Known issues
- Next steps (suggest running the `riskgate` skill before any release)

Print `.harness/done.md` to the user. Do not claim production readiness —
that requires the riskgate skill's risk-manager classification.
