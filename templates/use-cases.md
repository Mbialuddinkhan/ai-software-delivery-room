# Use-Case Catalogue

<!-- Save as: docs/02b-use-cases.md · Written by: business-analyst
One entry per use case. Every use case MUST link to at least one requirement
(FR id from docs/02-requirements.md) and one outcome (O id from the brief) —
a use case that traces to nothing is out of scope. Number use cases UC-01,
UC-02, … and never renumber; the architect, planner and traceability matrix
reference these ids.
Every alternate and exception flow is a testable item: label each one A1, A2,
E1, … at the start of its bullet ("E1: …"), and test cases refer to it as
UC-01.E1 / UC-01.A1. Each needs a test case that names it and, at the release
gate, a passing test that marks it with covers('UC-01.E1'). Write a flow for
every role the use case treats differently (e.g. "E1: a team member sees no
Delete button; A1: an admin deletes whether or not members may"). -->

### UC-01 · <title>

- Primary actor: <role / persona>
- Goal: <what the actor wants to achieve, one sentence>
- Preconditions: <what must be true before the flow starts>
- Main flow:
  1. <actor action>
  2. <system response>
  3. <…>
- Alternate / exception flows:
  - <A1: condition → alternate path>
  - <E1: error condition → how the system responds>
- Postconditions: <system state after success>
- Linked requirements: <FR-01, FR-02>   (at least one required)
- Linked outcome: <O-01>

### UC-02 · <title>

- Primary actor: <role / persona>
- Goal: <one sentence>
- Preconditions: <…>
- Main flow:
  1. <…>
  2. <…>
  3. <…>
- Alternate / exception flows:
  - <A1: …>
  - <E1: …>
- Postconditions: <…>
- Linked requirements: <FR-03>   (at least one required)
- Linked outcome: <O-02>
