# Assessment templates (/assess)

| File | Written by | Becomes |
|---|---|---|
| `intake.json` | orchestrator, with the user | report cover, scope and authorisation |
| `as-is.json` | business-analyst (ASSESS mode) | how the business runs today, where processes break, unknowns |
| `findings.json` → `findings-<area>.json` | one file per reviewer: `-process` (business-analyst, `P-`), `-architecture` (solution-architect, `A-`), `-security` (security-compliance, `S-`), `-operations` (devops, `O-`) | risks, findings register and detail (merged) |
| `technical.md` → `technical-<area>.md` | one file per reviewer; the architect's also carries "Options and effort" | Part B narrative (merged in order) |
| `triage.json` → `evidence/triage.json` | security-compliance | the verdict on every scanner hit; Part B's triage table |
| `opportunities.json` | product-owner (figures from the architect's effort table) | summary, recommendations, new-feature fit, options, commitment, numbered questions |
| `brand.json` | the user, once | look of every report (copy to `~/.asdr/brand.json`) |

Reviewers run in parallel, so each writes only its own files; the gate and the report merge them.

Generated: `evidence/` (assess_scan.py — locations only, no copied code), `report/` (build_assess_report.py: HTML + PDF).

Rules: every claim cites evidence (`path:line`, `db:`, `api:`, `tool:`; `git: <commit> path:line` for a file
that exists only in history), and every cited line must exist; never paste a secret value — cite where it is
(the gate searches every file here, evidence included, for the credential values the source assigns); mark
confidence honestly; anything code and data cannot answer goes to `unknowns`; effort, cost and time are
estimates. The report is private: share the PDF with the client, never a public page.
