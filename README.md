# AI Software Delivery Room
## Claude Code / Cowork Plugin + Agentic SDLC Harness · v3.3.0

A complete plug-and-play system that turns Claude (Claude Code, Cowork, Cursor,
Windsurf, etc.) into a disciplined **AI Software Delivery Room** — preventing the
most common AI coding failures: context loss, self-grading, hallucinated
completion, feature drift, security gaps, and broken production releases.

**What's new in v3.3 — runtime tiers, a design-system stage, companions,
update checks.** The ai-architect now decides *where each agent runs* (T1
function / T2 container worker / T3 sandboxed actor runtime) with four runtime
blocks per agent — Task, Workspace, Gateway, Model — that devops and security
build from; the critic rejects an unjustified sandbox or an agent with no
egress allowlist. Products with a UI get a **design-system stage**
(`docs/03b-design-system.md`) whose checklist becomes UI sprint criteria,
drafted by **UI UX Pro Max** — which now installs with ASDR as a plugin
dependency. The generator carries a built-in YAGNI **build ladder**
(adapted from Ponytail, MIT), so that plugin is optional. A once-a-day
**update check** at the start of every `/asdr` run tells you when ASDR or a
companion has a newer version and what it adds; nothing installs without a
yes, and nothing runs outside a run. See `docs/COMPANIONS.md` and
`docs/PUBLISHING.md`.

**What's new in v3.2 — context discipline.** Agents stop re-deriving what a
command already knows. `emit_facts.py` writes `.harness/facts.json` and **no
numeric criterion may be graded except by citing a fact key**, so a criterion
can never again ask an agent to transcribe command output it cannot run.
`preflight_contract.py` catches contracts no correct implementation could
satisfy *before* the evaluator sees them — each one used to cost a negotiation
round. And a script-maintained dependency graph feeds **budgeted per-task
context packs**: each agent gets files-in-scope, blast radius, fixture risks and
the facts slice instead of "go read the repo" — and if a pack busts its budget
the run stops and tells you to split the task, rather than discovering it when
an agent exhausts context mid-build. See `CONTEXT_ARCHITECTURE.md`.

**What's new in v3.1:** a **product-integrity** layer keeps the build provably
in sync with the vision/roadmap/brief/business-case/use-cases/requirements — a
living traceability matrix, drift detection, cross-sprint regression, and live
**Cypress** E2E you can watch run — plus first-class roadmap / business-case /
use-case discovery docs and a git & repository workflow. See `CHANGELOG.md`.

**From v3.0:** every stage runs as an independent triad
(planner → executor → a *separate* QA), tunable with a single **rigor dial**,
on self-healing safety limits and Opus-tuned agents. See
`docs/TRIAD_ARCHITECTURE.md`.

---

## The core idea

```
The same AI that writes something never signs it off.

  stage-planner   →   specialist executor   →   stage-qa
   (sets the bar)      (does the work)          (grades it — a DIFFERENT agent)

  Generator can build.   Evaluator can pass/fail.   Risk Manager can release/block.
```

Independent review happens at **every stage**, not just at the end — and the
safety limits that stop runaway loops now read the truth from disk, so they
can't be silently switched off.

---

## What's new in v3.1 — product integrity (stops feature drift)

- **Living traceability matrix** (`.harness/traceability.json` + readable
  `docs/traceability.md`): outcome → requirement → use case → sprint →
  acceptance criterion → test → status, seeded after discovery and updated
  every sprint.
- **`product-integrity-qa`** — a separate product-level QA agent that verifies
  the whole build against the strategic intent and emits an
  `in-sync | drifted | broken | incomplete` verdict the risk-manager honors.
- **Drift detection** (`validate_traceability.py`): if a requirement's text
  changes after a sprint built to it, the run **stops and surfaces it**; only on
  your approval are the brief, roadmap, business case, requirements, and use
  cases updated together and the matrix re-baselined.
