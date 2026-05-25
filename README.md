# AI Software Delivery Room
## Claude Code Skill + Agentic SDLC Harness · v1.1

A complete plug-and-play system that turns Claude Code (or Cursor, Windsurf, Replit Agent, etc.) into a disciplined **AI Software Delivery Room** — preventing the most common AI coding failures: context loss, self-grading, hallucinated completion, security gaps, and broken production releases.

---

## Quick install (copy into any project)

```bash
# From this folder, copy into your project root:
cp -R .claude /path/to/your-project/
cp -R .harness /path/to/your-project/
cp CLAUDE.md /path/to/your-project/
```

Or run the init script inside your project:

```bash
python scripts/init_asdr.py
```

Then open Claude Code inside your project and run:

```
/asdr "Build a multi-agent trading research platform with analyst agents, bull/bear debate, judge, trader, risk manager, audit trail, and dashboard."
```

---

## What this system does

```
USER IDEA
  ↓
/discover  →  Product Owner → Business Analyst → Critic → Judge
  ↓
/architect →  Solution Architect → AI Architect → Security → DevOps → Critic → Judge
  ↓
/longhorizon (or /asdr for full flow)
  ↓
  Planner creates user-visible sprints
  ↓
  Generator negotiates 20–27 acceptance criteria (contract)
  ↓
  Evaluator ratifies contract
  ↓
  Generator builds
  ↓
  Evaluator tests → PASS / FAIL / TEARDOWN
  ↓
  Repeat until all sprints pass
  ↓
/riskgate  →  Security + DevOps + Risk Manager classification
  ↓
/release   →  Documentation + Release Manager → Changelog + Deploy guide
```

---

## Available slash commands

| Command | What it does |
|---|---|
| `/asdr "<idea>"` | **Full workflow** — strategic layer + execution harness + release gates |
| `/longhorizon "<prompt>"` | **Execution only** — Planner → Generator ↔ Evaluator loop |
| `/discover "<idea>"` | **Discovery** — Product brief + requirements + critic + judge |
| `/architect "<brief>"` | **Architecture** — Solution + AI + Security + DevOps + critic + judge |
| `/riskgate` | **Risk gate** — Security review + deployment readiness + risk classification |
| `/release` | **Release** — Docs + changelog + release notes + deployment checklist |

---

## Agents included

### Strategic Layer
| Agent | Role |
|---|---|
| `@product-owner` | Product vision, MVP scope, personas, success metrics |
| `@business-analyst` | Requirements, user stories, acceptance criteria |
| `@solution-architect` | Architecture, APIs, DB design, trade-offs |
| `@ai-architect` | Agent workflows, prompts, tools, memory, evaluation |
| `@security-compliance` | Threat model, auth, injection risks, OWASP |
| `@devops` | Docker, CI/CD, monitoring, rollback |
| `@critic` | Challenges weak plans aggressively |
| `@judge` | Resolves conflicts, approves phases |
| `@documentation` | README, guides, API docs, handover |
| `@risk-manager` | Final release gate and classification |
| `@release-manager` | Changelog, release notes, deploy checklist |

### Execution Layer
| Agent | Role |
|---|---|
| `@planner` | User-visible sprints only — no technical detail |
| `@generator` | Negotiates acceptance contract + builds sprint |
| `@evaluator` | Adversarial QA — **only role that can declare done** |

---

## The most important rule

```
Generator can build.
Evaluator can pass/fail.
Risk Manager can release/block.
```

The same AI that wrote the code **cannot grade its own code**.

---

## Package contents

```
CLAUDE.md                                ← Root charter — drop at project root
README.md                                ← This file
scripts/
  init_asdr.py                           ← Init script
docs/
  AI_SOFTWARE_DELIVERY_ROOM_OPERATING_MANUAL.md
.claude/
  skills/
    ai-software-delivery-room/
      SKILL.md                           ← Skill trigger metadata
  agents/
    planner.md
    generator.md
    evaluator.md
    product-owner.md
    business-analyst.md
    solution-architect.md
    ai-architect.md
    security-compliance.md
    devops.md
    critic.md
    judge.md
    risk-manager.md
    release-manager.md
    documentation.md
  commands/
    asdr.md                              ← /asdr full workflow
    longhorizon.md                       ← /longhorizon execution only
    discover.md                          ← /discover product + requirements
    architect.md                         ← /architect full architecture
    riskgate.md                          ← /riskgate final gate
    release.md                           ← /release packaging
.harness/
  templates/
    contract.md                          ← Sprint contract template
    eval-report-template.md              ← Eval report template
    sprints.json                         ← Sprint state template
    progress.json                        ← Progress state template
    adr-template.md                      ← Architecture decision record
    risk-register.md                     ← Risk register
    agent-output.schema.json             ← JSON schema for agent outputs
    decision-log.jsonl                   ← Decision log template
  traces/                                ← Agent trace logs (populated at runtime)
  eval-reports/                          ← Evaluator reports (populated at runtime)
  decisions/                             ← Decision log (populated at runtime)
  risk-reports/                          ← Risk reports (populated at runtime)
evals/                                   ← AI evaluation outputs
```

---

## Recommended default stack

| Layer | Stack |
|---|---|
| Frontend | Next.js + React + Tailwind CSS + shadcn/ui |
| Backend | FastAPI + Python + PostgreSQL + Redis |
| AI/Agents | LangGraph + OpenAI/Anthropic APIs + structured JSON outputs |
| Vector memory | Qdrant or pgvector |
| DevOps | Docker + Docker Compose + GitHub Actions |
