import { test, expect, Page } from '@playwright/test';
import { authFile } from './asdr-auth';
import { covers, flowStep } from './asdr-cover';

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
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeHidden();
  await flowStep('PF-01.E1');
  covers('AC-01.2', 'EC-02', 'UC-01.E1');
});

// Found by reviewing the manual screenshots: the top bar showed "Sign out"
// before anyone had signed in, because CSS display:flex beat the hidden attribute.
test('[TC-13] the top bar stays hidden until someone signs in', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeHidden();
  await signIn(page, 'Sara');
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  covers('AC-01.3', 'FR-01');
});

test('[TC-08] a member adds a task and the counter updates', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Write release notes');
  await page.getByRole('button', { name: 'Add task' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'Write release notes' })).toBeVisible();
  await expect(page.locator('#counter')).toHaveText('1 open · 0 done');
  covers('FR-02', 'FR-05');
});

test('[TC-09] a completed task moves to the Done filter', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Fix login bug');
  await page.getByRole('button', { name: 'Add task' }).click();
  await page.getByLabel('Mark Fix login bug done').check();
  await expect(page.getByRole('listitem').filter({ hasText: 'Fix login bug' })).toHaveClass(/done/);
  await expect(page.locator('#counter')).toHaveText('0 open · 1 done');
  covers('AC-03.1');
  await page.getByRole('button', { name: 'Active' }).click();
  await expect(page.getByRole('listitem')).toHaveCount(0);
  covers('AC-04.1');
  await page.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByRole('listitem').filter({ hasText: 'Fix login bug' })).toBeVisible();
  covers('AC-04.2');
});

test('[TC-24] unticking a finished task makes it open again', async ({ page }) => {
  await signIn(page, 'Sara');
  await page.getByPlaceholder(/What needs doing/).fill('Call supplier');
  await page.getByRole('button', { name: 'Add task' }).click();
  const box = page.getByLabel('Mark Call supplier done');
  await box.check();
  await expect(page.locator('#counter')).toHaveText('0 open · 1 done');
  await box.uncheck();
  await expect(page.getByRole('listitem').filter({ hasText: 'Call supplier' })).not.toHaveClass(/done/);
  await expect(page.locator('#counter')).toHaveText('1 open · 0 done');
  covers('AC-03.2', 'FR-03');
});

test('[TC-06] members cannot open settings; admins can', async ({ page }) => {
  await signIn(page, 'Sara', 'member');
  await expect(page.getByRole('link', { name: 'Settings' })).toBeHidden();
  await page.goto('/#settings');
  await expect(page.getByRole('heading', { name: 'Team settings' })).toBeHidden();
  await flowStep('PF-03.E1');
  covers('AC-06.2', 'BR-01', 'UC-06.E1');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await signIn(page, 'Omar', 'admin');
  await page.getByRole('link', { name: 'Settings' }).click();
  await expect(page.getByRole('heading', { name: 'Team settings' })).toBeVisible();
  covers('FR-11');
});

test.describe('signed in as admin (saved login)', () => {
  test.use({ storageState: authFile('admin') });

  test('[TC-10] a new category appears when adding tasks', async ({ page }) => {
    await page.goto('/#settings');
    await expect(page.getByRole('heading', { name: 'Team settings' })).toBeVisible();
    await page.getByPlaceholder('New category name').fill('Design');
    await page.getByRole('button', { name: 'Add category' }).click();
    await page.getByRole('link', { name: 'Board' }).click();
    await expect(page.getByLabel('Category', { exact: true })).toContainText('Design');
    covers('FR-08');
  });
});

test('[TC-11] export downloads a CSV with every task', async ({ page }) => {
  await signIn(page, 'Sara');
  for (const t of ['Ship v1', 'Write docs']) {
    await page.getByPlaceholder(/What needs doing/).fill(t);
    await page.getByRole('button', { name: 'Add task' }).click();
  }
  await page.getByLabel('Mark Write docs done').check();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('tasks.csv');
  const lines = require('fs').readFileSync(await download.path(), 'utf8').trim().split('\n');
  expect(lines[0]).toBe('"id","title","category","done"');
  expect(lines).toHaveLength(3);
  expect(lines).toContain('"1","Ship v1","General","false"');
  expect(lines).toContain('"2","Write docs","General","true"');
  covers('AC-05.1', 'FR-07');
});
