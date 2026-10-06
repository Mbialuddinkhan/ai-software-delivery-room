// ASDR coverage markers for Cypress (browser side). Import from
// cypress/support/e2e.js; register asdr-cover-plugin.js in cypress.config.js.
//
//   cy.flowStep('PF-02.3');                 // a journey test reached this flow step
//   cy.covers('AC-03.2', 'BR-02');          // right where the test asserts them
//   cy.metric('board-render-500', ms, 'ms', 1000);
//
// The test title must carry its test-case id: it('[TC-03] …').
const tcIds = (title) => {
  const out = new Set();
  for (const m of title.matchAll(/\[TC-(\d+)\]|(?<![A-Za-z0-9])[Tt][Cc][_-](\d+)(?![0-9])/g)) out.add(`TC-${m[1] || m[2]}`);
  return [...out];
};

const record = (kind, extra) => {
  const title = Cypress.currentTest.titlePath.join(' ');
  return cy.task('asdrCover', { framework: 'cypress', test: title, tc: tcIds(title), kind, ...extra }, { log: false });
};

Cypress.Commands.add('flowStep', (id) => { cy.log(`flow step ${id}`); record('step', { items: [id] }); });
Cypress.Commands.add('covers', (...items) => { record('covers', { items }); });
Cypress.Commands.add('metric', (name, value, unit, budget) => {
  record('metric', { name, value, unit, budget: budget === undefined ? null : budget });
});
