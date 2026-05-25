---
description: Run the Release Manager. Packages the approved release with changelog, release notes, deployment checklist, and post-release plan.
allowed-tools: Task, Read, Write, Edit, Bash, Glob, Grep
---

You are the RELEASE ORCHESTRATOR.

Prerequisite: `/riskgate` must have been run and returned MVP-ready or Production-ready.

Verify `docs/09-risk-review.md` exists and contains MVP-ready or Production-ready classification. If not, stop and direct user to run `/riskgate` first.

# Phase 1 — Documentation

Invoke `@documentation` to ensure all docs are finalized.

Required outputs:
- `README.md` — updated with final setup and usage instructions
- `docs/user-guide.md`
- `docs/admin-guide.md`
- `docs/api-reference.md` (if API exists)
- `docs/deployment.md`
- `docs/troubleshooting.md`

# Phase 2 — Release packaging

Invoke `@release-manager`.

Produce:
- `CHANGELOG.md` — what changed, by sprint
- `docs/10-release-notes.md` — user-facing summary of features and fixes
- `docs/10-release-checklist.md` — final pre-deploy verification
- `docs/10-post-release-monitoring.md` — what to watch after deploy

Release checklist must confirm each item:
- [ ] All sprints passed evaluator review
- [ ] CI pipeline passes
- [ ] Security review passed (no unresolved critical/high)
- [ ] Risk Manager classified as MVP-ready or Production-ready
- [ ] Docker and docker-compose work locally
- [ ] Deployment guide is complete
- [ ] Rollback plan is documented
- [ ] Environment variables are documented in .env.example
- [ ] No hardcoded secrets in source
- [ ] Known limitations are documented
- [ ] Human owner has reviewed and approved

# Phase 3 — Final output

Print:
1. Release version tag recommendation (e.g. `v0.1.0-mvp`)
2. What was built (sprint summary table)
3. How to deploy (2–3 key commands)
4. How to roll back (if needed)
5. Known limitations
6. Recommended post-release monitoring steps
7. Next roadmap recommendations

This is the final step. After this, the human deploys manually.
