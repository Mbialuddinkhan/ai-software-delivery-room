import { test, expect } from '@playwright/test';
import { manualStep } from '../asdr-manual';
import { covers, flowStep } from '../asdr-cover';

const T = 'admin-settings';

test('[TC-05] Admin: categories and permissions', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Your name').fill('Omar');
  await page.getByLabel('Role').selectOption('admin');
  await manualStep(page, T, 'sign-in-admin', 'Sign in as a team admin', page.getByLabel('Role'));
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  await flowStep('PF-03.1');
  await manualStep(page, T, 'settings-link', 'Open Settings', page.getByRole('link', { name: 'Settings' }));
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: 'Team settings' })).toBeVisible();
  await flowStep('PF-03.2');
  await manualStep(page, T, 'settings-page', 'The settings page');
  await page.getByPlaceholder('New category name').fill('Design');
  await manualStep(page, T, 'new-category', 'Name a new category', page.getByPlaceholder('New category name'));
  await page.getByRole('button', { name: 'Add category' }).click();
  await expect(page.locator('#categories')).toContainText('Design');
  await flowStep('PF-03.3');
  await manualStep(page, T, 'category-added', 'Confirm the category was added', page.locator('#categories'));
  await page.getByLabel('Team members can delete tasks').check();
  await expect(page.getByRole('status')).toHaveText('Settings saved.');
  await flowStep('PF-03.4');
  covers('AC-07.4');
  await manualStep(page, T, 'allow-delete', 'Let team members delete tasks', page.getByLabel('Team members can delete tasks'));
  await page.getByRole('link', { name: 'Board' }).click();
  await page.getByPlaceholder(/What needs doing/).fill('Old duplicate task');
  await page.getByRole('button', { name: 'Add task' }).click();
  const del = page.getByRole('button', { name: 'Delete Old duplicate task' });
  await manualStep(page, T, 'delete-task', 'Delete a task', del);
  await del.click();
  await expect(page.getByRole('listitem')).toHaveCount(0);
  await flowStep('PF-03.5');
});
