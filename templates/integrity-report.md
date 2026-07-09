# Product Integrity Report · <run-id>

<!-- Save as: .harness/integrity-reports/integrity-report-<run-id>.md · Written by: product-integrity-qa
One report per run. Every requirement checked gets a row with real evidence —
a command + its output, a file:line, or a test result. A status without
evidence is not a status. The Verdict block is machine-read by the
orchestrator, so keep its keys and values exactly as shown. -->

## Requirement checks

| Requirement | Status | Evidence (command / file:line / test result) |
|---|---|---|
| <FR-01> | covered / uncovered / drifted / broken / deferred | <command → output, or file:line, or path/to/test::case → pass> |

## Drift / broken / orphan findings

<None, or a numbered list.>

1. <FR-0x: requirement text changed after sprint-0y built to it (drift) — re-align docs + code.>
2. <FR-0z: a passed feature now fails regression (broken) — fix before proceeding.>
3. <sprint-0k: built work no requirement asked for (orphan sprint).>

## Verdict

```yaml
integrity: in-sync | drifted | broken | incomplete
uncovered_requirements: [<ids>]
drifted_requirements: [<ids>]
broken_requirements: [<ids>]
orphan_sprints: [<ids>]
reason: <one sentence>
```
