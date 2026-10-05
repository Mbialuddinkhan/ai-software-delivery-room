// ASDR manual-tour command for Cypress (browser side).
//
// Usage in a tour spec:
//   cy.manualStep('member-basics', 'sign-in', 'Sign in', '#signin-submit')
// Outlines the element (red, 3px), takes a viewport screenshot, and hands
// the step to the node-side plugin (asdr-manual-plugin.js), which copies the
// screenshot to <ASDR_MANUAL_DIR>/screens/ and records it in
// <ASDR_MANUAL_DIR>/tours/<tour>.json — the same format the Playwright and
// Selenium helpers write, so build_manual.py treats them identically.
//
// Copy unchanged into cypress/support/ and import it from cypress/support/e2e.js.
const HIGHLIGHT = '3px solid #e5484d';

Cypress.Commands.add('manualStep', (tour, id, title, selector, note) => {
  const name = `asdr-manual__${tour}__${id}`;
  cy.url({ log: false }).then((url) =>
    cy.task('asdrManualPending', { tour, id, title, name, url,
      target: selector || null, note: note || null }, { log: false }));
  if (selector) {
    cy.get(selector).scrollIntoView().then(($el) => {
      const el = $el[0];
      el.setAttribute('data-asdr-prev-outline', el.style.outline || '');
      el.style.outline = HIGHLIGHT;
      el.style.outlineOffset = '3px';
    });
  }
  cy.screenshot(name, { capture: 'viewport', overwrite: true });
  if (selector) {
    cy.get(selector).then(($el) => {
      const el = $el[0];
      el.style.outline = el.getAttribute('data-asdr-prev-outline') || '';
      el.style.outlineOffset = '';
      el.removeAttribute('data-asdr-prev-outline');
    });
  }
});
