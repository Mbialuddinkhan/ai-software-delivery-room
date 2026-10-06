import { test, expect } from '@playwright/test';
import { manualStep } from '../asdr-manual';
import { covers, flowStep } from '../asdr-cover';

const T = 'member-advanced';

test('[TC-07] Member advanced: filters, keyboard shortcut and export', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Your name').fill('Sara');
  await page.getByRole('button', { name: 'Sign in' }).click();
  for (const t of ['Draft proposal', 'Review contract', 'Book venue']) {
    await page.getByPlaceholder(/What needs doing/).fill(t);
    await page.getByRole('button', { name: 'Add task' }).click();
  }
  await page.getByLabel('Mark Review contract done').check();
  await manualStep(page, T, 'counter', 'Read the task counter', page.locator('#counter'));
  await page.getByRole('button', { name: 'Active' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(2);
  covers('AC-04.1');
  await manualStep(page, T, 'filter-active', 'Show only open tasks', page.getByRole('button', { name: 'Active' }));
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('listitem')).toContainText('Review contract');
  await flowStep('PF-04.1');
  covers('AC-04.2');
  await manualStep(page, T, 'filter-done', 'Show finished tasks', page.getByRole('button', { name: 'Done' }));
  await page.getByRole('button', { name: 'All' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(3);
  covers('AC-04.3', 'FR-04');
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('n');
  await expect(page.getByPlaceholder(/What needs doing/)).toBeFocused();
  covers('AC-02.3', 'FR-06');
  await manualStep(page, T, 'shortcut-n', 'Press N to start a new task', page.getByPlaceholder(/What needs doing/));
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('tasks.csv');
  await flowStep('PF-04.2');
  await manualStep(page, T, 'export', 'Export your tasks to a spreadsheet', page.getByRole('button', { name: 'Export CSV' }));
});
