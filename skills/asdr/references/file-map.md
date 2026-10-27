# ASDR file map and stage table

Read this once at Phase 0. Use these exact paths everywhere. Agents receive
their output path from the orchestrator; never let an agent choose its own.
Templates live in `.harness/templates/`.

## Canonical file map

| # | Document | Path | Agent | Template |
|---|---|---|---|---|
| 0a-s | Validation seed + simulation requirement (validate only) | `docs/validation/seed.md`, `docs/validation/requirement.md` | product-owner (SEED) | validation-seed.md |
| 0a-d | Desk evidence (validate only) | `docs/validation/desk-evidence.md` | product-owner (DESK) | validation-desk-evidence.md |
| 0a-m | MiroFish outputs (generated, validate only) | `docs/validation/mirofish/{run,report,interviews}-<n>.*`, `uploaded-<seed>`; facts under `mirofish` in `.harness/validation.json` | `mirofish_validate.py` | — |
| 0a-p | Synthetic panel (validate only) | `docs/validation/panel/`: `config.json`, `stimulus.md`, `stimulus-SC-xx.md`, `scenarios.json` (product-owner, STIMULUS); `roster.json` (business-analyst, PANEL); generated `seed-for-roster.md`, `inputs/*.md`, `digest.md`, `followups/selection.json`; `responses/<scenario>/r<n>-Pxx.json`, `followups/Pxx.json` (panelist); facts under `panel` in `.harness/validation.json` | product-owner, business-analyst, panelist, `panel.py` | panel-stimulus.md, panel-scenarios.json, panel-roster.json |
| 0a-w | Persona walkthrough of the flows (generated) | `docs/validation/panel/walkthroughs/Pxx.json`, `walkthrough-summary.md`; facts under `walkthrough` | panelist, `panel.py walkthrough-next` | — |
| 0a-l | MiroFish launcher state (outside the project) | `~/.asdr/mirofish/state.json`, `~/.asdr/mirofish/<flavor>-<sha>/` | `mirofish_stack.py` | — |
| 0a | Idea validation | `docs/00a-idea-validation.md` | product-owner (VALIDATE) | idea-validation.md |
| 0a-c | Validation critique + decision | `docs/critique-validation.md`, `docs/decision-validation.md` | critic, judge | critique.md, decision.md |
| 1 | Product brief | `docs/01-product-brief.md` | product-owner | product-brief.md |
| 1b | Business case | `docs/01b-business-case.md` | product-owner | business-case.md |
| 0b | Roadmap | `docs/00b-roadmap.md` | product-owner | roadmap.md |
| 2 | Requirements | `docs/02-requirements.md` | business-analyst | requirements.md |
| 2b | Use cases | `docs/02b-use-cases.md` | business-analyst | use-cases.md |
| 2c | Feature list (requirements by feature) | `docs/02c-features.md` | product-manager | feature-list.md |
| 2d | Process flows (end-to-end journeys) | `docs/02d-process-flows.md` | product-manager | process-flows.md |
| 2e | Test cases | `docs/02e-test-cases.md` | business-analyst | test-cases.md |
| 2f | Parity list (existing systems only) | `docs/02f-parity.md` | business-analyst (assess hand-off) | parity.md |
| 3 | Discovery critique | `docs/critique-discovery.md` | critic | critique.md |
| 4 | Discovery decision | `docs/decision-discovery.md` | judge | decision.md |
| 5a | Architecture options + the user's decision (v3.8) | `docs/03c-architecture-options.md` (+ `.harness/architecture.json`) | solution-architect; `validate_architecture_options.py` | architecture-options.md |
| 5 | Architecture | `docs/03-architecture.md` | solution-architect | architecture.md |
| 5e | Services, contracts, adapters (microservices only, v3.8) | `docs/03e-services.md`, `contracts/` (+ `.harness/services.json`) | solution-architect; `validate_services.py` | services.md, microservices/README.md |
| 5d | Portability + cloud decision with costs (v3.8) | `docs/03d-portability.md` (+ `.harness/portability.json`) | devops; `validate_portability.py` | portability.md, cloud/catalogue.json |
| 5f | Configurable decisions and settings (v4.0) | `docs/03f-configuration.md` (+ `.harness/configuration.json`) | solution-architect; business-analyst adds a test case per allowed value; `validate_configurability.py` | configuration.md |
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
| 19 | Project dashboard (generated) | `docs/dashboard/index.html`, `dashboard.pdf` | `build_dashboard.py` | dashboard.json |
| 20 | Cost of the run (v3.8) | `.harness/agent-runs.jsonl`, `.harness/budget.json` | `log_agent_run.py` (orchestrator, after every agent run), `estimate_run.py` | — |
| 21 | Test cloud (v3.8) | `.harness/cloud.json`, `.harness/cloud-preflight.json`, `.harness/cloud-envs.jsonl`, `.harness/cloud-parity.json`, `infra/`, `docker-compose.yml` | orchestrator (Phase 0), devops; `cloud_preflight.py`, `cloud_env.py`, `cloud_parity.py` | cloud.json, microservices/infra-layout.md, microservices/docker-compose.services.yml |
| 22 | Start point and catch-up (v4.0) | `.harness/entry.json`; catch-up critique `docs/critique-intake.md`, `docs/decision-intake.md` | orchestrator (Phase 0 step 5a); owners in INTAKE mode; `entry_point.py` | critique.md, decision.md |
| 23 | Model plan (v4.0) | `.harness/models.json` | orchestrator (Phase 0 step 5c); `model_plan.py` | — |
| 19b | Dashboard inputs | `.harness/dashboard.json` (environments, repos, links), `.harness/questions.jsonl`, `.harness/sprint-clock.jsonl`, `.harness/forecast-history.jsonl`, `.harness/dashboard-snapshot.json` | orchestrator, devops, evaluator, `log_question.py`, `sprint_clock.py` | dashboard.json |
| A1 | Assessment intake (assess only) | `docs/assess/intake.json` | assess skill | assess/intake.json |
| A2 | Scanner evidence (assess only) | `docs/assess/evidence/scan-summary.{json,md}`, `osv-frontend.json` + raw outputs (locations only, no copied code); `triage.json` (a verdict per hit, security-compliance) | `assess_scan.py`, security-compliance | assess/triage.json |
| A3 | As-is processes (assess only) | `docs/assess/as-is.json` | business-analyst (ASSESS) | assess/as-is.json |
| A4 | Technical review + findings (assess only) | one pair per reviewer: `docs/assess/technical-<area>.md`, `docs/assess/findings-<area>.json` (area = process, architecture, security, operations); the architect's also holds "Options and effort" | business-analyst, solution-architect, security-compliance, devops (ASSESS) | assess/technical.md, assess/findings.json |
| A5 | Opportunities and options (assess only) | `docs/assess/opportunities.json` | product-owner (ASSESS) | assess/opportunities.json |
| A6 | Assessment critique + decision | `docs/critique-assessment.md`, `docs/decision-assessment.md` | critic, judge | critique.md, decision.md |
| A7 | Assessment report (generated, private) | `docs/assess/report/index.html`, `assessment.pdf` | `build_assess_report.py` | assess/brand.json |
| A8 | Parity with the old system (generated) | `docs/parity-report.md` (+ `.harness/parity.json`; baseline `.harness/test-results/parity-baseline.json`) | `compare_parity.py`, `run_tests.py --parity old` | — |

