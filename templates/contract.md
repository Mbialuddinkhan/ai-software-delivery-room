# CONTRACT · <sprint-id> · <short-name>

Negotiated by: generator + evaluator
Status: in-negotiation
Last edit: <ISO timestamp>

<!--
Status must be exactly one of: in-negotiation | revision-requested | ratified
Only the evaluator may set "ratified". Only the generator writes criteria;
only the evaluator edits or vetoes them.
Fill every category below. Each criterion is ONE testable assertion — if it
contains "and", split it. Validate with:
  python3 .harness/scripts/validate_contract.py <this file>

WRITING GOOD CRITERIA (this is what makes the contract un-gameable):
- Every criterion states an OBSERVABLE outcome — something a command, an HTTP
  response, a DOM query, or a row in the database can confirm. If you cannot
  name the check that proves it, it is not a criterion yet.
- Quantify or cite. A criterion that leans on "fast", "secure", "robust",
  "user-friendly", "handled gracefully", or "works correctly" is invalid
  unless a number or a concrete observable is attached.
    BAD:  "Search is fast and works correctly."
    GOOD: "Searching a 10,000-row dataset returns the first page in under
           300ms measured by `time curl -s '/search?q=abc'`."
    BAD:  "Errors are handled gracefully."
    GOOD: "POSTing malformed JSON returns HTTP 400 with body
           {"error":"invalid request"} and writes no row to `orders`."
- Write the cheapest cheat that would technically satisfy the wording, then
  rewrite the criterion so that cheat fails. That is the evaluator's first
  move; do it to yourself first.
-->

## Sprint goal

<Copy the goal verbatim from sprints.json>

## Acceptance criteria

### Happy path

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

### Failure & error handling

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

### Security

<!-- Draw from .harness/templates/security-baseline.md — pick the sections
this sprint touches (input handling, auth, authz, secrets, dependencies). -->

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

### Accessibility

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

### Data persistence

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

### Performance

1. <single testable assertion>
2. <single testable assertion>

### Edge cases

1. <single testable assertion>
2. <single testable assertion>
3. <single testable assertion>

## Test plan

- <exact command to run, e.g. `pytest tests/ -x` or `npm test`>
- <manual check with exact steps and expected result>
- <evidence to capture: log lines, screenshots, curl output>

## Out of scope

- <explicitly excluded item — protects the sprint from scope creep>

## Done definition

All acceptance criteria pass with recorded evidence, no critical/high
security issue exists, no console or runtime errors occur on the surfaces
this sprint touches, and the evaluator has written a PASS verdict in the eval
report.

## Revision notes

<!-- Evaluator only. When Status is revision-requested, list the exact
criteria numbers to fix and why. Generator addresses every item, then sets
Status back to in-negotiation. -->
