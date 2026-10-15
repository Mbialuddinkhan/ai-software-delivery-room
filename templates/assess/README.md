# Assessment templates (/assess)

| File | Written by | Becomes |
|---|---|---|
| `intake.json` | orchestrator, with the user | report cover, scope and authorisation |
| `as-is.json` | business-analyst (ASSESS mode) | how the business runs today, where processes break, unknowns |
| `findings.json` | solution-architect, security-compliance, devops, business-analyst | risks, findings register and detail |
| `technical.md` | solution-architect (+ security, devops sections) | Part B narrative |
| `opportunities.json` | product-owner (+ solution-architect for options) | summary, recommendations, new-feature fit, options, commitment |
| `brand.json` | the user, once | look of every report (copy to `~/.asdr/brand.json`) |

Generated: `evidence/` (assess_scan.py), `report/` (build_assess_report.py: HTML + PDF).

Rules: every claim cites evidence (`path:line`, `db:`, `api:`, `tool:`); never paste a secret value —
cite where it is; mark confidence honestly; anything code and data cannot answer goes to `unknowns`;
effort, cost and time are estimates. The report is private: share the PDF with the client, never a public page.
