export const signIn = (name, role = 'member') => {
  cy.visit('/', { onBeforeLoad: (win) => win.localStorage.clear() });
  cy.get('#name').type(name);
  cy.get('#role').select(role);
  cy.get('#signin-submit').click();
  cy.contains('h2, h1', 'Team board').should('be.visible');
};
