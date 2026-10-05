// ASDR Cypress config template. devops copies it to the project root and
// sets baseUrl. run_tests.py drives live vs CI runs:
//   CI / default : `cypress run`                    (headless, video on)
//   live         : `cypress run --headed --browser chrome` or `cypress open`
// JUnit goes to <results>/junit/cypress-<hash>.xml for publish_test_report.py.
const { defineConfig } = require('cypress');
const asdrManual = require('./cypress/plugins/asdr-manual-plugin');

const results = process.env.ASDR_RESULTS_DIR || 'test-results';

module.exports = defineConfig({
  video: true,
  videosFolder: `${results}/cypress/videos`,
  screenshotsFolder: `${results}/cypress/screenshots`,
  reporter: 'mocha-junit-reporter',
  reporterOptions: {
    mochaFile: `${results}/junit/cypress-[hash].xml`,
    testsuitesTitle: 'Cypress',
    attachments: true,
  },
  e2e: {
    baseUrl: process.env.BASE_URL || 'http://localhost:4173', // <- project URL
    specPattern: 'cypress/e2e/**/*.cy.{js,ts}',
    setupNodeEvents(on, config) {
      return asdrManual(on, config);
    },
  },
});
