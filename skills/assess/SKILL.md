---
name: assess
description: >
  Use this skill when a client already has a system — legacy, poorly built or undocumented — and wants it
  understood without sitting through discovery again: recover its business processes, review architecture,
  code health, security, performance and operations, and deliver a two-part report (business + technical)
  with a roadmap, options and new-feature fit, then hand it into a build. Trigger phrases: "assess this
  system", "audit our existing app", "review this codebase", "legacy system", "take over this project",
  "what's wrong with our software", "modernise".
metadata:
  version: "3.9.0"
---

# Assess — understand an existing system and say what to do with it

The client hands over a system and does not want to explain it again. Recover
what it does for the business and what state it is in, from evidence, and turn
that into a report they can act on. The client confirms a draft and answers a
short list of questions instead of sitting through weeks of workshops.

Subagents share none of your context: every invocation prompt must contain the
input paths, the output path and the template path.

**You run the evidence gate, not the agents.** business-analyst,
solution-architect, critic and judge have no shell. After every agent
returns, run `validate_assessment.py --strict` on what it wrote and send
every ERROR back to that agent before moving on.

**What to expect** (first full run, eShopOnWeb: 15k lines of .NET, source
only): about 2 hours end to end, 13 agent runs, about 3.5M subagent tokens;
45 findings after challenge; Part A 9 pages, Part B about 50. Tell the user
before starting on a larger system, and split it by module (Phase 3).

**Cost (v3.8).** Before Phase 1, show the user `python3
.harness/scripts/estimate_run.py --mode assess --kloc <thousands of lines>`
and confirm the rigor (`lite` skips the revision round; `paranoid` adds a
judge on every round), then `--set-budget`. After EVERY agent run, log it:
`log_agent_run.py --agent <name> --phase assess --model <model> --usage
"<the Agent result's usage block>"`; on OVER BUDGET stop and ask.

**Ground rules (not overridable):**

- **Authorisation first.** Record who authorised the assessment, of what, and by
  which document before reading anything. No authorisation → stop.
- **Defensive only.** Read code, configuration, git history and data; use the
  running app the way each role normally would. No attack or exploitation
  testing, no load testing, nothing against production, unless the client's
  written authorisation explicitly covers it.
- **Evidence or it does not ship.** Every feature, rule, flow step and finding
  cites `path:line`, `db:`, `api:` or `tool:` evidence.
  `validate_assessment.py --strict` blocks the report otherwise.
- **Never copy a secret into a document.** Cite where it is, not what it is.
- **Private.** The report describes a client's weaknesses. Give the user the
  PDF to share; never publish it as a public page. Make a private page only if
  the user asks.
- **Confidentiality.** The client's code is read by the model. Confirm the NDA
  and the client's consent at intake; for strict clients, suggest running
  Claude through their own cloud (Bedrock or Vertex).

## Phase 0 — Initialise

