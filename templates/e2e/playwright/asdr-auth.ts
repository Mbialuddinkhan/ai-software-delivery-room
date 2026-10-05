// ASDR saved logins for Playwright. Copy unchanged next to asdr-manual.ts.
//
// auth.setup.ts signs in once per test role and saves the browser state
// (cookies + localStorage) to <ASDR_AUTH_DIR>/<role>.json. Tests that are not
// about signing in start already signed in:
//
//   test.use({ storageState: authFile('admin') });
//
// Journey tests that walk the sign-in flow must NOT use a saved login.
// The files hold live session tokens: run_tests.py keeps them out of git
// (a "*" .gitignore inside the folder) and never publishes them.
import * as fs from 'fs';
import * as path from 'path';

export function authDir(): string {
  const dir = process.env.ASDR_AUTH_DIR || '.harness/auth';
  fs.mkdirSync(dir, { recursive: true });
  const ignore = path.join(dir, '.gitignore');
  if (!fs.existsSync(ignore)) fs.writeFileSync(ignore, '*\n');
  return dir;
}

export function authFile(role: string): string {
  return path.join(authDir(), `${role}.json`);
}
