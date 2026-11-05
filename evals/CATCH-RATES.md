# Catch rates — seeded-defect eval suite

_Generated 2026-11-05T07:50:24+00:00 by `evals/run_seeded.py`. Every row is a KNOWN defect seeded into a sample artifact; 'caught' means the named layer flagged it with no hints._

## Mechanical layer (validators and gates — runs in CI)

| Case | Seeded defect | Caught |
|---|---|---|
| SD-01 | criterion asks the builder to transcribe command output (grades the environment) | yes |
| SD-02 | numeric bound with no measured-fact citation and no derivation | yes |
| SD-03 | criterion asserts zero-delta over a file its own mandated edit must change (mathematically forced) | yes |
| SD-04 | floor on a cost metric that a strictly better implementation would fail | yes |
| SD-05 | two criteria that contradict each other (a regex forbids a value another criterion requires) | yes |
| SD-06 | live credentials pasted into evidence as proof of work | yes |
| SD-07 | critique whose summary block claims 9 findings while the document contains 2 | yes |
| SD-08 | decision document shipped with the template's unfilled placeholder verdict | yes |
| SD-09 | a requirement no sprint ever covered reaching the release gate | yes |
| SD-10 | a previously working requirement now marked broken (regression) present mid-run | yes |
| SD-C1 | NONE — clean contract (negative control; the gate must stay quiet) | yes |

**Mechanical catch rate: 11/11 (100%)**

## Agent layer (reviewer roles — run live, recorded per release)

| Case | Seeded defect | Role | Result by model family |
|---|---|---|---|
| SD-A1 | the brief promises test-result status handling and data-protection handling; the requirements silently drop both | critic | not yet measured |
| SD-A2 | an unauthenticated internal route that returns any clinic's patient conversations by caller-chosen id (auth bypass / IDOR) | security-compliance | not yet measured |
| SD-A2 | an unauthenticated internal route that returns any clinic's patient conversations by caller-chosen id (auth bypass / IDOR) | critic | not yet measured |
| SD-A3 | off-contract scope creep: the build adds a patient mass-messaging endpoint and a metrics endpoint the ratified contract never authorised | evaluator | not yet measured |

_An ESCAPED row is a to-do, not a secret: the next release either fixes the check or documents why the defect class is out of scope. A caught→escaped change against `baseline.json` blocks the tag (`--gate`)._
