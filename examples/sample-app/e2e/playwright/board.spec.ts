import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, name: string, role: 'member' | 'admin' = 'member') {
  await page.goto('/');
  await page.getByLabel('Your name').fill(name);
  await page.getByLabel('Role').selectOption(role);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
}

test('[TC-02] sign in requires a name', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => (document.getElementById('name') as HTMLInputElement).removeAttribute('required'));
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toHaveText('Please enter your name.');
});

// Found by reviewing the manual screenshots: the top bar showed "Sign out"
// before anyone had signed in, because CSS display:flex beat the hidden attribute.
test('[TC-13] the top bar stays hidden until someone signs in', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeHidden();
  await signIn(page, 'Sara');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
});

test('[TC-08] a member adds a task and the counter updates', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Write release notes');
  await page.getByRole('button', { name: 'Add task' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'Write release notes' })).toBeVisible();
  await expect(page.locator('#counter')).toHaveText('1 open · 0 done');
});

test('[TC-09] a completed task moves to the Done filter', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Fix login bug');
  await page.getByRole('button', { name: 'Add task' }).click();
  await page.getByLabel('Mark Fix login bug done').check();
  await page.getByRole('button', { name: 'Active' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(0);
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'Fix login bug' })).toBeVisible();
});

test('[TC-06] members cannot open settings; admins can', async ({ page }) => {
  await signIn(page, 'Sara', 'member');
  await expect(page.getByRole('link', { name: 'Settings' })).toBeHidden();
  await page.goto('/#settings');
  await expect(page.getByRole('heading', { name: 'Team settings' })).toBeHidden();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await signIn(page, 'Omar', 'admin');
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: 'Team settings' })).toBeVisible();
});

test('[TC-10] a new category appears when adding tasks', async ({ page }) => {
  await signIn(page, 'Omar', 'admin');
  await page.getByRole('link', { name: 'Settings' }).click();
  await page.getByPlaceholder('New category name').fill('Design');
  await page.getByRole('button', { name: 'Add category' }).click();
  await page.getByRole('link', { name: 'Board' }).click();
  await expect(page.getByLabel('Category', { exact: true })).toContainText('Design');
});

test('[TC-11] export downloads a CSV with the tasks', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Ship v1');
  await page.getByRole('button', { name: 'Add task' }).click();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('tasks.csv');
  const body = require('fs').readFileSync(await download.path(), 'utf8');
  expect(body).toContain('"Ship v1"');
});