Per-sprint integrity snapshots land at `docs/integrity-<sprint>.md`.

## Stage table (universal triad)

| Stage id | Executor agent | Artifact path | Tier |
|---|---|---|---|
| `idea-seed` | product-owner | docs/validation/seed.md | med (validate only; `--no-plan` under standard) |
| `desk-evidence` | product-owner | docs/validation/desk-evidence.md | high (validate only) |
| `panel-stimulus` | product-owner | docs/validation/panel/stimulus.md | med (validate only; `--no-plan` under standard) |
| `panel-roster` | business-analyst | docs/validation/panel/roster.json | med (validate only; `--no-plan` under standard) |
| `idea-validation` | product-owner | docs/00a-idea-validation.md | high (validate only) |
| `product-brief` | product-owner | docs/01-product-brief.md | high |
| `business-case` | product-owner | docs/01b-business-case.md | high |
| `roadmap` | product-owner | docs/00b-roadmap.md | med |
| `requirements` | business-analyst | docs/02-requirements.md | high |
| `use-cases` | business-analyst | docs/02b-use-cases.md | high |
| `features` | product-manager | docs/02c-features.md | high |
| `process-flows` | product-manager | docs/02d-process-flows.md | high |
| `test-cases` | business-analyst | docs/02e-test-cases.md | high |
| `architecture-options` | solution-architect | docs/03c-architecture-options.md | high (the user decides; `validate_architecture_options.py`) |
| `architecture` | solution-architect | docs/03-architecture.md | high (batched with `services` and `design-system`) |
| `services` | solution-architect | docs/03e-services.md | high (microservices only) |
| `portability` | devops | docs/03d-portability.md | high (the user decides; `validate_portability.py`) |
| `configuration` | solution-architect | docs/03f-configuration.md | high (the user decides each row; `validate_configurability.py`) |
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
