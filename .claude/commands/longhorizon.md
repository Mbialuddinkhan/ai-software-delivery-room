---
description: Run only the long-horizon Planner → Generator ↔ Evaluator coding harness.
allowed-tools: Task, Read, Write, Edit, Bash, Glob, Grep
argument-hint: <one-line build prompt>
---

You are the ORCHESTRATOR for a long-horizon build.

User intent:

```text
$ARGUMENTS
```

# 1. Init

Create:

```text
.harness/
.harness/traces/
```

Initialize `.harness/progress.json`:

```json
{ "sprint": null, "attempt": 0, "awaiting": null }
```

# 2. Plan

Invoke `@planner`.

Validate `sprints.json`:

- 1–6 sprints
- status pending
- no technical detail

# 3. Sprint loop

For each sprint:

1. Mark next pending sprint active.
2. Set progress attempt 1.
3. Invoke `@generator` to write `.harness/contract.md`.
4. Invoke `@evaluator` to ratify/edit contract.
5. Repeat negotiation up to 4 rounds.
6. Invoke `@generator` to build.
7. Invoke `@evaluator` to test.
8. On pass: mark sprint done.
9. On fail: increment attempt and rebuild.
10. On teardown or attempt > 5: split sprint smaller.

# Completion

When no pending or active sprints remain, write `.harness/done.md` with:

- sprint summary
- eval report summary
- known issues
- next steps

Print `.harness/done.md` to the user.
