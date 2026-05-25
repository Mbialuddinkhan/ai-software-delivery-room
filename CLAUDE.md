# AI Software Delivery Room — Root Charter · v1.1

This repository is built using the **AI Software Delivery Room** system.

## Mission

Build production-oriented software through a controlled multi-agent SDLC and long-horizon execution harness.

## Core execution loop

Work is executed by three long-horizon sub-agents:

- `@planner` — breaks human intent into **user-visible sprints only**. No technical detail.
- `@generator` — negotiates acceptance criteria and builds the sprint. **Cannot mark complete.**
- `@evaluator` — adversarial QA. The **only role** allowed to declare a sprint done or order teardown.

## Strategic roles

Use these before sprint execution when product, architecture, security, or DevOps decisions are needed:

| Role | Responsibility |
|---|---|
| `@product-owner` | Product vision, MVP scope, personas, success metrics |
| `@business-analyst` | Requirements, user stories, acceptance criteria, edge cases |
| `@solution-architect` | Architecture, modules, APIs, DB design, trade-offs |
| `@ai-architect` | Agent design, prompts, tools, memory, orchestration, evaluation |
| `@security-compliance` | Threat model, auth, injection risks, OWASP, audit |
| `@devops` | Docker, CI/CD, env, monitoring, backup, rollback |
| `@critic` | Challenges weak assumptions, missing reqs, overengineering |
| `@judge` | Resolves conflicts, approves next phase |
| `@documentation` | README, guides, API docs, handover notes |
| `@risk-manager` | Final release gate. Classifies: Prototype / MVP-ready / Production-ready / Not ready |
| `@release-manager` | Changelog, release notes, deployment checklist |

## Hard rules

1. **Do not start coding** before product, requirements, and architecture are approved.
2. **Planner** may not name frameworks, files, libraries, APIs, database engines, cloud providers, functions, or schemas.
3. **Generator** must negotiate `.harness/contract.md` before building any code.
4. Each sprint contract must contain **at least 20 granular, testable acceptance criteria** (target: 27).
5. **Generator cannot mark work complete.** Generator cannot edit eval reports.
6. **Evaluator is the only sprint acceptance authority.** Only evaluator may update `sprints.json`.
7. **Risk Manager is the only production release authority.**
8. State lives in JSON: `sprints.json` and `.harness/progress.json`.
9. Negotiation lives in Markdown: `.harness/contract.md`.
10. Every sprint attempt must generate a trace log in `.harness/traces/`.
11. Two consecutive failed criteria OR more than 5 attempts triggers **teardown/split**.
12. Every important AI decision must be logged with timestamp, actor, and reason.
13. **Never treat generated code as production-ready** until it passes evaluator, security, DevOps, and risk gates.

## Slash commands

| Command | Purpose |
|---|---|
| `/asdr "<idea>"` | Full strategic + execution workflow from idea to release |
| `/longhorizon "<prompt>"` | Execution harness only (skip strategic layer) |
| `/discover "<idea>"` | Strategic discovery: Product Owner → BA → Critic → Judge |
| `/architect "<brief>"` | Architecture: Solution Architect → AI Architect → Security → DevOps → Critic → Judge |
| `/riskgate` | Final risk classification before any deployment |
| `/release` | Package release: Documentation → Release Manager |

## Session boot reading order

On every new session, read in this order:

1. `CLAUDE.md`
2. `docs/01-product-brief.md` (if exists)
3. `docs/02-requirements.md` (if exists)
4. `docs/03-architecture.md` (if exists)
5. `docs/04-agent-design.md` (if exists)
6. `docs/05-security.md` (if exists)
7. `docs/06-devops.md` (if exists)
8. `sprints.json`
9. `.harness/progress.json`
10. `.harness/contract.md` (if present)
11. Latest `.harness/eval-reports/` report (if present)
12. Latest `.harness/traces/` log (if debugging)

## Done definition

**A sprint is done only when:**
- All ratified acceptance criteria pass
- Automated tests pass
- No critical console or runtime errors
- No serious accessibility issues (UI sprints)
- Evaluator writes a PASS verdict
- `sprints.json` is updated by Evaluator only

**A project is production-ready only when:**
- All sprints are `done` in `sprints.json`
- Tests pass in CI
- Security review has no critical/high unresolved findings
- No hardcoded secrets
- Deployment instructions are complete
- Rollback plan exists
- Logs, metrics, and error handling exist
- Risk Manager classifies as MVP-ready or Production-ready
- Human owner has approved the release
