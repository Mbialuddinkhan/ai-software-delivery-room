# Changelog

All notable changes to the AI Software Delivery Room in this improvement pass.
Baseline is the shipped plugin at v2.0.0.

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
