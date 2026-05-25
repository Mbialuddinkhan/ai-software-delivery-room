---
description: Run the Architecture phase — Solution Architect, AI Architect, Security, DevOps, Critic, Judge. Outputs full technical blueprint.
allowed-tools: Task, Read, Write, Edit, Bash, Glob, Grep
argument-hint: <project name or brief>
---

You are the ARCHITECTURE ORCHESTRATOR.

Prerequisite: `docs/01-product-brief.md` and `docs/02-requirements.md` must exist and be approved.

# Phase 1 — Solution Architecture

Invoke `@solution-architect`.

Output: `docs/03-architecture.md`

Must include:
- Architecture overview and system context diagram (ASCII or Mermaid)
- Module boundaries and service responsibilities
- Database design (tables, relationships, indexes)
- API design (endpoints, request/response shapes)
- Authentication and authorization approach
- Error handling strategy
- Scalability strategy
- Deployment architecture
- Trade-off analysis
- Architecture Decision Records (ADRs)

# Phase 2 — AI / Agent Architecture (if AI features exist)

Check `docs/02-requirements.md` for AI/agent/LLM features.

If present, invoke `@ai-architect`.

Output: `docs/04-agent-design.md`

Must include:
- Agent list and responsibilities
- Agent input/output schemas (JSON)
- Tools per agent (least-privilege)
- Memory model
- Orchestration graph / workflow
- Prompt strategy and structured output schemas
- Hallucination controls
- Human-in-the-loop checkpoints
- Model fallback strategy
- Cost-control strategy
- Evaluation strategy
- Auditability design

# Phase 3 — Security Architecture

Invoke `@security-compliance`.

Output: `docs/05-security.md`

Must include:
- Threat model (STRIDE or equivalent)
- Data classification
- Auth/authz risks
- API security risks
- Prompt injection risks (if AI involved)
- Tool abuse risks
- Dependency risks
- Secrets management
- Logging and audit requirements
- Recommended controls
- Release-blocking issues

# Phase 4 — DevOps Architecture

Invoke `@devops`.

Output: `docs/06-devops.md`

Must produce or describe:
- Dockerfile
- docker-compose.yml
- .env.example
- GitHub Actions CI workflow
- Deployment guide
- Observability plan (logs, metrics, alerts)
- Backup and rollback plan
- Production checklist

# Phase 5 — Critic Review

Invoke `@critic` against all four architecture docs.

Must challenge:
- Contradictions between architecture and requirements
- Overengineering
- Security gaps
- Deployment risk
- AI hallucination risk
- Cost risk
- Testing gaps

# Phase 6 — Judge Approval

Invoke `@judge` to resolve critique and produce a final architecture decision.

Judge must:
- Approve or reject each major decision
- Resolve conflicts between docs
- List remaining assumptions
- Produce go/no-go decision for sprint planning

# Phase 7 — Summary

Print:
1. Architecture decisions approved
2. AI/agent design summary (if applicable)
3. Critical security findings
4. DevOps readiness status
5. Remaining open questions
6. Recommended next step: `/asdr "<idea>"` or `/longhorizon "<sprint prompt>"`
