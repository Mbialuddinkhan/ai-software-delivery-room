# AI Software Delivery Room — Operating Manual

## Executive summary

The AI Software Delivery Room is a plug-and-play operating system for building software with Claude Code or similar AI coding tools. It combines strategic product/architecture governance with a long-horizon coding harness.

The system prevents the common failures of AI coding:

- vague requirements
- context loss
- one model grading its own work
- half-finished features
- hallucinated completion
- no audit trail
- weak security review
- no production gate

## Architecture

```text
User Idea
  ↓
Strategic SDLC Room
  ├─ Product Owner
  ├─ Business Analyst
  ├─ Solution Architect
  ├─ AI Architect
  ├─ Security & Compliance
  ├─ DevOps
  ├─ Critic
  └─ Judge
  ↓
Approved Build Blueprint
  ↓
Long-Horizon Execution Harness
  ├─ Planner
  ├─ Generator
  └─ Evaluator
  ↓
Final Gates
  ├─ Security Review
  ├─ DevOps Readiness
  ├─ Documentation
  ├─ Release Manager
  └─ Risk Manager
  ↓
Release / Deploy / Monitor
```

## Core loop

```text
Planner → Generator negotiates → Evaluator ratifies → Generator builds → Evaluator tests → pass/fail/teardown
```

## Why this works

- Planner prevents scope drift by defining only user-visible outcomes.
- Generator cannot build until acceptance criteria are negotiated.
- Evaluator prevents self-grading.
- JSON state prevents memory loss.
- Trace logs enable prompt/system improvement.
- Teardown rules prevent endless broken retries.
- Risk Manager prevents unsafe releases.

## How to use

1. Install package into repo.
2. Open Claude Code.
3. Run `/asdr "<software idea>"`.
4. Review strategic docs.
5. Let harness create sprints.
6. Let generator/evaluator execute sprint loop.
7. Review final risk classification.
8. Deploy only after gates pass.

## Production release requirements

- All sprints PASS.
- CI passes.
- Security review has no unresolved critical/high risks.
- Tests exist and pass.
- `.env.example` exists.
- Deployment guide exists.
- Rollback plan exists.
- Documentation exists.
- Risk Manager says MVP-ready or Production-ready.
