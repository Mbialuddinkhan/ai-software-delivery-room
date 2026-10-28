# Changelog

All notable changes to the AI Software Delivery Room in this improvement pass.
Baseline is the shipped plugin at v2.0.0.

## [4.0.1] — the release checks run green again

- **The automatic checks pass again.** GitHub moved its standard test machines
  to Ubuntu 26.04; the browser test tool in the sample app cannot install
  there yet, so every check now runs on Ubuntu 24.04 until it can.
- **The MiroFish health check no longer depends on the test machine's disk.**
  Two tests failed on GitHub's machines (under 20 GB free); the disk check now
  takes an override for tests, and has its own tests.
- No change to how ASDR runs a project.

### Fixed
- `scripts/mirofish_stack.py`: `ASDR_MIROFISH_DISK_GB` overrides the free-disk
  reading (as `ASDR_MIROFISH_RAM_GB` does for memory); the stack tests set it,
  and two new tests cover the low-disk FAIL / WARN and the real reading.
- `.github/workflows/ci.yml`: every job pinned to `ubuntu-24.04` (Playwright
  1.56 does not recognise Ubuntu 26.04, so `playwright install --with-deps`
  stopped at once); "Publish report" runs only when the suites ran, so a
  set-up failure is reported once instead of twice.
- `docs/PUBLISHING.md`: push at most three tags at a time — GitHub starts no
  workflow for a push of more than three tags, which is why 3.9.0 / 4.0.0 got
  no release run and no `.plugin` asset.

## [4.0.0] — start where you are, a model plan per role, and configurable decisions you choose

- **Choose where the run starts.** `/asdr` recommends a start point from your
  request and the folder — Validate, Discovery, Design, Build, Release gate,
  Assess, or Resume — with what each skips, the risk and the cost; you choose.
  Late starts convert your own documents instead of skipping the evidence.
- **Pay only for the model each role needs.** Economy / balanced / maximum
  model plans, Fable as the top model if you want it, automatic fallback when
  a model is not allowed; the estimate prices each plan.
- **Decide which decisions stay changeable.** Configure (a tested setting),
  prepare (built once behind a connection point) or decide-once, each with the
  extra cost of building every option; the release gate checks every setting.

### Added
- `scripts/entry_point.py` (`recommend`, `choose`, `catchup`): reads the
  request and scans the folder (an earlier run in `.harness/progress.json`,
  ASDR's canonical documents, the user's own PRD / spec / architecture
  documents by name, existing code by source files and manifests — code under
  `docs/` is ignored, symbolic links are not followed, the scan is
  breadth-first and capped); recommends one start with reasons, lists every
  start with the stages it skips (and their risk), the documents to catch up
  first (owner per document; design system, AI design and services only when
  the product has a UI, AI or microservices; portability unless `--local-only`)
  and the validators to run; marks Release `not advised` until every sprint
  is done and Assess when there is no code. A stage counts as done only when
  its phase decision says go — or the catch-up's decision says go and was
  written after every document it covers; documents nobody reviewed get one
  review item, always last, in the catch-up. A no-go decision sends the run
  back to that phase's required changes. A run still in the strategic phase is not a "resume" (that
  would send next_action.py straight to the planner); it continues from its
  documents and decisions. `choose` writes `.harness/entry.json`; `catchup`
  re-reads what the product needs from the documents written since and exits
  2 until nothing is missing.
- **INTAKE mode** on product-owner, business-analyst, product-manager,
  solution-architect, security-compliance and devops: convert the user's
  documents into the canonical templates, mark inferences `[inferred]`, list
  "Gaps for the user"; decisions found in the user's documents are shown to
  the user to confirm, never assumed. ai-architect has it too. The catch-up
  ends with the stage validators and one critic pass in every rigor mode
  (`docs/critique-intake.md`, `decide.py --phase intake`).
- `scripts/model_plan.py` (`set`, `get`, `unavailable`, `show`) and
  `.harness/models.json`: plans `balanced` (identical to the agents'
  frontmatter — a test enforces it), `economy` (critic, judge, evaluator,
  risk-manager, security-compliance on top; authors and checklist roles on
  Sonnet; panelist and release-manager on Haiku) and `maximum` (every role on
  top; the default under `paranoid`, also when no plan file exists);
  `--top fable`; fallbacks fable → opus → sonnet, haiku → sonnet, opus →
  sonnet, sonnet → opus, then any other model still available — never one
  marked unavailable while another exists; kept across plan changes; a
  hand-edited file with wrong types or unknown models is tolerated; `set`
  without `--plan` follows the rigor (maximum under paranoid).
- `estimate_run.py`: roles priced on their plan's model (`--plan`, or
  `.harness/models.json`); tokens per model (Opus/Fable, Sonnet, Haiku);
  `--price-haiku`, `--price-fable`; `--compare-plans`; `--start
  discover|design|build|release` counts only the work from there plus the
  catch-up (INTAKE at 60% of writing, an assumption, and one critic pass);
  `--compare-starts`; the budget records the start; the configurable-decision
  step and its per-value test cases are counted (about one more agent run on a
  typical build). Fixed: the USD column was appended without its separator.
- `templates/configuration.md` → `docs/03f-configuration.md` (row 5f, stage
  `configuration`, asdr Phase 1 step 6c): decision register (DEC-xx: options,
  recommended type, extra cost to build all options, data-model split, the
  user's decision), settings (CFG-xx: key, default, allowed values or range,
  who may change it, when it takes effect, owner, review date, test cases),
  prepared options (connection point, cost to switch later), interacting
  settings (pairwise), and how settings are removed. The feature list gains a
  "Decisions with options" table the product-manager fills.
- `scripts/validate_configurability.py`: types and the 15% / no-split rule
  for a configure recommendation (the user may override; recorded as a
  warning); every configure decision has a setting, every prepare decision a
  connection point; defaults are allowed values; one test case per allowed
  value (a range: minimum, maximum, default) and every TC exists — WAITING
  (exit 2) until the business-analyst has added them, an error with
  `--require-tests`; `pending` is a pending decision; duplicates and
  documents without a register fail; warnings above 12 settings or 64
  combinations without a pairwise plan; `--gate` fails a pending decision, a
  setting past its review date or a test case not passing in the latest
  results, and SKIPs only a project designed before 4.0 (no
  `.harness/entry.json` or `models.json`) that has no document. Escaped pipes
  (`\|`) stay inside their cell.
  Writes `.harness/configuration.json`; exit 0 / 2 / 1.
- Agents: generator builds settings through one settings layer (server-side
  permission, change log, safe default, no dead switches) and only the chosen
  option of a prepare decision; evaluator tests every value from the affected
  user's side; business-analyst writes the per-value test cases; critic
  checks over-configuration, wrong types, missing pieces, secrets exposed as
  settings; risk-manager and devops block on `--gate`; documentation adds a
  Settings page to the administrator manual.
- Dashboard: "Run set-up and settings" (start point and whether it followed
  the recommendation, model plan with the models actually used after
  fallbacks, decisions by type, every setting with its review date); a
  setting past its review date turns the status at risk, with a reason in the
  client report too; malformed new files never stop the dashboard.

### Changed
- asdr Phase 0: step 5a "Where to start"; step 5c now asks thoroughness and
  model plan together; every agent invocation passes `model: <model_plan.py
  get <agent>>` in every skill; `log_agent_run.py --model` records the model
  actually passed. `paranoid` no longer means "pass opus everywhere"; it
  defaults to the `maximum` plan. Phase 1 step 0 does not ask about
  validation again when the start point already decided it.
- architect skill: points to the architecture-options, portability and
  configurable-decision gates of the full workflow (Phase 1b); longhorizon
  points users with non-ASDR documents to `/asdr`'s Build start.
- `test_efficiency.py`: the wiring check looks for `model_plan.py get` instead
  of `model: "opus"`.
- 337 tests (62 new), passing on Python 3.9, 3.11 and 3.13. Two independent
  review rounds before release found 16 defects and then one regression in
  the fixes (among them: a mid-Phase-1 resume that skipped design, step 6c
  unable to pass in the documented order, a catch-up that went stale when the
  documents revealed a UI or AI, one review decision standing in for two
  phases); all are fixed and each has a test.

### Not changed
- The product keeps its name, ASDR; `/asdr` and the plugin id are unchanged,
  so existing installs update in place.

## [3.9.0] — a native synthetic panel learned from MiroFish, and a MiroFish launcher

