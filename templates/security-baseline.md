# Security & Production Baseline

<!-- This baseline applies to EVERY sprint, not just the release gate.
The generator builds to it; the evaluator verifies the items touching the
sprint's surface, with evidence. Aligned with OWASP Top 10 / ASVS Level 1
and 12-factor operational practice. Security bolted on at the end is
security that ships late and broken — it has to live in the loop. -->

## S1 — Input handling

- All external input (forms, query params, headers, file uploads, webhook
  payloads) is validated server-side: type, length, range, format.
- Database access uses parameterized queries or an ORM — never string
  concatenation into SQL/NoSQL queries.
- Output into HTML is escaped or rendered via a framework that escapes by
  default (XSS).
- File uploads: extension + content-type allowlist, size limit, stored
  outside the web root with generated names.

## S2 — Authentication & sessions

- Passwords hashed with a modern KDF (bcrypt/argon2), never reversible.
- Session tokens/JWTs: httpOnly + secure cookies or proper Authorization
  headers; sensible expiry; logout invalidates.
- Login errors never reveal which field was wrong; failed logins are rate
  limited.

## S3 — Authorization

- Every protected route/action checks authorization server-side — the UI
  hiding a button is not access control.
- Object-level checks: user A cannot read/modify user B's records by
  changing an ID (IDOR).
- Admin functionality is role-gated; no unauthenticated admin surface, ever.

## S4 — Secrets & configuration

- No secrets in source, logs, error messages, or client-side code.
  Environment variables only; `.env` is gitignored; `.env.example`
  documents every variable.
- Debug modes and default credentials are off outside development.

## S5 — Dependencies & transport

- Dependencies pinned (lockfile committed); no known critical CVEs at the
  time of the sprint.
- HTTPS assumed in production config; security-relevant headers set
  (at minimum: CSP or an explicit reason why not, X-Content-Type-Options,
  frame protection).

## S6 — AI features (only if present)

- All user-supplied or web-sourced content reaching a model prompt is
  treated as untrusted; tool calls triggered by model output are
  permission-checked like any user action.
- Model outputs shown to users or executed are validated/escaped.

## P1 — Production engineering standards

- Every sprint ships automated tests for its criteria; CI runs tests +
  lint on every push and fails the build on error.
- One consistent error-handling pattern (from docs/03 conventions);
  no bare excepts / swallowed errors on critical paths.
- Structured logging on auth events, mutations, and failures — enough to
  answer "what happened?" without logging secrets or PII.
- No TODO/FIXME/stub left on a critical path at sprint end.
- Health/readiness endpoint (or equivalent) exists once the app serves traffic.

## How this is enforced

1. Contract: the Security category draws its criteria from the sections
   above that the sprint touches.
2. Generator BUILD mode: builds to this baseline by default — it is part
   of the definition of "implemented".
3. Evaluator EVALUATE mode: verifies the applicable items with evidence
   (command output or file:line) even when a contract criterion doesn't
   name them; a baseline violation is grounds for FAIL.
4. Release gate: security-compliance re-verifies the full list on the
   whole codebase.
