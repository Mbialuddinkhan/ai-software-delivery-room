# Test Cases

<!-- Save as: docs/02e-test-cases.md · Written by: business-analyst
Test cases are written in discovery, before any code, from the process flows
and use cases. They say what "working" means for a user, so the generator
builds to them and the evaluator grades against them.

Format (validate_product_map.py parses it): one "### TC-xx · title" section
each, with the bullet lines below. Number TC-01, TC-02, … and never renumber.
Type is one of:
  journey     walks a whole process flow from trigger to outcome (happy path)
  exception   follows one exception path (Flow: PF-xx.E1)
  functional  one behaviour inside a step
  edge        a limit, empty state, concurrency or malformed input (EC ids)
  nfr         a measured non-functional target (NFR ids)
Rules the validator enforces:
  - every process flow has at least one journey test case
  - every exception path has at least one test case
  - every testable item is named by at least one test case: FR, NFR, AC,
    BR, EC ids, every use case and its alternate/exception flows (UC-xx.A1,
    UC-xx.E1), every feature, every flow step and exception path (warning
    while building; error with --require-coverage and at the release gate).
    A journey names all its flow's steps; a step names its use case and
    features; everything else goes on the Covers line.
  - Covers lists the items THIS test proves, and every id must exist. At the
    release gate the test must mark each one at run time with
    covers('<id>') at the assertion that proves it, and journey tests mark
    each step with flowStep('PF-xx.n') when the step's result is checked.
  - cross-role: when a feature changes another role's abilities (Affects in
    docs/02c-features.md), write test cases with that role as Persona — one
    for the setting ON and one for OFF when it is a switch.
  - assertions prove the user-visible result: the counter value, the row's
    columns, the message text, that the item is gone — never just "no error"
    or "the button was clicked".
  - Automation names the automated test that proves it. The test's title MUST
    start with the id in brackets, e.g. test('[TC-01] member signs in and adds
    a task'), so run_tests.py results can be matched back to this list.
    "manual: <reason>" is allowed only where automation is impossible; the
    release gate lists every manual case for sign-off.
At the release gate every Must test case must have a passing automated result
in the latest run_tests.py run. -->

### TC-01 · <persona> completes <flow title> end to end

- Type: journey
- Flow: PF-01
- Use cases: UC-01, UC-02
- Requirements: FR-01, FR-02
- Covers: AC-01.1, AC-02.1
- Persona: <persona>
- Priority: Must
- Preconditions: <starting data and state, e.g. "no account exists for the email">
- Steps:
  1. <action, as the user does it>
  2. <action>
  3. <action>
- Expected result: <the flow's Outcome, observable on screen or in data>
- Automation: <e2e/playwright/journeys.spec.ts › [TC-01] …>

### TC-02 · <what goes wrong> is handled at <step>

- Type: exception
- Flow: PF-01.E1
- Use cases: UC-01
- Requirements: FR-01
- Covers: AC-01.2, EC-01, UC-01.E1
- Persona: <persona>
- Priority: Must
- Preconditions: <…>
- Steps:
  1. <…>
- Expected result: <exactly what the user sees; what is NOT saved>
- Automation: <file › [TC-02] …>

### TC-03 · <other role> can <do X> when <admin setting> is on

- Type: functional
- Flow: PF-05
- Use cases: UC-07
- Requirements: FR-09
- Covers: AC-07.1, BR-02, F-02
- Persona: <the role the setting affects>
- Priority: Should
- Preconditions: <admin has turned the setting on>
- Steps:
  1. <as that role: the action the setting allows>
- Expected result: <what that role now sees and what changed in the data>
- Automation: <file › [TC-03] …>

### TC-04 · <other role> cannot <do X> when <admin setting> is off

- Type: exception
- Flow: PF-05.E1
- Use cases: UC-07
- Requirements: FR-09
- Covers: AC-07.2, BR-02, UC-07.E1
- Persona: <the role the setting affects>
- Priority: Should
- Preconditions: <the setting is off>
- Steps:
  1. <as that role: look for the action>
- Expected result: <the control is not shown / the action is refused>
- Automation: <file › [TC-04] …>
