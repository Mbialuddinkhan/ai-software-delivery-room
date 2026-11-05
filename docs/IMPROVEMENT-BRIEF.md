# ASDR improvement brief — re-baselined against v4.1.0

**Re-baselined:** 5 Nov 2026, against `main` = v4.1.0 (19 agents, 8 skills).
Supersedes the 4 Nov brief, whose baseline (main = 3.8.0, local 3.9 unpushed)
was stale: everything through 4.1.0 — including the Codex/Gemini export it
listed as pending — is on `main` and tagged. Item IDs kept; reference them in
commits and the changelog.

## Already shipped — do not propose again

| Item | Where |
|---|---|
| 2.1 push 3.9 + consistency | 3.9.0–4.1.0 on main, tagged; name stays ASDR by 4.0 decision |
| 3.1 model policy per role | 4.0 `model_plan.py`, `.harness/models.json` (economy/balanced/maximum, rigor overlay, priced by `estimate_run.py`) |
| 3.3 model fallback | 4.0 fallback chains + `unavailable` |
| 3.6 run manifest + resume | 4.0 `entry_point.py`, 4.1 legacy resume + `origin.json` |
| 1.2 Codex/Gemini export | 4.1 `export_targets.py`, verified on the real CLIs |
| 2.3 (validate half) | panel is Cowork-native; MiroFish optional, desk+panel fallback |

## Shipped in v4.2 (this release)

| Item | What landed |
|---|---|
| 8.1 seeded-defect eval suite | `evals/` — 11 mechanical cases + 1 clean control + 3 agent-layer cases; catch rates published in `evals/CATCH-RATES.md`; regression gate vs `baseline.json` in CI |
| 8.2 escape-rate per release | `run_seeded.py --release vX.Y.Z` → `evals/escape-log.md`; a caught→escaped change blocks the tag |
| 8.3 secrets gate | `check_secrets.py` (builtin patterns + gitleaks layer when installed, redacted output, allowlist); riskgate prerequisite + PUBLISHING pre-tag step |
| 4.3 decision log | `decision_log.py add|collect` → `docs/decision-log.md` (options seen, chosen, rationale, who, when; idempotent backfill) |
| 3.4 cost attribution | `cost_report.py` → per-stage/role/model/client USD from measured run stamps (prices supplied, never built in) |
| 4.4 verification one-pager | `docs/VERIFICATION-MODEL.md` |
| 7.2 founder mode | `set_profile.py founder|enterprise` — lite rigor + economy plan + buyer-justified-first scope; review and gates stay on |

## Open — next releases

**4.3 — blast-radius gating + cross-family second opinion**
- 4.1/4.2 per-stage blast-radius tags (`low|medium|high`; high = data, auth,
  money, PII, outbound, production deploys) driving check depth and an
  `awaiting-human` stage state with a dashboard queue. Low-risk stages never
  queue; "gate everything" is the failure mode to avoid.
- 3.2 reviewer on a second model family — scoped honestly: inside Claude
  Code the reviewer cannot BE another family, so the evaluator/stage-qa
  attach a second opinion by shelling out to the Codex/Gemini CLI (4.1
  exports; `detect_companions.py` knows when they exist), `SINGLE_PROVIDER`
  warning otherwise. Measured by the agent-layer eval cases per family
  before any stronger claim is published.
- Gate to tag: seeded-defect suite green incl. new radius cases; fault-run
  with the CLI absent shows the warning.

**4.4 — product design rules + buyer justification**
- 6.1 decision-boundary table (agent-design §14: LLM extracts/proposes,
  rules decide; consequential actions behind per-node allowlists) — critic
  blocks an agent-design doc without it.
- 6.2 "no LLM-written numbers" requirement pattern + evaluator test.
- 6.4 MVP vs full-scope-engine brief mode in `/discover`.
- 6.5 licence register (`licence-register.md`) as an architecture-stage
  output; security-compliance blocks release on unresolved non-commercial /
  AGPL-in-SaaS items.
- 7.1 buyer-justified requirement tags (`justification: buyer | hypothesis |
  regulatory | technical`), planner orders buyer-first, traceability shows
  the ratio.
- 3.5 tool-output compression: generator receives summarised logs, the
  evaluator ALWAYS raw output.

**4.5 (conditional) — forecasting**
- 5.1 gate test first: does a trend forecast change any historical
  `/validate` verdict? Only then 5.2/5.3 (Apache-licensed model only,
  labelled `proxy-extrapolation`) and 5.4 (covariate module for client
  products via BigQuery).

## Standing do-not-do list

No OmniRoute or free-tier gateways; no `auto` model selection; no TimesFM 3.0
weights (non-commercial licence); no forecaster inside greenfield validation
verdicts; no compression that touches evaluator evidence; no Ponytail
dependency; no dispatcher/20th agent without the run-log measurement first
(8.4 — the data now exists in `.harness/agent-runs.jsonl`); no published
version or agent count that `main` does not show.

## Decisions taken at this re-baseline

- Plugin name stays `ai-software-delivery-room`; display rename (EASDR was
  floated, E for Enterprise) deferred — not a priority (10.1).
- Default second family for 3.2: Gemini CLI, as the export verified all 19
  subagents load there (10.2).
- Router substrate (10.3): moot for native runs; deferred with 3.2's scope.
- 20th agent (10.4) and dispatcher: measure first (8.4).
- Blast-radius default for release (10.5): the risk-manager classification
  sets it; the human gate is forced when the release touches data, auth,
  money, PII or outbound sends.
- Forecasting model (10.6): decided only if the 5.1 gate test passes.
