// ASDR coverage markers for Cypress (node side): appends each marker to
// <ASDR_RESULTS_DIR>/coverage/cypress.jsonl for run_tests.py.
const fs = require('fs');
const path = require('path');

module.exports = function asdrCover(on, config) {
  on('task', {
    asdrCover(record) {
      const dir = path.join(process.env.ASDR_RESULTS_DIR || 'test-results', 'coverage');
      fs.mkdirSync(dir, { recursive: true });
      fs.appendFileSync(path.join(dir, 'cypress.jsonl'), JSON.stringify(record) + '\n');
      return null;
    },
  });
  return config;
};
