import { signIn } from '../support/sign-in';

describe('TaskBoard (Cypress)', () => {
  it('[TC-18] adds a task and updates the counter', () => {
    signIn('Sara');
    cy.get('#new-task').type('Write release notes');
    cy.get('#add-task').click();
    cy.contains('#tasks li', 'Write release notes').should('be.visible');
    cy.get('#counter').should('have.text', '1 open · 0 done');
  });

  it('[TC-19] hides settings from members', () => {
    signIn('Sara');
    cy.get('#nav-settings').should('not.be.visible');
  });

  it('[TC-12] keeps tasks after a page reload', () => {
    signIn('Sara');
    cy.get('#new-task').type('Order snacks{enter}');
    cy.reload();
    cy.contains('#tasks li', 'Order snacks').should('be.visible');
  });

  it('[TC-04] an empty task title adds nothing', () => {
    signIn('Sara');
    cy.get('#new-task').type('   {enter}');
    cy.get('#tasks li').should('have.length', 0);
    cy.get('#counter').should('have.text', '0 open · 0 done');
  });
});
