# Parity — behaviour the new version must keep

<!-- docs/02f-parity.md. Written at the /assess hand-off (Phase 10) by the
business-analyst from the as-is items marked "keep". Only for work on an
existing system. compare_parity.py reads the Summary table; the release gate
blocks while any "keep" item differs from the old system. -->

- Old system: <name, version or commit>
- Old system test URL: <https://old-test.example.com>  (the baseline run uses it; never production)
- Baseline captured: <date> by `run_tests.py --parity old --base-url <old URL> --no-server`
- Client approvals for changes: <who approves, e.g. the product owner named in docs/assess/intake.json>

## How it works

1. Each item below is something the business relies on today. A test case
   names it on its Covers line, and its test captures what the user sees or
   gets, with `parity('PAR-xx', value)` (or `cy.parity` / `parity(...)` in
   pytest).
2. Before any code changes, the same tests run against the **old** system:
   the baseline.
3. At every sprint that touches an item, and at release, they run against the
   **new** version and `compare_parity.py` compares the two, item by item.

## Summary

| ID | Behaviour to keep | From (as-is) | Compare | Ignore | Decision |
|---|---|---|---|---|---|
| PAR-01 | <A member sees the same tasks, in the same order, after signing in> | <AF-03, flow AP-01, app/app.js:40-61> | ui-text | timestamps, whitespace | keep |
| PAR-02 | <The CSV export has the same columns and the same rows> | <AF-07, BR-05> | file | exported_at, order | keep |
| PAR-03 | <Anyone can pick the admin role at sign-in> | <T-02> | ui-text | | change — <approved by Jane Doe (client PO), 2026-10-20, email "Roles">: admins are assigned by an administrator |

Columns:

- **Compare**: `ui-text` (visible text), `api` (a response body), `data`
  (rows read back), `file` (an export), `value` (anything else). Informational.
- **Ignore**: what may legitimately differ, comma-separated. Field names are
  removed from objects at any depth. Reserved words: `timestamps` (ISO dates and
  times), `uuids`, `numbers-in-ids` (digits inside `id`-like keys' values),
  `order` (lists compared as sorted), `whitespace`, `case`.
- **Decision**: `keep` (must match the old system exactly, after Ignore),
  `change — <who approved it, when, where>` (an intended difference; the
  approval text is required), or `drop — <who approved it>` (the behaviour is
  retired). A change or drop without an approval is treated as `keep`.
