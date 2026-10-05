// TaskBoard's sign-in for cy.loginAs(role). No passwords in the sample.
const NAMES = { member: 'Sara', admin: 'Omar' };

export function login(role) {
  cy.visit('/');
  cy.get('#name').type(NAMES[role]);
  cy.get('#role').select(role);
  cy.get('#signin-submit').click();
  cy.contains('h1', 'Team board').should('be.visible');
}
