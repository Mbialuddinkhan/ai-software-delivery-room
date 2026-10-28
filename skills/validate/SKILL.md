---
name: validate
description: >
  Use this skill when the user wants to test a software or product idea before scoping or building it —
  real desk evidence, a synthetic panel of evidence-grounded personas (with "what if" scenarios and follow-up
  interviews), and optionally a MiroFish swarm simulation — ending in a proceed / pivot / stop recommendation with
  objections and cheap real-world tests. Runs standalone or as the optional first step of `asdr`. Trigger phrases:
  "validate my idea", "idea validation", "will people want this", "simulate the market reaction",
  "test this idea before we build", "is this worth building", "what would customers say".
metadata:
  version: "4.0.1"
---

# Validate — Idea Validation Orchestrator

Ask the user for the idea if not provided. One sentence is enough.

You are the orchestrator: you invoke agents with precise inputs and run the
scripts. Subagents share none of your context, so every invocation prompt
contains the input paths, the output path and the template path.

## Models and the cost log (v4.0)

Pass `model: <the output of python3 .harness/scripts/model_plan.py get <agent>>`
on EVERY agent invocation; with no plan set it answers with the balanced plan
(the agents' own frontmatter). If a call fails because the model is not
allowed here, run `model_plan.py unavailable <model>` and retry with what
`get` returns. Log every run with `log_agent_run.py --model <the model you
passed>`.

## What this can and cannot show — say it once, before Phase 2

Three lanes, two kinds of evidence:

- **Desk evidence** (always): real reviews, forums, pricing pages, search and
  hiring signals. Real, partial, and the only lane that can corroborate.
- **Synthetic panel** (always): 8–30 Claude-played personas built from the
  desk evidence, reacting independently, then once more after an anonymous
  digest of the others' objections, plus "what if" scenarios and follow-up
  interviews.
- **MiroFish** (optional): a large simulated social network, run by the user
  or started by ASDR's launcher.

Panel and MiroFish are the SAME kind of evidence — synthetic opinion from
language-model personas. Research on such respondents finds less variation
than real people, a lean toward agreeing and positive answers, a crowd that
resembles itself more than humans, and an ability to infer and confirm what
the researcher hopes. So: they are good for finding objections, confusion,
switching barriers and competitor comparisons, and for comparing scenarios
on the same panel; they never show demand, willingness to pay or market
size; their agreement with each other is not corroboration; a hypothesis
backed only by them is at most "weakly supported"; desk evidence wins
disagreements; every validation ends with real-world tests (template §6).

## Stage execution, models, cost (the 3.8 rules apply here too)

Authoring stages follow the same protocol as `asdr` (read `.harness/progress.json`
→ `rigor`):

- `lite` — each executor runs once per batch and self-checks; no planner, no QA.
- `standard` (default) — batches; no stage planner (always `--no-plan`); one
  stage-qa run per batch that holds a high-tier stage.
- `paranoid` — every stage runs the full triad on its own; pass
  `model: "opus"` on every invocation, panelists included.

Drive each stage with `python3 .harness/scripts/stage_status.py <stage-id>
--artifact <path> --no-plan` (drop `--no-plan` under paranoid) until DONE;
under lite and standard, when every stage of a batch says EXECUTE, invoke
the executor once with every artifact path, and run stage-qa once for the
batch with one report per stage id.

| Stage id | Executor | Artifact | Tier | Batch (lite/standard) |
|---|---|---|---|---|
| `idea-seed` | product-owner (SEED) | docs/validation/seed.md | med | A |
| `desk-evidence` | product-owner (DESK) | docs/validation/desk-evidence.md | high | A |
| `panel-stimulus` | product-owner (STIMULUS) | docs/validation/panel/stimulus.md | med | A |
| `panel-roster` | business-analyst (PANEL) | docs/validation/panel/roster.json | med | B |
| `idea-validation` | product-owner (VALIDATE) | docs/00a-idea-validation.md | high | C |

`panel.py` checks the stimulus and roster mechanically before stage-qa sees
them; the panelists themselves are not a stage (they are the data). The
critic always reviews; the judge only when `decide.py` says so (Phase 5).

**Models.** Panelists run on the model plan's choice: Sonnet in `balanced`
(their frontmatter), Haiku in `economy` — many calls, no judgement, and the
panel's own flags (implausible positivity, herding, homogeneity) are what
would show a weaker model's personas getting worse. The first sample run used
the session's model, so neither is yet measured against it —
`log_agent_run.py` records which.

**Cost log, after EVERY agent run, panelists included:**
`python3 .harness/scripts/log_agent_run.py --agent <name> --phase validation
[--stage <id>] --model <the model you passed> --usage "<usage block>"`. On `WARN` say
how much of the budget is used; on `OVER BUDGET` stop and ask.

## Phase 0 — Initialize and choose lanes

1. Resolve PLUGIN_ROOT (two levels above this skill's base directory) and run
   `python3 PLUGIN_ROOT/scripts/init_asdr.py --source PLUGIN_ROOT`
   (idempotent).
2. Run `python3 .harness/scripts/detect_companions.py`; read `mirofish` in
   `.harness/companions.json` (`installed`, `url`, `flavor`, `launcher`).
3. Lanes: desk and panel always. MiroFish only if it is already answering,
   or the user wants it and can run it:
   - **Where you run decides.** In Claude Code on the user's machine, the
     launcher can install and start MiroFish there. In Cowork or any cloud
     session the scripts run in a sandbox: Docker is not there and
     `localhost` is not the user's machine. In Cowork, run desk + panel and
     tell the user MiroFish needs Claude Code on their own computer. Never
     suggest exposing MiroFish publicly — its API has no authentication.
   - Offer MiroFish once, in plain terms: a much larger simulated crowd,
     slow (tens of minutes to hours), costly on their LLM account (cloud) or
     their hardware (offline), and the same kind of evidence as the panel.
     Default is no.
4. Ask once whether to test any "what if" scenarios on the panel (a second
   price, a different pitch, a competitor's move) — at most three — and how
   large a panel (8–30, default 12). Show the cost first:
   `python3 .harness/scripts/estimate_run.py --mode validate --panel-size <n>
   --scenarios <k> --rounds 2 --followups 3 --rigor <rigor>` (add
   `--set-budget` once they choose). Each scenario adds a full panel round;
   one price scenario is a good default. Log the answers with
   `log_question.py`.

## Phase 1 — Seed

Invoke **product-owner** in SEED mode: the idea verbatim, output
`docs/validation/seed.md`, template `.harness/templates/validation-seed.md`.
Web search for §4–§5; cite every number. Stage-id `idea-seed`.

If the MiroFish lane is on, the product-owner also writes
`docs/validation/requirement.md`: one plain paragraph telling MiroFish what
to simulate (the launch: offer, price, channel; the seed's segments reacting
over the first weeks) and what to report (adoption intent per segment,
strongest objections, price reactions, competitor comparisons). It must NOT
name the hypotheses or their thresholds.

## Phase 2 — Desk evidence (before the panel: personas are built from it)

Invoke **product-owner** in DESK mode with web search: input
`docs/validation/seed.md`, output `docs/validation/desk-evidence.md`,
template `.harness/templates/validation-desk-evidence.md`. Stage-id
`desk-evidence`. Every row has an id (D-01 …), URL, date, and the hypothesis
it bears on; quotes copied exactly (panelists may carry them, and
`panel.py` rejects any quote not found verbatim here). Look as hard for
evidence against the idea as for it.

If the MiroFish lane is on, start Phase 3b now so it runs while the panel
works.

## Phase 3a — Synthetic panel

    python3 .harness/scripts/panel.py init --size 12 --rounds 2 --followups 3

(`--size` 8–30. Invoke panelists as the `panelist` agent, never a
general-purpose one: the same answer costs ~16k tokens instead of ~73k,
because a general-purpose agent carries every tool. A 12-person
panel with one scenario, two rounds and three follow-ups is ~39 calls; if a
previous panel for this idea raised `static_round2`, use `--rounds 1`.
Under `rigor: paranoid` also `init --dir
docs/validation/panel-2 --panel-id panel-2` and run a second, independently
built panel.) Then loop: run `python3 .harness/scripts/panel.py next` and do
exactly what it prints until `DONE`:

- `WRITE-STIMULUS` / `FIX-STIMULUS` → **product-owner** (STIMULUS mode):
  `docs/validation/panel/stimulus.md` from template `panel-stimulus.md`, and
  for each scenario the user chose a copy `stimulus-SC-0n.md` that changes
  ONE thing, listed in `scenarios.json` (template `panel-scenarios.json`).
  Pass any `errors` back verbatim. Stage-id `panel-stimulus`.
- `WAIT-DESK` → finish Phase 2 first.
- `FIX-LEAK` → a panelist brief would show a hypothesis id, hypothesis
  wording (even paraphrased) or template guidance. Each error names the
  brief; fix its source — the stimulus (product-owner), the roster
  (business-analyst) or, for walkthroughs, the process flows
  (product-manager) — never the brief itself. No panelist runs until clean.
- `WRITE-ROSTER` / `FIX-ROSTER` → **business-analyst** (PANEL mode), with
  the `inputs`, `template` and `size` printed. Pass `errors` back verbatim
  (max 2 rounds, then ask the user). Stage-id `panel-roster`.
- `RESPOND` / `REVISE` / `FOLLOWUP` → for every task, invoke **panelist**
  with ONLY: "Input file: <input>. Output path: <output>. Read only the input
  file." plus the task's `fix` list if present. Run them in parallel batches
  of about six. Never add context of your own — the input file is what the
  persona knows, and it has been checked to exclude our hypotheses.
- `DONE` → note `flags_raised`. If a later `next` asks for more work (the
  roster or stimulus changed), the stored results turn `status: stale` until
  it reaches DONE again; never synthesise from a stale panel. Under paranoid, finish panel-2 the same way
  and run `python3 .harness/scripts/panel.py compare docs/validation/panel
  docs/validation/panel-2`.

Results land in `.harness/validation.json` under `panel` (and
`panel_variance`); cite them as `validation:panel.<key>`.

## Phase 3b — MiroFish (optional)

1. If it is not answering and the user wants it (Claude Code only):
   `python3 .harness/scripts/mirofish_stack.py doctor --flavor offline|cloud`
   and show the result. Fix FAILs with the user. Then
   `mirofish_stack.py up --flavor …` WITHOUT `--yes` prints what will be
   downloaded and where data goes: show it, ask, and only on a yes re-run
   with `--yes` (and `--pull-models` only if they agreed to the model
   download). Cloud keys come from environment variables the user sets
   themselves (`MIROFISH_LLM_API_KEY`, `MIROFISH_LLM_BASE_URL`,
   `MIROFISH_LLM_MODEL`, `MIROFISH_ZEP_API_KEY`) — never ask for a key in
   chat. `up` prints the `MIROFISH_URL` to use.
2. Consent to upload (log it): the seed without its hypotheses section and
   the requirement go to MiroFish, and from there to the LLM provider in its
   `.env` and (cloud) Zep Cloud; rounds are capped (`--max-rounds`, default
   20); time and tokens are on the user's account. A "no" ends this lane.
   Never send customer data, credentials or named private individuals.
3. Run in the background (it outlives a single shell call), output to
   `docs/validation/mirofish/console.log`:

       python3 .harness/scripts/mirofish_validate.py \
         --seed docs/validation/seed.md \
         --requirement-file docs/validation/requirement.md \
         --max-rounds <n> --runs <n> --interview-sample 10

   Progress is in `docs/validation/mirofish/run-1.json`. Exit 0 → results
   under `mirofish` in `.harness/validation.json`. 2 → MiroFish went away;
   continue without it. 3 → a step failed: show the ERROR line, offer one
   `--resume`. 4 → time limit: re-run with `--resume` (nothing is paid
   twice). `status: incomplete` may not be cited as a finished simulation.
4. Afterwards, if ASDR started it, offer `mirofish_stack.py down`. Never
   leave it running without telling the user.

## Phase 4 — Synthesis

Invoke **product-owner** in VALIDATE mode: inputs `docs/validation/seed.md`,
`docs/validation/desk-evidence.md`, `.harness/validation.json`,
`docs/validation/panel/` (roster, responses, digest, followups) and, when it
ran, `docs/validation/mirofish/report-*.md` and `interviews-*.json`; output
`docs/00a-idea-validation.md`, template
`.harness/templates/idea-validation.md`. Stage-id `idea-validation`. Tell
the executor and stage-qa what to grade: every claim cited; numbers only as
`validation:<key>` or a desk source; panel + MiroFish treated as ONE source;
no hypothesis "supported" without desk evidence; scenario conclusions drawn
from within-panel deltas only; every raised flag answered in §7; §6 present
with pass thresholds.

Then `python3 .harness/scripts/validate_verdict.py
docs/00a-idea-validation.md --type validation`; send ERROR lines back.

## Phase 5 — Critique and decision

1. **critic** — inputs the seed, desk evidence, `.harness/validation.json`,
   the panel folder, MiroFish outputs if any, and `docs/00a-idea-validation.md`;
   output `docs/critique-validation.md`, template
   `.harness/templates/critique.md`. Its synthetic-evidence checks are in its
   agent file. Then `validate_critique.py docs/critique-validation.md`
   (max 2 rounds).
2. **Decision** — `python3 .harness/scripts/decide.py
   docs/critique-validation.md --out docs/decision-validation.md --phase
   validation --rigor <rigor>`. With no Critical or High finding it writes
   `go` itself (Medium findings become required changes for the
   product-owner). Exit 2 (`JUDGE: required`, always under paranoid) → invoke
   **judge** with the same inputs plus the critique; output
   `docs/decision-validation.md`, template `.harness/templates/decision.md`;
   `validate_verdict.py docs/decision-validation.md --type decision`.
   `go` = proceed to discovery (as recommended, or with the judge's pivot);
   `no-go` = stop or pivot before discovery. After the product-owner applies
   required changes, `check_required_changes.py docs/decision-validation.md
   --gate "python3 .harness/scripts/validate_verdict.py
   docs/00a-idea-validation.md --type validation"`, spot-check, and re-invoke
   the judge only if a spot check fails.

## Phase 6 — Output

Print:
1. The recommendation and the judge's verdict, each with its one-line reason
2. Hypotheses table (id, result, confidence)
3. Top three objections, whether the product can answer each, and what the
   follow-up interviews said was behind them
4. Scenario comparisons (within-panel shifts), if any were run
5. Flags raised and how the synthesis treated them
6. The real-world tests (§6) — what to do this week
7. What ran: desk sources; panel size, rounds, scenarios, follow-ups;
   MiroFish runs/rounds/agents or "not run"

Then rebuild the dashboard (`python3 .harness/scripts/build_dashboard.py`)
and stop. Do not start discovery automatically. When the user continues
(`discover` or `asdr`), the product-owner reads `docs/00a-idea-validation.md`,
and `discover` can reuse the panel to walk the process flows.
