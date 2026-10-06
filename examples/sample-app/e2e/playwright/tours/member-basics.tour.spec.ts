import { test, expect } from '@playwright/test';
import { manualStep } from '../asdr-manual';
import { covers, flowStep } from '../asdr-cover';

const T = 'member-basics';

test('[TC-01] Member basics: sign in, add and complete a task', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await flowStep('PF-01.1');
  await manualStep(page, T, 'signin-page', 'Open TaskBoard');
  await page.getByLabel('Your name').fill('Sara');
  await manualStep(page, T, 'enter-name', 'Enter your name', page.getByLabel('Your name'));
  await manualStep(page, T, 'choose-role', 'Choose your role', page.getByLabel('Role'));
  await manualStep(page, T, 'sign-in', 'Sign in', page.getByRole('button', { name: 'Sign in' }));
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();
  await flowStep('PF-01.2');
  await manualStep(page, T, 'empty-board', 'Your empty board', page.locator('#empty'));
  await page.getByPlaceholder(/What needs doing/).fill('Prepare sprint demo');
  await manualStep(page, T, 'type-task', 'Type a new task', page.getByPlaceholder(/What needs doing/));
  await manualStep(page, T, 'pick-category', 'Pick a category', page.getByLabel('Category', { exact: true }));
  await manualStep(page, T, 'add-task', 'Add the task', page.getByRole('button', { name: 'Add task' }));
  await page.getByRole('button', { name: 'Add task' }).click();
  const row = page.getByRole('listitem').filter({ hasText: 'Prepare sprint demo' });
  await expect(row).toBeVisible();
  await expect(row).toContainText('General');
  await expect(page.locator('#counter')).toHaveText('1 open · 0 done');
  await flowStep('PF-01.3');
  covers('AC-02.1');
  await manualStep(page, T, 'task-added', 'See your task on the board', row);
  await page.getByLabel('Mark Prepare sprint demo done').check();
  await expect(page.locator('#counter')).toHaveText('0 open · 1 done');
  covers('AC-03.1');
  await manualStep(page, T, 'complete-task', 'Mark a task done', page.getByLabel('Mark Prepare sprint demo done'));
});
