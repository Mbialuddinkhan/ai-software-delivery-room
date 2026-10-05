---
name: asdr
description: >
  Use this skill when the user wants to build software from scratch, run the full
  AI Software Delivery Room workflow, turn a rough idea into production-grade software,
  create an app, SaaS, dashboard, API, MVP, or automation product, or set up a complete
  multi-agent SDLC. Trigger phrases: "build me", "I want to create", "let's build",
  "full ASDR", "start a new software project", "run the delivery room".
metadata:
  version: "3.4.1"
---

# ASDR — Full Workflow Orchestrator

Ask the user for their software idea if not provided. One sentence is enough.

You are the orchestrator. You do not write product docs or code yourself —
you invoke agents with precise inputs and you keep state correct. The state
machine lives in scripts, not in your memory: when unsure what to do next,
run `python3 .harness/scripts/next_action.py` and do exactly what it says.

## Phase 0 — Initialize

1. Resolve PLUGIN_ROOT: the directory two levels above this skill's base
   directory (the base directory is stated at the top of this invocation;
   PLUGIN_ROOT contains `scripts/` and `templates/`).
2. From the project root, run:
   `python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`
3. Fallback if the script cannot run: create
   `.harness/{contracts,eval-reports,traces,tests,scripts,templates}`,
   `docs/`, `evals/`; copy every file from PLUGIN_ROOT/scripts and
   PLUGIN_ROOT/templates into `.harness/scripts/` and `.harness/templates/`;
   seed `.harness/progress.json` from `.harness/templates/progress.json`;
   create `CLAUDE.md` from `.harness/templates/CLAUDE-template.md`.
4. Detect companions: `python3 .harness/scripts/detect_companions.py`
   (-> `.harness/companions.json`). Surface every `WARN:` line to the user
   verbatim before continuing. ASDR never bundles third-party plugins; it
   adapts to what the host session has installed (see "Companions" below).
   Append a one-line "Companions:" summary to the Project facts in
   `CLAUDE.md` (e.g. `Companions: uupm 2.13.0, ponytail (scoped), graphify;
   rtk absent`).
