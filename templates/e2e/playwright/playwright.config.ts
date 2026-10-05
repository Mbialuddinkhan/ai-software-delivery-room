// ASDR Playwright config template. devops copies this to the project root
// and sets the three marked values. run_tests.py drives it through env vars,
// so the same file serves CI (headless) and live runs (headed, slowed down,
// one worker, video on) in front of the user.
import { defineConfig, devices } from '@playwright/test';

const live = !!process.env.ASDR_LIVE;
const results = process.env.ASDR_RESULTS_DIR || 'test-results';
const baseURL = process.env.BASE_URL || 'http://localhost:4173'; // <- project URL
const startCmd = process.env.ASDR_START_CMD || '';               // <- e.g. 'npm run dev'

export default defineConfig({
  testDir: './e2e/playwright',                                   // <- project test dir
  outputDir: `${results}/playwright/artifacts`,
  fullyParallel: !live,
  workers: live ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ['list'],
    ['junit', { outputFile: `${results}/junit/playwright.xml` }],
    ['html', { outputFolder: `${results}/playwright/html`, open: 'never' }],
  ],
  use: {
    baseURL,
    headless: !live,
    launchOptions: { slowMo: Number(process.env.ASDR_SLOWMO || (live ? 400 : 0)) },
    screenshot: 'on',
    video: live || process.env.ASDR_RECORD ? 'on' : 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    // Behaviour tests.
    { name: 'e2e', testIgnore: /\.tour\.spec\.ts$/, use: { ...devices['Desktop Chrome'] } },
    // Manual tours: serial, fixed viewport so screenshots are consistent.
    {
      name: 'manual',
      testMatch: /\.tour\.spec\.ts$/,
      fullyParallel: false,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: startCmd
    ? { command: startCmd, url: baseURL, reuseExistingServer: true, timeout: 120_000 }
    : undefined,
});
