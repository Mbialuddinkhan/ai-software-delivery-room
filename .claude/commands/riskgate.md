---
description: Run the final Risk Manager gate. Reviews security, tests, deployment, observability, and classifies the release.
allowed-tools: Task, Read, Write, Edit, Bash, Glob, Grep
---

You are the RISK GATE ORCHESTRATOR.

This command runs the final release gate before any production or staging deployment.

# Prerequisites check

Before proceeding, verify these exist:
- `sprints.json` — all sprints must have status: done
- `.harness/eval-reports/` — at least one eval report with PASS verdict
- `docs/` — product brief, requirements, architecture docs
- Tests must exist in the repo

If any prerequisite is missing, print a blocklist and stop.

# Phase 1 — Security final review

Invoke `@security-compliance` for a final pass against the codebase.

Check:
- No hardcoded secrets in source code
- Auth exists on all protected routes
- Input validation is present
- Prompt injection controls exist if AI features are present
- Audit logs exist for sensitive actions
- Dependencies have no known critical CVEs (check package files)

Output: `docs/09-security-review-final.md`

# Phase 2 — DevOps readiness check

Invoke `@devops` for final deployment readiness.

Check:
- Docker builds without errors
- docker-compose.yml is valid
- .env.example is complete
- CI workflow exists and would pass
- Deployment guide exists
- Rollback plan exists
- Monitoring/observability documented

Output: `docs/09-devops-readiness.md`

# Phase 3 — Risk Manager final classification

Invoke `@risk-manager`.

Output: `docs/09-risk-review.md`

Must classify as one of:
- **Production-ready** — all gates pass, tests pass, security clean, deployment documented
- **MVP-ready** — functional and tested, minor operational gaps acceptable for controlled launch
- **Prototype** — demonstrates concept, not safe for real users or real data
- **Not ready** — critical blockers exist; do not release

Classification rules:
- Critical/high unresolved security findings → Not ready
- Missing tests → cannot be Production-ready
- Missing deployment guide → cannot be Production-ready
- Missing rollback plan → cannot be Production-ready
- Hardcoded secrets → Not ready

# Phase 4 — Output

Print:
1. Risk classification result
2. Release blocker list (if any)
3. Warnings list (non-blocking)
4. Recommended next step:
   - If Production-ready or MVP-ready → `/release`
   - If Prototype or Not ready → list what must be fixed first

Do not deploy. Do not package the release. This command only classifies.
