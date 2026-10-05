// TaskBoard's test roles and how each signs in. The sample has no passwords
// (a name and a role), so no ASDR_USER_/ASDR_PASS_ variables are needed; a real
// app reads them here — see .harness/templates/e2e/playwright/login.ts.
import { expect, type Page } from '@playwright/test';

export const ROLES = ['member', 'admin'];
const NAMES: Record<string, string> = { member: 'Sara', admin: 'Omar' };

export async function login(page: Page, role: string): Promise<void> {
  await page.goto('/');
  await page.getByLabel('Your name').fill(NAMES[role]);
  await page.getByLabel('Role').selectOption(role);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
}