### Added
- **Synthetic panel (`scripts/panel.py`, new `panelist` agent).** The default
  simulation lane of `validate`; no install, no extra accounts, works in
  Cowork. A state machine like `next_action.py`: `panel.py next` does the
  deterministic work and prints the next agent task(s).
  - *Grounded in evidence first* (MiroFish's graph-from-documents idea, without
    the graph store): the business-analyst builds `roster.json` from the seed
    without its hypotheses and the desk evidence; every persona cites desk
    rows (D-xx), and any quote it carries must appear verbatim in
    `desk-evidence.md`.
  - *Quotas against the known lean of LLM respondents toward agreement:*
    ≥ 25% loyal to their current tool, ≥ 15% would never buy, ≤ 20% early
    adopters; every seed segment covered; few, strong traits.
  - *Independence:* each panelist reads ONE generated brief
    (`inputs/*.md`) — persona card, real quotes, the stimulus, the questions,
    the JSON to write — checked to contain no hypothesis id or wording.
  - *One round of social exposure, measured:* an anonymous, shuffled digest
    of round-1 objections (no ids, no tallies); round 2 records declared and
    actual stance changes. No further rounds.
  - *"What if" scenarios* (up to 3: price, pitch, a competitor's move) on the
    same personas; `deltas` report same-persona shifts and objection changes.
  - *Follow-up interviews* of the personas with the strongest, most varied
    objections (fixed probes; the persona sees its own earlier answers).
  - *Spread and flags:* intent, price reaction, objection categories, fair
    price median/range, by segment; flags `implausible_positivity`,
    `herding`, `homogeneous`, `thin_segments`; under `paranoid`, a second
    independent panel and `panel.py compare` → `panel_variance`.
  - *Persona walkthrough* (`panel.py walkthrough-next`): in `discover`/`asdr`,
    a segment-spread sample walks every process flow step by step; friction,
    severity and drop-offs go to `walkthrough-summary.md` for the
    product-manager. Skipped when no validated panel exists.
- **MiroFish launcher (`scripts/mirofish_stack.py`):** `doctor`, `up`,
  `status`, `logs`, `down`, `purge`. Clones the commit pinned in
  `upstream.json` (original `666ghj/MiroFish` = cloud, or
  `nikmcfly/MiroFish-Offline` = Neo4j + Ollama) into `~/.asdr/mirofish/`,
  builds it locally, and binds every port to 127.0.0.1 through a compose
  override (`!override`, Compose ≥ 2.24.4; verified with `docker compose
  config` against both pinned compose files). Keys only from environment
  variables, `.env` mode 600, output redacted, Neo4j password generated and
  reused. Offline on macOS uses the host's Ollama (Docker has no Apple GPU).
  `up`/`purge` refuse without `--yes`. ASDR still contains no MiroFish code.
- `check_updates.py`: `git-commit` pins — reports when upstream has moved
  past the pin and what changed; users move only when the maintainer
  re-pins.
- `scripts/validation_questions.py`: one set of questions, probes and closed
  lists shared by the panel and MiroFish, and the hypothesis-stripping and
  leak checks.
- Templates `panel-stimulus.md`, `panel-scenarios.json`, `panel-roster.json`;
  product-owner STIMULUS mode, business-analyst PANEL mode, critic checks
  for synthetic evidence; dashboard rows for desk evidence, roster and the
  walkthrough.

### Changed
- `validate`: desk evidence now runs before the panel (personas are built
  from it); lanes are desk + panel always, MiroFish optional (Claude Code
  only; in Cowork, desk + panel). Panel and MiroFish are treated as ONE kind
  of evidence everywhere: their agreement is not corroboration, absolute
  panel shares are not findings, scenario conclusions come from within-panel
  deltas, every raised flag is answered.
- `mirofish_validate.py`: sends `Accept-Language: en` (the original answers
  in Chinese by default); writes under the `mirofish` key of
  `.harness/validation.json` instead of replacing the file; records the
  flavour and capability differences when the launcher started it.
- `validate_verdict.py --type validation` checks `evidence_class` ∈
  {desk-only, panel+desk, mirofish+desk, panel+mirofish+desk}.

### Fits the 3.8 rules (this release sits on top of 3.8.0)
- `validate` uses 3.8's stage protocol (batches under lite/standard, no
  stage planner in standard, Opus everywhere under paranoid), logs every
  agent run with `log_agent_run.py` (panelists included), and decides with
  `decide.py` — the judge only when the critique has a Critical or High
  finding — then `check_required_changes.py`.
- `panelist` runs on Sonnet: many calls, no judgement. The sample run below
  used the session's model; the Sonnet panel is not yet measured against it.
- `estimate_run.py --mode validate --panel-size --scenarios --rounds
  --followups` prices a validation before the user picks the panel size;
  the panelist figure (~16k tokens per answer) is measured with the
  registered `panelist` agent. MiroFish runs are not counted (they spend the user's own LLM
  account).
- `detect_companions.py` reports both 3.8's cloud tooling and MiroFish.

