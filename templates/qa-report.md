# QA Report · <stage-id> · round <n>

<!-- Written by the stage-qa, a different agent than the one that produced the
artifact. Every row needs Evidence: a quoted section, a file:line, or a command
output. A verdict without evidence is not a verdict. -->

| # | Checklist item | Verdict | Evidence |
|---|---|---|---|
| 1 | <item from the plan> | PASS/FAIL | <quoted section / file:line / command → output> |

## New blockers not in the plan

- None / <blocker + where it is + what it breaks>

## Verdict

```yaml
stage: <id>
verdict: pass | revise
failed_checks: [<item numbers to fix, empty list if pass>]
```
