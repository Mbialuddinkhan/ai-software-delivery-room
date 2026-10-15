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
  version: "3.6.0"
---

# Assess — understand an existing system and say what to do with it

The client hands over a system and does not want to explain it again. Recover
what it does for the business and what state it is in, from evidence, and turn
that into a report they can act on. The client confirms a draft and answers a
short list of questions instead of sitting through weeks of workshops.

Subagents share none of your context: every invocation prompt must contain the
input paths, the output path and the template path.

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
3. `mkdir -p docs/assess` and copy `.harness/templates/assess/*.json` and
   `technical.md` there as starting points (do not overwrite existing files).

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

It runs whatever is installed — OSV-Scanner (dependencies), Semgrep, gitleaks
(code and history, redacted), lizard (complexity), jscpd (duplication) and git
churn — and writes `evidence/scan-summary.md`. Show the user its tool table. A
missing tool is reported, not fatal; tell the user what installing it would add.

Scanner hits are not findings. Semgrep measured about 40% precision on a real
codebase, so every hit is triaged in the code by the agents in Phase 4.

**No source code** (live system only): skip the code scanners. Phase 3 then
works from the running app as each role and its network traffic, and confidence
is lower. REA (an optional reverse-engineering tool, `npx rea-agents@6.4.0`) can
map a shipped front-end bundle or compare old and new behaviour. Use it only if
`authorization.rea_allowed` is true and the user agrees to install it; never
install it silently.

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

Each writes its part of `docs/assess/technical.md` and appends findings to
`docs/assess/findings.json` (template `.harness/templates/assess/findings.json`).
Use one id prefix per agent so ids never collide.

| Agent (ASSESS mode) | Covers | Prefix |
|---|---|---|
| **solution-architect** | architecture, code health (hotspots from the scan), performance | `A-` |
| **security-compliance** | security design: authentication, authorisation per route, input handling, secrets handling, dependencies; triage of every Semgrep / gitleaks / OSV hit | `S-` |
| **devops** | build, deploy, environments, backups, monitoring, infrastructure as code | `O-` |
| **business-analyst** | process findings worth a severity (from the gaps) | `P-` |

## Phase 5 — Opportunities and options

Invoke **product-owner** in ASSESS mode with: `as-is.json`, `findings.json`,
`technical.md`; output `docs/assess/opportunities.json` (template). It writes:

- the summary;
- recommendations for Now (0–30 days), Next (1–3 months) and Later (3–6 months);
- where new features can safely be built and where code must be fixed first;
- opportunities;
- the three options — fix in place, replace piece by piece, or rebuild — with
  cost, time and risk estimates from **solution-architect**;
- the one commitment to the client;
- the limits of the assessment.

## Phase 6 — Challenge

Invoke **critic** with all of `docs/assess/`; output
`docs/critique-assessment.md`. Its assessment checks:

- unsupported or uncited claims;
- severity that does not match the stated business impact;
- "used" claims with no data behind them;
- areas never examined;
- options whose estimates contradict the findings.

Then **judge** → `docs/decision-assessment.md`; owners fix the required
changes, max 2 rounds.

## Phase 7 — Evidence gate

    python3 .harness/scripts/validate_assessment.py --root <source path> --strict

Send every ERROR to its owner until it passes. A SECRET line means a value was
pasted into a document: replace it with its location.

## Phase 8 — Report

    python3 .harness/scripts/build_assess_report.py

It writes `docs/assess/report/index.html` and `assessment.pdf`. The brand comes
from `~/.asdr/brand.json`, else `.harness/brand.json`, else a neutral style.

- **Part A** (business, for owners): summary, health scorecard, how the
  business runs today, where processes break, the most serious risks in
  business terms, recommendations, adding new features, options, the
  commitment, and the questions for the client.
- **Part B** (technical appendix): scope and method, architecture and code
  health, findings register and detail with evidence, process detail, scanner
  results, limits.

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
   requirements), `docs/02e-test-cases.md`.
3. **Characterisation tests first.** Before any sprint changes existing code,
   the generator writes tests that pin the current behaviour of every area it
   will touch, so refactoring cannot silently break what works. These test
   cases are the "keep" items.
4. Run `validate_product_map.py --require-coverage`, then continue with the
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
