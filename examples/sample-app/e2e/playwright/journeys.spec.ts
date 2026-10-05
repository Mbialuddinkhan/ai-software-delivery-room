// End-to-end journey tests: each walks one process flow (docs/02d-process-flows.md)
// from trigger to outcome. Titles start with the test-case id from docs/02e-test-cases.md.
import { test, expect } from '@playwright/test';
import { checkA11y } from './asdr-a11y';

test('[TC-03] member works through the day: quick add, complete, filter, sign out and come back', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Your name').fill('Sara');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
  await checkA11y(page, 'empty board');

  // PF-02.1–2: N jumps to the new-task box; Enter adds the task
  await page.keyboard.press('n');
  await expect(page.getByPlaceholder(/What needs doing/)).toBeFocused();
  await page.keyboard.type('Draft the agenda');
  await page.keyboard.press('Enter');
  await page.getByPlaceholder(/What needs doing/).fill('Book the room');
  await page.keyboard.press('Enter');
  await expect(page.locator('#counter')).toHaveText('2 open · 0 done');

  // PF-02.3: tick one done
  await page.getByLabel('Mark Draft the agenda done').check();
  await expect(page.locator('#counter')).toHaveText('1 open · 1 done');
  await checkA11y(page, 'board with tasks');

  // PF-02.4: Active shows only what is left
  await page.getByRole('button', { name: 'Active' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('listitem')).toContainText('Book the room');

  // PF-02.5: sign out, sign back in, everything is still there
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await page.getByLabel('Your name').fill('Sara');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('button', { name: 'All' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  await expect(page.locator('#counter')).toHaveText('1 open · 1 done');
});
