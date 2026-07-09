---
name: asdr
description: >
  Use this skill when the user wants to build software from scratch, run the full
  AI Software Delivery Room workflow, turn a rough idea into production-grade software,
  create an app, SaaS, dashboard, API, MVP, or automation product, or set up a complete
  multi-agent SDLC. Trigger phrases: "build me", "I want to create", "let's build",
  "full ASDR", "start a new software project", "run the delivery room".
metadata:
  version: "3.1.0"
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

### Resume protocol

If `.harness/progress.json` already exists with phase ≠ `strategic` or a
non-null sprint, this is a resumed run: tell the user where the project
stands (phase, sprint, attempt), run `next_action.py`, and continue from
there. Never restart phases that already produced approved documents.

## Canonical file map

Use these exact paths everywhere. Agents receive their output path from you
— never let an agent choose its own.

| # | Document | Path | Agent | Template |
|---|---|---|---|---|
| 1 | Product brief | `docs/01-product-brief.md` | product-owner | product-brief.md |
| 1b | Business case | `docs/01b-business-case.md` | product-owner | business-case.md |
| 0b | Roadmap | `docs/00b-roadmap.md` | product-owner | roadmap.md |
| 2 | Requirements | `docs/02-requirements.md` | business-analyst | requirements.md |
| 2b | Use cases | `docs/02b-use-cases.md` | business-analyst | use-cases.md |
| 3 | Discovery critique | `docs/critique-discovery.md` | critic | critique.md |
| 4 | Discovery decision | `docs/decision-discovery.md` | judge | decision.md |
| 5 | Architecture | `docs/03-architecture.md` | solution-architect | architecture.md |
| 6 | Agent design (AI only) | `docs/04-agent-design.md` | ai-architect | agent-design.md |
| 7 | Security | `docs/05-security.md` | security-compliance | security.md |
| 8 | DevOps | `docs/06-devops.md` | devops | devops.md |
| 9 | Architecture critique | `docs/critique-architecture.md` | critic | critique.md |
| 10 | Architecture decision | `docs/decision-architecture.md` | judge | decision.md |
| 11 | Blueprint digest | `docs/00-blueprint-summary.md` | you | blueprint-summary.md |
| 12 | E2E testing plan | `docs/08-e2e-testing.md` | devops | e2e-testing.md |
| 13 | Traceability matrix | `docs/traceability.md` (+ `.harness/traceability.json`) | product-integrity-qa | traceability.md |
| 14 | Product integrity (gate) | `docs/09-product-integrity.md` | product-integrity-qa | integrity-report.md |

Per-sprint integrity snapshots land at `docs/integrity-<sprint>.md`.
Templates live in `.harness/templates/`.

## Validators

Three machine checks catch a bad document before it corrupts the run. Use
them at the steps below; feed any `ERROR:` lines straight back to the agent
that produced the file.

- `validate_critique.py <critique.md>` — structure, self-consistent counts,
  and the ≥8-findings floor (unless the critic set `shortfall_justified`).
- `validate_verdict.py <decision-or-risk.md> --type decision|risk` — the
  fenced verdict block has the required fields and a real (non-placeholder)
  headline value.
- `validate_contract.py` and `validate_sprints.py` run in later phases as
  before.

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
| `business-case` | product-owner | docs/01b-business-case.md | high |
| `roadmap` | product-owner | docs/00b-roadmap.md | med |
| `requirements` | business-analyst | docs/02-requirements.md | high |
| `use-cases` | business-analyst | docs/02b-use-cases.md | high |
| `architecture` | solution-architect | docs/03-architecture.md | high |
| `agent-design` | ai-architect | docs/04-agent-design.md | high (AI only) |
| `security-design` | security-compliance | docs/05-security.md | high |
| `devops-design` | devops | docs/06-devops.md | high |
| `security-final` | security-compliance | docs/09-security-review-final.md | high |
| `devops-readiness` | devops | docs/09-devops-readiness.md | high |
| `documentation` | documentation | six-doc set | low (`--no-plan` under standard) |

