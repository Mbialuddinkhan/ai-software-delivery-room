// PROJECT-SPECIFIC (devops fills this in): how a person in each test role signs
// in. Credentials come from ASDR_USER_<ROLE> / ASDR_PASS_<ROLE>, which
// cypress.config.js passes through as sensitive env — test users created by
// the seed step, never real accounts.
const secrets = (keys) => (typeof cy.env === 'function'
  ? cy.env(keys, { log: false })                                   // Cypress 16+
  : cy.wrap(Object.fromEntries(keys.map((k) => [k, Cypress.env(k)])), { log: false }));

export function login(role) {
  const key = role.toUpperCase();
  secrets([`ASDR_USER_${key}`, `ASDR_PASS_${key}`]).then((v) => {
    const user = v[`ASDR_USER_${key}`];
    const pass = v[`ASDR_PASS_${key}`];
    if (!user || !pass) throw new Error(`Set ASDR_USER_${key} and ASDR_PASS_${key}`);
    cy.visit('/login');                                     // <- your sign-in page
    cy.get('input[name=email]').type(user);                 // <- your fields
    cy.get('input[name=password]').type(pass, { log: false });
    cy.contains('button', 'Sign in').click();
    cy.location('pathname').should('include', '/dashboard'); // <- where a signed-in user lands
  });
}
