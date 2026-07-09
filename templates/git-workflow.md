# Git & Repository Workflow

<!-- Save as: docs/07-git-workflow.md · Written by: devops (architecture phase)
Fill every section for THIS project. The generator follows this document when
it lands each sprint's work; the release-manager follows it when tagging.
Also copy the "Conventions the build loop follows" block into CLAUDE.md's
Project facts so the generator sees it every sprint. -->

## 1. Repository setup

- Host: <GitHub | GitLab | …> · Visibility: <private | public>
- Default branch: `main` (protected — see §5)
- Create with: `gh repo create <name> --private --source=. --remote=origin --push`
  (or the host's UI; do NOT initialize with a README if one already exists).
- `.gitignore` must exclude: secrets/`.env`, build output, dependency dirs,
  caches, and the harness runtime dirs (`.harness/traces/`, `.harness/tests/`
  artifacts if not meant to ship). Commit `.env.example`, never `.env`.

## 2. Branching strategy

Default: **trunk-based with short-lived per-sprint branches.**

- One branch per sprint, cut from `main`: `sprint-NN-<short-slug>`
  (e.g. `sprint-02-login`).
- Branches live hours-to-days, never weeks. Merge back to `main` only after the
  sprint's evaluator verdict is PASS and CI is green.
- No long-lived `develop`/feature branches (they are where drift hides). If the
  project genuinely needs release trains, document the exception here with why.

## 3. Commit conventions

Use **Conventional Commits**: `type(scope): summary` (≤ 50 chars), body wraps at
72. Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `build`,
`ci`. Reference the sprint and requirement ids in the body:

```
feat(auth): reject wrong password without leaking which field

Implements sprint-02 criteria 3,7. Covers FR-04, FR-05.
```

- Commit in small, working increments — every commit should build.
- Never commit secrets, credentials, tokens, or real customer data.

## 4. Pull requests

- One PR per sprint, from `sprint-NN-*` into `main`. Title = the sprint goal.
- PR description lists: the requirement ids covered, the evaluator verdict, and
  the eval-report path.
- **Required to merge:** CI green **and** evaluator verdict PASS **and** (if the
  Product-Integrity layer is enabled) no new `broken`/`drifted` requirements.
- Squash-merge by default (one clean commit per sprint on `main`), unless the
  project needs full history — state which here.

## 5. Branch protection (set once on the host)

- `main`: require PR before merge, require status checks (CI) to pass, no direct
  pushes, no force-push. Require at least the CI check defined in
  `.github/workflows/ci.yml`.

## 6. What to commit / what not

Commit: source, tests, config templates (`.env.example`), IaC, CI workflows,
docs, lockfiles. Do NOT commit: `.env`/secrets, build artifacts, `node_modules`
/ virtualenvs, editor/OS junk, large binaries (use LFS or external storage).

## 7. Versioning & release

- **SemVer** (`MAJOR.MINOR.PATCH`). Tag releases on `main`: `git tag -a vX.Y.Z`.
- The release-manager cuts the tag and CHANGELOG only after the risk-manager
  classifies `mvp-ready` or `production-ready`.
- Pre-1.0: minor bumps may include breaking changes; document that here.

## 8. Conventions the build loop follows (copy into CLAUDE.md)

```
Branching: one branch per sprint `sprint-NN-<slug>` off main; squash-merge on PASS+green CI.
Commits: Conventional Commits; reference sprint + requirement ids in the body.
Never commit secrets or .env; commit .env.example only.
Tag releases with SemVer only after risk-manager says mvp/production-ready.
```
