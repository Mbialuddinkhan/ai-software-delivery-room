// [TC-25] NFR-02: the board renders 500 tasks in under a second. The time is
// measured inside the page, from navigation start to the moment the 500th task
// is in the list (a MutationObserver, so test-runner polling is not counted),
// and recorded as a measurement so the report and facts carry the number.
import { test, expect } from '@playwright/test';
import { covers, metric } from './asdr-cover';

test('[TC-25] the board renders 500 tasks in under a second', async ({ page }) => {
  await page.addInitScript(() => {
    if (localStorage.getItem('taskboard.v1')) return;
    const tasks = Array.from({ length: 500 }, (_, i) => ({
      id: i + 1, title: `Task ${i + 1}`, category: i % 2 ? 'Bugs' : 'General', done: i % 3 === 0 }));
    localStorage.setItem('taskboard.v1', JSON.stringify({
      user: { name: 'Sara', role: 'member' }, tasks, nextId: 501,
      categories: ['General', 'Bugs'], membersCanDelete: false, filter: 'all' }));
  });
  await page.addInitScript(() => {
    const obs = new MutationObserver(() => {
      if (document.querySelectorAll('#tasks li').length >= 500) {
        (window as any).__rendered500 = performance.now();
        obs.disconnect();
      }
    });
    obs.observe(document, { childList: true, subtree: true });
  });
  await page.goto('/');
  await expect(page.getByRole('listitem')).toHaveCount(500);
  const ms = Math.round(await page.evaluate(() => (window as any).__rendered500));
  metric('board-render-500', ms, 'ms', 1000);
  expect(ms).toBeLessThan(1000);
  covers('NFR-02');
});
