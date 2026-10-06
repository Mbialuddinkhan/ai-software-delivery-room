// [TC-26] NFR-01: everything works from the keyboard alone, and every control
// that takes focus has an accessible name.
import { test, expect, Page } from '@playwright/test';
import { covers } from './asdr-cover';

async function tabTo(page: Page, matches: () => Promise<boolean>, max = 20) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return '';
      const labels = (el as HTMLInputElement).labels;
      return el.getAttribute('aria-label') || (labels && labels[0] ? labels[0].innerText : '') ||
        el.innerText || (el as HTMLInputElement).placeholder || '';
    });
    expect(name.trim(), 'every control reached with Tab needs an accessible name').not.toBe('');
    if (await matches()) return;
  }
  throw new Error('control not reachable with Tab');
}

test('[TC-26] everything works from the keyboard alone', async ({ page }) => {
  await page.goto('/');
  await tabTo(page, () => page.locator('#name').evaluate((el) => el === document.activeElement));
  await page.keyboard.type('Sara');
  await tabTo(page, () => page.locator('#signin-submit').evaluate((el) => el === document.activeElement));
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Team board' })).toBeVisible();

  await page.keyboard.press('n');
  await page.keyboard.type('Plan offsite');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('listitem').filter({ hasText: 'Plan offsite' })).toBeVisible();
  covers('AC-02.2');

  await tabTo(page, () => page.getByLabel('Mark Plan offsite done').evaluate((el) => el === document.activeElement));
  await page.keyboard.press('Space');
  await expect(page.locator('#counter')).toHaveText('0 open · 1 done');
  covers('NFR-01');
});
