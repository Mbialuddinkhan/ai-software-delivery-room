import { signIn } from '../support/sign-in';

describe('TaskBoard (Cypress)', () => {
  it('[TC-18] adds a task and updates the counter', () => {
    signIn('Sara');
    cy.get('#new-task').type('Write release notes');
    cy.get('#add-task').click();
    cy.contains('#tasks li', 'Write release notes').should('be.visible');
    cy.get('#counter').should('have.text', '1 open · 0 done');
    cy.asdrA11y('board');
    cy.covers('FR-02', 'FR-05');
  });

  it('[TC-19] hides settings from members', () => {
    signIn('Sara');
    cy.get('#nav-settings').should('not.be.visible');
    cy.covers('AC-06.2');
  });

  it('[TC-12] keeps tasks after a page reload', () => {
    cy.loginAs('member');          // saved login: this test is not about signing in
    cy.visit('/');
    cy.get('#new-task').type('Order snacks{enter}');
    cy.reload();
    cy.contains('#tasks li', 'Order snacks').should('be.visible');
    cy.covers('AC-08.3');
  });

  it('[TC-04] an empty task title adds nothing', () => {
    signIn('Sara');
    cy.get('#new-task').type('   {enter}');
    cy.get('#tasks li').should('have.length', 0);
    cy.get('#counter').should('have.text', '0 open · 0 done');
    cy.flowStep('PF-02.E1');
    cy.covers('AC-02.4', 'EC-01', 'UC-02.E1');
  });

  it('[TC-23] a member sees no Delete when deleting is not allowed', () => {
    cy.loginAs('member');          // saved login; deleting by members is off by default
    cy.visit('/');
    cy.get('#new-task').type('Cannot remove me{enter}');
    cy.contains('#tasks li', 'Cannot remove me').should('be.visible');
    cy.get('#tasks button.delete').should('not.exist');
    cy.flowStep('PF-05.E1');
    cy.covers('AC-07.2', 'BR-02', 'UC-07.E1');
  });
});