- **Cross-sprint regression**: the evaluator re-runs the entire test suite each
  sprint (and at the gate), so an earlier feature breaking is caught at once.
- **Live E2E** with **Cypress** — video + screenshots so you can watch the tests
  run (`cypress open` / `run --headed` locally; headless with artifacts in CI).
- **Richer discovery**: first-class **roadmap**, **business case**, and
  **use-case** docs, kept in sync on approved changes.
- **Git & repository workflow** doc: branching, Conventional Commits, per-sprint
  PR + required checks, what-to-commit, branch protection, SemVer tagging.

## What's new in v3 (vs v1.1 / v2.x)

- **Universal triad.** Every authoring stage runs `stage-planner → executor →
  stage-qa`. A separate QA agent grades each artifact against an explicit
  acceptance checklist and returns `pass` or `revise` with evidence. No agent
  grades its own work.
- **Rigor dial** (`.harness/progress.json` → `rigor`): `paranoid` (full triad
  everywhere), `standard` (full triad on high-stakes stages, light review
  elsewhere), or `lite` (no per-stage triad — original v2.x behavior). Pick the
  intensity per project.
- **Self-healing circuit breakers.** The per-sprint attempt cap and the
  contract negotiation-round cap are now derived from artifacts on disk
  (eval-report files, trace-log lines), not a hand-kept counter — a missed
  increment can no longer disable a safety net.
- **Opus model routing.** The adversarial and architecture roles (critic,
  judge, evaluator, risk-manager, solution-architect, ai-architect,
  security-compliance, stage-planner, stage-qa) are pinned to the strongest
  model; builders and writers inherit.
- **An Operating Standard on every agent:** reason before committing, read
  inputs in parallel, quantify-or-cite every claim, and self-verify before
  stopping.
- **Mechanical validators** catch malformed work before it corrupts a run:
  `validate_contract.py`, `validate_sprints.py`, `validate_verdict.py`
  (judge / eval / risk / qa blocks), `validate_critique.py` (structure,
  self-consistent counts, ≥8-findings floor).

---

## Quick install

**Claude Code.** This repo is both a plugin (`.claude-plugin/plugin.json`)
and a one-plugin marketplace (`.claude-plugin/marketplace.json`), so it
installs in two commands:

```bash
claude plugin marketplace add Mbialuddinkhan/ai-software-delivery-room   # or a local clone path
claude plugin install ai-software-delivery-room@asdr
```

The install also pulls in `ui-ux-pro-max` (a declared dependency, pinned by
commit). Update later with `claude plugin marketplace update asdr` followed by
`claude plugin update ai-software-delivery-room@asdr`. Each `/asdr` run checks
for newer versions of ASDR and its companions at Phase 0 and asks before
installing anything; there is no session-start hook or background traffic.

