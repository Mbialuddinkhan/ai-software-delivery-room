---
name: ai-software-delivery-room
description: A complete plug-and-play agentic software delivery system for Claude Code. Use this skill when the user wants to build, plan, review, or release software with a multi-agent SDLC, long-horizon Planner/Generator/Evaluator loop, acceptance contracts, trace logs, teardown recovery, security review, DevOps, and risk-gated release.
---

# AI Software Delivery Room Skill

## When to use this skill

Use this skill whenever the user asks to:

- Build software with Claude Code or another AI coding tool.
- Create a complete app, SaaS, dashboard, AI agent system, API, web platform, automation product, or MVP.
- Turn a rough idea into production-grade software.
- Set up a multi-agent development process.
- Improve AI coding quality, reduce hallucinated code, or create a long-running coding harness.
- Implement a TradingAgents-style system or any multi-agent architecture.

## Operating model

This skill has two layers.

### Layer 1 — Strategic SDLC Room

Use this layer before coding. It converts idea into approved blueprint.

Roles:

1. Product Owner
2. Business Analyst
3. Solution Architect
4. AI Architect
5. Security & Compliance Architect
6. DevOps Architect
7. Critic
8. Judge
9. Risk Manager
10. Documentation Agent
11. Release Manager

Outputs:

- Product brief
- MVP scope
- Personas
- User stories
- Acceptance criteria
- Non-functional requirements
- Architecture blueprint
- Agent architecture
- Security threat model
- DevOps plan
- Risk register
- Release plan

### Layer 2 — Long-Horizon Execution Harness

Use this layer during coding.

Roles:

1. Planner — creates user-visible sprints only.
2. Generator — negotiates contract and builds.
3. Evaluator — adversarial QA and only sprint acceptance authority.

The execution loop is:

```text
Planner → Generator negotiates contract ↔ Evaluator ratifies → Generator builds → Evaluator tests → pass/fail/teardown → next sprint
```

## Non-negotiable rules

1. Do not start coding before product scope, requirements, architecture, and risk assumptions are clear.
2. Planner writes only user-visible sprint goals. No technical choices.
3. Generator writes at least 20 granular acceptance criteria before building.
4. Evaluator must ratify `.harness/contract.md` before build starts.
5. Generator cannot declare done.
6. Evaluator cannot write implementation code.
7. Risk Manager can block release even if all sprints pass.
8. State must be machine-readable JSON.
9. Negotiation must be human-readable Markdown.
10. Every sprint attempt must produce a trace log.
11. Repeated failure triggers teardown or sprint split.
12. Production release requires CI, tests, security review, deployment guide, and rollback plan.

## Default stack unless user specifies otherwise

Frontend:
- Next.js
- React
- Tailwind CSS
- shadcn/ui

Backend:
- FastAPI
- Python
- PostgreSQL
- Redis

AI/Agents:
- LangGraph or equivalent workflow engine
- OpenAI/Anthropic-compatible LLM APIs
- Structured JSON outputs
- Tool calling
- Optional Qdrant/pgvector for vector memory

DevOps:
- Docker
- Docker Compose
- GitHub Actions
- Environment-based configuration
- Observability logs and traces

## Required file structure

Create or use:

```text
CLAUDE.md
sprints.json
.harness/progress.json
.harness/contract.md
.harness/traces/
.harness/templates/
.claude/agents/
.claude/commands/
docs/
evals/
```

## Required workflow

For a new software idea:

1. Run strategic discovery.
2. Produce product brief.
3. Produce SRS and user stories.
4. Run Critic review.
5. Run Judge approval.
6. Produce architecture blueprint.
7. Produce AI/agent design, if relevant.
8. Produce security threat model.
9. Produce DevOps plan.
10. Run Judge blueprint approval.
11. Run Planner to create `sprints.json`.
12. Activate one sprint.
13. Run Generator in negotiate mode.
14. Run Evaluator to ratify the contract.
15. Run Generator in build mode.
16. Run Evaluator to test.
17. On PASS, mark sprint done.
18. On FAIL, fix and re-evaluate.
19. On repeated FAIL, teardown/split.
20. After all sprints pass, run Security, DevOps, Documentation, Release, and Risk Manager gates.

## Quality standard

Classify every output as one of:

- Prototype
- MVP-ready
- Production-ready
- Not ready

Never claim production-ready unless the release passes all gates.
