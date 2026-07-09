# End-to-End Testing Plan

<!-- Save as: docs/08-e2e-testing.md · Written by: devops
A LIVE E2E plan the user can watch run. Runs must produce a video and
screenshots so a human — or the evaluator — can review exactly what happened.
Fill the placeholders for THIS project's app URL, routes and flows. -->

## 1. Tool choice

- Web UIs (default): <Cypress>.
- Alternative: <Playwright> — pick it when you need multi-browser, multi-tab, or cross-origin flows.
- Services with no UI: API-level E2E via <supertest (Node) / pytest + httpx (Python)> hitting real endpoints.
- Decision for this project: <tool + one-line reason>.

## 2. Folder structure

```
cypress/
  e2e/            <feature>.cy.js        # one spec per user-facing flow
  support/        commands.js, e2e.js    # shared setup, custom commands
cypress.config.js                        # base URL, video + screenshot config
cypress/videos/                          # recorded runs (artifacts)
cypress/screenshots/                     # failure screenshots (artifacts)
```

## 3. Config — make every run visible and reviewable

```js
// cypress.config.js
const { defineConfig } = require('cypress');

module.exports = defineConfig({
  video: true,                  // record every run to cypress/videos/
  screenshotOnRunFailure: true, // capture the screen at the point of failure
  e2e: {
    baseUrl: '<http://localhost:3000>',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.js',
  },
});
```

Artifacts land in `cypress/videos/` and `cypress/screenshots/` — these are the evidence a reviewer opens.

## 4. How to watch it live

- Interactive, headed, local: `npx cypress open` — opens the runner and steps through each command as it happens.
- Headed batch run: `npx cypress run --headed` — the full suite in a visible browser.
- Headless (CI): `npx cypress run` — no window, but `video: true` still records; upload `cypress/videos/` and `cypress/screenshots/` as CI artifacts.

## 5. Minimal sample spec

```js
// cypress/e2e/login.cy.js
describe('login', () => {
  it('shows the app and logs a user in', () => {
    cy.visit('/');                                  // 1. visit the app
    cy.contains('<Sign in>').should('be.visible');  // 2. assert a visible element
    cy.get('[data-cy=email]').type('<user@example.com>');  // 3. login flow
    cy.get('[data-cy=password]').type('<password>');
    cy.get('[data-cy=submit]').click();
    cy.url().should('include', '/<dashboard>');     // assert we landed inside
    cy.contains('<Welcome>').should('be.visible');
  });
});
```

## 6. Rules

- Every user-facing acceptance criterion gets an E2E spec — no criterion ships unwatched.
- The FULL E2E suite runs every sprint (regression) and again at the release gate.
- The evaluator captures the recorded video / screenshot path as evidence in its report.
