# Feature List

<!-- Save as: docs/02c-features.md · Written by: product-manager
The product requirements, organised by feature. The Summary table is the
machine-readable source: validate_product_map.py reads it, so keep one row per
feature, keep the column order, and write ids exactly (F-01, PF-01, UC-01,
FR-01). Number features F-01, F-02, … and never renumber.
Rules the validator enforces:
  - every feature names at least one process flow, use case and requirement
    that exist in docs/02d-process-flows.md, 02b-use-cases.md, 02-requirements.md
  - every Must feature appears in at least one process flow's Features line
  - every row has a "### F-xx · name" detail section below
  - Affects (optional 9th column): the OTHER roles whose abilities this
    feature changes — an admin setting, a permission, a shared list. Write the
    role as it appears in personas; add "(on/off)" when it is a switch. The
    validator then requires a process-flow step where that role meets the
    effect, and test cases with Persona <role> that cover the feature: one for
    a plain effect, two for a switch (on and off). Leave it "—" when the
    feature only affects its own users.
Priority is MoSCoW: Must | Should | Could | Won't. Release is MVP or a version. -->

## Summary

| ID | Feature | Persona(s) | Priority | Release | Flows | Use cases | Requirements | Affects |
|---|---|---|---|---|---|---|---|---|
| F-01 | <short name> | <persona> | Must | MVP | PF-01 | UC-01 | FR-01, FR-02 | — |
| F-02 | <admin setting> | <admin persona> | Should | MVP | PF-03, PF-05 | UC-07 | FR-09 | <member persona> (on/off) |

## Feature detail

### F-01 · <short name>

- Problem it solves: <the user problem from the brief, in the user's words>
- Who uses it: <persona(s)> — <how often, in what situation>
- Value: <what changes for the user when it exists>
- In scope: <what this release includes>
- Out of scope: <what it deliberately does not do yet>
- Where it sits in the journey: <PF-01 steps 3–5: the moment the user needs it>
- Success measure: <metric with a number, e.g. "80% of new users add a task within 2 minutes">
- Dependencies: <F-xx that must exist first, or none>
- Open questions: <or none>

### F-02 · <short name>

- Problem it solves: <…>
- Who uses it: <…>
- Value: <…>
- In scope: <…>
- Out of scope: <…>
- Where it sits in the journey: <…>
- Success measure: <…>
- Dependencies: <…>
- Open questions: <…>
