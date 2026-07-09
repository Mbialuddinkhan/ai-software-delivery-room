---
name: architect
description: >
  Use this skill when the user wants to design the technical architecture for a software project —
  system design, database model, API design, security architecture, and DevOps plan. Requires
  discovery docs to already exist. Trigger phrases: "architect", "design the architecture",
  "system design", "technical blueprint", "design the system", "create architecture docs".
metadata:
  version: "3.1.0"
---

# Architect — Architecture Orchestrator

Prerequisite: `docs/01-product-brief.md` and `docs/02-requirements.md`
must exist. If either is missing, stop and tell the user to run the
`discover` skill first.

If `.harness/templates/` is missing, resolve PLUGIN_ROOT (two levels above
this skill's base directory) and run
`python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`.

Subagents share none of your context: every invocation prompt must contain
the input paths, the output path, and the template path.

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
| `architecture` | solution-architect | docs/03-architecture.md | high |
| `agent-design` | ai-architect | docs/04-agent-design.md | high (AI only) |
| `security-design` | security-compliance | docs/05-security.md | high |
| `devops-design` | devops | docs/06-devops.md | high |

## Phase 1 — Solution architecture

Invoke **solution-architect** with: inputs `docs/01-product-brief.md` and
`docs/02-requirements.md`, output `docs/03-architecture.md`, template
`.harness/templates/architecture.md`. Run this stage via the Stage execution
protocol (executor: solution-architect, stage-id: architecture, artifact:
docs/03-architecture.md).

## Phase 2 — AI / agent architecture (conditional)

Read `docs/02-requirements.md` and decide, by meaning rather than keywords,
whether the product has any AI / LLM / agent / RAG / ML capability. Features
such as "semantic search", "smart recommendations", "summarization",
"natural-language input", "a chat assistant", or "personalization driven by a
model" all count even when the letters "AI" never appear. Only if such a
capability exists, invoke **ai-architect** with: inputs
`docs/02-requirements.md` and `docs/03-architecture.md`, output
`docs/04-agent-design.md`, template `.harness/templates/agent-design.md`. When
invoked, run this stage via the Stage execution protocol (executor:
ai-architect, stage-id: agent-design, artifact: docs/04-agent-design.md). If
there is genuinely no AI surface, skip this phase and note that you evaluated
the requirements and found none — do not skip silently.

## Phase 3 — Security architecture

Invoke **security-compliance** with: inputs `docs/03-architecture.md` (and
`docs/04-agent-design.md` if it exists), output `docs/05-security.md`,
template `.harness/templates/security.md`. Context: architecture phase —
threat-model the design. Run this stage via the Stage execution protocol
(executor: security-compliance, stage-id: security-design, artifact:
docs/05-security.md).

## Phase 4 — DevOps architecture

Invoke **devops** with: inputs `docs/03-architecture.md` and
`docs/05-security.md`, output `docs/06-devops.md`, template
`.harness/templates/devops.md`. Context: architecture phase — also create
`Dockerfile`, `docker-compose.yml`, `.env.example`,
`.github/workflows/ci.yml`, and the **git & repository workflow** at
`docs/07-git-workflow.md` (from `.harness/templates/git-workflow.md`) —
branching, commit/PR conventions, what-to-commit, branch protection, and
SemVer tagging — copying its "Conventions the build loop follows" block into
`CLAUDE.md`. DevOps ALSO produces the live E2E testing plan
`docs/08-e2e-testing.md` (from `.harness/templates/e2e-testing.md`) and, for
web-UI products, scaffolds the Cypress config plus a sample spec
(`cypress.config.js`, `cypress/e2e/`, with video and screenshots on) so runs
are watchable. Run this stage via the Stage execution protocol
(executor: devops, stage-id: devops-design, artifact: docs/06-devops.md).

## Phase 5 — Critique

Invoke **critic** with: inputs all docs from phases 1–4 plus
`docs/02-requirements.md`, output `docs/critique-architecture.md`,
template `.harness/templates/critique.md`. Remind it: minimum 8 findings;
hunt especially for contradictions between architecture and requirements.

Then run `python3 .harness/scripts/validate_critique.py
docs/critique-architecture.md`. If it prints ERROR lines, re-invoke the
critic with exactly those lines (max 2 rounds), then continue.

## Phase 6 — Judge

Invoke **judge** with: inputs all architecture docs plus the critique,
output `docs/decision-architecture.md`, template
`.harness/templates/decision.md`.

Validate the machine-readable block before trusting it: run
`python3 .harness/scripts/validate_verdict.py docs/decision-architecture.md
--type decision`. If it errors, re-invoke the judge to fix the block, then
read it:

- `verdict: no-go` → stop; print reasons and required changes.
- `required_changes` non-empty → re-invoke the responsible agent with
  exactly those changes, then re-invoke the judge. Max 2 repair rounds,
  then stop and ask the user.

## Phase 7 — Blueprint digest and summary

After a `go` verdict:

1. Write `docs/00-blueprint-summary.md` from
   `.harness/templates/blueprint-summary.md` — one page max. The build
   harness reads this page every sprint instead of the full docs.
2. Update the "Project facts" section of `CLAUDE.md` (stack, commands,
   conventions) if `CLAUDE.md` exists.
3. Print: approved decisions, agent-design summary (if applicable),
   critical security findings, DevOps readiness, open questions, and the
   recommended next step — run the `asdr` or `longhorizon` skill.