1. Resolve PLUGIN_ROOT (two levels above this skill's base directory).
2. `python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`
3. `mkdir -p docs/assess` and copy `intake.json`, `as-is.json` and
   `opportunities.json` from `.harness/templates/assess/` there as starting
   points (do not overwrite existing files). The findings and technical
   templates stay in `.harness/templates/assess/`: each reviewer writes its own
   `findings-<area>.json` and `technical-<area>.md` (Phase 4).

## Phase 1 — Intake and authorisation

Ask the user, in one AskUserQuestion round where possible:

- client and system name, and where the source is (path or repository);
- what access exists: source code, a test environment with one login per role,
  the database (structure, plus anonymised data if possible), logs or tickets,
  or only the live system;
- who authorised the assessment and the document (SOW, e-mail);
- whether live checks beyond normal use are authorised (default: no);
- confidentiality: NDA in place, consent to send code to the model provider.

Write `docs/assess/intake.json` (template fields). Record every question and
answer: `python3 .harness/scripts/log_question.py --q "<q>" --a "<a>" --phase intake --asked-by assess`.

Credentials for test logins stay in environment variables (`${VAR}`); never
write them into any file.

## Phase 2 — Inventory and scanners

    python3 .harness/scripts/assess_scan.py --target <source path> --out docs/assess/evidence

It runs whatever is installed — OSV-Scanner (dependencies; for .NET without a
lock file it reads the packages from the project files), Semgrep, gitleaks
(code and history, redacted), lizard (complexity), jscpd (duplication), git
churn, and a front-end check (libman.json and CDN `<script>`/`<link>` tags,
looked up in OSV) — and writes `evidence/scan-summary.md`. Show the user its
tool table. A missing tool is reported, not fatal; tell the user what
installing it would add. The evidence keeps locations only: copied code
(clone fragments, matched lines) is stripped, because it can carry a password.

Scanner hits are not findings. Precision was about 40% on one codebase and
over 90% on another, and recall was poor on both: hard-coded keys, open
database firewalls and authorisation flaws were found only by reading the
code. Every hit is triaged in the code in Phase 4, and the summary's "What
these scanners do not cover" goes into the report's limits.

**No source code** (live system only): skip the code scanners. Phase 3 then
works from the running app as each role and its network traffic, and confidence
is lower. REA (an optional reverse-engineering tool, `npx rea-agents@6.4.0`) can
map a shipped front-end bundle or compare old and new behaviour. Use it only if
`authorization.rea_allowed` is true and the user agrees to install it; never
install it silently.

Then rank the files each reviewer should start from:

    python3 .harness/scripts/assess_scope.py --target <source path>

It writes `evidence/scope-<area>.txt` (process, architecture, security,
operations): the shared core files (entry points, manifests, CI, Compose,
infrastructure roots) plus the files most relevant to that area, using path
and content signals, scanner hits and hotspots. Pass each reviewer its list as
the place to START — a starting point, not a fence. On the eShopOnWeb run the
lists covered 71% of the files the reviewers ended up citing, at about a third
of the codebase each.

## Phase 3 — Recover the business processes

Invoke **business-analyst** in ASSESS mode with: the source path, the test
environment URL and role names, database access, `docs/assess/evidence/`;
output `docs/assess/as-is.json` (template `.harness/templates/assess/as-is.json`).
It reconstructs roles, features (each with a "used?" signal from the data),
use cases, end-to-end flows with every step, business rules (and where each is
enforced: server, browser only, or nowhere), gaps where processes break, and
the unknowns only the client can answer.

Large systems: run it per module (top-level folders from the inventory) and
merge, so no single pass outgrows its context.

## Phase 4 — Technical review (run in parallel)

They run at the same time, so **each writes its own files** — never a shared
one: `docs/assess/technical-<area>.md` (its narrative) and
`docs/assess/findings-<area>.json` (its findings; template
`.harness/templates/assess/findings.json`), with `<area>` = architecture,
security, operations or process. The validator and the report merge them.
Each agent keeps its own id prefix; a repeated id is an error.

| Agent (ASSESS mode) | Covers | Prefix |
|---|---|---|
| **solution-architect** | architecture, code health (hotspots from the scan), performance | `A-` |
| **security-compliance** | security design: authentication, authorisation per route, input handling, secrets handling, dependencies; triage of every Semgrep / gitleaks / OSV hit | `S-` |
| **devops** | build, deploy, environments, backups, monitoring, infrastructure as code | `O-` |
| **business-analyst** | process findings worth a severity (from the gaps) | `P-` |

security-compliance also writes `docs/assess/evidence/triage.json` (template
`.harness/templates/assess/triage.json`): a verdict for every scanner hit —
confirmed, false-alarm or not-applicable — so the report can show what the
scanners were worth. Then run the gate over everything: its `DUPLICATE?`
lines are the same issue filed by two reviewers, for the critic to settle.

## Phase 5 — Effort, options, opportunities

1. **solution-architect** (second invocation, now that every register exists):
   add "## Options and effort" to `technical-architecture.md` — one table with
   every finding from every register, one S/M/L → person-week scale, one rate
   assumption, and each option's total built from the rows it still has to
   fix. Every figure is labelled an estimate. (In the first run the options
   left out the security and operations work, and the totals could not be
   reproduced.)
2. **product-owner** in ASSESS mode with: `as-is.json`, every
   `findings*.json` and `technical*.md`; output `docs/assess/opportunities.json`
   (template). It takes every figure from the architect's table and writes:

- the summary;
- recommendations for Now (0–30 days), Next (1–3 months) and Later (3–6 months);
- where new features can safely be built and where code must be fixed first;
- opportunities;
- the three options — fix in place, replace piece by piece, or rebuild — with
  cost, time and risk estimates from **solution-architect**;
- the one commitment to the client — only what the Now list actually delivers;
- the limits of the assessment;
- `questions`: the few the client must answer (`{ids, question, why}`); the
  report numbers them Q1, Q2 … and lists every as-is unknown in Part B.

## Phase 6 — Challenge

Invoke **critic** with all of `docs/assess/` and the gate's `DUPLICATE?`
lines; output `docs/critique-assessment.md`. It opens the cited lines and
checks: unsupported claims; severity against business impact; "used" claims
with no data; areas never examined; duplicates across registers and
severity disagreements between reviewers; options whose estimates leave out
a register or contradict the findings; a commitment the plan cannot keep;
scanner gaps the limits do not state.

Then the decision: `python3 .harness/scripts/decide.py
docs/critique-assessment.md --out docs/decision-assessment.md --phase
assessment --rigor <rigor>`. With no Critical or High finding it writes the
decision itself and no judge runs. Exit 2 → **judge** →
`docs/decision-assessment.md`, with every required change numbered (RC-01 …)
and assigned to one owner and file. Owners revise in parallel —
product-owner last, because it takes the revised figures — and you run the
gate after the round.

Round 2 is a script, not a judge run: `python3
.harness/scripts/check_required_changes.py docs/decision-assessment.md --since
<when the revision round started> --gate "python3
.harness/scripts/validate_assessment.py --root <source path> --strict"`. Read
the changed files for every change that came from a Critical or High finding,
then re-run with `--write --spot-checked <ids>`. Invoke the judge again only
if a spot check fails or an owner disputes a change (on the eShopOnWeb run the
script reached the judge's round-2 verdict in seconds instead of 9 minutes).
Max 2 rounds. A merged finding keeps a "merged from O-12" note for
traceability; no live reference to a removed id may remain.

## Phase 7 — Evidence gate

    python3 .harness/scripts/validate_assessment.py --root <source path> --strict

Send every ERROR to its owner until it passes. The gate requires every
`path:line` an item cites to exist (a wrong line next to a right one fails),
and searches every file under `docs/assess/`, evidence included, for the
credential values the source assigns — never printing them. A SECRET line
means a value reached a document or the evidence: remove it and cite the
location instead.

## Phase 8 — Report

    python3 .harness/scripts/build_assess_report.py

It writes `docs/assess/report/index.html` and `assessment.pdf`. The brand comes
from `~/.asdr/brand.json`, else `.harness/brand.json`, else a neutral style.

- **Part A** (business, for owners): summary, health scorecard, how the
  business runs today, where processes break, the most serious risks in
  business terms, recommendations, adding new features, options, the
  commitment, and the numbered questions for the client.
- **Part B** (technical appendix): scope and method (stating what access was
  and was not available), architecture and code health, findings register
  and detail with evidence, process detail and every open point, scanner
  results with the triage counts, limits.

Give the user the PDF (SendUserFile in Cowork) and the file path. Do not
publish it as a page unless they ask for a private one.

## Phase 9 — Client review

The client reviews the draft and answers the unknowns. Record each answer with
`log_question.py`, update `as-is.json` and `opportunities.json`, re-run
Phases 7–8, and keep both report versions.

## Phase 10 — Hand-off into a build (only when the user asks)

Turn the assessment into ASDR discovery documents so `/asdr` continues from
architecture or sprint planning:

1. **product-manager**: `docs/02c-features.md` from the as-is features, each
   marked keep / fix / new; `docs/02d-process-flows.md` from the as-is flows
   (to-be), with the gaps fixed.
2. **business-analyst**: `docs/02-requirements.md` (rules and fixes become
   requirements), `docs/02e-test-cases.md`, and **`docs/02f-parity.md`**
   (template `.harness/templates/parity.md`): every behaviour the client keeps
   becomes a `PAR-xx` item; an intended difference is a `change` with the
   client's approval (who, when, where), a retired one a `drop`. Ask the user
   for any approval that is not on record; never assume one.
3. **Characterisation tests first.** Before any sprint changes existing code,
   the generator writes tests that pin the current behaviour of every area it
   will touch, so refactoring cannot silently break what works. Tests that
   observe a parity item call `parity('PAR-xx', value)`.
4. **Baseline the old system** before any code changes, on its test
   environment (never production):

       python3 .harness/scripts/run_tests.py --parity old --base-url <old system test URL> --no-server

   It records `.harness/test-results/parity-baseline.json`. Suites may define
   `parity_cmd` in the test config to run only the parity tests.
5. From then on, every sprint's regression run and the release gate compare
   the new build with that baseline (`compare_parity.py`; `--gate` at release),
   writing `docs/parity-report.md`. A kept behaviour that differs fails the
   sprint and blocks the release. Optional, when the client's authorisation
   allows it: REA's `compare-web-captures` for a deeper DOM / network diff of
   web screens.
6. Run `validate_product_map.py --require-coverage`, then continue with the
   `architect` skill or Phase 2 of `asdr`.

## Dashboard

Assessments get the project dashboard too. Run
`python3 .harness/scripts/build_dashboard.py` at the end of every phase. Its
documents section lists everything under `docs/assess/`, and its questions
section shows the intake and review answers.

## Final response

1. The verdict in one line and the health scorecard.
2. The three most serious risks, in business terms.
3. The recommended option, with its estimate.
4. The questions waiting on the client.
5. The PDF path, and the reminder that the report is private.
