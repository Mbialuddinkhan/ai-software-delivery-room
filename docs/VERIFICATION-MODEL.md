# How ASDR verifies work — the one-page model

> Verification never skips; it changes shape. The depth of checking is set by
> what a mistake would cost — defined up front, not case-by-case in the moment.

## The three layers

**1. Mechanical validators (always on, every rigor level, free).**
Scripts, not model opinions — they cannot be talked out of a finding. A
contract no correct implementation could satisfy is rejected before anyone
builds (`preflight_contract.py`: 10 defect classes, each one observed in a
real run). A critique whose self-reported counts don't add up is rejected
(`validate_critique.py`). A verdict with an unfilled placeholder is rejected
(`validate_verdict.py`). A requirement nothing covers, or one that regressed,
is flagged (`validate_traceability.py`). A credential pasted into evidence
fails the gate (`check_secrets.py`). Numbers may only be asserted by citing
measured facts (`emit_facts.py` → `facts:` keys), never derived by a model.

**2. Independent review (the rigor dial sets how much).**
No agent signs off its own work — ever, at any setting. The author of a
stage is never its grader (stage-qa), the build is judged by an adversarial
evaluator that ratified the contract first, the critic challenges every
phase, and the judge rules only when the critic found something serious
(Critical/High) — a mechanical script accepts the rest, so review effort
goes where findings are.

| Rigor | What runs |
|---|---|
| lite | author + self-check, every mechanical validator, critic each phase, evaluator signs every sprint |
| standard | + independent stage-QA on high-stakes stages, judge on serious findings |
| paranoid | + full planner→executor→QA triad on every stage, maximum model plan, second independent panel in validation |

**3. Release gates (binary, evidence-backed).**
Security review of the code, DevOps readiness with command output as
evidence, product-integrity check (every requirement traced to a sprint and
passing tests; drift stops the release), configuration gate (every decision
decided, every setting tested per value), secrets gate on everything the run
wrote, then the risk-manager's classification: production-ready, MVP-ready,
prototype, or not ready. A `broken` or `drifted` integrity verdict blocks
release regardless of anything else. The gate only classifies; it never
packages its own approval.

## What sets the depth

The cost of being wrong, decided when work is planned:

| Blast radius | Examples | What it gets |
|---|---|---|
| Low | copy, docs, an internal report | mechanical validators + one review pass |
| Medium | a feature behind the existing auth | the full triad at the chosen rigor |
| High | data, auth, money, PII, outbound sends, production deploys | full adversarial review by agents that never saw the work, plus the human decision gates below |

The human decides — and the decision is recorded: where the run starts, the
rigor and model plan (with a priced estimate), the architecture and
portability options, every configurable-decision in the register, contract
ratification, and release. Each lands in `docs/decision-log.md` with options
seen, choice, rationale, who and when.

## How we know the checks work

The repo carries a seeded-defect eval suite (`evals/`): artifacts with known
defects — an impossible contract, a leaked key in evidence, a cooked
critique, an uncovered requirement — run against the validators on every CI
build, with the catch rates published in `evals/CATCH-RATES.md`. A defect
that was caught at the last release and escapes now blocks the tag. Reviewer
agents are measured the same way, live, per release — and the table says
"not yet measured" until they are, instead of guessing.

Since 4.3 the blast-radius table is enforced mechanically, not by judgement
in the moment: every acceptance criterion carries a declared radius,
`blast_radius.py` floors declarations against the trigger list (a criterion
touching auth, money, PII, deletion, migrations, production or outbound
sends is high whatever it claims — under-declaring is a blocking error), a
contract with any high criterion waits for ONE recorded human approval with
its rationale before the build starts, and high-radius work gets a
**cross-family second opinion**: a locally installed Gemini or Codex CLI
reviews the artifact and the deciding reviewer must address every concern —
agree or rebut, in writing. When no second family is installed the run
proceeds and says so (`SINGLE_PROVIDER` in the run warnings), instead of
pretending. Role boundaries are unchanged by design: the second opinion is
evidence, never a vote — the evaluator alone passes a sprint, the judge
alone resolves a phase, the human alone accepts a high-radius risk.
