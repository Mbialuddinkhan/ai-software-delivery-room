# Project Charter — built with the AI Software Delivery Room

This project is executed by a multi-agent SDLC harness. This file is the
working memory every agent reads first: keep it short, current, and factual.

## Current state

Run `python3 .harness/scripts/next_action.py` — never guess the next step.

State lives in exactly two files:
- `sprints.json` — sprint list. Status enum: `pending | active | done | torn-down`
- `.harness/progress.json` — phase, active sprint, attempt, awaiting

## Canonical file map

| Artifact | Path |
|---|---|
| Blueprint digest (read this, not the full docs) | `docs/00-blueprint-summary.md` |
| Product brief | `docs/01-product-brief.md` |
| Requirements | `docs/02-requirements.md` |
| Architecture | `docs/03-architecture.md` |
| Agent design (only if AI features) | `docs/04-agent-design.md` |
| Security | `docs/05-security.md` |
| DevOps | `docs/06-devops.md` |
| Sprint contract | `.harness/contracts/contract-<sprint-id>.md` |
| Eval report | `.harness/eval-reports/eval-report-<sprint-id>-attempt-<n>.md` |
| Executable checks | `.harness/tests/` |
| Trace log | `.harness/traces/log.jsonl` |

## Project facts

<!-- Orchestrator: fill after blueprint approval, keep updated. -->
- Stack: <filled after architecture approval>
- Run locally: `<command>`
- Run tests: `<command>`
- Lint: `<command>`
- Conventions: <filled after architecture approval>

## Hard rules

1. The generator cannot declare work done — completion claims from the
   builder are untrusted by design; only the evaluator's verdict counts.
2. Only the evaluator updates `sprints.json` status after a build.
3. Contracts must be `Status: ratified` before any build starts.
4. Every agent invocation appends one line via
   `python3 .harness/scripts/trace.py <actor> <action> <result>`.
5. Never claim production-ready — that is the risk-manager's call alone.
