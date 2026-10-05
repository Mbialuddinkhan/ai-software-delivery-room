// ASDR saved logins for Cypress (browser side). Import from
// cypress/support/e2e.js. Tests that are not about signing in start with
//
//   cy.loginAs('admin'); cy.visit('/settings');
//
// cy.session signs in once per role (login.js) and restores cookies,
// localStorage and sessionStorage for every later test, across specs.
// Journey tests that walk the sign-in flow must not use it.
import { login } from './login';

Cypress.Commands.add('loginAs', (role) => {
  cy.session(['asdr', role], () => login(role), { cacheAcrossSpecs: true });
});
