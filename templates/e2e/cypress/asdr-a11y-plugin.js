// ASDR accessibility plugin for Cypress (node side): serves axe-core's source
// to the browser and writes each check's result for run_tests.py.
// In cypress.config.js:  setupNodeEvents(on, config) { asdrManual(on, config); return asdrA11y(on, config); }
const fs = require('fs');
const path = require('path');

const slug = (s) => String(s).replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);

module.exports = function asdrA11y(on, config) {
  on('task', {
    asdrAxeSource() {
      return fs.readFileSync(require.resolve('axe-core/axe.min.js', { paths: [process.cwd()] }), 'utf8');
    },
    asdrA11yWrite(record) {
      const dir = path.join(process.env.ASDR_RESULTS_DIR || 'test-results', 'a11y');
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, `cypress--${slug(record.test)}--${slug(record.label)}.json`),
        JSON.stringify(record, null, 2));
      return null;
    },
  });
  return config;
};