**Cowork.** Zip the repo (without `.git`) as `ai-software-delivery-room.plugin`
and add it in the Claude desktop app, or accept the `.plugin` package when
Claude hands it to you in chat. Then trigger a skill (e.g. ask to "run the
full ASDR workflow" or use the trigger phrases below).

**Or copy into a project** and run the initializer:

```bash
python3 scripts/init_asdr.py --source .
```

This creates the harness in your project (`.harness/`, `docs/`, `CLAUDE.md`,
state files) and seeds the rigor dial. Then start a run:

```
Run the asdr skill: "Build a multi-agent trading research platform with
analyst agents, bull/bear debate, judge, trader, risk manager, audit trail,
and dashboard."
```

Set the rigor dial any time by editing `.harness/progress.json`:

```json
{ "rigor": "standard" }   // paranoid | standard | lite
```

---

## The workflow

```
USER IDEA
  ↓
discover  →  [product-brief]→[requirements]  (each: plan → execute → QA)  → Critic → Judge
  ↓
architect →  [architecture]→[agent-design]→[security]→[devops]  (each triad) → Critic → Judge
  ↓
asdr (full flow) / longhorizon (build only)
  ↓
  Planner creates user-visible sprints
  ↓
  Generator negotiates the acceptance contract  (validate_contract.py)
  ↓
  Evaluator ratifies the contract
  ↓
  Generator builds → Evaluator tests → PASS / FAIL / TEARDOWN
  ↓
  Repeat until all sprints pass  (self-healing attempt + negotiation caps)
  ↓
riskgate  →  Security + DevOps (triad) + Risk-Manager classification
  ↓
release   →  Documentation + Release-Manager → Changelog + Deploy guide
```

---

## Skills

| Skill | What it does |
|---|---|
| `asdr` | **Full workflow** — strategic layer + execution harness + release gates |
| `longhorizon` | **Execution only** — Planner → Generator ↔ Evaluator loop |
| `discover` | **Discovery** — product brief + requirements + critic + judge |
| `architect` | **Architecture** — solution + AI + security + devops + critic + judge |
| `riskgate` | **Risk gate** — security review + deployment readiness + classification |
| `release` | **Release** — docs + changelog + release notes + deployment checklist |

Trigger phrases like "build me…", "let's build…", "run the delivery room",
"design the architecture", "is this ready to ship", etc. map to the skills.

---

## Agents (17)

### Triad + integrity roles (new in v3 / v3.1)
| Agent | Role |
|---|---|
| `stage-planner` | Writes each stage's acceptance checklist before the executor runs |
| `stage-qa` | Independent per-stage reviewer — grades the artifact, returns pass/revise |
| `product-integrity-qa` | Product-level QA (v3.1) — traceability matrix, drift + regression, integrity verdict |

### Strategic layer
| Agent | Role |
|---|---|
| `product-owner` | Product vision, MVP scope, personas, quantified success metrics |
| `business-analyst` | Requirements, user stories, measurable acceptance criteria |
| `solution-architect` | Architecture, APIs, DB design, trade-offs (records rejected ADR options) |
| `ai-architect` | Agent workflows, prompts, tools, memory, evaluation (AI features only) |
| `security-compliance` | Threat model, auth, injection risks, OWASP; release-gate code verification |
| `devops` | Docker, CI/CD, monitoring, rollback |
| `critic` | Challenges plans aggressively — cross-document contradictions |
| `judge` | Resolves conflicts, binding go/no-go with a machine-readable verdict |
| `documentation` | README, guides, API docs, handover |
| `risk-manager` | Final release gate and classification |
| `release-manager` | Changelog, release notes, deploy checklist |

### Execution layer
| Agent | Role |
|---|---|
| `planner` | User-visible sprints only — no technical detail |
| `generator` | Negotiates the acceptance contract + builds the sprint |
| `evaluator` | Adversarial QA — **only role that can declare a sprint done** |

---

## Package contents

```
.claude-plugin/plugin.json   ← plugin manifest (v3.3.0)
README.md                    ← this file
CHANGELOG.md                 ← full v2.1 → v3 → v3.1 → v3.2 → v3.3 change log
agents/                      ← 17 agent definitions (incl. stage-planner, stage-qa,
                               product-integrity-qa)
skills/                      ← 6 orchestrator skills (asdr, discover, architect,
                               longhorizon, riskgate, release)
scripts/
  init_asdr.py               ← project initializer (seeds harness + rigor dial + matrix)
  next_action.py             ← sprint state machine (self-healing circuit breakers)
  stage_status.py            ← per-stage triad driver (plan → execute → QA)
  trace.py                   ← append-only trace log
  validate_contract.py       ← contract structure gate
  validate_sprints.py        ← sprint schema gate (high-precision tech denylist)
  validate_verdict.py        ← decision / eval / risk / qa / integrity block gate
  validate_critique.py       ← critique structure + counts + floor gate
  validate_traceability.py   ← traceability matrix: drift, orphans, coverage (v3.1)
  emit_facts.py              ← measured facts: diff, census, assertions, tests (v3.2)
  preflight_contract.py      ← contract satisfiability linter, 10 checks (v3.2)
  build_graph.py             ← dependency graph + blast radius + fixture risk (v3.2)
  build_digest.py            ← one-page machine-generated state digest (v3.2)
  make_context_pack.py       ← budgeted per-task context packs, exit 1 over budget (v3.2)
  detect_companions.py       ← Phase 0: UI UX Pro Max / Ponytail / Graphify / RTK detection (v3.3)
  uupm_design_system.py      ← drafts docs/03b via UI UX Pro Max when installed (v3.3)
  check_updates.py           ← installed vs upstream versions + changelog excerpt (v3.3)
  upstream.json              ← where check_updates.py looks for each item's latest version
templates/                   ← fill-in templates: contract, plan, qa-report,
                               eval-report, critique, decision, security-baseline,
                               roadmap, business-case, use-cases, traceability,
                               integrity-report, git-workflow, e2e-testing (v3.1),
                               design-system, agent-runtime.yaml, build-ladder (v3.3)
docs/
  AI_SOFTWARE_DELIVERY_ROOM_OPERATING_MANUAL.md
  TRIAD_ARCHITECTURE.md      ← the v3 triad + rigor dial design
  CONTEXT_ARCHITECTURE.md    ← the v3.2 context-discipline review and plan
  COMPANIONS.md              ← companion install/scoping rules (v3.3)
  PUBLISHING.md              ← marketplace layout, release checklist, tagging (v3.3)
tests/
  test_context_discipline.py ← unit tests for the v3.2 scripts (python3 -m unittest)
```

## The 17 agents at a glance

**Triad + integrity (v3 / v3.1):** `stage-planner` sets each stage's acceptance
checklist, the specialist executor builds to it, `stage-qa` grades it
independently, and `product-integrity-qa` verifies the whole product against
the vision/roadmap/requirements every sprint (drift + regression).

**Strategic (11):** `product-owner` (brief, roadmap, business case),
`business-analyst` (requirements, use cases), `solution-architect`,
`ai-architect`, `security-compliance`, `devops` (Docker/CI + git-workflow + E2E),
`critic`, `judge`, `documentation`, `risk-manager`, `release-manager`.

**Execution (3):** `planner` (user-visible sprints), `generator` (contract +
build), `evaluator` (adversarial QA + cross-sprint regression; the only role
that can declare a sprint done).

No agent signs off its own work — a *different* agent always reviews it.

Project state created by `init_asdr.py`:

```
CLAUDE.md                       working memory: facts, commands, file map
sprints.json                    status enum: pending | active | done | torn-down
.harness/progress.json          phase, sprint, attempt, negotiation_rounds, rigor
.harness/plans/                 stage-planner acceptance checklists (triad)
.harness/qa-reports/            stage-qa review reports (triad)
.harness/contracts/             per-sprint acceptance contracts
.harness/eval-reports/          evaluator reports (attempt count derives from here)
.harness/traces/log.jsonl       one line per agent invocation
docs/00..10-*.md                blueprint and gate documents
```

---

## Non-negotiable rules

1. No coding before scope, requirements, and architecture are approved.
2. No agent signs off its own work — a separate stage-qa (or the evaluator for
   sprints) is the authority.
3. Planner writes only user-visible sprint goals — enforced by `validate_sprints.py`.
4. Contracts cover 7 categories with minimum counts — enforced by `validate_contract.py`.
5. Only the evaluator sets `Status: ratified` and updates sprint status.
6. Generator cannot declare a sprint done; evaluator cannot write implementation code.
7. Risk Manager can block release even if all sprints pass.

---

## Recommended default stack

| Layer | Stack |
|---|---|
| Frontend | Next.js + React + Tailwind CSS + shadcn/ui |
| Backend | FastAPI + Python + PostgreSQL + Redis |
| AI/Agents | LangGraph + OpenAI/Anthropic APIs + structured JSON outputs |
| Vector memory | Qdrant or pgvector |
| DevOps | Docker + Docker Compose + GitHub Actions |