### Fixed after the first real panel run
A full `validate` run on a sample idea ("a $19/month WhatsApp tool that
answers small clinics' patient enquiries after hours"): real desk research,
8 personas played by real Claude subagents, base + a $49 scenario, two
rounds, two follow-up interviews, then synthesis, critic and judge. The
judge returned a reasoned no-go with cheap real-world tests first. What the
run exposed, each now pinned by a test:
- **The roster planted the findings.** The critic showed that four persona
  cards stated attitudes ("will not let software talk to patients…", "a
  cheap tool reads as not enterprise-ready") that came straight back as the
  panel's top objections. `panel.py` now rejects attitude phrasings in the
  card fields (`OPINION_MARKERS`) and the business-analyst's PANEL mode says
  to describe situations, not attitudes. Re-running with corrected cards:
  the planted "another screen" and "not enterprise-ready" objections
  disappeared; trust in automated replies to patients came up unprompted in
  5 of 8 personas, so that theme survives the fix.
- **Answers to an old card were kept.** After the roster changed, earlier
  answers still counted. Briefs are now rewritten only when their content
  changes, and an answer older than its brief is asked again (`stale`).
- **Echo.** An objection that restates the persona's own card is the roster
  talking: `panel.echo` lists those personas and `echo_heavy` is raised at
  a third of the panel; product-owner and critic treat them as the desk row
  behind the card, not as panel evidence.
- **Noise in scenarios.** The $19 → $49 shift moved one persona in one run
  and a different persona the other way in the re-run. Each delta now
  carries `within_noise` (fewer than max(2, 15% of the panel) personas
  moved), reported as "no detectable difference".
- **A silent round 2.** No persona changed its mind after the digest, in
  either run. `static_round2` says so instead of letting stability read as
  conviction.
- Panelists wrote prices as text ("19"); `fair_price` and `changed` are now
  normalised instead of costing a re-run, and the brief says "plain number".
- Intent shares were identical across the two runs (4 maybe / 4 no) even as
  objections changed — confirming that the roster quotas set the shares and
  that absolute shares must not be read as findings.

### Fixed after an independent review
- Hypotheses could still reach a persona: ids spelt `H1`/`H-1`, paraphrases,
  the desk evidence's hypothesis column and Gaps section (which the roster
  builder read, and which "real quotes" were matched against), and the
  process flows in walkthrough briefs. Now: every brief is checked on every
  `next` (`FIX-LEAK`, with the source to fix); the roster builder reads
  `desk-for-roster.md` (no hypothesis column, no Gaps, no comments); voice
  quotes must come from the "What it shows" cells; stimuli with template
  comments or placeholders are refused. Zero false positives on the 52 real
  briefs from the sample run.
- A persona saw its own round-1 objection in "what other people said";
  round-2 digests are now per persona.
- Results stayed `complete` after the panel was reopened → `stale`.
- `walkthrough-next` crashed without a panel instead of printing SKIP (its
  test ran `init` first); `compare` accepted one panel twice; a removed
  persona survived in the digest and follow-ups; `--size` was not enforced;
  valid JSON of the wrong shape crashed `next`.
- Launcher: on Linux the default offline setup could not reach the host's
  Ollama (127.0.0.1-only) while `doctor` and `up` reported success — `up`
  now checks Ollama from inside the backend container and `doctor` explains
  the docker0 binding; the fork's NVIDIA reservation is dropped whenever no
  NVIDIA runtime exists (not only on macOS); `--pull-models` pulls inside
  the container in container mode; state is saved before anything can fail,
  `purge` cleans up folders, containers, volumes and built images even
  without state, and a folder at the wrong commit is moved to the pin.
- `localhost` vs `127.0.0.1` no longer hides which flavour is running, and
  `mirofish_validate.py`/`detect_companions.py` default to the launcher's URL.
- `fair_price` carries `would_pay_nothing` and a "not willingness to pay"
  label; "€1.200" reads as 1200.
- Template §7 lists every flag, the echo personas and within-noise deltas.
- Second review pass: the leak check now covers only what the team wrote
  (card, stimulus, flows), never the panel's own answers in round-2 and
  follow-up briefs — a persona raising a hypothesis unprompted is the signal,
  and an earlier version could block the panel with nothing to fix; "H1
  2027"-style half-years are not hypothesis ids; a stimulus that states the
  hoped-for outcome gets a clear "describe what it does" error; `purge` also
  removes the custom-tagged built image; container-mode `up` fails when the
  Ollama container has no models instead of reporting success;
  `scenarios.json` of the wrong shape is a fix, not a crash.

### Not done
- No run against a live MiroFish yet (needs the user's LLM/Zep keys or a
  machine that can run a local model). The launcher was exercised with
  stubbed `docker`/`git`; the overrides were validated with a real
  `docker compose config`, not a real `up`. `doctor` was run for real on a
  Linux sandbox (no Docker daemon, 8 GB RAM, no Ollama → three FAILs with
  fixes); not yet on a Mac.
- Panelist cost: the sample run invoked panelists as general-purpose agents
  (the `panelist` type was not registered yet), about 81k tokens each. The
  same brief through the registered `panelist` agent (Read/Write only) cost
  about 16k — the difference is the general-purpose agent's tool
  definitions. Always invoke panelists as the `panelist` agent: a 12-person
  panel with one scenario, two rounds and three follow-ups is ~39 calls,
  ~0.6M tokens for the panel (~3.2M the way the sample run did it).
  If `static_round2` keeps firing for an idea, re-run with `--rounds 1`
  and save the eight-to-twelve round-2 calls.

### The `validate` skill this release introduces (built first as an unreleased 3.8 branch)

#### Added
- **`validate` skill.** Tests an idea before any scoping: the product-owner
  writes a market seed (`docs/validation/seed.md`, template
  `templates/validation-seed.md`) with falsifiable hypotheses H-xx; two
  evidence lanes run in parallel — a MiroFish simulation and desk evidence
  (`docs/validation/desk-evidence.md`, real sources with URL and date); the
  product-owner synthesises `docs/00a-idea-validation.md` (template
  `templates/idea-validation.md`) with a `recommendation: proceed | pivot |
  stop` block; critic and judge decide (`docs/critique-validation.md`,
  `docs/decision-validation.md`). Offered once as step 0 of `asdr` Phase 1
  and Phase 1b of `discover`; a judge `no-go` stops before discovery. When
  `docs/00a` exists the brief, business case and roadmap read it.
- `scripts/mirofish_validate.py`: drives a user-run MiroFish backend over
  HTTP — ontology → graph build → simulation create/prepare/start (rounds
  capped, default 20) → wait until every platform has finished its rounds →
  fixed validation interviews with an evenly spread agent sample (one
  platform by default; a failed batch is recorded, not fatal) → close-env
  (then `/stop` after a grace period) → report, which MiroFish only writes
  for a finished run. Seed sections about hypotheses are stripped before
  upload and the uploaded copy is kept. Saves ids after every step, so
  `--resume` continues a run that hit its time limit; it falls back to the
  project status when a restarted MiroFish has forgotten a task, and never
  starts a run twice. Measured numbers go to `.harness/validation.json`
  (`validation:<key>`), written `incomplete` before anything is spent and
  `complete` at the end. Exit 2 unreachable, 3 a step failed or answered
  unexpectedly, 4 time limit. Tested against an in-process fake of the API
  that keeps the environment alive after the rounds, as MiroFish does.
- Dashboard: the validation documents appear under "Validation".
- `detect_companions.py` → `mirofish` (probes `$MIROFISH_URL/health`,
  default localhost:5001, 1.5 s; `MIROFISH_URL=off` skips).
- `validate_verdict.py --type validation`.
- product-owner: SEED, DESK and VALIDATE modes, with WebSearch/WebFetch.

#### Rules
- Simulated evidence is synthetic opinion from personas built from our own
  seed: it may surface objections and comparisons, never stand alone as
  demand ("weakly supported" at most); desk evidence wins disagreements;
  every validation ends with real-world tests and pass thresholds.
- Nothing is uploaded to MiroFish (and so to the user's LLM provider and Zep
  Cloud) without the user's yes; seeds never carry customer data,
  credentials or named private individuals.
- MiroFish is AGPL-3.0 and is never bundled, vendored or modified; ASDR
  only calls a separately running instance.

## [3.8.0] — leaner runs; microservices and cloud portability by the user's decision

### Efficiency
- **Every agent run is measured.** `scripts/log_agent_run.py` records tokens,
  time and model after each run (the Agent result's usage block) in
  `.harness/agent-runs.jsonl`; run metrics and the dashboard show cost by role
  and phase; going over budget turns the internal status "at risk".
- **Cost before choosing rigor.** `scripts/estimate_run.py` estimates agent
  runs, tokens (Opus / Sonnet) and hours for lite, standard and paranoid —
  and what 3.7 would have cost — for the project's shape (sprints, services,
  UI, AI, cloud; or system size for /assess). Phase 0 shows it; the user
  chooses; `--set-budget` writes the budget (+30%). Per-role figures come from
  the first /assess run where measured, and recalibrate from each project's
  own log.
- **Model tiering.** Opus for judgement roles; Sonnet for stage-planner,
  stage-qa, product-integrity-qa, planner, documentation and release-manager.
  `paranoid` forces Opus.
- **Batched stages.** Under lite and standard, consecutive stages with the
  same executor run as one agent run (the product-owner writes brief, business
  case and roadmap together) and one stage-qa run reviews the batch; standard
  no longer runs a stage planner. Estimated: about 30% fewer agent runs and 18%
  fewer tokens than 3.7's standard for a typical build (to be confirmed by the
  agent-run log on real projects).
- **The judge only when needed.** `scripts/decide.py` writes the phase
  decision when the critique has no Critical or High finding (Medium → required
  changes, Low → assumptions). `scripts/check_required_changes.py` replaces the
  judge's second round with a scripted check plus the orchestrator's spot checks
  — on the eShopOnWeb data it reached the judge's verdict in seconds.
- **/assess reviewers get a starting list of files.** `scripts/assess_scope.py`
  ranks files per area (shared core files, path and content signals, scanner
  hits, hotspots); on eShopOnWeb the lists covered 71% of what the reviewers
  cited at a third of the codebase each.

### Microservices and cloud
- **Architecture decision gate.** Before any design the solution-architect
  writes `docs/03c-architecture-options.md`: eight criteria scored with evidence,
  each option (modular monolith with service-ready boundaries, microservices,
  serverless-first) with pros, cons, business impact, build and run cost
  estimates and when it wins, a side-by-side table and a recommendation. The
  user decides; `validate_architecture_options.py` blocks design until then.
- **Portability decision with costs.** devops writes `docs/03d-portability.md`
  from a catalogue of 20 building blocks (portable choice, AWS, Azure, Google
  Cloud, local stand-in): strategies — portable core, native services behind
  adapters, single-cloud native — with monthly cost per cloud, the source and
  date of the prices, and a recommendation. The user picks the strategy and the
  production clouds; `validate_portability.py`.
- **Microservice rules.** `docs/03e-services.md` + `validate_services.py`: one
  owner per table, a tested `CT-xx` contract for every call and every consumed
  event, no synchronous cycles, every service runnable standalone with mocks of
  its neighbours, an adapter per building block for local and each production
  cloud. Contracts are testable items in `validate_product_map.py`. Standards
  in `templates/microservices/` (ports and adapters, outbox, idempotent
  consumers, health endpoints, OpenTelemetry, walking-skeleton first sprint),
  a Compose template with per-service profiles, and an IaC layout.
- **Test cloud chosen at the start.** Phase 0 asks which cloud ASDR deploys to
  for testing (AWS, Azure, Google Cloud or none). `cloud_preflight.py` checks,
  read-only, the CLI sign-in, Terraform/OpenTofu validation, Compose and
  settings. Deploys need the user's approval, use a least-privilege role, are
  tagged with a time-to-live and recorded by `cloud_env.py`; the dashboard flags
  any past its time-to-live, and the release gate refuses while one runs.
  `cloud_parity.py` proves every test that passes locally passes on the cloud,
  from the same commit.
- **The vendors' own agent tools.** `detect_companions.py` now reports the AWS
  MCP Server, the Azure Skills plugin / Azure MCP Server, Google Cloud MCP
  servers and the Terraform MCP server, plus the cloud CLIs; devops and
  security use them for current service names, prices and IAM guidance.
  ASDR never installs them.
- Agents: solution-architect (options, services), devops (portability, IaC,
  test environments), security-compliance (per-cloud IAM, network, service
  identity), critic (architecture and cloud checks), evaluator (standalone
  services, contract tests, cloud parity), generator (ports and adapters),
  planner (walking skeleton), risk-manager (cloud release blockers), judge
  (when it is invoked).

