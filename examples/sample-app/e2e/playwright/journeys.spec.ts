// End-to-end journey tests: each walks one process flow (docs/02d-process-flows.md)
// from trigger to outcome. Titles start with the test-case id from docs/02e-test-cases.md.
import { test, expect } from '@playwright/test';
import { checkA11y } from './asdr-a11y';
import { covers, flowStep } from './asdr-cover';

test('[TC-03] member works through the day: quick add, complete, filter, sign out and come back', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Your name').fill('Sara');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
  await checkA11y(page, 'empty board');

  // PF-02.1–2: N jumps to the new-task box; Enter adds the task
  await page.keyboard.press('n');
  await expect(page.getByPlaceholder(/What needs doing/)).toBeFocused();
  await flowStep('PF-02.1');
  covers('AC-02.3');
  await page.keyboard.type('Draft the agenda');
  await page.keyboard.press('Enter');
  await page.getByPlaceholder(/What needs doing/).fill('Book the room');
  await page.keyboard.press('Enter');
  await expect(page.locator('#counter')).toHaveText('2 open · 0 done');
  await flowStep('PF-02.2');
  covers('AC-02.2');

  // PF-02.3: tick one done
  await page.getByLabel('Mark Draft the agenda done').check();
  await expect(page.locator('#counter')).toHaveText('1 open · 1 done');
  await flowStep('PF-02.3');
  covers('AC-03.1');
  await checkA11y(page, 'board with tasks');

  // PF-02.4: Active shows only what is left
  await page.getByRole('button', { name: 'Active' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('listitem')).toContainText('Book the room');
  await flowStep('PF-02.4');
  covers('AC-04.1');

  // PF-02.5: sign out, sign back in, everything is still there
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  covers('AC-08.1');
  await page.getByLabel('Your name').fill('Sara');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByRole('button', { name: 'All' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  covers('AC-04.3');
  await expect(page.locator('#counter')).toHaveText('1 open · 1 done');
  await flowStep('PF-02.5');
  covers('AC-08.2', 'FR-10');
});
