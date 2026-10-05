// Manual tour: who you are signed in as, and signing out.
import { signIn } from '../support/sign-in';

const T = 'account';

describe('Tour: your account', () => {
  it('[TC-20] shows who is signed in and signs out', () => {
    signIn('Sara');
    cy.get('#whoami').should('contain', 'Sara');
    cy.manualStep(T, 'whoami', 'Check who is signed in', '#whoami',
      'Your name and role always show in the top bar.');
    cy.manualStep(T, 'sign-out', 'Sign out', '#sign-out');
    cy.get('#sign-out').click();
    cy.get('#signin-form').should('be.visible');
    cy.manualStep(T, 'signed-out', 'You are back at the sign-in page', '#signin-form');
  });
});