### Not in 3.8
- Exporting ASDR to Codex CLI and Gemini CLI: a later release (3.9 became idea validation).

## [3.7.0] — parity with the old system, a client status report, and /assess hardened by a real run

### Added
- **Parity gate (existing systems).** At the `/assess` hand-off the
  business-analyst writes `docs/02f-parity.md` (template `templates/parity.md`):
  every behaviour the client keeps is a `PAR-xx` item with a decision — `keep`,
  or `change` / `drop` with the client's approval (who, when, where). Tests
  capture what the user sees or gets with `parity('PAR-xx', value)` in
  Playwright, Cypress and Selenium. `run_tests.py --parity old --base-url <old
  test URL>` records the old system once as the baseline;
  `scripts/compare_parity.py` compares every later run with it after Ignore
  rules (field names, `timestamps`, `uuids`, `order`, `whitespace`, `case`,
  `numbers-in-ids`) and writes `docs/parity-report.md` with a diff per
  difference. A kept behaviour that differs fails the sprint and blocks the
  release; captures count only from passing tests; a value that changes within
  one run is "unstable"; comparing a URL with itself is refused. PAR items join
  the coverage rules (`validate_product_map.py`), facts (`facts:parity.*`), the
  dashboard's status rule, the critic's checks and the release notes.
- **Client status report.** `build_dashboard.py --audience client` writes
  `docs/dashboard/client/index.html` and `status-report.pdf` in your brand:
  the same facts and status rule in client wording, without agent activity,
  effort, git internals, local paths, internal questions (`log_question.py
  --client` marks the ones for the client), local or internal environments,
  internal links, hidden risks or process records. Never published, never
  sent by ASDR.
- `scripts/assess_scan.py`: a front-end library check (libman.json and CDN
  `<script>`/`<link>` tags, with the integrity flag, looked up in OSV npm →
  `evidence/osv-frontend.json`); NuGet packages read from the project files
  when a .NET repo has no lock file; a "What these scanners do not cover"
  section for the report's limits.
- `evidence/triage.json` (template `templates/assess/triage.json`): a verdict
  for every scanner hit; Part B shows the counts per tool.
- `opportunities.json` → `questions`: the report numbers them Q1, Q2 … in
  Part A and lists every as-is unknown in Part B.

### Changed (from the first full /assess run — eShopOnWeb, 15k lines of .NET)
- Reviewers run in parallel, so each writes its own `findings-<area>.json` and
  `technical-<area>.md`; the gate and the report merge them.
- Phase 5 starts with the solution-architect's "Options and effort" table:
  every finding from every register on one S/M/L scale and one rate, so the
  option totals can be reproduced. The first run's options left out the
  security and operations work.
- Phase 6 runs as numbered required changes (RC-01 …) with owners revising in
  parallel, the product-owner last, then a judge "Round 2" verdict.
- The orchestrator runs the evidence gate after every agent:
  business-analyst, solution-architect, critic and judge have no shell.
- Critic: duplicates across registers, severity disagreements between
  reviewers, options missing a register, a commitment the plan cannot keep,
  unstated scanner gaps. Product-owner: figures only from the architect's
  table, a commitment that promises only what the Now list delivers, numbered
  questions, short summary paragraphs. Security: triage file, look for
  constants, route authorisation and infrastructure network rules whatever the
  scans say.
- Hotspots need at least two changes; a file changed once was ranked first on
  its size alone.
- The report's method line states what access was NOT available (no running
  system, no data) instead of assuming it.
- The dashboard keeps a regression flagged until it is fixed.

### Fixed
- **The evidence gate accepted a finding if any one citation resolved.** Every
  `path:line` must now exist; `git: <commit> path:line` marks a file that
  exists only in history, and paths inside URLs are ignored.
- **A password reached the evidence folder** through jscpd clone fragments.
  Scanner output now keeps locations only (fragments, matched lines and
  gitleaks lines are stripped), and the gate harvests the credential values
  the source assigns and fails if any file under `docs/assess/`, evidence
  included, contains one — without printing it — plus a key/token/password
  pattern sweep of the evidence.
- Two reviewers filing the same issue went unnoticed: the gate lists likely
  duplicates (similar titles plus the same primary citation or most citations
  shared) for the critic.
- `--findings` naming one of the merged files counted it twice.
- osv-scanner treated a folder named `source` as its subcommand, and on a .NET
  repo without a lock file reported "0 vulnerable" after scanning nothing; it
  now reports that nothing was read, then scans the packages from the project
  files.
- `.cshtml`, `.razor` and project files were missing from the inventory.
- The report never showed the client the curated questions that Part A
  referred to; the triage table vanished when there was no scan summary.

## [3.6.0] — assess an existing system; a dashboard for every project

### Added
- **`/assess` skill.** For a client's existing system (legacy, poorly built or
  undocumented) whose owner will not sit through discovery again. Recovers the
  business processes (roles, features with a "used?" signal, flows, rules and
  where each is enforced, gaps, unknowns) and reviews architecture, code
  health, security, performance and operations, then writes a two-part report
  (business + technical appendix) with a Now / Next / Later roadmap, where new
  features fit, three options (fix in place, replace piece by piece, rebuild)
  and the questions only the client can answer. Phase 10 hands it into a build.
  Ground rules: authorisation recorded first, defensive only (no attack or
  load testing), every claim cites evidence, no secret value ever copied into
  a document, reports stay private.
- `scripts/assess_scan.py`: inventory plus whatever is installed — OSV-Scanner
  (npm audit fallback), Trivy, Semgrep (`p/default` + `p/owasp-top-ten`),
  gitleaks on code and history (`--redact`), lizard, jscpd and git churn —
  and hotspots (churn × complexity). A missing tool is reported, never fatal.
  Writes `docs/assess/evidence/scan-summary.{json,md}`.
- `scripts/validate_assessment.py`: every feature, rule, flow step and finding
  needs evidence that resolves (`path:line` that exists, or a `db:` / `api:` /
  `tool:` note, or a scanner output); fixed vocabularies for severity,
  confidence, area and effort; a pasted secret fails even without `--strict`.
- `scripts/build_assess_report.py`: branded HTML + A4 PDF. The health
  scorecard follows a stated rule (any critical → Critical, high → Weak,
  medium → Fair, low only → Good); every cost, time and effort figure carries
  an "estimate" label. Brand from `--brand`, `.harness/brand.json`,
  `~/.asdr/brand.json`, else neutral.
- `templates/assess/` (intake, as-is, findings, opportunities, technical,
  brand) and a worked sample in `examples/sample-app/docs/assess/`.
- REA (`rea-agents@6.4.0`) as an opt-in tool for live-only systems, only when
  the client's authorisation allows it.
- **Project dashboard** (`scripts/build_dashboard.py`) for every ASDR project,
  rebuilt at every phase and sprint end and on `/asdr status`: status (blocked
  > at risk > on track, with reasons), phases and overall progress, **expected
  delivery date with standard deviation and a 95% range** (from measured
  finish-to-finish sprint cycle time; no date before two sprints have
  finished), forecast drift, roadmap Gantt, features and their status
  (planned → in progress → delivered → verified), development speed, quality,
  open risks, decisions, every document (present / missing / not yet / only if
  needed, plus all others), environments with a live reachability check and
  test roles, repositories, links, every question asked and its answer, and
  activity. Regressions since the last build are flagged. Writes
  `docs/dashboard/index.html` and `dashboard.pdf` (A4, printable); a private
  claude.ai page is published from it.
- `scripts/log_question.py` (`.harness/questions.jsonl`) and
  `scripts/sprint_clock.py` (`.harness/sprint-clock.jsonl`; start / done /
  torn-down). `templates/dashboard.json` lists environments, repos and links —
  role names only, never credentials.
- PDF for every report: the test report now writes `test-report.pdf` beside
  its HTML. `report_style.to_pdf()` is the shared headless-Chrome exporter.

### Changed
- business-analyst, solution-architect, security-compliance, devops and
  product-owner gained an ASSESS mode; critic has mandatory assessment checks;
  generator writes characterisation tests before changing an existing system.
- evaluator stamps `sprint_clock.py done` on a pass; the orchestrator stamps
  `start` and `torn-down`, logs every question it asks, and asks for
  environments, repos and links during setup.
- discover, architect, riskgate and release rebuild the dashboard at the end.
- `init_asdr.py` seeds `.harness/dashboard.json` and `.harness/questions.jsonl`.

### Fixed
- The pasted-secret check scanned the JSON encoding of each item, where quotes
  are escaped, so `api_key = "…"` slipped through; it now scans raw values.

## [3.5.1] — every documented item tested, and proven at run time

