---
name: release
description: >
  Use this skill when the user wants to package and prepare the final release — changelog,
  release notes, deployment checklist, and post-release monitoring plan. Requires riskgate
  to have passed first. Trigger phrases: "release", "package the release", "prepare release",
  "release notes", "create changelog", "final release".
metadata:
  version: "3.4.0"
---

# Release — Release Packaging Orchestrator

## Prerequisite (mechanical)

Read `docs/09-risk-review.md` and its fenced classification block. Proceed
only if `classification` is `mvp-ready` or `production-ready`. Otherwise
stop and direct the user to run the `riskgate` skill — packaging bypassing
the gate would defeat the gate.

Subagents share none of your context: pass explicit paths in every
invocation.

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
| `documentation` | documentation | six-doc set | low (`--no-plan` under standard) |
| `release-packaging` | release-manager | changelog + notes + checklist | low (`--no-plan` under standard) |

## Phase 1 — Documentation

Invoke **documentation** with the default six-doc set and instruction to
verify every command against the actual code:

- `README.md`, `docs/user-guide.md`, `docs/admin-guide.md`,
  `docs/api-reference.md` (if an API exists), `docs/troubleshooting.md`,
  `docs/handover.md`

For a product with a UI, the documentation agent also writes
`docs/manuals/manual.json`: explanations for every manual-tour screenshot and
the manuals to build — Getting started + Advanced per persona, and Beginner,
Everyday user, Power user and Administrator. Refresh the screenshots first so
they come from this commit: `python3 .harness/scripts/run_tests.py --tours`.

Run this stage via the Stage execution protocol (executor: documentation,
stage-id: documentation, artifact: the six-doc set + manual.json; low tier —
use `--no-plan` under standard).

## Phase 2 — Release packaging

Invoke **release-manager** with: inputs `sprints.json`,
`.harness/eval-reports/`, `docs/09-risk-review.md`; outputs
`CHANGELOG.md`, `docs/10-release-notes.md`, `docs/10-release-checklist.md`,
`docs/10-post-release-monitoring.md`, the release test report
(`docs/test-reports/v<version>/`) and the user manuals
(`docs/manuals/<version>/`, HTML + PDF for every persona and tier). It runs
the tests on the release commit, the product-map gate, the report and the
manual build itself (see its agent file).

When it finishes, publish the two single-file pages it prints — the test
report and `.harness/manual-artifact.html` — as private Artifacts (titles
"<Product> Test Report" and "<Product> User Manuals"; update the same two
artifacts every release so the links stay stable), and give the user both
links.

The checklist must tick only what was actually verified (its agent file
defines the required items).

Run this stage via the Stage execution protocol (executor: release-manager,
stage-id: release-packaging, artifact: changelog + release notes + checklist;
low tier — use `--no-plan` under standard).

## Phase 3 — Final output

Print:

1. Version tag recommendation (e.g. `v0.1.0-mvp` — match the risk classification)
2. What was built (sprint summary table)
3. How to deploy (2–3 key commands)
4. How to roll back
5. Where to find the user manuals (each persona and tier, HTML + PDF) and
   the test report, with links
6. Known limitations
7. Post-release monitoring steps
8. Next roadmap recommendations

This is the final step. The human deploys manually — automated deployment
is outside this system's authority.
