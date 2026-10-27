# AI Software Delivery Room
## Claude Code / Cowork Plugin + Agentic SDLC Harness · v4.0.0

A complete plug-and-play system that turns Claude (Claude Code, Cowork, Cursor,
Windsurf, etc.) into a disciplined **AI Software Delivery Room** — preventing the
most common AI coding failures: context loss, self-grading, hallucinated
completion, feature drift, security gaps, and broken production releases.

**What's new in v4.0 — start where you are, pay for the models you need, and
choose which decisions stay changeable.**

- **Where to start.** `/asdr` now opens by recommending a start point —
  Validate, Discovery, Design, Build, Release gate, Assess an existing system,
  or Resume — from your request and what is already in the folder (an earlier
  run, ASDR's documents, your own PRD or architecture notes, existing code).
  It shows what each start skips, the risk, and the cost; you choose
  (`entry_point.py`). A late start skips stages, never the evidence: the
  missing documents are converted from yours by their owners in a new INTAKE
  mode (inferences marked, gaps asked), checked by the stage validators and one
  critic pass, before the chosen stage begins. Documents that exist but were
  never reviewed are reviewed, not trusted.
- **A model plan per role.** Every role runs on its own model, whatever the
  conversation uses: `economy` keeps only the roles that can stop a bad release
  (critic, judge, tester, risk manager, security) on the strongest model, moves
  authors to Sonnet and the panel and release notes to Haiku; `balanced` is
  3.9's setup; `maximum` puts every role on the strongest model, and `--top
  fable` makes that Fable (`model_plan.py`). If your account does not allow a
  model, ASDR falls back and records it. `estimate_run.py --compare-plans`
  prices each plan (an estimate: about 30% cheaper for economy than balanced on
  a typical build at list prices).
- **Configurable decisions.** Every decision with more than one sensible
  answer is typed **configure** (cheap and reversible: built as a setting with a
  default, who may change it, a change log, a review date and a test for every
  allowed value), **prepare** (expensive: one option built behind a connection
  point, the other priced for later) or **decide-once** (hard to reverse), with
  the extra cost of building every option — and you decide each one
  (`docs/03f-configuration.md`, `validate_configurability.py`). Configure is
  recommended only at 15% extra cost or less and when the data model does not
  split. The release gate fails on a setting past its review date or a value
  without a passing test.

**v3.9 — ASDR's own simulated market, learned from MiroFish.**
`validate` now runs a **synthetic panel** natively, with no install and no
extra accounts, so it works in Cowork too. Personas are built from the desk
evidence (each cites the rows it comes from; any quote must be real). They
react independently, then once more after an anonymous digest of everyone's
objections, and `panel.py` measures who changed their mind. **"What if"
scenarios** (another price, another pitch, a competitor's move) run on the
same personas, so the comparison is within-persona — the most trustworthy
number a synthetic panel produces. The personas with the strongest
objections get **follow-up interviews**. Results report spread and **flags**
(implausible positivity, herding, homogeneity, thin segments, objections
that only echo the persona's own card, a second round where nobody moved)
that the synthesis must answer; a scenario shift too small to tell from
noise is marked as such. The same personas can later **walk the process
flows** in discovery to find friction. What it did not copy from MiroFish:
thousands of agents and simulated social networks — research on
language-model respondents shows a bigger crowd of one model is not more
evidence. MiroFish stays as an optional heavy lane, now with a **launcher**
(`mirofish_stack.py`) that installs a pinned version locally (cloud or fully
offline with Ollama + Neo4j), binds it to 127.0.0.1, and asks before every
download. Panel and MiroFish count as ONE kind of evidence: never demand,
never corroboration of each other.

**Also in v3.9 — validate the idea before you scope it.** The new
`validate` skill (also offered once as the first step of `asdr` and
`discover`) runs desk research first — real reviews, forums, pricing pages,
search signals, each with a URL — then the synthetic panel built from it,
and MiroFish only if you want it. The product-owner writes a proceed /
pivot / stop recommendation (`docs/00a-idea-validation.md`) with every
claim cited; the critic and the judge decide. Synthetic evidence can never
count as demand, the team's hypotheses never reach a persona (checked in
every brief), and every validation ends with cheap real-world tests and pass
thresholds. MiroFish (AGPL-3.0) is never bundled; see `docs/COMPANIONS.md`.

**What's new in v3.4 — the product has to work end to end, and you can watch
it.** A new **product-manager** agent writes the feature list and the
**end-to-end process flows** (Mermaid journeys, role handoffs, exception
paths, and one lifecycle map of how every journey connects); the
business-analyst turns them into **test cases** before any code exists.
`validate_product_map.py` follows the whole chain — lifecycle → flow → step →
use case → feature → requirement → test case → automated test → latest result
— and the planner must slice sprints through whole journeys. Browser tests run
in **Playwright, Cypress or Selenium** through one runner (`run_tests.py`),
**live in front of you** (`--live`: headed, slowed down) or recorded where
there is no screen. Every run is **published privately** (repo, CI artifact,
private claude.ai page; GitHub Pages only if you opt in). Every release builds
**user manuals with real screenshots** — Getting started + Advanced per
persona, and Beginner / Everyday / Power user / Administrator — as HTML and
PDF, stamped with the version and commit. A worked example lives in
`examples/sample-app/`.

**v3.8 — leaner runs, and microservices on any cloud by your decision.**
Every agent run is logged with its tokens and time, and before a project starts
`estimate_run.py` shows what each rigor level will cost so you choose knowing
it. Checklist roles run on Sonnet; consecutive documents by the same specialist
are written in one run and reviewed once; the judge runs only when the critic
finds something serious. Architecture is a decision you make: the architect
lays out modular monolith, microservices and serverless with pros, cons,
business impact and costs, and recommends one. Portability is a decision too:
20 building blocks mapped to AWS, Azure, Google Cloud and a local stand-in,
strategies priced per cloud, your choice recorded. Microservices follow
enforced rules (owned data, tested contracts, no call cycles, every service
runnable alone), and ASDR tests on the cloud you picked at the start — with
your approval, a time-to-live and a teardown — proving the cloud build passes
the same tests as the local one. It uses the cloud vendors' own agent tools
(AWS MCP Server, Azure Skills plugin, Google Cloud MCP servers, Terraform MCP)
when you have them.

**v3.7 — rebuild an old system without breaking it, report to the client,
and an assessment you can trust.** When ASDR takes over an existing system,
every behaviour the client keeps becomes a `PAR-xx` item; tests capture it on
the old system once and on every build of the new one, and
`compare_parity.py` blocks the release while a kept behaviour differs (an
intended difference needs the client's recorded approval). The dashboard
gains a **client status report** (`--audience client`): your brand, the same
facts and status rule, nothing internal. And `/assess` was run end to end on
a real open-source system (eShopOnWeb): the run exposed gaps that are now
closed — every cited line must exist, the evidence keeps no copied code and
is searched for the source's own credential values, duplicate findings across
reviewers are flagged, front-end libraries are checked, option estimates come
from one finding-level table, and the client's questions are numbered in the
report.

**v3.6 — assess an existing system, and a dashboard for every project.**
`/assess` takes over a system someone else built — legacy, poorly built or
undocumented — without making the client explain it again. It recovers how
the business runs on it (roles, features and whether they are used, flows,
rules and where each is enforced, where processes break) and reviews
architecture, code health, security, performance and operations from evidence:
scanners first (`assess_scan.py`), then agents triage every hit in the code.
`validate_assessment.py` blocks any claim without a resolvable `path:line` or
data note, and any secret pasted into a document. `build_assess_report.py`
writes a two-part report — business first, technical appendix second — with a
roadmap, where new features fit, three options with labelled estimates and the
questions for the client, as HTML and a branded A4 PDF that stays private.
Every ASDR project also gets a **dashboard** (`build_dashboard.py`), rebuilt at
each phase and sprint end and on `/asdr status`: status with reasons, phases,
the **expected delivery date with its standard deviation** (from measured
sprint cycle times; none until two sprints have finished), roadmap, features
and their status, speed, quality, risks, decisions, every document, every
environment (with a live check), repos, and every question asked with its
answer — printable and exported to PDF.

**v3.5.1 — every item of your own documents is tested, and the run proves
it.** Coverage is per project: the validator enumerates every functional and
non-functional requirement, acceptance criterion, business rule, edge case,
use-case alternate/exception flow, feature and flow step THIS project's
documents define, and requires a test case for each. Tests mark what they
actually reached at run time (`flowStep('PF-02.3')`, `covers('AC-03.2')`,
`metric(...)` for measured NFRs) in Playwright, Cypress and Selenium, and the
release gate requires every Must step and every promised item to be reached
by a passing test. Admin settings that change what another role can do must
be tested from that role's side, on and off. `docs/product-map.md` shows the
full coverage matrix.

**v3.5 — manuals a person signs off, accessibility, saved logins, screen
diffs.** Manual explanations are checked against the text on each screenshot
and approved by you before release (review page → approve / flag); every
journey screen is checked against WCAG 2.1 A/AA with axe-core; tests that are
not about signing in reuse one saved login per role across Playwright, Cypress
and Selenium; and each release shows which screens changed since the last one,
with before / after / diff images.

**v3.3 — runtime tiers, a design-system stage, companions,
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

A fresh install from the `asdr` marketplace also pulls in `ui-ux-pro-max`
(declared as a dependency in `marketplace.json`, pinned by commit). Update later with `claude plugin marketplace update asdr` followed
by `claude plugin update ai-software-delivery-room@asdr`. **Upgrading from
3.2.x or earlier:** `plugin update` does not install newly declared
dependencies, so ASDR shows "failed to load" until you also run
`claude plugin install ui-ux-pro-max@asdr` once. Each `/asdr` run checks
for newer versions of ASDR and its companions at Phase 0 and asks before
installing anything; there is no session-start hook or background traffic.

**Cowork.** Cowork installs the plugin on its own, outside the `asdr`
marketplace, so UI UX Pro Max is not pulled in there; the design-system
stage falls back to the hand-written template. Zip the repo (without `.git`) as `ai-software-delivery-room.plugin`
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
USER IDEA (+ whatever is already in the folder)
  ↓
where to start (v4.0) → recommended start point; you choose; a late start
                        converts your documents first (INTAKE + validators + critic)
  ↓
discover  →  [product-brief]→[requirements]→[use cases]
             →[features]→[process flows]→[test cases]  (each: plan → execute → QA)
             → validate_product_map.py → Critic → Judge
  ↓
architect →  [architecture]→[agent-design]→[security]→[devops]  (each triad) → Critic → Judge
  ↓
asdr (full flow) / longhorizon (build only)
  ↓
  Planner slices sprints through whole process flows (sprint 1 = entry journey)
  ↓
  Generator negotiates the acceptance contract  (validate_contract.py)
  ↓
  Evaluator ratifies the contract
  ↓
  Generator builds + [TC-xx] browser tests → Evaluator runs run_tests.py (--live to watch)
     → journeys proven? → report published privately → PASS / FAIL / TEARDOWN
  ↓
  Repeat until all sprints pass  (self-healing attempt + negotiation caps)
  ↓
riskgate  →  Security + DevOps (triad) + Risk-Manager classification
  ↓
release   →  Documentation + Release-Manager → Changelog + Deploy guide
             + versioned test report + user manuals (HTML + PDF, every persona and tier)
```

---

## Skills

| Skill | What it does |
|---|---|
| `asdr` | **Full workflow** — strategic layer + execution harness + release gates |
| `validate` | **Idea validation** — desk evidence + a synthetic persona panel (scenarios, follow-ups, flags) + optional MiroFish → proceed / pivot / stop, objections, real-world tests + critic + judge (v3.9) |
| `longhorizon` | **Execution only** — Planner → Generator ↔ Evaluator loop |
| `discover` | **Discovery** — brief, requirements, use cases, feature list, process flows, test cases + critic + judge |
| `architect` | **Architecture** — solution + AI + security + devops + critic + judge |
| `riskgate` | **Risk gate** — security review + deployment readiness + classification |
| `release` | **Release** — docs + changelog + release notes + deployment checklist |
| `assess` | **Assess an existing system** — recover processes, review the code, two-part report, hand-off into a build with a parity gate (v3.6, v3.7) |

Trigger phrases like "build me…", "let's build…", "run the delivery room",
"design the architecture", "is this ready to ship", etc. map to the skills.

---

## Agents (19)

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
| `business-analyst` | Requirements, user stories, measurable acceptance criteria, use cases, test cases |
| `product-manager` | Feature list and end-to-end process flows — owns how the pieces join into journeys (v3.4) |
| `solution-architect` | Architecture, APIs, DB design, trade-offs (records rejected ADR options) |
| `ai-architect` | Agent workflows, prompts, tools, memory, evaluation (AI features only) |
| `security-compliance` | Threat model, auth, injection risks, OWASP; release-gate code verification |
| `devops` | Docker, CI/CD, monitoring, rollback, browser test suites (Playwright / Cypress / Selenium) |
| `critic` | Challenges plans aggressively — cross-document contradictions |
| `judge` | Resolves conflicts, binding go/no-go with a machine-readable verdict |
| `documentation` | README, guides, API docs, handover, user manuals from test screenshots |
| `risk-manager` | Final release gate and classification |
| `release-manager` | Changelog, release notes, deploy checklist |
| `panelist` | Plays one persona on the validation panel from a single prepared input file (v3.9) |

### Execution layer
| Agent | Role |
|---|---|
| `planner` | User-visible sprints only — no technical detail |
| `generator` | Negotiates the acceptance contract + builds the sprint |
| `evaluator` | Adversarial QA — **only role that can declare a sprint done** |

---

## Package contents

```
.claude-plugin/plugin.json   ← plugin manifest (v4.0.0)
README.md                    ← this file
CHANGELOG.md                 ← full v2.1 → v3 → … → v4.0 change log
agents/                      ← 19 agent definitions (incl. stage-planner, stage-qa,
                               product-integrity-qa, product-manager)
skills/                      ← 8 orchestrator skills (asdr, validate, discover,
                               architect, longhorizon, riskgate, release, assess)
scripts/
  init_asdr.py               ← project initializer (seeds harness + rigor dial + matrix)
  next_action.py             ← sprint state machine (self-healing circuit breakers)
  stage_status.py            ← per-stage triad driver (plan → execute → QA)
  trace.py                   ← append-only trace log
  validate_contract.py       ← contract structure gate
  validate_sprints.py        ← sprint schema gate (high-precision tech denylist)
  validate_verdict.py        ← decision / eval / risk / qa / integrity / validation block gate
  mirofish_validate.py       ← drives a MiroFish instance for the validate skill (v3.8)
  panel.py                   ← synthetic panel state machine: briefs, checks, digest, follow-ups, scenarios, flags, walkthrough (v3.9)
  mirofish_stack.py          ← installs/starts/stops a pinned MiroFish locally (v3.9)
  validation_questions.py    ← shared questions and lists for panel and MiroFish (v3.9)
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
  validate_product_map.py    ← end-to-end chain + coverage of every testable item + docs/product-map.md (v3.4, v3.5.1)
  run_tests.py               ← runs Playwright / Cypress / Selenium suites, --live (v3.4)
  publish_test_report.py     ← HTML report: repo, CI, private Artifact; Pages opt-in (v3.4)
  build_manual.py            ← persona + tier user manuals, HTML + PDF (v3.4)
  run_metrics.py             ← per-run metrics: rounds, attempts, packs, tests (v3.4)
  report_style.py            ← shared look for reports and manuals (v3.4)
  compare_screens.py         ← screenshot diffs between runs or releases (v3.5)
  build_dashboard.py         ← project dashboard, HTML + PDF, delivery forecast with SD (v3.6)
  log_question.py            ← every question asked and its answer → dashboard (v3.6)
  sprint_clock.py            ← sprint start / done / torn-down stamps for the forecast (v3.6)
  assess_scan.py             ← /assess: inventory + scanners + hotspots (v3.6)
  validate_assessment.py     ← /assess: evidence gate + pasted-secret check (v3.6)
  build_assess_report.py     ← /assess: two-part report, HTML + branded PDF (v3.6)
  compare_parity.py          ← old system vs new build, behaviour by behaviour; release gate (v3.7)
  log_agent_run.py           ← tokens, time and model per agent run; budget warnings (v3.8)
  estimate_run.py            ← cost per rigor level before the run starts; sets the budget (v3.8)
  decide.py                  ← phase decision without a judge when nothing is Critical/High (v3.8)
  check_required_changes.py  ← scripted second round of required changes (v3.8)
  assess_scope.py            ← /assess: a starting list of files per reviewer (v3.8)
  validate_architecture_options.py ← the user's monolith / microservices decision, with costs (v3.8)
  validate_portability.py    ← the user's portability strategy and clouds, with costs (v3.8)
  validate_services.py       ← microservice rules: owned data, contracts, no cycles, standalone (v3.8)
  cloud_preflight.py         ← read-only readiness on the test cloud (v3.8)
  cloud_env.py               ← ledger of temporary test environments, time-to-live, teardown (v3.8)
  cloud_parity.py            ← the cloud build passes the same tests as the local one (v3.8)
  entry_point.py             ← recommends where a run starts; records the choice and its catch-up (v4.0)
  model_plan.py              ← economy / balanced / maximum: the model per role, with fallbacks (v4.0)
  validate_configurability.py ← configure / prepare / decide-once decisions, settings tested per value (v4.0)
templates/                   ← fill-in templates: contract, plan, qa-report,
                               eval-report, critique, decision, security-baseline,
                               roadmap, business-case, use-cases, traceability,
                               integrity-report, git-workflow, e2e-testing (v3.1),
                               design-system, agent-runtime.yaml, build-ladder (v3.3),
                               feature-list, process-flows, test-cases, publish.json,
                               ci-asdr.yml, e2e/{playwright,cypress,selenium} (v3.4),
                               dashboard.json, assess/ (v3.6), parity.md, assess/triage.json (v3.7),
                               architecture-options.md, portability.md, services.md, cloud.json,
                               cloud/catalogue.json, microservices/ (v3.8), configuration.md (v4.0)
examples/sample-app/         ← TaskBoard: a small app with every v3.4 artifact —
                               product docs, [TC-xx] tests in all three frameworks,
                               tours, manual.json (v3.4), and a worked assessment
                               of the app in docs/assess/ (v3.6)
.github/workflows/ci.yml     ← release gate: unit tests, validate, both install
                               paths, sample e2e, .plugin asset on tag (v3.4)
docs/
  AI_SOFTWARE_DELIVERY_ROOM_OPERATING_MANUAL.md
  TRIAD_ARCHITECTURE.md      ← the v3 triad + rigor dial design
  CONTEXT_ARCHITECTURE.md    ← the v3.2 context-discipline review and plan
  COMPANIONS.md              ← companion install/scoping rules (v3.3)
  PUBLISHING.md              ← marketplace layout, release checklist, tagging (v3.3)
tests/                       ← python3 -m unittest discover -s tests (337 tests)
```

## The 19 agents at a glance

**Triad + integrity (v3 / v3.1):** `stage-planner` sets each stage's acceptance
checklist, the specialist executor builds to it, `stage-qa` grades it
independently, and `product-integrity-qa` verifies the whole product against
the vision/roadmap/requirements every sprint (drift + regression).

**Strategic (12):** `product-owner` (brief, roadmap, business case),
`business-analyst` (requirements, use cases, test cases), `product-manager`
(feature list, end-to-end process flows), `solution-architect`,
`ai-architect`, `security-compliance`, `devops` (Docker/CI + git-workflow + E2E),
`critic`, `judge`, `documentation`, `risk-manager`, `release-manager`.

**Validation (1):** `panelist` plays one persona per invocation, from one
input file, so personas stay independent (v3.9).

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
.harness/test-config.json       browser suites run_tests.py runs (v3.4)
.harness/test-results/<run>/    JUnit, screenshots, videos, summary.json (v3.4)
.harness/manual/                manual-tour screenshots + manifests (v3.4)
.harness/publish.json           where reports go; private by default (v3.4)
docs/product-map.md             generated end-to-end chain (v3.4)
docs/test-reports/, docs/manuals/<version>/   published reports and manuals (v3.4)
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
8. Every Must process flow is proven end to end by a passing journey test on
   the release commit, and every Must step and every test case's Covers item
   is reached by a passing test — enforced by `validate_product_map.py --gate`.

---

## Recommended default stack

| Layer | Stack |
|---|---|
| Frontend | Next.js + React + Tailwind CSS + shadcn/ui |
| Backend | FastAPI + Python + PostgreSQL + Redis |
| AI/Agents | LangGraph + OpenAI/Anthropic APIs + structured JSON outputs |
| Vector memory | Qdrant or pgvector |
| DevOps | Docker + Docker Compose + GitHub Actions |

---

## Licence

MIT — see `LICENSE`. Adapted and referenced third-party work (Ponytail's
build ladder, UI UX Pro Max, the AX schema vocabulary, the test tools) is
listed with its licences in `THIRD_PARTY_NOTICES.md`.
