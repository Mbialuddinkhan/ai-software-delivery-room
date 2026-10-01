# Changelog

All notable changes to the AI Software Delivery Room in this improvement pass.
Baseline is the shipped plugin at v2.0.0.

## [3.3.0] — agent runtime tiers, design-system stage, companion detection

### Added
- `docs/04-agent-design.md` §13 **Runtime and deployment**: a tier decision
  table per agent (T1 function / T2 container worker / T3 sandboxed actor
  runtime) and four runtime blocks per agent — Task, Workspace, Gateway,
  Model — the primitives of AX (google/ax), used as the design vocabulary
  for every tier. devops consumes Task + Model + topology; security-compliance
  consumes Gateway (default-deny egress allowlist, gateway-injected secrets).
- `templates/agent-runtime.yaml` — T3 reference manifest in AX `v1alpha1`
  schema; devops writes `deploy/agents/<agent>.yaml` per T3 agent.
- `design-system` stage (row 5b, `docs/03b-design-system.md`,
  `templates/design-system.md`) — runs after architecture when the product
  has a UI surface. Its §9 checklist becomes UI sprint contract criteria.
- `scripts/detect_companions.py` — Phase 0 detection of UI UX Pro Max,
  Ponytail, Graphify and RTK → `.harness/companions.json`, with warnings.
- `scripts/uupm_design_system.py` — drafts 03b via UI UX Pro Max when
  installed (exit 2 when not → hand-written from template).
- `docs/COMPANIONS.md` — install and scoping notes; the Ponytail
  `PONYTAIL_SUBAGENT_MATCHER='^generator$'` requirement; why RTK is not used.

### Changed
- critic: mandatory findings for §13 (unjustified T3, untrusted code at T1,
  missing allowlist, secret values) and for 03b (fit vs brief, contrast).
- generator: UI sprints copy 03b §9 into the contract; Ponytail rules —
  YAGNI objections belong in NEGOTIATE, a ratified criterion is never
  skipped.
- devops inputs now include 04; release gate validates `deploy/agents/*.yaml`.
- `init_asdr.py` creates `deploy/agents/`; `CLAUDE-template.md` gains
  Companions / Design system / Agent runtime tiers lines.

### Added — packaging and updates
- `.claude-plugin/marketplace.json` (the `asdr` marketplace, added in 3.2.1)
  now lists companions: `ui-ux-pro-max` is a declared dependency of ASDR
  (installs with it, pinned by SHA); `ponytail` is listed but disabled by
  default. `plugin.json` gains `dependencies`, `hooks`, `license`, `repository`.
- `scripts/check_updates.py` + `scripts/upstream.json`: compares installed
  vs upstream versions for ASDR, UI UX Pro Max, Ponytail and Graphify,
  pulls each changelog's top section as "what it adds", and reports. Runs
  as a once-a-day SessionStart notice (`hooks/hooks.json`) and as Phase 0
  step 5, where the orchestrator asks per item before running the update.
- `templates/build-ladder.md`: the generator's BUILD-mode ladder, adapted
  from Ponytail (MIT), so the plugin is no longer needed for the generator.
- `docs/PUBLISHING.md`: marketplace layout, release checklist, tagging,
  re-pinning companions, directory submission.

### Not added (deliberately)
- RTK: rewrites the evaluator's evidence commands; detected and warned only.
- Vendoring any companion: all MIT, all fast-moving; detection over forks.

### Merge note
- Built against 3.2.0 and merged onto 3.2.2: every 3.2.1/3.2.2 fix is kept.
  The v1.1 `.claude/` mirror copies the patch re-synced were removed in
  the repo cleanup after 3.2.1 and stay removed; `docs/PUBLISHING.md` no
  longer has a "resync mirrors" step.

## [3.2.2] — drop the v1.1 push script; two more bound phrasings

### Removed
- `scripts/github_push.sh` — the v1.1 one-time "create the GitHub repo" script.
  `init_asdr.py` copies every file in `scripts/` into each project's
  `.harness/scripts/`, so it was landing in every project that used the
  plugin. The repo exists; the script had no remaining purpose.

### Changed
- `preflight_contract.py` — `over <n>` and `above <n>` count as bounds
  (`over 300ms` now needs a `facts:` key). The lookahead requires a digit, so
  "over HTTPS on port 443" is untouched. One test added (23 total).