### Added
- **Coverage of every testable item, per project.** `validate_product_map.py`
  now enumerates every id the project's own documents define — FR, NFR,
  acceptance criteria (`AC-<story>.<n>`), business rules, edge cases, each use
  case and each of its alternate/exception flows (`UC-xx.A1`, `UC-xx.E1`),
  every feature, every flow step and exception path — and requires a test case
  that names each one (new `Covers:` line on test cases; a journey names all
  its flow's steps, a step names its use case and features). Gaps are warnings
  while building and errors with the new `--require-coverage` (end of
  discovery) and at `--gate`. A Covers id no document defines is an error.
- **Runtime proof (markers).** New helpers `asdr-cover.ts` (Playwright),
  `asdr-cover.js` + `asdr-cover-plugin.js` (Cypress) and `asdr_cover.py`
  (Selenium): `flowStep('PF-02.3')`, `covers('AC-03.2', …)` and
  `metric(name, value, unit, budget)`. They write
  `<run>/coverage/<framework>.jsonl`; `run_tests.py` collects them into
  `summary.json` → `coverage`. The gate requires every step and exception path
  of every Must flow, and every item on each test case's Covers line, to be
  marked by a PASSING test, and lists any testable item no passing test
  reached. Markers from failing tests do not count.
- **Cross-role effects.** Features get an optional `Affects` column
  (`Team member`, or `Team member (on/off)` for a switch). The validator then
  requires a flow step where that role meets the effect, and test cases from
  that role's side — one for a plain effect, two (on and off) for a switch.
- **Measurements.** `metric(...)` values appear in the report's new
  Measurements section and in `facts:test_runs.metrics.<name>`
  (`within_budget`); coverage per kind in `facts:product_map.coverage.*` and
  `facts:product_map.counts.items_executed`.
- **Coverage matrix** in `docs/product-map.md`: per kind, every item with the
  test cases that name it, the passing tests that reached it and its status
  (tested / named, not reached / no test case).

### Changed
- business-analyst: acceptance criteria for both directions (untick, remove,
  off) and exact export content; Covers on every test case; role-side tests
  for cross-role features; runs `--require-coverage`.
- product-manager: fills Affects and adds the affected role's steps.
- critic: admin-only testing of a setting, one-directional criteria, fakeable
  expected results and unchecked Covers items are findings.
- evaluator: assertion depth ("what is the cheapest fake that still passes?"),
  markers placed after the assertion that proves them, coverage of the
  sprint's flows on the latest run.
- generator: calls the markers; drives cross-role tests as the affected role.
- devops: copies the cover helpers and registers the Cypress plugin.
- risk-manager / release-manager: unreached items or an NFR over budget keep
  a release below Production-ready; release checklist items for both.
- Templates: requirements (one bullet per id), use cases (labelled A1/E1),
  feature list (Affects), test cases (Covers, cross-role examples), process
  flows (cross-role steps, markers), e2e-testing (marker table).

### Fixed
- `UC-07.E1` was read as use case `UC-0` by the id parser.

### Sample (TaskBoard)
- Requirements rewritten with 22 acceptance criteria, NFR-02 (500 tasks in
  under 1 s), BR-01/02 and EC-01/02; new flow PF-05 "Team member tidies the
  board" (delete permission from the member's side, on and off).
- 28 test cases (was 21): member delete allowed (TC-22) and not allowed
  (TC-23), untick (TC-24), NFR-02 performance with a measured value (TC-25),
  keyboard-only use (TC-26), an admin's category reaching a member (TC-27),
  admins always deleting (TC-28); CSV export now checks the header and every
  row's category and status.
- Every test in all three frameworks carries markers: 81 of 81 items reached
  by a passing test.

## [3.5.0] — reviewed manuals, accessibility checks, saved logins, screen-change diffs

### Added
- **Manual wording is checked against the screen.** The tour helpers (all
  three frameworks) now record the text a person can read on each screenshot.
  `build_manual.py` fails when an explanation names a **button or label** that
  is not on that screen — the commonest manual error after a UI rename. Keys
  (**Enter**, **N**) are exempt; deliberate exceptions go under `"offscreen"`.
- **A person signs off the wording.** `build_manual.py --review-page` writes
  one page with every screenshot and its explanation per manual;
  `--approve` / `--flag` record the answer in `docs/manuals/review.json`, keyed
  by a hash of each explanation so later releases only ask about new or
  changed steps. Release builds use `--require-review`; the manuals state who
  reviewed them. The release skill publishes the review page privately and
  waits for the user.
- **Accessibility checks.** `checkA11y` (Playwright), `cy.asdrA11y` (Cypress)
  and `check_a11y` (Selenium) run axe-core's WCAG 2.1 A/AA rules at each
  journey screen and fail on serious or critical problems. `run_tests.py`
  adds them up (`summary.json` → `a11y`, `facts:test_runs.a11y.*`), the report
  opens with an Accessibility section, and serious or critical violations keep
  a release below Production-ready.
- **Test users and saved logins.** `app.seed_cmd` creates test users and data
  before the suites; config `env` passes credentials as `${VAR}` references.
  Playwright's `auth.setup.ts` signs in once per role and saves the session to
  `.harness/auth/`; tests that are not about signing in reuse it
  (`storageState`, `cy.loginAs`, `sign_in_as` — Selenium reuses the Playwright
  file). The folder is cleared every full run, git-ignored and never published.
- **Screen changes between releases.** `compare_screens.py` (zero-dependency
  PNG decode, Pillow when present) compares two screenshot folders and writes
  diff images with changed pixels in red. Each manual build compares with the
  previous version: changed steps carry a badge, `ui-changes.html` shows before
  / after / diff, and the release notes list every changed screen for the
  user to confirm.
- `LICENSE` (MIT) and `THIRD_PARTY_NOTICES.md` (Ponytail attribution for the
  build ladder; UI UX Pro Max, AX and the test tools as not bundled). Both ship
  in the `.plugin` file.

### Changed
- Cypress templates use the Cypress 16 APIs (`cy.env` for credentials,
  `Cypress.expose` for settings; `Cypress.env` was removed in 16) and open the
  browser at 1400×1000 so manual screenshots are 1280×800 like the other
  frameworks.
- Sample (TaskBoard 1.1.0): saved logins and accessibility checks in all three
  frameworks, TC-21 (WCAG on key screens), and three explanations corrected
  after review — two claimed other team members see the board, which this
  local-storage sample cannot do.

## [3.4.1] — CI fix and stable report name

### Fixed
- CI's "Cowork path" step ran `pytest`, which the plugin job never installs, so
  the 3.4.0 run failed there and skipped the release asset. It now runs
  `unittest`. Unit tests and the sample app in Playwright, Cypress and
  Selenium already passed on GitHub's runners.
- The private test-report page now always has the same name ("<Product> Test
  Report"), so every sprint and release updates one page instead of creating
  a new one per label; per-run repo pages no longer repeat the product name.

## [3.4.0] — end-to-end journeys, live browser tests, published results, user manuals

### Why
Products built through ASDR passed every sprint and still did not hang
together: each sprint proved its own pieces, and nothing described or checked
the whole path a user walks. 3.4 makes the journey a first-class artifact, makes
it the unit of planning and testing, and shows the result.

### Added
- **product-manager agent** (18th). Writes `docs/02c-features.md` (requirements
  by feature: priority, release, persona, flows, use cases, requirements) and
  `docs/02d-process-flows.md` (end-to-end flows with Mermaid diagrams, role
  handoffs, exception paths, and a PF-00 lifecycle map of how the flows
  connect). Templates `feature-list.md`, `process-flows.md`.
- **Test cases in discovery.** The business-analyst writes
  `docs/02e-test-cases.md` from the flows: a journey test case per flow, one
  per exception path, then functional/edge/nfr until every FR is covered.
  Automated tests carry the id in their title (`[TC-03] …`, `test_tc_03_…`).
- **`validate_product_map.py`** follows lifecycle → flow → step → use case →
  feature → requirement → test case → automated test → latest result and
  writes `docs/product-map.md` + `.harness/product-map.json`
  (`facts:product_map.*`). Errors name the gap: a Must feature no journey uses,
  a use case on no flow, a flow nothing leads to, a Must flow with no exception
  path, a flow with no journey test case. `--gate` requires passing results.
- **Flow-based sprints.** `sprints.json` entries carry `flows`; when the flows
  document exists, `validate_sprints.py` requires them and rejects a plan that
  leaves a Must flow undelivered. The planner slices sprints through whole
  journeys, sprint 1 being the entry journey working end to end.
- **Browser testing in three frameworks.** `templates/e2e/` ships Playwright
  (default), Cypress and Selenium (pytest) setups that write to one run folder.
  `run_tests.py` runs every suite in `.harness/test-config.json`, starts the
  app once, parses all JUnit, links each test to its screenshots, videos and
  traces, and writes `summary.json` (`facts:test_runs.*`). A suite with no
  results counts as failed. `--live` runs headed and slowed down so the user
  watches; with no screen (Cowork sandbox, CI, SSH) it records video instead
  and says so.
- **Published results, private by default.** `publish_test_report.py` writes
  `docs/test-reports/<label>/` with evidence and a history page, plus a
  single-file copy for a private claude.ai Artifact. `.harness/publish.json`
  (seeded by init) keeps GitHub Pages off unless the user turns it on.
  `templates/ci-asdr.yml` runs the suites in CI, uploads artifacts, and has a
  Pages job gated on that flag.
- **User manuals with real screenshots.** Manual tours call
  `manualStep` / `cy.manualStep` / `manual_step`, which outline the element in
  red and record the step with URL and commit. The documentation agent writes
  `docs/manuals/manual.json`; `build_manual.py` builds HTML + PDF manuals per
  persona (Getting started, Advanced) and per tier (Beginner, Everyday user,
  Power user, Administrator), with a version/commit banner and "What is new"
  from the changelog. It refuses screenshots from a different commit.
- **`run_metrics.py`** → `docs/run-metrics.md`: agent invocations, evaluations
  and negotiation rounds per sprint, stage QA rounds, context-pack sizes, test
  runs.
- **`examples/sample-app/`** (TaskBoard): product docs 02–02e, 20 test cases,
  [TC-xx] tests in Playwright, Cypress and Selenium, five tours, manual.json.
  Its manual screenshots exposed a real bug (the top bar showed "Sign out"
  before sign-in), now covered by TC-13.
- **`.github/workflows/ci.yml`**: unit tests, `claude plugin validate`, the
  Claude Code marketplace install (with ui-ux-pro-max) and the Cowork manifest
  rules, the sample app in all three frameworks with report and manuals as
  artifacts, and a `.plugin` file attached to the GitHub release on a version
  tag. Nothing is submitted to a public marketplace.

### Changed
- evaluator: contracts for flow-delivering sprints must include the flows'
  journey and exception test cases; every sprint runs `run_tests.py` and the
  product map (a flow that was proven and no longer is, is a regression), and
  publishes the report.
- generator, devops, documentation, critic, product-integrity-qa,
  risk-manager, release-manager, and the asdr/discover/architect/longhorizon/
  riskgate/release skills wired to the above. Risk: a failing Must journey →
  Not ready; an unproven one caps at MVP-ready.
- `skills/asdr/SKILL.md` moved the file map, stage table and companion rules to
  `skills/asdr/references/` (2,893 words, from 3,247, with the new stages).
- `init_asdr.py` copies template folders (`templates/e2e/`) and seeds
  `publish.json`.
- UI UX Pro Max re-pinned to upstream `477bcb2` (2.13.0); the design-system
  wrapper was smoke-tested against it.

## [3.3.2] — ASDR loads in Cowork again

### Fixed
- 3.3.0 and 3.3.1 did not load in Cowork: `/ai-software-delivery-room:asdr`
  reported "isn't installed in this session" and no ASDR agents appeared.
  `plugin.json` declared `dependencies: ["ui-ux-pro-max"]`; Cowork installs
  the plugin outside the `asdr` marketplace, cannot resolve that
  dependency, and skips the plugin ("will not load without it"). The
  dependency now lives only on the ASDR entry in `marketplace.json`, where
  Claude Code still installs it automatically. In Cowork the design-system
  stage uses the hand-written template unless UI UX Pro Max is added
  separately. `tests/test_manifests.py` forbids `dependencies` in
  `plugin.json`.

## [3.3.1] — manifest description within Cowork's 500-character limit

### Fixed
- `plugin.json` `description` was 584 characters. Claude Code's validator
  accepts that; Cowork's does not ("Plugin description must be at most 500
  characters") and refused the 3.3.0 package. Now 485 characters, same
  content. `tests/test_manifests.py` enforces the cap on `plugin.json` and
  every `marketplace.json` entry, and checks skill versions match the
  manifest and that no hooks ship. No functional change.

## [3.3.0] — agent runtime tiers, design-system stage, companion detection

### Added
- `docs/04-agent-design.md` §13 **Runtime and deployment**: a tier decision
  table per agent (T1 function / T2 container worker / T3 sandboxed actor
  runtime) and four runtime blocks per agent — Task, Workspace, Gateway,
  Model — the primitives of AX (google/ax), used as the design vocabulary
  for every tier. devops consumes Task + Model + topology; security-compliance
  consumes Gateway (default-deny egress allowlist, gateway-injected secrets).
- `templates/agent-runtime.yaml` — T3 reference manifest in AX `v1alpha1`
  schema; devops writes `deploy/agents/<agent>.yaml` per T3 agent.
- `design-system` stage (row 5b, `docs/03b-design-system.md`,
  `templates/design-system.md`) — runs after architecture when the product
  has a UI surface. Its §9 checklist becomes UI sprint contract criteria.
- `scripts/detect_companions.py` — Phase 0 detection of UI UX Pro Max,
  Ponytail, Graphify and RTK → `.harness/companions.json`, with warnings.
- `scripts/uupm_design_system.py` — drafts 03b via UI UX Pro Max when
  installed (exit 2 when not → hand-written from template).
- `docs/COMPANIONS.md` — install and scoping notes; the Ponytail
  `PONYTAIL_SUBAGENT_MATCHER='^generator$'` requirement; why RTK is not used.

### Changed
- critic: mandatory findings for §13 (unjustified T3, untrusted code at T1,
  missing allowlist, secret values) and for 03b (fit vs brief, contrast).
- generator: UI sprints copy 03b §9 into the contract; Ponytail rules —
  YAGNI objections belong in NEGOTIATE, a ratified criterion is never
  skipped.
- devops inputs now include 04; release gate validates `deploy/agents/*.yaml`.
- `init_asdr.py` creates `deploy/agents/`; `CLAUDE-template.md` gains
  Companions / Design system / Agent runtime tiers lines.

### Added — packaging and updates
- `.claude-plugin/marketplace.json` (the `asdr` marketplace, added in 3.2.1)
  now lists companions: `ui-ux-pro-max` is a declared dependency of ASDR
  (installs with it, pinned by SHA); `ponytail` is listed but disabled by
  default. `plugin.json` gains `dependencies`, `hooks`, `license`, `repository`.
- `scripts/check_updates.py` + `scripts/upstream.json`: compares installed
  vs upstream versions for ASDR, UI UX Pro Max, Ponytail and Graphify,
  pulls each changelog's top section as "what it adds", and reports. It
  runs only as Phase 0 step 5 of `/asdr`, where the orchestrator asks per
  item before running the update. (The patch also shipped a once-a-day
  SessionStart hook; it is deliberately not included — ASDR makes no
  network call outside a run. `check_updates.py --hook` still exists for
  anyone who wants to wire their own.)
- `templates/build-ladder.md`: the generator's BUILD-mode ladder, adapted
  from Ponytail (MIT), so the plugin is no longer needed for the generator.
- `docs/PUBLISHING.md`: marketplace layout, release checklist, tagging,
  re-pinning companions, directory submission.

### Not added (deliberately)
- RTK: rewrites the evaluator's evidence commands; detected and warned only.
- Vendoring any companion: all MIT, all fast-moving; detection over forks.

### Upgrading from 3.2.x
- `claude plugin update ai-software-delivery-room@asdr` leaves the plugin
  "failed to load" until the new dependency is installed once:
  `claude plugin install ui-ux-pro-max@asdr`. Fresh installs are unaffected.

### Merge note
- Built against 3.2.0 and merged onto 3.2.2: every 3.2.1/3.2.2 fix is kept.
  The v1.1 `.claude/` mirror copies the patch re-synced were removed in
  the repo cleanup after 3.2.1 and stay removed; `docs/PUBLISHING.md` no
  longer has a "resync mirrors" step.

## [3.2.2] — drop the v1.1 push script; two more bound phrasings

### Removed
- `scripts/github_push.sh` — the v1.1 one-time "create the GitHub repo" script.
  `init_asdr.py` copies every file in `scripts/` into each project's
  `.harness/scripts/`, so it was landing in every project that used the
  plugin. The repo exists; the script had no remaining purpose.

### Changed
- `preflight_contract.py` — `over <n>` and `above <n>` count as bounds
  (`over 300ms` now needs a `facts:` key). The lookahead requires a digit, so
  "over HTTPS on port 443" is untouched. One test added (23 total).
- `.gitignore` — reduced to `.harness/` + `sprints.json` (runtime state if
  `init_asdr.py` is ever run inside this repo) plus env/Python/OS noise; the
  v1.1 `.harness/contract.md` / `.gitkeep` entries referred to files that no
  longer exist here.
- Manifest, marketplace entry and all skills at 3.2.2.

## [3.2.1] — context-discipline fixes found by testing the v3.2 scripts

A test pass over the five v3.2 scripts (fake repo with git history, tests, a
contract, a sprint and an eval report; every check exercised on a true
positive and probed for false positives) found the two headline features
weaker than documented. No crashes; no change to agent roles, verdict formats
or state-file schemas. `tests/test_context_discipline.py` now covers all of it
(`python3 -m unittest discover tests`).

### Fixed — `build_graph.py` (blast radius)
- Imports that climb a directory (`../db/lead`) never resolved: the path was
  "normalised" with `.replace("./", "")`, turning `src/voice/../db/lead` into
  `src/voice/.db/lead`. Now `posixpath.normpath`. Every cross-module edge and
  every test-file→source edge was missing from the blast radius.
- Python imports never resolved (`from .utils import x`, `from pkg.utils import
  x`, `import pkg.utils`): only `./`-style specifiers were handled. Relative
  dots now climb directories; absolute dotted names are tried from the repo
  root and from each ancestor of the importer (`src/` layouts). Python
  projects previously produced a graph with zero edges.
- `facts:<key>` citations are stripped before file-path scanning, as the pack
  builder and the linter already did; a phantom `diff.src/...` file no longer
  appears in `file_to_criteria` / `file_to_requirements`.

### Fixed — `preflight_contract.py` (satisfiability linter)
- **P06** cost-metric words are word-bounded. "already" matched `read` and
  "called" matched `call`, so ordinary criteria were rejected as cost floors —
  costing exactly the negotiation round the linter exists to save.
- The comparator list gains `under`, `within`, `below`, `less than`, `more
  than`, `up to`, `no later than`, `not exceed`, `maximum of`, `minimum of`,
  `no fewer than`. The contract template's own GOOD example ("under 300ms")
  passed pre-flight with no fact key; the measurement rule is now enforced
  for those phrasings.
- **P01** no longer treats identifiers as measurements: `HTTP 404`, `status
  code 201`, `port 5432`, `error 500`, `v2.1` need no `facts.json` key.
- **P09** new-file budget counts source files only (`.md`, `.json` and URLs
  are not fixture-isolation risk) and URLs are stripped before any path scan.
- **P05** regex literals may not start after a path character, so
  `src/4/legacy.ts` is no longer read as the regex `/4/`.

### Fixed — `emit_facts.py` (measured facts)
- `diff.<file>.net_nonblank` measured the WHOLE FILE, not the change: a
  5-line edit to a 400-line file reported 400, so every "diff budget" was a
  file-size cap. It is now `added_nonblank − removed_nonblank` computed from
  `git diff -U0` hunks (the unit `CONTEXT_ARCHITECTURE.md`'s own example
  uses: 112 added, 8 removed, net 104). The whole-file count is kept as
  `file_nonblank`; `added_nonblank` / `removed_nonblank` are also emitted.
- Untracked new files are included (`git ls-files --others`), flagged
  `"untracked": true`. A generator's brand-new module was invisible to the
  diff until staged.
- `.harness/` bookkeeping (contracts, packs, facts.json itself) is skipped in
  the diff, as the census already skipped it.
- `--base` defaults to `sprint_base_ref` in `.harness/progress.json`, then
  `HEAD` with a note. The v3.2 generator commits its own work, after which a
  diff against `HEAD` is empty and every `facts:diff.*` citation dangles.
  `next_action.py`'s activate step, `init_asdr.py`, `templates/progress.json`
  and the `asdr` / `longhorizon` skills now carry `sprint_base_ref`.

### Changed
- `make_context_pack.py` recognises the new diff keys in citations.
- `.claude-plugin/marketplace.json` added: the repo is its own one-plugin
  marketplace (`asdr`), so Claude Code installs it with
  `claude plugin marketplace add Mbialuddinkhan/ai-software-delivery-room`
  + `claude plugin install ai-software-delivery-room@asdr`.
- README package contents list the v3.2 scripts, `CONTEXT_ARCHITECTURE.md`
  and the test file; manifest and all skills bumped to 3.2.1.

### Removed (repo hygiene, after the v3.2.1 tag)
- `.claude/` (14 v1.1 agents, 6 v1.1 slash commands, 1 v1.1 skill) and the
  root `.harness/` (v1.1 template copies, three of them stale) — not part of
  the plugin, and opening this repo in Claude Code loaded the v1.1 agents as
  project-level agents. The root `CLAUDE.md` (v1.1 charter for a *project*)
  is replaced by a charter for this *repository*: layout, change rules,
  release steps. Plugin content is unchanged; the version stays 3.2.1.

## [3.2.0] — context discipline: measured facts, contract pre-flight, context packs

Answers a field review of a real 7-sprint run in which 50 subagent runs consumed
more effective tokens than every directly-executed action combined, and the
largest constraint was environmental: agents were asked to measure things they
had no ability to measure.

### Added — Phase 0: measurement (nothing else works without this)
- **`scripts/emit_facts.py`** → `.harness/facts.json`, the single source of
  MEASURED truth: per-file diff (`added`/`removed`/**`net_nonblank`**), file
  census, per-file assertion counts, test results, commit. Runs where a shell
  exists (CI or an operator terminal). Degrades gracefully — missing git, tests
  or coverage yields a null section and a note, never a crash.
- **Measurement rule, enforced:** *no numeric criterion may be graded except by
  citing a key in `facts.json`* — written `facts:<dotted.key>`. This
  mechanically kills the "generator transcribes `git diff --stat`" criterion
  class, which grades the environment rather than the code.
- **Diff budgets now count non-blank, non-comment lines.** Raw diff lines count
  the documentation the method itself mandates (observed: 221/67/32/9/44 →
  112/28/9/1/25).

### Added — Phase 1: contract satisfiability
- **`scripts/preflight_contract.py`** — runs BEFORE the evaluator sees a draft.
  `validate_contract.py` checks shape; this checks whether a correct
  implementation could satisfy the contract at all. Ten checks, every one a
  violation class observed in the field: unmeasurable numbers (P01), unresolved
  `file:line` (P02), zero-delta over a file the same criterion edits (P03),
  self-report of command output (P04), a regex forbidding a literal another
  criterion requires (P05), a floor on a cost metric a better build would fail
  (P06), absolute clock vs clamped fixture (P07), >7 criteria naming one
  integration file (P08), new-file budget (P09), undefined derivation (P10).
  Unsatisfiable first drafts were costing a full negotiation round each.

### Added — Phase 2: the knowledge/dependency graph and context packs
- **`scripts/build_graph.py`** — extends `.harness/traceability.json` with a
  `graph` section: modules, imports, **dependents (blast radius)**,
  file→criteria, file→requirements, and **fixture_risk** (global-unique keys,
  contended keys, FK-ordered deletes, `afterAll` cleanup, absolute counts).
  A script cannot hallucinate an edge; an agent can.
- **`scripts/build_digest.py`** → `.harness/state-digest.md`, one page of
  authoritative state derived from state files — replaces re-reading a stack of
  eval reports. Machine-generated, so a wrong digest is a findable bug rather
  than a silent hallucination copied into every brief.
- **`scripts/make_context_pack.py`** → `.harness/packs/pack-<sprint>-<role>.md`:
  files in scope, blast radius, requirements served, fixture risks, the relevant
  facts slice and the last verdict — **paths and fact keys, never file
  contents**. **Exits 1 when the pack exceeds its budget**, which converts
  context overflow from a silent mid-task failure into a cheap planning-time
  signal: the task is too big, split it — never raise the budget.

### Changed
- `agents/generator.md` — reads its context pack first as task scope; numeric
  criteria must cite `facts:`; runs both validators before handoff; never
  derives a number by reading files; **commits its own work before stopping**
  (uncommitted output from an exhausted agent was the most expensive observed
  failure mode).
- `agents/evaluator.md` — reads pack + facts; grades numeric criteria from the
  cited fact key and never re-derives; a numeric criterion with no fact key is
  ungradeable (contract defect, not an estimate); runs `preflight_contract.py`
  at ratification, ERRORs are automatic `revision-requested`.
- `agents/stage-qa.md` — pack-aware; numeric checks from `facts.json` only.
- `skills/asdr`, `skills/longhorizon` — new **Context discipline** section:
  `emit_facts` → `build_graph` → `build_digest` → `make_context_pack` before any
  dispatch; pre-flight feedback to the generator before the evaluator is invoked.
- `templates/contract.md` — the measurement rule at the point of authoring.
- `scripts/init_asdr.py` — seeds `.harness/packs/` and prints the context-discipline
  sequence.

### Deliberately not built
A central "development manager" agent that holds the knowledge graph. Subagents
share no context, so the manager's knowledge must be serialised into every
prompt anyway (no saving); it adds a coordination hop; it becomes the broadest,
most-called agent in the system; and it centralises hallucination — today two
roles derive independently and disagree, which is exactly the check that caught
a cap wrong by 60. The graph is therefore a **file a script maintains**, not an
agent that remembers. A thin dispatcher role remains a candidate for a later
version, once the measured effect of Phases 0–2 is known.

## [3.1.0] — product integrity, richer discovery, git workflow, live E2E

Attacks feature drift: keeps the built product provably in sync with the
vision, roadmap, brief, business case, use cases, and requirements.

### Added — product-integrity QA
- **`agents/product-integrity-qa.md`** — independent product-level QA (opus).
  Runs after discovery (seed), after each sprint (update + drift check), and at
  the final gate (full verification). Emits an `in-sync | drifted | broken |
  incomplete` integrity verdict the risk-manager honors.
- **Living traceability matrix** — `.harness/traceability.json` (seeded by
  `init_asdr.py`) + readable mirror `docs/traceability.md`, mapping outcome →
  requirement → use case → sprint → criteria → tests → status.
- **`scripts/validate_traceability.py`** — mechanically flags uncovered
  requirements (at the gate), orphan sprints, uncovered use cases, `broken`
  rows, and **drift** (a requirement's text changed after a sprint built to it,
  detected via a stored hash). `--gate` and `--requirements` modes.
- **`scripts/validate_verdict.py`** — extended with `--type integrity`.
- **Drift handling**: on drift, the run STOPS and surfaces the exact
  requirement(s); only on your approval do product-owner + business-analyst
  update every affected strategic doc, then the matrix is re-baselined.

### Added — cross-sprint regression + live E2E
- The **evaluator** now re-runs the ENTIRE accumulated test suite each sprint
  (including the Cypress/E2E suite); a previously-passing test that now fails
  blocks the sprint. The full suite runs again at the release gate.
- **`templates/e2e-testing.md`** + devops scaffolding: **Cypress** with
  `video: true` and screenshots so you can watch the tests run
  (`cypress open` / `run --headed` locally, headless with artifacts in CI).

### Added — richer discovery (first-class, traceable)
- **`templates/roadmap.md`** (`docs/00b-roadmap.md`, product-owner),
  **`templates/business-case.md`** (`docs/01b-business-case.md`, product-owner),
  **`templates/use-cases.md`** (`docs/02b-use-cases.md`, business-analyst).
  Kept in sync on approved scope changes.

### Added — git & repository workflow
- **`templates/git-workflow.md`** (`docs/07-git-workflow.md`, devops):
  branching strategy, Conventional Commits, per-sprint PR + required checks,
  what-to-commit, branch protection, SemVer tagging.

### Changed
- `agents/{product-owner,business-analyst,evaluator,risk-manager,devops}.md`,
  `skills/{discover,architect,asdr,riskgate}` wired to the above.
- `scripts/init_asdr.py` seeds `.harness/traceability.json`.

## [3.0.0] — universal triad with a rigor dial

Adds independent per-stage review: every authoring stage runs as
stage-planner → specialist executor → stage-qa, so no agent signs off its own
work. See `TRIAD_ARCHITECTURE.md`.

### Added
- **`agents/stage-planner.md`** — generic per-stage planner (opus): turns a
  stage's goal, inputs, and template into an observable acceptance checklist.
- **`agents/stage-qa.md`** — generic independent reviewer (opus): grades the
  artifact against the plan, returns `pass` or `revise` with evidence; never
  grades its own work.
- **`scripts/stage_status.py`** — per-stage driver: reads state from disk and
  prints the next action (PLAN / EXECUTE / QA / FORCE-ACCEPT / DONE), with a
  capped revise loop so a stage cannot stall. Supports `--no-plan` (light mode).
- **`templates/plan.md`, `templates/qa-report.md`** — the triad artifacts.
- **`scripts/validate_verdict.py`** — extended with `--type qa` (pass|revise).
- **Rigor dial** in `.harness/progress.json` → `rigor`: `paranoid` (full triad
  everywhere), `standard` (full triad on high-stakes stages, light elsewhere),
  `lite` (no per-stage triad — identical to v2.1). `scripts/init_asdr.py` seeds
  it and the new `.harness/plans` and `.harness/qa-reports` directories.

### Changed
- The `asdr`, `discover`, `architect`, `riskgate`, and `release` skills now
  drive each authoring stage through the triad protocol per the rigor dial.
  The cross-document critic and the judge are kept in every mode; gate roles
  (critic, judge, risk-manager) are not wrapped in a triad — they are the
  independent review, terminated by their mechanical validators.

### Compatibility
`lite` reproduces v2.1 exactly; upgrading changes nothing until you turn the
dial up. Every new loop is bounded by the same on-disk circuit-breaker pattern
as the sprint loop.

## [2.1.0] — quality uplift, Opus 4.8 tuning, and reliability fixes

### Fixed (reliability)
- **Circuit breakers no longer depend on the model remembering to increment
  counters.** `scripts/next_action.py` now derives the per-sprint `attempt`
  count from eval-report files on disk and the `negotiation_rounds` count from
  `generator negotiate-<sprint>` lines in the trace log, combining each with
  the `progress.json` ledger via `max()`. The "too many attempts → split" and
  "too many rounds → force-ratify" safeguards can no longer be silently
  disabled by a missed manual increment. Covered by 11 state-transition tests.
- **`scripts/validate_contract.py`** — corrected the "7 x 3 = 21" comment; the
  category minimums sum to 20. No behavior change.
- **`templates/contract.md`** — the done-definition's "no console/runtime
  errors" is scoped to "the surfaces this sprint touches," so it is testable
  on back-end sprints.

### Added (rigor)
- **`scripts/validate_verdict.py`** — validates the judge decision, evaluator
  eval report, and risk-manager risk review fenced blocks
  (`--type decision|eval|risk`): required fields present, headline value is a
  real enum value (not the template's "a | b | c"), no surviving placeholders.
- **`scripts/validate_critique.py`** — enforces critique structure, that
  `findings_total` matches the actual finding count, that severity counts sum
  correctly, and the ≥8-findings floor with a `shortfall_justified` escape
  hatch for genuinely small doc sets.
- Both validators are wired into the `discover`, `architect`, `riskgate`, and
  `asdr` skills at the points where the orchestrator reads those blocks.

### Changed (quality & Opus 4.8 tuning)
- **All 14 agents** gained a shared Operating Standard: reason before
  committing a binding decision, read inputs in parallel, quantify or cite
  every quality claim, and self-verify against the template and role invariant
  before stopping.
- **Model routing:** the adversarial and architecture gates (evaluator,
  critic, judge, risk-manager, solution-architect, ai-architect,
  security-compliance) are pinned to `opus`; builders and writers stay
  `inherit`.
- **Per-agent specifics:** evaluator writes each criterion's cheapest
  fake-PASS then defeats it; critic treats 8 findings as a floor not a target;
  judge self-checks its verdict block against its findings; generator
  self-reviews the diff against the contract before handoff; planner
  self-checks each sprint; product-owner requires quantified success metrics;
  business-analyst adds a closing traceability check; solution-architect
  reasons through key trade-offs and records rejected ADR options; ai-architect
  adds concrete examples and a least-privilege self-check; security-compliance
  gains a design-vs-release path map pinning `docs/09-security-review-final.md`;
  risk-manager adds a test floor, parallel reads, and block self-consistency;
  release-manager pins the security-review filename and cross-checks the
  CHANGELOG against sprints.json; documentation runs a final README walkthrough.
- **`templates/contract.md`** — added "writing good criteria" guidance
  (quantify or cite; write the cheapest cheat then defeat it) with BAD/GOOD
  examples.
- **`templates/critique.md`** — added the `shortfall_justified` field.

### Changed (fewer false stops)
- **`scripts/validate_sprints.py`** — the technical-term denylist is now
  high-precision: removed the documented false-positive words (queue, cache,
  python), added missing real tech (supabase, prisma, kafka), and fixed the
  sentence counter so version strings like "v2.0" aren't miscounted.
- **`skills/architect` and `skills/asdr`** — AI-feature detection now judges by
  meaning, not a literal keyword grep, so features like "semantic search" or
  "smart recommendations" correctly pull in the AI architect; a genuine
  no-AI finding must be stated, not skipped silently.

### Compatibility
Drop-in. No paths, category names, verdict-block formats, validator contracts,
or state-file schemas changed. A project mid-run stays valid after the swap.
