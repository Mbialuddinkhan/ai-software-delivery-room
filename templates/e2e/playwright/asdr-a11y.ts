// ASDR accessibility check for Playwright (axe-core). Copy unchanged.
//
//   await checkA11y(page, 'board');                 // whole page
//   await checkA11y(page, 'settings', { include: '#settings' });
//
// Call it in journey tests at every new screen. Each call writes
// <ASDR_RESULTS_DIR>/a11y/playwright--<test>--<label>.json (run_tests.py adds
// them up for the report) and fails the test on violations whose impact is in
// ASDR_A11Y_FAIL_ON (default "critical,serious"; "none" only records).
// Rules: ASDR_A11Y_TAGS (default WCAG 2.1 A + AA).
// Needs: npm i -D @axe-core/playwright
import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'fs';
import * as path from 'path';

const slug = (s: string) => s.replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);

export async function checkA11y(page: Page, label: string,
  opts: { include?: string; exclude?: string[] } = {}): Promise<void> {
  const tags = (process.env.ASDR_A11Y_TAGS || 'wcag2a,wcag2aa,wcag21a,wcag21aa').split(',').map((t) => t.trim());
  const failOn = (process.env.ASDR_A11Y_FAIL_ON || 'critical,serious').split(',')
    .map((t) => t.trim()).filter((t) => t && t !== 'none');
  let builder = new AxeBuilder({ page }).withTags(tags);
  if (opts.include) builder = builder.include(opts.include);
  for (const x of opts.exclude || []) builder = builder.exclude(x);
  const r = await builder.analyze();
  const violations = r.violations.map((v) => ({
    id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.length,
    targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')),
  }));
  const info = test.info();
  const record = { schema: 1, framework: 'playwright', test: info.title, label, url: page.url(),
    fail_on: failOn, tags, violations, passes: r.passes.length };
  const dir = path.join(process.env.ASDR_RESULTS_DIR || 'test-results', 'a11y');
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `playwright--${slug(info.title)}--${slug(label)}.json`);
  fs.writeFileSync(file, JSON.stringify(record, null, 2));
  await info.attach(`accessibility: ${label}`, { path: file, contentType: 'application/json' });
  const blocking = violations.filter((v) => failOn.includes(v.impact || ''));
  expect(blocking, `accessibility (${label}): ` +
    blocking.map((v) => `${v.impact} ${v.id} — ${v.help} (${v.targets.join(', ')})`).join('; ')).toEqual([]);
}