- `.gitignore` — reduced to `.harness/` + `sprints.json` (runtime state if
  `init_asdr.py` is ever run inside this repo) plus env/Python/OS noise; the
  v1.1 `.harness/contract.md` / `.gitkeep` entries referred to files that no
  longer exist here.
- Manifest, marketplace entry and all skills at 3.2.2.

## [3.2.1] — context-discipline fixes found by testing the v3.2 scripts

A test pass over the five v3.2 scripts (fake repo with git history, tests, a
contract, a sprint and an eval report; every check exercised on a true
positive and probed for false positives) found the two headline features
weaker than documented. No crashes; no change to agent roles, verdict formats
or state-file schemas. `tests/test_context_discipline.py` now covers all of it
(`python3 -m unittest discover tests`).

### Fixed — `build_graph.py` (blast radius)
- Imports that climb a directory (`../db/lead`) never resolved: the path was
  "normalised" with `.replace("./", "")`, turning `src/voice/../db/lead` into
  `src/voice/.db/lead`. Now `posixpath.normpath`. Every cross-module edge and
  every test-file→source edge was missing from the blast radius.
- Python imports never resolved (`from .utils import x`, `from pkg.utils import
  x`, `import pkg.utils`): only `./`-style specifiers were handled. Relative
  dots now climb directories; absolute dotted names are tried from the repo
  root and from each ancestor of the importer (`src/` layouts). Python
  projects previously produced a graph with zero edges.
- `facts:<key>` citations are stripped before file-path scanning, as the pack
  builder and the linter already did; a phantom `diff.src/...` file no longer
  appears in `file_to_criteria` / `file_to_requirements`.

### Fixed — `preflight_contract.py` (satisfiability linter)
- **P06** cost-metric words are word-bounded. "already" matched `read` and
  "called" matched `call`, so ordinary criteria were rejected as cost floors —
  costing exactly the negotiation round the linter exists to save.
- The comparator list gains `under`, `within`, `below`, `less than`, `more
  than`, `up to`, `no later than`, `not exceed`, `maximum of`, `minimum of`,
  `no fewer than`. The contract template's own GOOD example ("under 300ms")
  passed pre-flight with no fact key; the measurement rule is now enforced
  for those phrasings.
- **P01** no longer treats identifiers as measurements: `HTTP 404`, `status
  code 201`, `port 5432`, `error 500`, `v2.1` need no `facts.json` key.
- **P09** new-file budget counts source files only (`.md`, `.json` and URLs
  are not fixture-isolation risk) and URLs are stripped before any path scan.
- **P05** regex literals may not start after a path character, so
  `src/4/legacy.ts` is no longer read as the regex `/4/`.

### Fixed — `emit_facts.py` (measured facts)
- `diff.<file>.net_nonblank` measured the WHOLE FILE, not the change: a
  5-line edit to a 400-line file reported 400, so every "diff budget" was a
  file-size cap. It is now `added_nonblank − removed_nonblank` computed from
  `git diff -U0` hunks (the unit `CONTEXT_ARCHITECTURE.md`'s own example
  uses: 112 added, 8 removed, net 104). The whole-file count is kept as
  `file_nonblank`; `added_nonblank` / `removed_nonblank` are also emitted.
- Untracked new files are included (`git ls-files --others`), flagged
  `"untracked": true`. A generator's brand-new module was invisible to the
  diff until staged.
- `.harness/` bookkeeping (contracts, packs, facts.json itself) is skipped in
  the diff, as the census already skipped it.
- `--base` defaults to `sprint_base_ref` in `.harness/progress.json`, then
  `HEAD` with a note. The v3.2 generator commits its own work, after which a
  diff against `HEAD` is empty and every `facts:diff.*` citation dangles.
  `next_action.py`'s activate step, `init_asdr.py`, `templates/progress.json`
  and the `asdr` / `longhorizon` skills now carry `sprint_base_ref`.

### Changed
- `make_context_pack.py` recognises the new diff keys in citations.
- `.claude-plugin/marketplace.json` added: the repo is its own one-plugin
  marketplace (`asdr`), so Claude Code installs it with
  `claude plugin marketplace add Mbialuddinkhan/ai-software-delivery-room`
  + `claude plugin install ai-software-delivery-room@asdr`.
- README package contents list the v3.2 scripts, `CONTEXT_ARCHITECTURE.md`
  and the test file; manifest and all skills bumped to 3.2.1.

