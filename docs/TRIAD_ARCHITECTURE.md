# ASDR v3 — the universal triad (with a rigor dial)

## The idea

Every stage of the delivery room runs as an independent triad:

```
stage-planner  ->  specialist executor  ->  stage-qa
 (sets the bar)     (does the work)         (grades it — a DIFFERENT agent)
```

No agent is the authority on its own work. The planner writes an acceptance
checklist, the specialist produces the artifact, and a separate QA agent grades
the artifact against that checklist and returns `pass` or `revise`. This is the
generator↔evaluator discipline from the sprint loop, generalized to every stage.

The self-check each executor already does is kept — but only as a cheap
pre-filter (catch placeholders and missing sections before wasting the QA's
time). The QA is the authority.

## The rigor dial

Running a full triad on *every* stage triples agent calls. Most of that pays
off on high-stakes, compounding stages; little of it pays off on trivial ones
(release notes). So intensity is configurable in `.harness/progress.json`:

| `rigor` | What runs per stage |
|---|---|
| `paranoid` | Full triad (plan → execute → QA) on **every** stage. |
| `standard` (default) | Full triad on high-stakes stages; light `execute → QA` (no planner) on low-stakes stages. |
| `lite` | No per-stage triad — the executor self-checks (this is exactly v2.1 behavior). |

In **all three** modes the phase-level cross-document **critic** and the
binding **judge** still run. Per-stage QA reviews each artifact in isolation;
the critic catches contradictions *between* documents that per-artifact review
cannot. They are complementary, so both are kept for maximum rigor.

## Stage tiers

The triad wraps **authoring** stages — the ones that produce an artifact a
later stage builds on.

High-stakes (full triad under `standard` and `paranoid`):
`product-brief`, `requirements`, `architecture`, `agent-design` (AI only),
`security-design`, `devops-design`, `security-final`, `devops-readiness`.

Low-stakes (light `execute → QA` under `standard`; full triad under `paranoid`):
`documentation`, `release-packaging`, `blueprint-summary`.

**Gate / reviewer stages are NOT wrapped in a triad.** The critic, the judge,
and the risk-manager *are* the independent review — wrapping them would mean
reviewing the reviewer's verdict, an infinite regress. They are terminated by
mechanical validators instead: `validate_critique.py` for the critic and
`validate_verdict.py --type decision|risk` for the judge and risk-manager. The
sprint build loop is likewise already a triad (generator builds, evaluator
grades) driven by `next_action.py`, and is unchanged.

## How the orchestrator runs one stage

Drive each triad stage with the script until it says DONE:

```
python3 .harness/scripts/stage_status.py <stage-id> --artifact <path> [--no-plan]
```

It reads state from disk and prints one instruction:

| action | do this |
|---|---|
| `PLAN` | invoke **stage-planner** → `.harness/plans/plan-<stage>.md` |
| `EXECUTE` | invoke the stage's **specialist executor** → the artifact |
| `QA` | invoke **stage-qa** → `.harness/qa-reports/qa-<stage>-r<n>.md` |
| `FORCE-ACCEPT` | after the round cap: **stage-qa** makes minimal fixes and passes |
| `DONE` | stage passed independent QA — go to the next stage |

Pass `--no-plan` for a light stage (QA grades against the template + standard
instead of a plan). The revise loop is capped (default 3 rounds) so a stage
cannot loop forever — the same circuit-breaker philosophy as the sprint loop.

## Files this adds to a project

```
.harness/plans/plan-<stage>.md         acceptance checklist (stage-planner)
.harness/qa-reports/qa-<stage>-r<n>.md  independent review (stage-qa), one per round
.harness/progress.json  ->  "rigor"     the dial: paranoid | standard | lite
```

## New pieces in the plugin

- `agents/stage-planner.md` — generic per-stage planner (opus).
- `agents/stage-qa.md` — generic independent reviewer (opus); pass/revise.
- `scripts/stage_status.py` — per-stage driver + circuit breaker.
- `scripts/validate_verdict.py` — extended with `--type qa` (pass|revise).
- `templates/plan.md`, `templates/qa-report.md`.
- `scripts/init_asdr.py` — seeds `.harness/plans`, `.harness/qa-reports`, and
  the `rigor` setting.

## Why this is safe to adopt

`lite` reproduces v2.1 exactly, so upgrading changes nothing until you turn the
dial up. Every new loop is bounded by the same kind of on-disk circuit breaker
that protects the sprint loop, so more review never means more stalls.
