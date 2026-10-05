// ASDR auth setup: signs in once per role from login.ts and saves the state
// for every other test. Runs as the "setup" project before the others
// (playwright.config.ts). Copy unchanged.
import { test as setup } from '@playwright/test';
import { authFile } from './asdr-auth';
import { ROLES, login } from './login';

for (const role of ROLES) {
  setup(`sign in as ${role}`, async ({ page }) => {
    await login(page, role);
    await page.context().storageState({ path: authFile(role) });
  });
}