### Removed (repo hygiene, after the v3.2.1 tag)
- `.claude/` (14 v1.1 agents, 6 v1.1 slash commands, 1 v1.1 skill) and the
  root `.harness/` (v1.1 template copies, three of them stale) — not part of
  the plugin, and opening this repo in Claude Code loaded the v1.1 agents as
  project-level agents. The root `CLAUDE.md` (v1.1 charter for a *project*)
  is replaced by a charter for this *repository*: layout, change rules,
  release steps. Plugin content is unchanged; the version stays 3.2.1.

## [3.2.0] — context discipline: measured facts, contract pre-flight, context packs

Answers a field review of a real 7-sprint run in which 50 subagent runs consumed
more effective tokens than every directly-executed action combined, and the
largest constraint was environmental: agents were asked to measure things they
had no ability to measure.

### Added — Phase 0: measurement (nothing else works without this)
- **`scripts/emit_facts.py`** → `.harness/facts.json`, the single source of
  MEASURED truth: per-file diff (`added`/`removed`/**`net_nonblank`**), file
  census, per-file assertion counts, test results, commit. Runs where a shell
  exists (CI or an operator terminal). Degrades gracefully — missing git, tests
  or coverage yields a null section and a note, never a crash.
- **Measurement rule, enforced:** *no numeric criterion may be graded except by
  citing a key in `facts.json`* — written `facts:<dotted.key>`. This
  mechanically kills the "generator transcribes `git diff --stat`" criterion
  class, which grades the environment rather than the code.
- **Diff budgets now count non-blank, non-comment lines.** Raw diff lines count
  the documentation the method itself mandates (observed: 221/67/32/9/44 →
  112/28/9/1/25).

### Added — Phase 1: contract satisfiability
- **`scripts/preflight_contract.py`** — runs BEFORE the evaluator sees a draft.
  `validate_contract.py` checks shape; this checks whether a correct
  implementation could satisfy the contract at all. Ten checks, every one a
  violation class observed in the field: unmeasurable numbers (P01), unresolved
  `file:line` (P02), zero-delta over a file the same criterion edits (P03),
  self-report of command output (P04), a regex forbidding a literal another
  criterion requires (P05), a floor on a cost metric a better build would fail
  (P06), absolute clock vs clamped fixture (P07), >7 criteria naming one
  integration file (P08), new-file budget (P09), undefined derivation (P10).
  Unsatisfiable first drafts were costing a full negotiation round each.

### Added — Phase 2: the knowledge/dependency graph and context packs
- **`scripts/build_graph.py`** — extends `.harness/traceability.json` with a
  `graph` section: modules, imports, **dependents (blast radius)**,
  file→criteria, file→requirements, and **fixture_risk** (global-unique keys,
  contended keys, FK-ordered deletes, `afterAll` cleanup, absolute counts).
  A script cannot hallucinate an edge; an agent can.
- **`scripts/build_digest.py`** → `.harness/state-digest.md`, one page of
  authoritative state derived from state files — replaces re-reading a stack of
  eval reports. Machine-generated, so a wrong digest is a findable bug rather
  than a silent hallucination copied into every brief.
- **`scripts/make_context_pack.py`** → `.harness/packs/pack-<sprint>-<role>.md`:
  files in scope, blast radius, requirements served, fixture risks, the relevant
  facts slice and the last verdict — **paths and fact keys, never file
  contents**. **Exits 1 when the pack exceeds its budget**, which converts
  context overflow from a silent mid-task failure into a cheap planning-time
  signal: the task is too big, split it — never raise the budget.

### Changed
- `agents/generator.md` — reads its context pack first as task scope; numeric
  criteria must cite `facts:`; runs both validators before handoff; never
  derives a number by reading files; **commits its own work before stopping**
  (uncommitted output from an exhausted agent was the most expensive observed
  failure mode).
- `agents/evaluator.md` — reads pack + facts; grades numeric criteria from the
  cited fact key and never re-derives; a numeric criterion with no fact key is
  ungradeable (contract defect, not an estimate); runs `preflight_contract.py`
  at ratification, ERRORs are automatic `revision-requested`.
- `agents/stage-qa.md` — pack-aware; numeric checks from `facts.json` only.
- `skills/asdr`, `skills/longhorizon` — new **Context discipline** section:
  `emit_facts` → `build_graph` → `build_digest` → `make_context_pack` before any
  dispatch; pre-flight feedback to the generator before the evaluator is invoked.
- `templates/contract.md` — the measurement rule at the point of authoring.
- `scripts/init_asdr.py` — seeds `.harness/packs/` and prints the context-discipline
  sequence.

### Deliberately not built
A central "development manager" agent that holds the knowledge graph. Subagents
share no context, so the manager's knowledge must be serialised into every
prompt anyway (no saving); it adds a coordination hop; it becomes the broadest,
most-called agent in the system; and it centralises hallucination — today two
roles derive independently and disagree, which is exactly the check that caught
a cap wrong by 60. The graph is therefore a **file a script maintains**, not an
agent that remembers. A thin dispatcher role remains a candidate for a later
version, once the measured effect of Phases 0–2 is known.

## [3.1.0] — product integrity, richer discovery, git workflow, live E2E

Attacks feature drift: keeps the built product provably in sync with the
vision, roadmap, brief, business case, use cases, and requirements.

### Added — product-integrity QA
- **`agents/product-integrity-qa.md`** — independent product-level QA (opus).
  Runs after discovery (seed), after each sprint (update + drift check), and at
  the final gate (full verification). Emits an `in-sync | drifted | broken |
  incomplete` integrity verdict the risk-manager honors.
- **Living traceability matrix** — `.harness/traceability.json` (seeded by
  `init_asdr.py`) + readable mirror `docs/traceability.md`, mapping outcome →
  requirement → use case → sprint → criteria → tests → status.
- **`scripts/validate_traceability.py`** — mechanically flags uncovered
  requirements (at the gate), orphan sprints, uncovered use cases, `broken`
  rows, and **drift** (a requirement's text changed after a sprint built to it,
  detected via a stored hash). `--gate` and `--requirements` modes.
- **`scripts/validate_verdict.py`** — extended with `--type integrity`.
- **Drift handling**: on drift, the run STOPS and surfaces the exact
  requirement(s); only on your approval do product-owner + business-analyst
  update every affected strategic doc, then the matrix is re-baselined.

### Added — cross-sprint regression + live E2E
- The **evaluator** now re-runs the ENTIRE accumulated test suite each sprint
  (including the Cypress/E2E suite); a previously-passing test that now fails
  blocks the sprint. The full suite runs again at the release gate.
- **`templates/e2e-testing.md`** + devops scaffolding: **Cypress** with
  `video: true` and screenshots so you can watch the tests run
  (`cypress open` / `run --headed` locally, headless with artifacts in CI).

### Added — richer discovery (first-class, traceable)
- **`templates/roadmap.md`** (`docs/00b-roadmap.md`, product-owner),
  **`templates/business-case.md`** (`docs/01b-business-case.md`, product-owner),
  **`templates/use-cases.md`** (`docs/02b-use-cases.md`, business-analyst).
  Kept in sync on approved scope changes.

### Added — git & repository workflow
- **`templates/git-workflow.md`** (`docs/07-git-workflow.md`, devops):
  branching strategy, Conventional Commits, per-sprint PR + required checks,
  what-to-commit, branch protection, SemVer tagging.

### Changed
- `agents/{product-owner,business-analyst,evaluator,risk-manager,devops}.md`,
  `skills/{discover,architect,asdr,riskgate}` wired to the above.
- `scripts/init_asdr.py` seeds `.harness/traceability.json`.

## [3.0.0] — universal triad with a rigor dial

Adds independent per-stage review: every authoring stage runs as
stage-planner → specialist executor → stage-qa, so no agent signs off its own
work. See `TRIAD_ARCHITECTURE.md`.

### Added
- **`agents/stage-planner.md`** — generic per-stage planner (opus): turns a
  stage's goal, inputs, and template into an observable acceptance checklist.
- **`agents/stage-qa.md`** — generic independent reviewer (opus): grades the
  artifact against the plan, returns `pass` or `revise` with evidence; never
  grades its own work.
- **`scripts/stage_status.py`** — per-stage driver: reads state from disk and
  prints the next action (PLAN / EXECUTE / QA / FORCE-ACCEPT / DONE), with a
  capped revise loop so a stage cannot stall. Supports `--no-plan` (light mode).
- **`templates/plan.md`, `templates/qa-report.md`** — the triad artifacts.
- **`scripts/validate_verdict.py`** — extended with `--type qa` (pass|revise).
- **Rigor dial** in `.harness/progress.json` → `rigor`: `paranoid` (full triad
  everywhere), `standard` (full triad on high-stakes stages, light elsewhere),
  `lite` (no per-stage triad — identical to v2.1). `scripts/init_asdr.py` seeds
  it and the new `.harness/plans` and `.harness/qa-reports` directories.

### Changed
- The `asdr`, `discover`, `architect`, `riskgate`, and `release` skills now
  drive each authoring stage through the triad protocol per the rigor dial.
  The cross-document critic and the judge are kept in every mode; gate roles
  (critic, judge, risk-manager) are not wrapped in a triad — they are the
  independent review, terminated by their mechanical validators.

### Compatibility
`lite` reproduces v2.1 exactly; upgrading changes nothing until you turn the
dial up. Every new loop is bounded by the same on-disk circuit-breaker pattern
as the sprint loop.

## [2.1.0] — quality uplift, Opus 4.8 tuning, and reliability fixes

### Fixed (reliability)
- **Circuit breakers no longer depend on the model remembering to increment
  counters.** `scripts/next_action.py` now derives the per-sprint `attempt`
  count from eval-report files on disk and the `negotiation_rounds` count from
  `generator negotiate-<sprint>` lines in the trace log, combining each with
  the `progress.json` ledger via `max()`. The "too many attempts → split" and
  "too many rounds → force-ratify" safeguards can no longer be silently
  disabled by a missed manual increment. Covered by 11 state-transition tests.
- **`scripts/validate_contract.py`** — corrected the "7 x 3 = 21" comment; the
  category minimums sum to 20. No behavior change.
- **`templates/contract.md`** — the done-definition's "no console/runtime
  errors" is scoped to "the surfaces this sprint touches," so it is testable
  on back-end sprints.

### Added (rigor)
- **`scripts/validate_verdict.py`** — validates the judge decision, evaluator
  eval report, and risk-manager risk review fenced blocks
  (`--type decision|eval|risk`): required fields present, headline value is a
  real enum value (not the template's "a | b | c"), no surviving placeholders.
- **`scripts/validate_critique.py`** — enforces critique structure, that
  `findings_total` matches the actual finding count, that severity counts sum
  correctly, and the ≥8-findings floor with a `shortfall_justified` escape
  hatch for genuinely small doc sets.
- Both validators are wired into the `discover`, `architect`, `riskgate`, and
  `asdr` skills at the points where the orchestrator reads those blocks.

### Changed (quality & Opus 4.8 tuning)
- **All 14 agents** gained a shared Operating Standard: reason before
  committing a binding decision, read inputs in parallel, quantify or cite
  every quality claim, and self-verify against the template and role invariant
  before stopping.
- **Model routing:** the adversarial and architecture gates (evaluator,
  critic, judge, risk-manager, solution-architect, ai-architect,
  security-compliance) are pinned to `opus`; builders and writers stay
  `inherit`.
- **Per-agent specifics:** evaluator writes each criterion's cheapest
  fake-PASS then defeats it; critic treats 8 findings as a floor not a target;
  judge self-checks its verdict block against its findings; generator
  self-reviews the diff against the contract before handoff; planner
  self-checks each sprint; product-owner requires quantified success metrics;
  business-analyst adds a closing traceability check; solution-architect
  reasons through key trade-offs and records rejected ADR options; ai-architect
  adds concrete examples and a least-privilege self-check; security-compliance
  gains a design-vs-release path map pinning `docs/09-security-review-final.md`;
  risk-manager adds a test floor, parallel reads, and block self-consistency;
  release-manager pins the security-review filename and cross-checks the
  CHANGELOG against sprints.json; documentation runs a final README walkthrough.
- **`templates/contract.md`** — added "writing good criteria" guidance
  (quantify or cite; write the cheapest cheat then defeat it) with BAD/GOOD
  examples.
- **`templates/critique.md`** — added the `shortfall_justified` field.

### Changed (fewer false stops)
- **`scripts/validate_sprints.py`** — the technical-term denylist is now
  high-precision: removed the documented false-positive words (queue, cache,
  python), added missing real tech (supabase, prisma, kafka), and fixed the
  sentence counter so version strings like "v2.0" aren't miscounted.
- **`skills/architect` and `skills/asdr`** — AI-feature detection now judges by
  meaning, not a literal keyword grep, so features like "semantic search" or
  "smart recommendations" correctly pull in the AI architect; a genuine
  no-AI finding must be stated, not skipped silently.

### Compatibility
Drop-in. No paths, category names, verdict-block formats, validator contracts,
or state-file schemas changed. A project mid-run stays valid after the swap.
