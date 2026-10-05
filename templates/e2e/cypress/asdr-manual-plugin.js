// ASDR manual-tour plugin for Cypress (node side). Register it in
// cypress.config.js:  setupNodeEvents(on, config) { return asdrManual(on, config); }
// If the project already handles 'after:screenshot', call asdrManual first and
// chain your own handler from inside it — Cypress keeps one handler per event.
const fs = require('fs');
const path = require('path');

module.exports = function asdrManual(on, config) {
  const dir = process.env.ASDR_MANUAL_DIR || '.harness/manual';
  const pending = {};

  on('task', {
    asdrManualPending(entry) {
      pending[entry.name] = entry;
      return null;
    },
  });

  on('after:screenshot', (details) => {
    const entry = pending[details.name];
    if (!entry) return;
    delete pending[details.name];
    const rel = `screens/${entry.tour}--${entry.id}.png`;
    fs.mkdirSync(path.join(dir, 'screens'), { recursive: true });
    fs.mkdirSync(path.join(dir, 'tours'), { recursive: true });
    fs.copyFileSync(details.path, path.join(dir, rel));

    const file = path.join(dir, 'tours', `${entry.tour}.json`);
    const m = fs.existsSync(file)
      ? JSON.parse(fs.readFileSync(file, 'utf8'))
      : { schema: 1, tour: entry.tour, framework: 'cypress', steps: [] };
    m.commit = process.env.ASDR_COMMIT || null;
    m.captured_at = new Date().toISOString();
    m.steps = m.steps.filter((s) => s.id !== entry.id);
    m.steps.push({
      id: entry.id, title: entry.title, url: entry.url, screenshot: rel,
      target: entry.target, note: entry.note,
      viewport: details.dimensions || null,
    });
    m.steps.forEach((s, i) => (s.order = i + 1));
    fs.writeFileSync(file, JSON.stringify(m, null, 2));
  });

  return config;
};
