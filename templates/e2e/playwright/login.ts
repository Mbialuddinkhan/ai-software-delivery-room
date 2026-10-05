// PROJECT-SPECIFIC (devops fills this in): the test roles and how a person in
// each role signs in. Credentials are test users the seed step creates
// (test-config.json "app.seed_cmd"), passed in through the environment —
// never real accounts, never committed:
//   ASDR_USER_<ROLE>, ASDR_PASS_<ROLE>   e.g. ASDR_USER_ADMIN, ASDR_PASS_ADMIN
import type { Page } from '@playwright/test';

export const ROLES = ['member', 'admin'];                       // <- your roles

export async function login(page: Page, role: string): Promise<void> {
  const key = role.toUpperCase();
  const user = process.env[`ASDR_USER_${key}`];
  const pass = process.env[`ASDR_PASS_${key}`];
  if (!user || !pass) {
    throw new Error(`Set ASDR_USER_${key} and ASDR_PASS_${key}: the seed step creates these test users`);
  }
  await page.goto('/login');                                      // <- your sign-in page
  await page.getByLabel('Email').fill(user);                      // <- your fields
  await page.getByLabel('Password').fill(pass);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.waitForURL('**/dashboard');                          // <- where a signed-in user lands
}
