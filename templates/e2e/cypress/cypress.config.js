// ASDR Cypress config template. devops copies it to the project root and
// sets baseUrl. run_tests.py drives live vs CI runs:
//   CI / default : `cypress run`                    (headless, video on)
//   live         : `cypress run --headed --browser chrome` or `cypress open`
// JUnit goes to <results>/junit/cypress-<hash>.xml for publish_test_report.py.
const { defineConfig } = require('cypress');
const asdrManual = require('./cypress/plugins/asdr-manual-plugin');
const asdrA11y = require('./cypress/plugins/asdr-a11y-plugin');

const results = process.env.ASDR_RESULTS_DIR || 'test-results';

module.exports = defineConfig({
  // Same viewport as the Playwright manual project and the Selenium driver,
  // so manual screenshots from every framework match in size.
  viewportWidth: 1280,
  viewportHeight: 800,
  video: true,
  videosFolder: `${results}/cypress/videos`,
  screenshotsFolder: `${results}/cypress/screenshots`,
  reporter: 'mocha-junit-reporter',
  reporterOptions: {
    mochaFile: `${results}/junit/cypress-[hash].xml`,
    testsuitesTitle: 'Cypress',
    attachments: true,
  },
  // Cypress 16+: test-user credentials (ASDR_USER_<ROLE>, ASDR_PASS_<ROLE>)
  // are sensitive and read with cy.env([...]); the accessibility settings
  // (ASDR_A11Y_*) are public and read with Cypress.expose(). On Cypress 15 or
  // older, merge both into `env` instead.
  env: Object.fromEntries(Object.entries(process.env).filter(([k]) => /^ASDR_(USER|PASS)_/.test(k))),
  expose: Object.fromEntries(Object.entries(process.env).filter(([k]) => /^ASDR_A11Y_/.test(k))),
  e2e: {
    baseUrl: process.env.BASE_URL || 'http://localhost:4173', // <- project URL
    specPattern: 'cypress/e2e/**/*.cy.{js,ts}',
    setupNodeEvents(on, config) {
      asdrManual(on, config);
      return asdrA11y(on, config);
    },
  },
});
