---
name: asdr
description: >
  Use this skill when the user wants to build software from scratch, run the full
  AI Software Delivery Room workflow, turn a rough idea into production-grade software,
  create an app, SaaS, dashboard, API, MVP, or automation product, or set up a complete
  multi-agent SDLC. Trigger phrases: "build me", "I want to create", "let's build",
  "full ASDR", "start a new software project", "run the delivery room".
metadata:
  version: "4.0.0"
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

5a. **Where to start (v4.0).** Run

       python3 .harness/scripts/entry_point.py recommend --prompt "<the user's request, verbatim>"

   It reads the request and looks at the folder (an earlier run, ASDR's own
   documents, the user's own PRDs, specs or architecture notes, existing code)
   and prints every start point — Validate, Discovery, Design, Build, Release
   gate, Assess an existing system, Resume — with what each skips, the risk of
   skipping it, and what must be caught up first, and marks one as
   recommended with its reasons. Show the user the recommendation and its
   reasons in plain words, then ask with AskUserQuestion: the recommended start
   first (label ending "(Recommended)"), then the two or three next most
   sensible ones, each description saying what it skips and the catch-up it
   needs; leave out options marked `not advised` unless the user asked for
   them. Never choose for the user — except when they said to run end-to-end
   without stopping: then take the recommendation and say so. Record it:

       python3 .harness/scripts/entry_point.py choose <start> --by "<user>" --prompt "<request>"

   and log the question with `log_question.py`. A start other than Discovery
   or Validate runs the catch-up below once the rest of Phase 0 (steps 5b–6)
   is done; Resume follows the Resume protocol; Assess hands over to the
   assess skill. A run whose progress.json is still in the strategic phase is
   not a resume: the recommendation comes from its documents and decisions.

5b. Ask the user once for the project's environments, repositories and links
   (test, staging, production URLs; repository URLs; CI) and write them to
   `.harness/dashboard.json` (`environments`, `repos`, `links`). List test
   login role names only; credentials stay in environment variables.

5c. **Rigor, model plan and cost.** Estimate the run from the idea (sprints:
   small 2–3, medium 4–6, large 7+; add `--ui` / `--ai` when the idea has
   them; services stay 1 until the architecture decision):

       python3 .harness/scripts/estimate_run.py --sprints <n> [--ui] [--ai] --rigor standard [--start <start>] --compare-plans

   (`--start` for Discovery, Design, Build or Release gate; for Validate add a
   second estimate with `--mode validate`; Assess has its own estimate in the
   assess skill; for Resume leave it out.)

   Add `--price-opus/--price-sonnet/--price-haiku/--price-fable` (USD per
   million tokens, blended) when the user wants money figures; prices are not
   built in. Show the user the tables and ask two questions in ONE
   AskUserQuestion round:
   - **Thoroughness:** `lite` for internal tools and prototypes with no client
     data, `standard` (default), `paranoid` for client-facing work with money,
     personal or regulated data.
   - **Model plan (v4.0):** `balanced` (default: judgement and authoring roles
     on the strongest model, checklist roles and the panel on Sonnet),
     `economy` (only the roles that can stop a bad release stay on the
     strongest model; authors on Sonnet; the panel and release notes on
     Haiku), `maximum` (every role on the strongest model; the default under
     `paranoid`). If the main conversation runs on Fable, ask whether the top
     roles should use Fable too (`--top fable`). Say plainly: each role runs
     on its own model, but this conversation stays on the model the user
     selected — the cheapest setup is a Sonnet conversation with this plan; on
     a Pro or Max subscription the saving shows as usage limits lasting
     longer, not a smaller bill.
   If they choose `paranoid` and did not pick a plan, use `maximum`. Write
   `rigor` to `.harness/progress.json`, run `python3
   .harness/scripts/model_plan.py set --plan <plan> [--top fable]`, then run
   the estimate again with `--rigor <choice> --set-budget`. Re-estimate after
   the architecture and portability decisions (`--services <n> --cloud`) and
   tell the user if it moved by more than 20%.

5d. **Test cloud.** Ask once: "Which cloud should ASDR deploy to for testing?"
   — AWS, Azure, Google Cloud, or None (local only). Say what that means:
   every deploy still asks first, uses a least-privilege role, is tagged with a
   time-to-live and is torn down after the test; production is never touched;
   sign-in uses the cloud's own CLI, never keys pasted into ASDR. Write the
   answer and region to `.harness/cloud.json` (`test_cloud`, `region`), log the
   question, then run `python3 .harness/scripts/cloud_preflight.py` and show
   any NOT READY reasons. From `.harness/companions.json` → `cloud`, AND from
   your own tool list (`mcp__aws*`, `mcp__azure*`, `mcp__google*` /
   `mcp__gcloud*`, `mcp__terraform*`), tell the user which vendor agent tools
   are present: AWS MCP Server, Azure Skills plugin / Azure MCP Server, Google
   Cloud MCP servers, Terraform MCP server. When the chosen cloud's are
   missing, say what they add (current service docs and prices, validated
   deploys) and where to get them; never install them yourself.

6. Read `references/file-map.md` (in this skill's base directory) now: the
   canonical paths, the stage table and the state fields. Rows cited below
   ("row 2c") are rows of that file map. Browser testing, live runs,
   publishing and manuals are in `references/testing-and-manuals.md`;
   companion rules in `references/companions.md`.

### Questions, sprint clock and the dashboard (every phase)

- **Every question you ask the user** (AskUserQuestion or in chat) and its
  answer: `python3 .harness/scripts/log_question.py --q "<question>" --a
  "<answer>" --phase <phase> --asked-by <who asked> [--changed <docs it
  changed>]`. A question still waiting for an answer gets logged with `--status
  open`; log it again under the same `--id` once it is answered. Add
  `--client` when the question is for the client (a business decision, an
  approval, access): only those appear in the client status report.
- **Model, on EVERY agent invocation** (v4.0): pass `model: <the output of
  python3 .harness/scripts/model_plan.py get <agent>>`. If the call fails
  because the account or organisation does not allow that model, run
  `model_plan.py unavailable <model>`, tell the user in one line, and retry
  with the model `get` now returns.
- **Cost log, after EVERY agent run** (v3.8): `python3
  .harness/scripts/log_agent_run.py --agent <name> --phase <phase> [--stage
  <id>] --model <the model you passed> --usage "<the usage block at the end of the
  Agent result>"`. On `WARN` tell the user how much of the budget is used; on
  `OVER BUDGET` stop and ask whether to continue, lower the rigor or cut scope.
- **Sprint clock**: `python3 .harness/scripts/sprint_clock.py start <sprint>`
  when a sprint is activated, and `torn-down <sprint>` on a teardown (the evaluator stamps `done` itself). The
  delivery date is computed from these.
- **Dashboard**: at the end of every phase and every sprint, and whenever the
  user asks for the status, run `python3 .harness/scripts/build_dashboard.py`.
  It writes `docs/dashboard/index.html` and `dashboard.pdf`. Publish
  `docs/dashboard/dashboard-artifact.html` as the private Artifact
  "<Product> Dashboard", updating the same one each time so the link stays the
  same, and send the PDF on request.
- **"/asdr status"** (or "where are we?"): rebuild the dashboard and answer
  from it with:
  - status and its reasons;
  - expected delivery ± its standard deviation;
  - what is waiting on the user;
  - the link to the dashboard.
- **Client status report** (only when the user asks for one, e.g. "status
  report for the client"): `python3 .harness/scripts/build_dashboard.py
  --audience client` writes `docs/dashboard/client/status-report.pdf` in the
  user's brand (`~/.asdr/brand.json`), from the same facts and the same status
  rule, without agent activity, effort, internal questions, local paths or
  internal links. Fill `client` in `.harness/dashboard.json` first (name,
  reference). Give the user the PDF to read and send themselves; never publish
  it and never send it to the client yourself.

### Resume protocol

If `.harness/progress.json` already exists with phase ≠ `strategic` or a
non-null sprint, this is a resumed run: tell the user where the project
stands (phase, sprint, attempt), run `next_action.py`, and continue from
there. Never restart phases that already produced approved documents.

### Starting late: the catch-up (v4.0)

A late start skips stages, never the evidence the later gates check. When
`.harness/entry.json` lists `catch_up` items:

1. Work through them in the order listed, one invocation per run of
   consecutive items by the same owner, in **INTAKE mode** — product-owner
   (brief), business-analyst (requirements, use cases), product-manager
   (features, process flows), business-analyst (test cases),
   solution-architect (architecture options; then, after the user's
   decision, the architecture, services, design system), ai-architect (AI
   design), devops (portability), solution-architect (configurable
   decisions; then the business-analyst adds a test case per allowed value),
   security-compliance (security design), devops (deployment plan). Pass each
   owner: the user's documents
   (`user_docs` in entry.json, plus anything they attached), the request
   verbatim, the output paths and the templates. INTAKE means convert, not
   invent: everything taken from the user's documents keeps its meaning; what
   the owner had to infer is marked `[inferred]`; what is missing goes under
   "Gaps for the user". Ask the user about the gaps in one round.
2. Decisions still need the user: when the catch-up writes the architecture
   options, the portability decision or the configurable decisions, the
   validator exits 2 and you ask exactly as in Phase 1 (4c, 6b, 6c) — a
   decision already made in the user's documents is shown to them to
   confirm, not assumed.
3. Run the stage validators listed in entry.json (`validators`); send ERROR
   lines back to the owner (max 2 rounds).
4. One **critic** pass over the whole catch-up set, in every rigor mode
   (`docs/critique-intake.md`, validated with `validate_critique.py`), then
   `decide.py docs/critique-intake.md --out docs/decision-intake.md --phase
   intake --rigor <rigor>`; the judge only when it says so. Documents that
   already existed but were never reviewed (no phase decision) are part of
   this set: `entry_point.py` lists the review as a catch-up item.
5. `python3 .harness/scripts/entry_point.py catchup` must exit 0. Then continue
   where entry.json says (`continue_at`); for Build, set progress phase to
   `planning` after steps 11–13; for Release gate, set it to `final-gates`.

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
- `validate_product_map.py [--require-coverage] [--gate]` — the end-to-end
  chain: every feature on a journey, every use case on a flow, every flow
  reachable and proven by a journey test case, and every testable item of
  THIS project (FR, NFR, AC, BR, EC, use-case alternate/exception flows,
  features, flow steps) named by a test case; features that change another
  role's abilities tested from that role's side. `--gate` adds passing
  `[TC-xx]` results and the runtime markers (`flowStep` / `covers`) that
  prove each Must step and each Covers item was reached. Writes
  `docs/product-map.md` with the coverage matrix.
- `build_dashboard.py` — the project dashboard (status by a fixed rule,
  expected delivery ± standard deviation, roadmap, features, documents,
  environments, repositories, questions and decisions); HTML + PDF, private.
  Fed by `log_question.py` and `sprint_clock.py`.
- `assess_scan.py`, `validate_assessment.py`, `build_assess_report.py` — the
  `assess` skill's scanner run, evidence gate and two-part report.
- `compare_parity.py [--gate]` — existing systems only (`docs/02f-parity.md`):
  compares what tests captured with `parity('PAR-xx', …)` on the old system
  (`run_tests.py --parity old`) and on the new build; a kept behaviour that
  differs fails the sprint and blocks the release. `validate_product_map.py
  --gate` requires a fresh, passing comparison.
- `estimate_run.py`, `log_agent_run.py`, `decide.py`,
  `check_required_changes.py` (v3.8) — the cost estimate per rigor level, the
  per-agent cost log with budget warnings, the scripted decision when a
  critique has nothing Critical or High, and the scripted second round.
- `validate_architecture_options.py`, `validate_portability.py`,
  `validate_services.py` (v3.8) — the user's architecture decision (monolith /
  microservices / serverless, with pros, cons, business impact and costs), the
  portability decision (strategy and clouds, with a cost comparison), and the
  microservices rules (owned data, tested contracts `CT-xx`, no synchronous
  cycles, standalone run, adapters per cloud).
- `cloud_preflight.py`, `cloud_env.py`, `cloud_parity.py` (v3.8) — read-only
  readiness on the test cloud, the ledger of temporary test environments with
  their time-to-live, and the proof that the cloud build passes the same tests
  as the local one.
- `entry_point.py`, `model_plan.py`, `validate_configurability.py` (v4.0) — the
  recommended start point and the user's choice with its catch-up list; the
  model each role runs on, with fallbacks when a model is not allowed; and the
  configurable decisions (configure / prepare / decide-once, each decided by
  the user) with their settings, a test case per allowed value
  (`--require-tests` once the business-analyst has added them) and a review
  date (`--gate` at release).
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
    python3 .harness/scripts/compare_parity.py    # existing systems only (docs/02f-parity.md)
                                                  # -> .harness/parity.json
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

- `lite` — each executor runs once per batch (below) and self-checks; no
  stage planner, no stage QA.
- `standard` (default) — batches; no stage planner (always pass `--no-plan`:
  the QA grades against the template and the standard); one stage-qa run per
  batch that holds a high-tier stage; other batches are executor-only.
- `paranoid` — every stage runs the full triad on its own; the model plan
  defaults to `maximum` (every role on the strongest model).

**Batches (lite and standard, v3.8).** Consecutive stages with the same
executor run as ONE invocation that writes all their artifacts, so the inputs
are read once: product-owner → product-brief, business-case, roadmap;
business-analyst → requirements, use-cases; product-manager → features,
process-flows; business-analyst → test-cases; solution-architect →
architecture (+ services, design-system). Run `stage_status.py` for each stage
of the batch with `--no-plan`; when all say EXECUTE, invoke the executor once
with every artifact path; when they say QA, invoke stage-qa once with every
artifact and ask for one report per stage id
(`.harness/qa-reports/qa-<stage>-r<n>.md`). Re-run only the stages marked
`revise`. By the estimator (an estimate, not yet a measurement): about 30%
fewer agent runs and 18% fewer tokens than 3.7's standard for a typical build;
the agent-run log measures the real figure on each project.

**Models (v4.0).** Each role's model comes from the model plan
(`model_plan.py get <role>`), passed on every invocation. The `balanced` plan
equals the agents' frontmatter: Opus for the judgement and authoring roles;
stage-planner, stage-qa, product-integrity-qa, planner, documentation,
release-manager and panelist on Sonnet.

**Phase review (v3.8).** When a phase critique passes
`validate_critique.py`, run

    python3 .harness/scripts/decide.py docs/critique-<phase>.md --out docs/decision-<phase>.md --phase <phase> --rigor <rigor>

With no Critical or High finding it writes the decision itself — verdict go;
Medium findings become required changes for their owners, applied before the
next phase without another review; Low findings are recorded as assumptions —
and no judge runs. Exit 2 (`JUDGE: required`) → invoke the judge as before.
After a judge's no-go and the owners' fixes, run
`check_required_changes.py docs/decision-<phase>.md --gate "<the phase's
validator>"`, read a sample of the changed files yourself (every change from a
Critical or High finding), then re-run it with `--write --spot-checked <ids>`;
re-invoke the judge only if a spot check fails or an owner disputes a change.

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
The critic runs at the end of each phase in every rigor mode; the judge when
`decide.py` says it is needed, and always under `paranoid`.

The stage ids, executors, artifact paths and tiers are in the stage table in
`references/file-map.md`.

## Phase 1 — Strategic SDLC Room

Invoke agents in order. Subagents share none of your context, so every
invocation prompt must contain: (a) the input file paths to read, (b) the
output path, (c) the template path, (d) the user's idea verbatim for the
first two agents.

0. **Idea validation (optional).** When the start point (Phase 0 step 5a) is
   Validate, run it without asking; when it is Discovery, the user already
   declined — skip this step. Otherwise, if `docs/00a-idea-validation.md` does not
   exist, ask the user once whether to validate the idea before scoping it
   (say whether MiroFish simulation is available, from
   `.harness/companions.json` → `mirofish.installed`; desk-only otherwise).
   Default is no when the user asked to run end-to-end without stopping. On
   yes, read `PLUGIN_ROOT/skills/validate/SKILL.md` and run its Phases 1–5
   (Phase 0 is already done; its stage table and rules apply) and
   honour `docs/decision-validation.md`: `no-go` stops here with the reasons
   and §6 tests; `go` continues. When `docs/00a-idea-validation.md` exists,
   pass it (row 0a) as an input to the product-owner in step 1.
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
2c+. **Persona walkthrough** (only if `validate` ran and built a panel).
   Run it with `python3 .harness/scripts/panel.py walkthrough-next` (it
   prints SKIP when no validated panel exists — then skip silently). For each
   `WALKTHROUGH` task invoke **panelist** with ONLY its input and output paths;
   repeat until `DONE`, then pass `docs/validation/panel/walkthrough-summary.md`
   to the product-manager as input for revising the flows (friction to fix,
   steps where personas gave up). It is simulated: it finds friction, it does
   not predict usage, and it never overrides what real users or the client
   said.
2d. **business-analyst** (test cases) — inputs rows 2, 2b, 2c, 2d + row 2e
   paths. Stage-id `test-cases`. Then run
   `python3 .harness/scripts/validate_product_map.py --require-coverage`; send ERROR lines to the
   owner (product-manager for features/flows, business-analyst for use cases
   and test cases), max 2 rounds. Discovery cannot pass with a broken chain:
   this is where "the pieces don't connect" is caught for the price of a doc
   edit.
3. **critic** — pass rows 1–2e as inputs + row 3 paths. Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-discovery.md`;
   if it errors, re-invoke the critic with those lines (max 2 rounds).
4. **Decision** — run `decide.py` on `docs/critique-discovery.md` (Stage
   execution → Phase review). If it writes the decision, give each required
   change to its owner and continue at 4b. Exit 2 → **judge** — pass rows 1–3
   (including 2c–2e and `docs/product-map.md`) as inputs + row 4 paths.
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
4c. **solution-architect (architecture options, v3.8)** — inputs rows 1, 1b,
   2, 2d + row 5a path (`docs/03c-architecture-options.md`, template
   architecture-options.md). Stage-id `architecture-options`. Then run
   `python3 .harness/scripts/validate_architecture_options.py`: ERROR → back to
   the architect; exit 2 → show the user the side-by-side table (section 03)
   and the recommendation, and ask them to choose (AskUserQuestion: one option
   per architecture, the recommended one first, each description giving its
   business impact and its build and run cost estimates). Write the answer into
   section 05 (Decision, Decided by), log it with `log_question.py --client`,
   and re-run until exit 0. No design starts before the user has decided.
5. **solution-architect** — inputs rows 1–2, 5a + `.harness/architecture.json`
   + row 5 paths. Run this stage via the Stage execution protocol (executor:
   solution-architect, stage-id: architecture, artifact:
   docs/03-architecture.md). When the decided style is `microservices` it also
   writes `docs/03e-services.md` (row 5e, template services.md) to
   `.harness/templates/microservices/README.md`, in the same batch; then run
   `python3 .harness/scripts/validate_services.py` and send ERROR lines back.
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
6b. **devops (portability, v3.8)** — unless the user said the product runs
   only on their own machines. Inputs rows 5, 5e +
   `.harness/templates/cloud/catalogue.json` + `.harness/cloud.json`; output
   `docs/03d-portability.md` (row 5d, template portability.md). Tell it to
   price each strategy with the vendor tools present in this session (AWS MCP
   Server, Azure MCP Server, Google Cloud) or the vendors' calculators, and to
   state source and date. Then `python3
   .harness/scripts/validate_portability.py`: ERROR → back to devops; exit 2 →
   show the user the cost comparison and the recommendation and ask them to
   choose the strategy and the production cloud(s); write the decision, log it
   with `--client`, re-run until exit 0. Then re-run `validate_services.py`
   (adapters per production cloud) and re-estimate the run.
6c. **solution-architect (configurable decisions, v4.0)** — inputs rows 2c
   (its "Decisions with options" section), 5, 5a, 5d + row 5f path
   (`docs/03f-configuration.md`, template configuration.md). Stage-id
   `configuration`. Every decision with more than one sensible answer is typed
   configure (cheap, reversible, business-level: built as a setting), prepare
   (expensive technical choice: one option built behind a connection point)
   or decide-once (hard to reverse), with the extra cost of building every
   option. Then `python3 .harness/scripts/validate_configurability.py`: ERROR
   → back to the architect; exit 2 → show the user the decision register (one
   line per decision: the options, the recommended type, the extra cost and
   why) and ask them to decide each one (AskUserQuestion, recommended type
   first; a decision against the 15% rule is allowed and recorded). Write the
   answers into the register (Decision, Decided by), log them with
   `--client`, and re-run until nothing is pending (it may still exit 2 with
   `WAITING:` lines — the settings' test cases, which come next). Then the
   **business-analyst** adds a test case for every allowed value of every
   setting to `docs/02e-test-cases.md` (tested from the side of the user the
   setting affects; pairwise for settings that interact, section 05) and the
   TC ids to the Tests column; then `validate_configurability.py
   --require-tests` must exit 0, and `validate_product_map.py
   --require-coverage` still passes.
7. **security-compliance** — inputs rows 5–6, 5d + row 7 paths; for each
   production cloud in `.harness/portability.json` it designs least-privilege
   roles, network exposure and the secrets service; point it at
   the §13.2 Gateway blocks in row 6 (default-deny egress per agent). Run this stage via
   the Stage execution protocol (executor: security-compliance, stage-id:
   security-design, artifact: docs/05-security.md).
8. **devops** — inputs rows 5, 5d, 5e, 6 and 7 + row 8 paths; it also sets up the
   browser suites and writes row 12 (`.harness/test-config.json`). For every T3 agent
   in row 6 §13.1 it also writes `deploy/agents/<agent>.yaml` from
   `.harness/templates/agent-runtime.yaml` (row 6b). It writes the
   infrastructure as code to `.harness/templates/microservices/infra-layout.md`
   for the production clouds and the test cloud, and the local Compose file
   (template `docker-compose.services.yml` for microservices: every service
   runs standalone with its own data store and mocks of what it calls). Run
   this stage via the Stage execution protocol (executor: devops, stage-id:
   devops-design, artifact: docs/06-devops.md). Then `cloud_preflight.py`
   must say READY (or the test cloud is `none`).
9. **critic** — inputs rows 5, 5a, 5b, 5d, 5e, 6, 7, 8 + row 9 paths. Its mandatory
   checks on row 6 §13 (tier justified, no untrusted code at T1, allowlist
   per agent, no secret values) and on row 5b (fit vs brief, contrast) are
   in the critic's own instructions; pass row 5f too (over-configuration is
   one of its checks). Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-architecture.md`;
   if it errors, re-invoke the critic (max 2 rounds).
10. **Decision** — `decide.py` on `docs/critique-architecture.md`; exit 2 →
    **judge** — inputs rows 5–9 (with 5a, 5d, 5e, 5f) + row 10 paths. Run
    `python3 .harness/scripts/validate_verdict.py docs/decision-architecture.md
    --type decision` first; then same verdict handling as step 4.

After the blueprint is approved:

11. **You** write `docs/00-blueprint-summary.md` from the template — one
    page max. Include the agent tier table from row 6 §13.1 (one line per
    agent), the path to row 5b when it exists, and the settings from row 5f
    (key, default, who may change it) — the generator reads them every
    sprint. This digest is what the generator and evaluator read every
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
   instructed, run `python3 .harness/scripts/sprint_clock.py start <sprint>`,
   then rerun the script. The evaluator stamps `done` itself when it passes a
   sprint; on a teardown, run `sprint_clock.py torn-down <sprint>`. Rebuild the
   dashboard after every sprint.
4. When invoking generator/evaluator, pass: sprint id, mode, and attempt;
   when the sprint's features have settings (row 5f), pass
   `docs/03f-configuration.md` too: the generator builds each setting through
   the one settings layer, and the evaluator tests every allowed value from
   the affected user's side.
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

6. **Cloud test run (v3.8)** — when `.harness/cloud.json` → `test_cloud` is
   not `none`: after the first sprint (for microservices, the walking
   skeleton), after the last sprint, and whenever the user asks.
   a. devops runs `cloud_preflight.py`; show the user the Terraform plan
      summary and the time-to-live, and ask to approve the deploy. No answer,
      no deploy.
   b. On yes, devops applies `infra/envs/test-<cloud>` and records it:
      `cloud_env.py create --name <name> --cloud <cloud> --approved-by
      "<user>, <date>" --ttl-hours <cloud.json ttl> --url <url> --stack <folder>`.
   c. `run_tests.py --label cloud-<cloud> --base-url <url> --no-server`, then
      `cloud_parity.py --local <the latest local label> --cloud cloud-<cloud>`.
      A parity ERROR fails the sprint like a failing test.
   d. devops destroys it at once and records `cloud_env.py destroyed --name
      <name>`. The dashboard shows anything still running; past its
      time-to-live it turns the status "at risk".

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
   `deploy/agents/*.yaml` against docs/04 §13.2, paste evidence. It also runs
   `cloud_preflight.py`, `validate_services.py --gate` (microservices) and
   `cloud_env.py list --overdue`: a test environment still running blocks
   the release. It also runs `validate_configurability.py --gate` (v4.0): a
   setting past its review date, or a setting value whose test cases do not
   pass, blocks the release. Run this stage via
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
   `docs/product-map.md`, eval reports, sprints.json, and (v3.8)
   `.harness/cloud-parity.json`, `.harness/services.json`,
   `.harness/cloud-envs.jsonl`, and (v4.0) `.harness/configuration.json`; output
   `docs/09-risk-review.md`. Then run
   `python3 .harness/scripts/validate_verdict.py docs/09-risk-review.md
   --type risk`; if it errors, re-invoke the risk-manager to fix the block.
6. Read the risk-manager's fenced classification block. Only if
   `mvp-ready` or `production-ready`: first get the user's review of the
   manual wording (release skill, Phase 1b: review page → approve / flag),
   then invoke **release-manager**, which runs
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
6. Run metrics: `python3 .harness/scripts/run_metrics.py`, show the table;
   then the final dashboard: `python3 .harness/scripts/build_dashboard.py`
   (link and PDF)
7. Known limitations
8. Next recommended steps

Never claim production-ready unless the risk-manager's block says
`production-ready` — that word is its authority alone.
