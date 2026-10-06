// Cross-role effects of admin settings (F-06, F-07): tested from the side of the
// role they change — the team member — with the setting on and off.
import { test, expect, Page } from '@playwright/test';
import { authFile } from './asdr-auth';
import { covers, flowStep } from './asdr-cover';

async function signIn(page: Page, name: string, role: 'member' | 'admin') {
  await page.getByLabel('Your name').fill(name);
  await page.getByLabel('Role').selectOption(role);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
}

test('[TC-22] a member deletes a task when the admin allows it', async ({ page }) => {
  await page.goto('/');
  await signIn(page, 'Omar', 'admin');
  await page.getByRole('link', { name: 'Settings' }).click();
  await page.getByLabel('Team members can delete tasks').check();
  await expect(page.getByRole('status')).toHaveText('Settings saved.');
  await page.getByRole('button', { name: 'Sign out' }).click();

  await signIn(page, 'Sara', 'member');
  for (const t of ['Keep this', 'Old duplicate']) {
    await page.getByPlaceholder(/What needs doing/).fill(t);
    await page.getByRole('button', { name: 'Add task' }).click();
  }
  await expect(page.getByRole('button', { name: /^Delete / })).toHaveCount(2);   // Delete on each task
  await flowStep('PF-05.1');
  await page.getByRole('button', { name: 'Delete Old duplicate' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(1);
  await expect(page.getByRole('listitem')).toContainText('Keep this');
  await expect(page.locator('#counter')).toHaveText('1 open · 0 done');
  await flowStep('PF-05.2');
  covers('AC-07.1', 'BR-02', 'F-07');
});

test('[TC-27] a category an admin adds reaches a team member', async ({ page }) => {
  await page.goto('/');
  await signIn(page, 'Omar', 'admin');
  await page.getByRole('link', { name: 'Settings' }).click();
  await page.getByPlaceholder('New category name').fill('Design');
  await page.getByRole('button', { name: 'Add category' }).click();
  await page.getByRole('button', { name: 'Sign out' }).click();

  await signIn(page, 'Sara', 'member');
  await expect(page.getByLabel('Category', { exact: true }).locator('option', { hasText: 'Design' })).toHaveCount(1);
  covers('AC-06.1', 'F-06');
});

test.describe('admin (saved login), members may not delete', () => {
  test.use({ storageState: authFile('admin') });

  test('[TC-28] an admin can always delete', async ({ page }) => {
    await page.goto('/#settings');
    await expect(page.getByLabel('Team members can delete tasks')).not.toBeChecked();
    await page.getByRole('link', { name: 'Board' }).click();
    await page.getByPlaceholder(/What needs doing/).fill('Admin cleanup');
    await page.getByRole('button', { name: 'Add task' }).click();
    await page.getByRole('button', { name: 'Delete Admin cleanup' }).click();
    await expect(page.getByRole('listitem')).toHaveCount(0);
    covers('AC-07.3', 'BR-02', 'UC-07.A1', 'FR-09');
  });
});
