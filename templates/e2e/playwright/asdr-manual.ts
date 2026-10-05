// ASDR manual-tour helper for Playwright.
//
// A "tour" is an ordinary Playwright test that walks one user task and calls
// manualStep() at every moment a user manual should show. Each call:
//   1. outlines the element the user acts on (red, 3px) so the screenshot
//      shows exactly where to click or type,
//   2. saves a viewport screenshot to <ASDR_MANUAL_DIR>/screens/<tour>--<id>.png,
//   3. records the step in <ASDR_MANUAL_DIR>/tours/<tour>.json,
//   4. attaches the screenshot to the test so it appears in the test report.
// Tours assert like any test, so a manual can never show a broken flow: if
// the flow breaks, the tour fails and build_manual.py refuses stale shots.
//
// Copy unchanged into the project (devops does this from
// .harness/templates/e2e/playwright/). Environment, set by run_tests.py:
//   ASDR_MANUAL_DIR  where screens/ and tours/ go (default .harness/manual)
//   ASDR_COMMIT      commit the screenshots were taken from
import { test } from '@playwright/test';
import type { Locator, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const HIGHLIGHT = '3px solid #e5484d';

export async function manualStep(
  page: Page,
  tour: string,
  id: string,
  title: string,
  target?: Locator | null,
  note?: string,
): Promise<void> {
  const dir = process.env.ASDR_MANUAL_DIR || '.harness/manual';
  fs.mkdirSync(path.join(dir, 'screens'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'tours'), { recursive: true });

  if (target) {
    await target.scrollIntoViewIfNeeded();
    await target.evaluate((el: HTMLElement, outline: string) => {
      el.setAttribute('data-asdr-prev-outline', el.style.outline || '');
      el.style.outline = outline;
      el.style.outlineOffset = '3px';
    }, HIGHLIGHT);
  }
  const rel = `screens/${tour}--${id}.png`;
  const abs = path.join(dir, rel);
  await page.screenshot({ path: abs });
  if (target) {
    await target.evaluate((el: HTMLElement) => {
      el.style.outline = el.getAttribute('data-asdr-prev-outline') || '';
      el.style.outlineOffset = '';
      el.removeAttribute('data-asdr-prev-outline');
    });
  }
  await test.info().attach(`manual: ${title}`, { path: abs, contentType: 'image/png' });

  const file = path.join(dir, 'tours', `${tour}.json`);
  const manifest = fs.existsSync(file)
    ? JSON.parse(fs.readFileSync(file, 'utf8'))
    : { schema: 1, tour, framework: 'playwright', steps: [] as any[] };
  manifest.commit = process.env.ASDR_COMMIT || null;
  manifest.captured_at = new Date().toISOString();
  manifest.steps = manifest.steps.filter((s: any) => s.id !== id);
  manifest.steps.push({
    id, title, url: page.url(), screenshot: rel,
    target: target ? target.toString() : null, note: note || null,
    viewport: page.viewportSize(),
  });
  manifest.steps.forEach((s: any, i: number) => (s.order = i + 1));
  fs.writeFileSync(file, JSON.stringify(manifest, null, 2));
}
