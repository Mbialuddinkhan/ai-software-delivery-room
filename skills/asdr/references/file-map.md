# ASDR file map and stage table

Read this once at Phase 0. Use these exact paths everywhere. Agents receive
their output path from the orchestrator; never let an agent choose its own.
Templates live in `.harness/templates/`.

## Canonical file map

| # | Document | Path | Agent | Template |
|---|---|---|---|---|
| 1 | Product brief | `docs/01-product-brief.md` | product-owner | product-brief.md |
| 1b | Business case | `docs/01b-business-case.md` | product-owner | business-case.md |
| 0b | Roadmap | `docs/00b-roadmap.md` | product-owner | roadmap.md |
| 2 | Requirements | `docs/02-requirements.md` | business-analyst | requirements.md |
| 2b | Use cases | `docs/02b-use-cases.md` | business-analyst | use-cases.md |
| 2c | Feature list (requirements by feature) | `docs/02c-features.md` | product-manager | feature-list.md |
| 2d | Process flows (end-to-end journeys) | `docs/02d-process-flows.md` | product-manager | process-flows.md |
| 2e | Test cases | `docs/02e-test-cases.md` | business-analyst | test-cases.md |
| 3 | Discovery critique | `docs/critique-discovery.md` | critic | critique.md |
| 4 | Discovery decision | `docs/decision-discovery.md` | judge | decision.md |
| 5 | Architecture | `docs/03-architecture.md` | solution-architect | architecture.md |
| 5b | Design system (UI only) | `docs/03b-design-system.md` | solution-architect | design-system.md |
| 6 | Agent design (AI only), incl. §13 runtime/deployment | `docs/04-agent-design.md` | ai-architect | agent-design.md |
| 6b | Agent runtime manifests (T3 agents only) | `deploy/agents/<agent>.yaml` | devops | agent-runtime.yaml |
| 7 | Security | `docs/05-security.md` | security-compliance | security.md |
| 8 | DevOps | `docs/06-devops.md` | devops | devops.md |
| 9 | Architecture critique | `docs/critique-architecture.md` | critic | critique.md |
| 10 | Architecture decision | `docs/decision-architecture.md` | judge | decision.md |
| 11 | Blueprint digest | `docs/00-blueprint-summary.md` | orchestrator | blueprint-summary.md |
| 12 | E2E testing plan + suite config | `docs/08-e2e-testing.md`, `.harness/test-config.json` | devops | e2e-testing.md, e2e/test-config.json |
| 13 | Traceability matrix | `docs/traceability.md` (+ `.harness/traceability.json`) | product-integrity-qa | traceability.md |
| 13b | Product map (generated) | `docs/product-map.md` (+ `.harness/product-map.json`) | `validate_product_map.py` | — |
| 14 | Product integrity (gate) | `docs/09-product-integrity.md` | product-integrity-qa | integrity-report.md |
| 15 | Test reports (generated) | `docs/test-reports/<label>/` | `publish_test_report.py` | — |
| 16 | Manual spec | `docs/manuals/manual.json` | documentation | e2e/manual.json |
| 17 | User manuals (generated) | `docs/manuals/<version>/` (HTML + PDF) | `build_manual.py` | — |
| 18 | Run metrics (generated) | `docs/run-metrics.md` (+ `.harness/metrics.json`) | `run_metrics.py` | — |

Per-sprint integrity snapshots land at `docs/integrity-<sprint>.md`.

## Stage table (universal triad)

| Stage id | Executor agent | Artifact path | Tier |
|---|---|---|---|
| `product-brief` | product-owner | docs/01-product-brief.md | high |
| `business-case` | product-owner | docs/01b-business-case.md | high |
| `roadmap` | product-owner | docs/00b-roadmap.md | med |
| `requirements` | business-analyst | docs/02-requirements.md | high |
| `use-cases` | business-analyst | docs/02b-use-cases.md | high |
| `features` | product-manager | docs/02c-features.md | high |
| `process-flows` | product-manager | docs/02d-process-flows.md | high |
| `test-cases` | business-analyst | docs/02e-test-cases.md | high |
| `architecture` | solution-architect | docs/03-architecture.md | high |
| `design-system` | solution-architect | docs/03b-design-system.md | med (UI only; `--no-plan` under standard) |
| `agent-design` | ai-architect | docs/04-agent-design.md | high (AI only) |
| `security-design` | security-compliance | docs/05-security.md | high |
| `devops-design` | devops | docs/06-devops.md | high |
| `security-final` | security-compliance | docs/09-security-review-final.md | high |
| `devops-readiness` | devops | docs/09-devops-readiness.md | high |
| `documentation` | documentation | developer docs + `docs/manuals/manual.json` | low (`--no-plan` under standard) |

Phase 1 authoring stages run from `product-brief` through `devops-design`.
Phase 4 gate-authoring stages are `security-final`, `devops-readiness`,
`documentation`.

## State field reference

- `sprints.json` entry: `id`, `goal`, `status` (`pending | active | done | torn-down`), `flows` (process flow ids)
- Contract status: `in-negotiation | revision-requested | ratified`
- `progress.json` awaiting: `null | negotiate | ratify | build | evaluate`
