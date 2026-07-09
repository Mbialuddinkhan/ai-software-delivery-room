---
name: riskgate
description: >
  Use this skill when the user wants to run the final risk gate before releasing software —
  checking security, tests, deployment readiness, and classifying the release. Must be run
  before the release skill. Trigger phrases: "risk gate", "riskgate", "classify my release",
  "is this ready to ship", "final review", "pre-release check", "run risk assessment".
metadata:
  version: "3.0.0"
---

# Risk Gate — Pre-Release Classification Orchestrator

## Prerequisites check (mechanical — verify each, print what's missing)

- `sprints.json` exists and every sprint has status `done`
  (`torn-down` sprints must have `done` replacements covering their goal)
- `.harness/eval-reports/` contains, for every sprint, a report whose
  verdict block says `verdict: pass`
- `docs/01-product-brief.md`, `docs/02-requirements.md`,
  `docs/03-architecture.md` exist
- Tests exist in the repo (look in `.harness/tests/` and the project's
  test directory)

If anything is missing, print the blocklist and stop — classifying an
unfinished build would only produce a false answer.

Subagents share none of your context: every invocation prompt must contain
input paths, output path, and template path.

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

| Stage id | Executor agent | Artifact path | Tier |
|---|---|---|---|
| `security-final` | security-compliance | docs/09-security-review-final.md | high |
| `devops-readiness` | devops | docs/09-devops-readiness.md | high |

The **risk-manager** stays a gate, not a triad stage — it is already validated
with `validate_verdict.py --type risk`.

## Phase 1 — Security final review

Invoke **security-compliance** with: input the codebase, output
`docs/09-security-review-final.md`, template
`.harness/templates/security.md`. Context: release gate — verify the code,
not the docs. Check at minimum: no hardcoded secrets, auth on all
protected routes, input validation, prompt-injection controls if AI
features exist, audit logs for sensitive actions, no known critical CVEs
in dependencies. Evidence as file:line or command output. Run this stage via
the Stage execution protocol (executor: security-compliance, stage-id:
security-final, artifact: docs/09-security-review-final.md).

## Phase 2 — DevOps readiness

Invoke **devops** with: input the codebase, output
`docs/09-devops-readiness.md`, template `.harness/templates/devops.md`.
Context: release gate — actually run `docker build`, validate compose,
diff `.env.example` against the variables the code reads, confirm CI
workflow and rollback plan exist. Paste command output as evidence. Run this
stage via the Stage execution protocol (executor: devops, stage-id:
devops-readiness, artifact: docs/09-devops-readiness.md).

## Phase 3 — Risk classification

Invoke **risk-manager** with: inputs both 09-docs, the eval reports
directory, and `sprints.json`; output `docs/09-risk-review.md`.

Validate the machine-readable block first: run
`python3 .harness/scripts/validate_verdict.py docs/09-risk-review.md
--type risk`. If it errors, re-invoke the risk-manager to fix the block,
then read the fenced classification block at the end
(`classification: production-ready | mvp-ready | prototype | not-ready`).

## Phase 4 — Output

Print:

1. The classification
2. Blockers (from the block's `blockers` list)
3. Warnings (non-blocking)
4. Next step: `production-ready` or `mvp-ready` → run the `release`
   skill; otherwise → the blocker list is the work queue, fix and rerun
   this skill.

Do not deploy. Do not package. This skill only classifies — mixing the
gate with the release would let the gate approve its own work.
