# Requirements

<!-- Save as: docs/02-requirements.md · Written by: business-analyst
Every acceptance criterion must be testable by a specific check. Vague
words (fast, easy, secure, user-friendly) are only allowed with a number
attached. Example of the required standard:
  BAD:  "Search should be fast."
  GOOD: "Search results for a 10,000-record dataset render in under 1
         second on the reference machine."

Every id in this file is a TESTABLE ITEM: validate_product_map.py requires a
test case that names each one (docs/02e-test-cases.md, Covers or Requirements
line), and at the release gate a passing test must have reached it (a
covers('<id>') marker in the test). Write each item on its own bullet that
starts with its id, exactly like this, so the validator can read it:
  - FR-01: <one capability>
  - NFR-01: <quality target with a number>
  - AC-03.2: <one observable check for user story US-03>
  - BR-01: <rule the system always enforces>
  - EC-01: <edge case and the exact expected behaviour>
Acceptance criteria are numbered per story: AC-<story>.<n>. Write one for every
behaviour a user can see, including the "undo" direction (untick, remove,
turn off) and what a file or export must contain (columns, values), not just
that it exists. -->

## 1. Functional requirements

- FR-01: <one sentence, one capability>
- FR-02: <…>

## 2. Non-functional requirements

- NFR-01: <performance, security, accessibility or scalability target with a number>
  (a measured NFR is proven by a test that records the value with
  metric('<name>', value, '<unit>', budget) and asserts it)

## 3. User stories

<US-01... Format: As a [user], I want [goal], so that [benefit].>

## 4. Acceptance criteria

- AC-01.1: <testable assertion for US-01>
- AC-01.2: <…>
- AC-02.1: <testable assertion for US-02>

## 5. Business rules

- BR-01: <rule the system must always enforce — say which role it allows and which it stops>

## 6. Edge cases

- EC-01: <empty state, limit, concurrency or malformed input → exact expected behaviour>

## 7. Data requirements

<Entities, key fields, retention needs — no table designs (architect's job).>

## 8. Integration requirements

<External systems, what data flows in/out, failure expectations.>

## 9. Reporting requirements

<What users/admins need to see aggregated, if anything.>

## 10. Open questions

<Unresolved items — these block the judge if critical.>