5. Check for updates: `python3 .harness/scripts/check_updates.py --json
   --plugin-root PLUGIN_ROOT`. If `updates` is non-empty, show the user one
   block per item — name, installed → latest, the "benefits" text verbatim
   (it is the top of that project's changelog), and whether it is optional
   — then ask, per item, whether to install now. Rules:
   - Never install without a yes. A "no" is final for this run; do not
     re-ask. Skip the question entirely when the user said to run
     end-to-end without stopping (note the available updates instead).
   - On yes, run the item's `update_command` via Bash, then tell the user
     to run `/reload-plugins` and re-invoke `/asdr`; the harness state on
     disk survives, so this is a resume, not a restart.
   - An ASDR update mid-run changes the scripts the state machine depends
     on: offer it only at Phase 0 (fresh or resumed), never inside Phase 3.
   - `skipped` entries with "not installed" are fine (optional companions).
     "upstream unreachable" means offline — say so in one line and move on.
   This step is the only place the check runs — ASDR makes no network
   call at session start — and the only place the user decides.

6. Read `references/file-map.md` (in this skill's base directory) now: the
   canonical paths, the stage table and the state fields. Rows cited below
   ("row 2c") are rows of that file map. Browser testing, live runs,
   publishing and manuals are in `references/testing-and-manuals.md`;
   companion rules in `references/companions.md`.

### Resume protocol

If `.harness/progress.json` already exists with phase ≠ `strategic` or a
non-null sprint, this is a resumed run: tell the user where the project
stands (phase, sprint, attempt), run `next_action.py`, and continue from
there. Never restart phases that already produced approved documents.

## Canonical file map

`references/file-map.md`. Use those exact paths everywhere; agents receive
their output path from you and never choose their own.

## Validators

These machine checks catch a bad document before it corrupts the run. Use
them at the steps below; feed any `ERROR:` lines straight back to the agent
that produced the file.

- `validate_critique.py <critique.md>` — structure, self-consistent counts,
  and the ≥8-findings floor (unless the critic set `shortfall_justified`).
- `validate_verdict.py <decision-or-risk.md> --type decision|risk` — the
  fenced verdict block has the required fields and a real (non-placeholder)
  headline value.
- `preflight_contract.py <contract>` — satisfiability linter, run BEFORE the
  evaluator sees a draft: unmeasurable numbers, self-report of command output,
  zero-delta over an edited file, regex conflicts, cost-metric floors, file
  overload (>7 criteria naming one integration file), new-file budget.
- `validate_product_map.py [--gate]` — the end-to-end chain: every feature
  on a journey, every use case on a flow, every flow reachable and proven by
  a journey test case; `--gate` adds passing `[TC-xx]` results. Writes
  `docs/product-map.md`.
- `validate_contract.py` and `validate_sprints.py` (which also requires each
  sprint's `flows` and every Must flow delivered) run in later phases.

Measured numbers live in `.harness/facts.json` (written by `emit_facts.py`)
and nowhere else: **a number not in facts.json is not measured and may not be
asserted; cite it as `facts:<dotted.key>`.**

## Context discipline (v3.2)

Before dispatching ANY agent in the sprint loop, run these in order:

    python3 .harness/scripts/validate_product_map.py --results latest
                                                  # -> .harness/product-map.json (journey state;
                                                  #    ERROR lines are expected mid-build)
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

After the generator writes a contract, run
`python3 .harness/scripts/preflight_contract.py <contract path>` and return
its ERROR lines to the generator BEFORE the evaluator is invoked. Catching an
unsatisfiable contract here is what removes negotiation rounds.

## Stage execution (universal triad)

Every authoring stage in this skill runs as an independent triad — a planner
sets the bar, the specialist executor does the work, and a SEPARATE stage-qa
grades it, so no agent signs off its own work. Honor the dial in
`.harness/progress.json` -> `rigor`:

- `lite` — invoke the executor once (it self-checks); skip the planner and QA.
- `standard` (default) — high-stakes stages run the full triad; low-stakes
  stages skip the planner (light execute -> QA).
- `paranoid` — every stage runs the full triad.

To run one triad stage, drive it with the script until it prints DONE:

    python3 .harness/scripts/stage_status.py <stage-id> --artifact <path> [--no-plan]

Do exactly what it says: PLAN -> invoke stage-planner (writes
`.harness/plans/plan-<stage>.md`); EXECUTE -> invoke the stage's executor named
in the table below (build to the plan); QA -> invoke stage-qa (writes
`.harness/qa-reports/qa-<stage>-r<n>.md`, verdict pass|revise); FORCE-ACCEPT ->
stage-qa makes minimal fixes and passes; DONE -> go to the next stage. Add
`--no-plan` for a low-stakes stage under `standard`. The revise loop is capped
so a stage cannot stall.

Gate/reviewer roles (critic, judge, risk-manager) are NOT wrapped in a triad —
they ARE the independent review, terminated by their mechanical validators.
The critic and judge still run at the end of each phase in every rigor mode.

The stage ids, executors, artifact paths and tiers are in the stage table in
`references/file-map.md`.

## Phase 1 — Strategic SDLC Room

Invoke agents in order. Subagents share none of your context, so every
invocation prompt must contain: (a) the input file paths to read, (b) the
output path, (c) the template path, (d) the user's idea verbatim for the
first two agents.

1. **product-owner** — pass the idea verbatim + row 1 paths. Run this stage
   via the Stage execution protocol (executor: product-owner, stage-id:
   product-brief, artifact: docs/01-product-brief.md). The product-owner ALSO
   writes the business case `docs/01b-business-case.md` (rows 1b, template
   business-case.md) and the roadmap `docs/00b-roadmap.md` (row 0b, template
   roadmap.md) — run each via the Stage execution protocol (stage-ids
   `business-case`, `roadmap`).
2. **business-analyst** — pass row 1 output as input + row 2 paths. Run this
   stage via the Stage execution protocol (executor: business-analyst,
   stage-id: requirements, artifact: docs/02-requirements.md). The
   business-analyst ALSO writes the use-case catalogue `docs/02b-use-cases.md`
   (row 2b, template use-cases.md) via the Stage execution protocol (stage-id
   `use-cases`).
2c. **product-manager** — inputs rows 1, 0b, 2, 2b + rows 2c and 2d paths.
   It writes the feature list and the end-to-end process flows (with the PF-00
   lifecycle map). Run each via the Stage execution protocol (stage-ids
   `features`, `process-flows`).
2d. **business-analyst** (test cases) — inputs rows 2, 2b, 2c, 2d + row 2e
   paths. Stage-id `test-cases`. Then run
   `python3 .harness/scripts/validate_product_map.py`; send ERROR lines to the
   owner (product-manager for features/flows, business-analyst for use cases
   and test cases), max 2 rounds. Discovery cannot pass with a broken chain:
   this is where "the pieces don't connect" is caught for the price of a doc
   edit.
3. **critic** — pass rows 1–2e as inputs + row 3 paths. Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-discovery.md`;
   if it errors, re-invoke the critic with those lines (max 2 rounds).
4. **judge** — pass rows 1–3 (including 2c–2e and `docs/product-map.md`) as inputs + row 4 paths.
   Run `python3 .harness/scripts/validate_verdict.py docs/decision-discovery.md
   --type decision`; if it errors, re-invoke the judge to fix the block.
   Then read the fenced verdict block at the end of the decision doc:
   - `verdict: no-go` → stop; print the reasons and required changes.
   - `required_changes` non-empty → re-invoke the responsible agent with
     exactly those changes, then re-invoke judge. Max 2 repair rounds, then
     stop and ask the user.
4b. Show the user the flow table from `docs/product-map.md` and the PF-00
   lifecycle diagram: it is the whole product on one page, and the cheapest
   place to say "that is not how my users work".
5. **solution-architect** — inputs rows 1–2 + row 5 paths. Run this stage via
   the Stage execution protocol (executor: solution-architect, stage-id:
   architecture, artifact: docs/03-architecture.md).
5b. **solution-architect (design-system)** — invoke only if
   `docs/02-requirements.md` or `docs/02b-use-cases.md` describes a user
   interface (web, mobile, desktop, embedded screen), judged by meaning.
   If `.harness/companions.json` says `uupm.installed: true`, first run
   `python3 .harness/scripts/uupm_design_system.py --query "<product type>
   <industry> <2-4 keywords from the brief>" --project "<name>"` to draft
   `docs/03b-design-system.md`; exit 2 means not installed — the executor
   writes it by hand from the template. Then run this stage via the Stage
   execution protocol (executor: solution-architect, stage-id:
   design-system, artifact: docs/03b-design-system.md, `--no-plan` under
   standard). Tell the executor and stage-qa explicitly: the draft is
   keyword-matched, so the thing to grade is FIT against docs/01 (§10
   fit review filled, pattern/style justified, every text pair ≥ 4.5:1),
   not formatting. If no UI, skip and note you evaluated and found no UI
   surface.
6. **ai-architect** — invoke only if `docs/02-requirements.md` describes any
   AI/LLM/agent/RAG/ML capability, judged by meaning not keywords (e.g.
   "semantic search", "smart recommendations", "summarization", "chat
   assistant" all count); inputs rows 2 and 5 + row 6 paths. If none, skip
   and note you evaluated and found no AI surface. When invoked, run this
   stage via the Stage execution protocol (executor: ai-architect, stage-id:
   agent-design, artifact: docs/04-agent-design.md). Pass row 5b as an
   extra input when it exists. Tell the executor that §13 (runtime and
   deployment: tier per agent + Task/Workspace/Gateway/Model blocks) is
   mandatory and is what devops and security-compliance build from.
7. **security-compliance** — inputs rows 5–6 + row 7 paths; point it at
   the §13.2 Gateway blocks in row 6 (default-deny egress per agent). Run this stage via
   the Stage execution protocol (executor: security-compliance, stage-id:
   security-design, artifact: docs/05-security.md).
8. **devops** — inputs rows 5, 6 and 7 + row 8 paths; it also sets up the
   browser suites and writes row 12 (`.harness/test-config.json`). For every T3 agent
   in row 6 §13.1 it also writes `deploy/agents/<agent>.yaml` from
   `.harness/templates/agent-runtime.yaml` (row 6b). Run this stage via the
   Stage execution protocol (executor: devops, stage-id: devops-design,
   artifact: docs/06-devops.md).
9. **critic** — inputs rows 5, 5b, 6, 7, 8 + row 9 paths. Its mandatory
   checks on row 6 §13 (tier justified, no untrusted code at T1, allowlist
   per agent, no secret values) and on row 5b (fit vs brief, contrast) are
   in the critic's own instructions. Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-architecture.md`;
   if it errors, re-invoke the critic (max 2 rounds).
10. **judge** — inputs rows 5–9 + row 10 paths. Run
    `python3 .harness/scripts/validate_verdict.py docs/decision-architecture.md
    --type decision` first; then same verdict handling as step 4.

After the blueprint is approved:

11. **You** write `docs/00-blueprint-summary.md` from the template — one
    page max. Include the agent tier table from row 6 §13.1 (one line per
    agent) and the path to row 5b when it exists — the generator reads
    both every UI or agent sprint. This digest is what the generator and evaluator read every
    sprint; the full docs stay available for lookups.
12. Update the "Project facts" section of `CLAUDE.md` (stack, run/test/lint
    commands, conventions) from the approved architecture.
13. Invoke **product-integrity-qa** in SEED mode to build the traceability
    matrix (`.harness/traceability.json` + `docs/traceability.md`) from the
    strategic docs (brief, business case, roadmap, requirements, use cases,
    features, process flows, test cases), then run
    `python3 .harness/scripts/validate_traceability.py
    .harness/traceability.json --sprints sprints.json`.
14. Log: `python3 .harness/scripts/trace.py orchestrator blueprint-approved "phase 1 done"`

### User checkpoint

Show the user a 5-bullet blueprint summary and ask whether to proceed to
the build. Building runs long and compounds on these decisions — this is
the cheapest moment to correct course. If the user already told you to run
end-to-end without stopping, note that and continue.

## Phase 2 — Sprint planning

1. Set `.harness/progress.json` phase to `planning`.
2. Invoke **planner** with: the user's idea verbatim + the paths
   `docs/00-blueprint-summary.md`, `docs/02d-process-flows.md` and
   `docs/02e-test-cases.md` + instruction to write `sprints.json` as slices
   through whole flows (sprint 1 = the entry flow working end to end).
3. Run `python3 .harness/scripts/validate_sprints.py`.
4. If it prints ERROR lines, re-invoke the planner with those exact lines.
   Max 3 rounds, then stop and ask the user.

## Phase 3 — Sprint execution loop

Drive the loop with the script — after every agent invocation:

1. Run `python3 .harness/scripts/next_action.py`.
2. Do exactly what its JSON says (`next_agent`, `mode`, `sprint`, `attempt`).
3. When it says `activate`: update `sprints.json` and `progress.json` as
   instructed, then rerun the script.
4. When invoking generator/evaluator, pass: sprint id, mode, and attempt.
4b. Before the evaluator's EVALUATE run, tell it whether the user wants to
   watch (`run_tests.py --live`). After it reports, publish the test report it
   produced as the private Artifact (see `references/testing-and-manuals.md`)
   and give the user the link with one line: passed/failed, flows proven.
5. After each sprint the evaluator marks `done`, invoke **product-integrity-qa**
   in UPDATE mode to refresh `.harness/traceability.json` +
   `docs/traceability.md` and write the snapshot `docs/integrity-<sprint>.md`,
   then run `python3 .harness/scripts/validate_traceability.py
   .harness/traceability.json --sprints sprints.json`. If it reports
   DRIFT/ORPHAN/BROKEN, STOP and surface it to the user. Only on the user's
   approval, re-invoke **product-owner** and **business-analyst** to update
   every affected strategic doc (brief, roadmap, business case, requirements,
   use cases) consistently, then have **product-integrity-qa** re-baseline the
   matrix before the loop continues.

Companion rules for UI sprints, the build ladder, Ponytail, Graphify and RTK
are in `references/companions.md`; apply them every sprint.

The script encodes the rules — contract before build, evaluator-only
ratification, max 4 negotiation rounds then force-ratify, attempt > 5
forces a planner split, two teardowns stops for the human. It now derives
the attempt and negotiation counters from artifacts on disk as well as from
`progress.json`, so a missed manual increment can no longer disable a
circuit breaker. Do not improvise around it: if you think the state is
wrong, fix the state files, rerun the script, and follow it.

State fields: `references/file-map.md` → State field reference.

## Phase 4 — Final gates

When `next_action.py` says `final-gates`, set phase to `final-gates`, then:

1. **security-compliance** — inputs: the codebase; output
   `docs/09-security-review-final.md`; template security.md. Tell it this
   is the release gate: verify code, not docs. Run this stage via the Stage
   execution protocol (executor: security-compliance, stage-id:
   security-final, artifact: docs/09-security-review-final.md).
2. **devops** — output `docs/09-devops-readiness.md`; template devops.md;
   release-gate context: run the builds, validate every
   `deploy/agents/*.yaml` against docs/04 §13.2, paste evidence. Run this stage via
   the Stage execution protocol (executor: devops, stage-id: devops-readiness,
   artifact: docs/09-devops-readiness.md).
3. **documentation** — the developer docs plus, for any UI,
   `docs/manuals/manual.json` (row 16) from the tour screenshots. Run this
   stage via the Stage execution protocol (executor: documentation, stage-id:
   documentation; low tier — use `--no-plan` under standard). Before invoking
   it, run `python3 .harness/scripts/run_tests.py --tours` so the screenshots
   are from the current commit.
4. **product-integrity-qa** — GATE mode: run the full regression (all sprints)
   and emit the integrity verdict to `docs/09-product-integrity.md` (template
   integrity-report.md). Then run `python3 .harness/scripts/validate_verdict.py
   docs/09-product-integrity.md --type integrity`; if it errors, re-invoke to
   fix the block. A `broken` or `drifted` integrity verdict is a release
   blocker.
5. **risk-manager** — inputs: both 09-docs, `docs/09-product-integrity.md`,
   `docs/product-map.md`, eval reports, sprints.json; output
   `docs/09-risk-review.md`. Then run
   `python3 .harness/scripts/validate_verdict.py docs/09-risk-review.md
   --type risk`; if it errors, re-invoke the risk-manager to fix the block.
6. Read the risk-manager's fenced classification block. Only if
   `mvp-ready` or `production-ready`: invoke **release-manager**, which runs
   the release test run, publishes the versioned report and builds the user
   manuals (HTML + PDF, every persona and tier). Publish the report and the
   manual page it prints as private Artifacts. Otherwise skip packaging and
   report the blockers.

## Phase 5 — Final response

Set phase to `done`. Print:

1. What was built
2. Sprint status table (from `sprints.json`)
3. Final risk classification (from the classification block)
4. How to run locally, test, deploy (from `CLAUDE.md` / docs)
5. Where the results are: the test report and the user manuals (links to the
   private pages, and the repo paths), and the product-map flow table
6. Run metrics: `python3 .harness/scripts/run_metrics.py`, show the table
7. Known limitations
8. Next recommended steps

Never claim production-ready unless the risk-manager's block says
`production-ready` — that word is its authority alone.
