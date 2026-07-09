---
name: discover
description: >
  Use this skill when the user wants to run the discovery and planning phase for a software idea —
  product brief, requirements, user stories, and acceptance criteria — before moving to architecture
  or coding. Trigger phrases: "discover", "product discovery", "define requirements",
  "write a product brief", "plan my software", "what should I build", "let's scope this out".
metadata:
  version: "3.0.0"
---

# Discover — Strategic Discovery Orchestrator

Ask the user for their software idea if not provided.

Subagents share none of your context: every invocation prompt must contain
the input paths to read, the output path, and the template path.

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
| `product-brief` | product-owner | docs/01-product-brief.md | high |
| `requirements` | business-analyst | docs/02-requirements.md | high |

## Phase 1 — Initialize

1. Resolve PLUGIN_ROOT (two levels above this skill's base directory).
2. Run `python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`
   (idempotent; safe if the project is already initialized).
3. Fallback: create `docs/` and `.harness/templates/`, copy the plugin's
   templates in.

## Phase 2 — Product discovery

Invoke **product-owner** with: the user's idea verbatim, output
`docs/01-product-brief.md`, template
`.harness/templates/product-brief.md`. Run this stage via the Stage execution
protocol (executor: product-owner, stage-id: product-brief, artifact:
docs/01-product-brief.md).

## Phase 3 — Requirements engineering

Invoke **business-analyst** with: input `docs/01-product-brief.md`, output
`docs/02-requirements.md`, template `.harness/templates/requirements.md`. Run
this stage via the Stage execution protocol (executor: business-analyst,
stage-id: requirements, artifact: docs/02-requirements.md).

## Phase 4 — Critique

Invoke **critic** with: inputs `docs/01-product-brief.md` and
`docs/02-requirements.md`, output `docs/critique-discovery.md`, template
`.harness/templates/critique.md`. Remind it: minimum 8 findings, each with
severity, quoted evidence, and a required fix.

Then run `python3 .harness/scripts/validate_critique.py
docs/critique-discovery.md`. If it prints ERROR lines, re-invoke the critic
with exactly those lines (max 2 rounds), then continue.

## Phase 5 — Judge

Invoke **judge** with: inputs both docs plus the critique, output
`docs/decision-discovery.md`, template `.harness/templates/decision.md`.

Validate the machine-readable block first: run
`python3 .harness/scripts/validate_verdict.py docs/decision-discovery.md
--type decision`. If it errors, re-invoke the judge to fix the block, then
read the fenced verdict block at the end of the decision doc:

- `verdict: no-go` → stop; print reasons and required changes.
- `required_changes` non-empty → re-invoke the responsible agent
  (product-owner or business-analyst) with exactly those changes, then
  re-invoke the judge. Max 2 repair rounds, then stop and ask the user.
- `verdict: go` with no changes → proceed to summary.

## Phase 6 — Output summary

Print:

1. Product brief summary (3–5 bullets)
2. Requirements counts (functional, non-functional, user stories)
3. Critical issues found and how they were resolved
4. Open questions remaining
5. Recommended next step: run the `architect` skill

Do not proceed to architecture automatically. Discovery output is exactly
what the user should correct while corrections are still cheap — wait for
their review.
