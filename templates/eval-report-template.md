# Eval Report · <sprint-id> · attempt <n>

<!-- Save as: .harness/eval-reports/eval-report-<sprint-id>-attempt-<n>.md
Every row needs Evidence: a command + its actual output, or file:line.
A verdict without evidence is not a verdict. -->

| # | Criterion | Verdict | Reason | Evidence |
|---|---|---|---|---|
| 1 | <criterion text> | PASS/FAIL | <why> | <command → output, or file:line> |

## Console/runtime errors

- None / list errors with the exact message

## Security/accessibility concerns

- None / list concerns with location

## Final verdict

```yaml
verdict: pass | fail | teardown
sprint: <id>
attempt: <n>
failed_criteria: [<numbers, empty list if pass>]
required_next_action: <one sentence: what the generator must do next, or "proceed">
```
