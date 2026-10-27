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
2. Open Claude Code or Cowork (a Sonnet conversation is the cheapest; each role
   runs on its own model from the model plan).
3. Run `/asdr "<software idea>"`. ASDR recommends where to start (Validate,
   Discovery, Design, Build, Release gate, Assess, or Resume) from your request
   and what is already in the folder; you choose. A late start converts your
   own documents first (v4.0).
4. Choose the thoroughness and the model plan (economy / balanced / maximum)
   from the cost estimate.
5. Review strategic docs, and decide the architecture, the cloud and which
   decisions become settings (configure / prepare / decide-once).
6. Let harness create sprints.
7. Let generator/evaluator execute sprint loop.
8. Review final risk classification.
9. Deploy only after gates pass.

## Production release requirements

- All sprints PASS.
- CI passes.
- Security review has no unresolved critical/high risks.
- Tests exist and pass.
- `.env.example` exists.
- Deployment guide exists.
- Rollback plan exists.
- Documentation exists.
- Every setting has a passing test for each allowed value and is not past its review date (v4.0).
- Risk Manager says MVP-ready or Production-ready.