Phase 1 authoring stages are `product-brief`, `requirements`, `architecture`,
`agent-design`, `security-design`, `devops-design`. Phase 4 gate-authoring
stages are `security-final`, `devops-readiness`, `documentation`.

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
3. **critic** — pass rows 1–2 as inputs + row 3 paths. Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-discovery.md`;
   if it errors, re-invoke the critic with those lines (max 2 rounds).
4. **judge** — pass rows 1–3 as inputs + row 4 paths.
   Run `python3 .harness/scripts/validate_verdict.py docs/decision-discovery.md
   --type decision`; if it errors, re-invoke the judge to fix the block.
   Then read the fenced verdict block at the end of the decision doc:
   - `verdict: no-go` → stop; print the reasons and required changes.
   - `required_changes` non-empty → re-invoke the responsible agent with
     exactly those changes, then re-invoke judge. Max 2 repair rounds, then
     stop and ask the user.
5. **solution-architect** — inputs rows 1–2 + row 5 paths. Run this stage via
   the Stage execution protocol (executor: solution-architect, stage-id:
   architecture, artifact: docs/03-architecture.md).
6. **ai-architect** — invoke only if `docs/02-requirements.md` describes any
   AI/LLM/agent/RAG/ML capability, judged by meaning not keywords (e.g.
   "semantic search", "smart recommendations", "summarization", "chat
   assistant" all count); inputs rows 2 and 5 + row 6 paths. If none, skip
   and note you evaluated and found no AI surface. When invoked, run this
   stage via the Stage execution protocol (executor: ai-architect, stage-id:
   agent-design, artifact: docs/04-agent-design.md).
7. **security-compliance** — inputs rows 5–6 + row 7 paths. Run this stage via
   the Stage execution protocol (executor: security-compliance, stage-id:
   security-design, artifact: docs/05-security.md).
8. **devops** — inputs rows 5 and 7 + row 8 paths. Run this stage via the
   Stage execution protocol (executor: devops, stage-id: devops-design,
   artifact: docs/06-devops.md).
9. **critic** — inputs rows 5–8 + row 9 paths. Then run
   `python3 .harness/scripts/validate_critique.py docs/critique-architecture.md`;
   if it errors, re-invoke the critic (max 2 rounds).
10. **judge** — inputs rows 5–9 + row 10 paths. Run
    `python3 .harness/scripts/validate_verdict.py docs/decision-architecture.md
    --type decision` first; then same verdict handling as step 4.

After the blueprint is approved:

11. **You** write `docs/00-blueprint-summary.md` from the template — one
    page max. This digest is what the generator and evaluator read every
    sprint; the full docs stay available for lookups.
12. Update the "Project facts" section of `CLAUDE.md` (stack, run/test/lint
    commands, conventions) from the approved architecture.
13. Invoke **product-integrity-qa** in SEED mode to build the traceability
    matrix (`.harness/traceability.json` + `docs/traceability.md`) from the
    strategic docs (brief, business case, roadmap, requirements, use cases),
    then run `python3 .harness/scripts/validate_traceability.py
    .harness/traceability.json --sprints sprints.json`.
14. Log: `python3 .harness/scripts/trace.py orchestrator blueprint-approved "phase 1 done"`

### User checkpoint

Show the user a 5-bullet blueprint summary and ask whether to proceed to
the build. Building runs long and compounds on these decisions — this is
the cheapest moment to correct course. If the user already told you to run
end-to-end without stopping, note that and continue.

## Phase 2 — Sprint planning

1. Set `.harness/progress.json` phase to `planning`.
2. Invoke **planner** with: the user's idea verbatim + the path
   `docs/00-blueprint-summary.md` + instruction to write `sprints.json`.
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

The script encodes the rules — contract before build, evaluator-only
ratification, max 4 negotiation rounds then force-ratify, attempt > 5
forces a planner split, two teardowns stops for the human. It now derives
the attempt and negotiation counters from artifacts on disk as well as from
`progress.json`, so a missed manual increment can no longer disable a
circuit breaker. Do not improvise around it: if you think the state is
wrong, fix the state files, rerun the script, and follow it.

State field reference:

- `sprints.json` status: `pending | active | done | torn-down`
- Contract status: `in-negotiation | revision-requested | ratified`
- `progress.json` awaiting: `null | negotiate | ratify | build | evaluate`

## Phase 4 — Final gates

When `next_action.py` says `final-gates`, set phase to `final-gates`, then:

1. **security-compliance** — inputs: the codebase; output
   `docs/09-security-review-final.md`; template security.md. Tell it this
   is the release gate: verify code, not docs. Run this stage via the Stage
   execution protocol (executor: security-compliance, stage-id:
   security-final, artifact: docs/09-security-review-final.md).
2. **devops** — output `docs/09-devops-readiness.md`; template devops.md;
   release-gate context: run the builds, paste evidence. Run this stage via
   the Stage execution protocol (executor: devops, stage-id: devops-readiness,
   artifact: docs/09-devops-readiness.md).
3. **documentation** — the six-doc default set. Run this stage via the Stage
   execution protocol (executor: documentation, stage-id: documentation,
   artifact: the six-doc set; low tier — use `--no-plan` under standard).
4. **product-integrity-qa** — GATE mode: run the full regression (all sprints)
   and emit the integrity verdict to `docs/09-product-integrity.md` (template
   integrity-report.md). Then run `python3 .harness/scripts/validate_verdict.py
   docs/09-product-integrity.md --type integrity`; if it errors, re-invoke to
   fix the block. A `broken` or `drifted` integrity verdict is a release
   blocker.
5. **risk-manager** — inputs: both 09-docs, `docs/09-product-integrity.md`,
   eval reports, sprints.json; output `docs/09-risk-review.md`. Then run
   `python3 .harness/scripts/validate_verdict.py docs/09-risk-review.md
   --type risk`; if it errors, re-invoke the risk-manager to fix the block.
6. Read the risk-manager's fenced classification block. Only if
   `mvp-ready` or `production-ready`: invoke **release-manager**.
   Otherwise skip packaging and report the blockers.

## Phase 5 — Final response

Set phase to `done`. Print:

1. What was built
2. Sprint status table (from `sprints.json`)
3. Final risk classification (from the classification block)
4. How to run locally, test, deploy (from `CLAUDE.md` / docs)
5. Known limitations
6. Next recommended steps

Never claim production-ready unless the risk-manager's block says
`production-ready` — that word is its authority alone.
