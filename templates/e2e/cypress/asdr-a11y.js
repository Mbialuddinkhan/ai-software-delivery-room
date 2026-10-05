// ASDR accessibility check for Cypress (axe-core, browser side). Import from
// cypress/support/e2e.js; register asdr-a11y-plugin.js in cypress.config.js.
//
//   cy.asdrA11y('board');                        // whole page
//   cy.asdrA11y('settings', { include: '#settings' });
//
// Writes <ASDR_RESULTS_DIR>/a11y/cypress--<test>--<label>.json and fails on
// violations whose impact is in ASDR_A11Y_FAIL_ON (default "critical,serious").
// Needs: npm i -D axe-core
const DEFAULT_TAGS = 'wcag2a,wcag2aa,wcag21a,wcag21aa';
// Cypress 16 reads public config with Cypress.expose(); older versions with Cypress.env().
const setting = (k) => (typeof Cypress.expose === 'function' ? Cypress.expose(k) : Cypress.env(k));

Cypress.Commands.add('asdrA11y', (label, opts = {}) => {
  const tags = (setting('ASDR_A11Y_TAGS') || DEFAULT_TAGS).split(',').map((t) => t.trim());
  const failOn = (setting('ASDR_A11Y_FAIL_ON') || 'critical,serious').split(',')
    .map((t) => t.trim()).filter((t) => t && t !== 'none');
  cy.task('asdrAxeSource', null, { log: false }).then((src) => {
    cy.window({ log: false }).then({ timeout: 30000 }, (win) => {
      if (!win.axe) win.eval(src);
      const context = opts.include ? win.document.querySelector(opts.include) : win.document;
      return win.axe.run(context, { runOnly: { type: 'tag', values: tags } });
    }).then((r) => {
      const violations = r.violations.map((v) => ({
        id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.length,
        targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')),
      }));
      cy.url({ log: false }).then((url) => {
        const record = { schema: 1, framework: 'cypress', test: Cypress.currentTest.titlePath.join(' '),
          label, url, fail_on: failOn, tags, violations, passes: r.passes.length };
        cy.task('asdrA11yWrite', record, { log: false });
        const blocking = violations.filter((v) => failOn.includes(v.impact || ''));
        expect(blocking, `accessibility (${label}): ` +
          blocking.map((v) => `${v.impact} ${v.id} — ${v.help}`).join('; ')).to.deep.equal([]);
      });
    });
  });
});
