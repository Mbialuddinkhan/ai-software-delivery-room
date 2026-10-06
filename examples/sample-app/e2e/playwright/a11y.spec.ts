// [TC-21] Every key screen meets WCAG 2.1 A/AA with no serious or critical
// problems (NFR-01). Board and settings start from saved logins.
import { test, expect } from '@playwright/test';
import { checkA11y } from './asdr-a11y';
import { authFile } from './asdr-auth';
import { covers } from './asdr-cover';

test('[TC-21] sign-in page is accessible', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await checkA11y(page, 'sign-in');
  covers('NFR-01');
});

test.describe('member', () => {
  test.use({ storageState: authFile('member') });
  test('[TC-21] board is accessible', async ({ page }) => {
    await page.goto('/');
    await page.getByPlaceholder(/What needs doing/).fill('Check contrast');
    await page.keyboard.press('Enter');
    await page.getByLabel('Mark Check contrast done').check();
    await checkA11y(page, 'board');
    covers('NFR-01');
  });
});

test.describe('admin', () => {
  test.use({ storageState: authFile('admin') });
  test('[TC-21] settings page is accessible', async ({ page }) => {
    await page.goto('/#settings');
    await expect(page.getByRole('heading', { name: 'Team settings' })).toBeVisible();
    await checkA11y(page, 'settings');
    covers('NFR-01');
  });
});
