// ASDR coverage markers for Playwright. Copy unchanged.
//
// Linking a test case to a requirement proves nothing on its own; these
// markers record what a test actually exercised, so validate_product_map.py
// --gate can require that every flow step and every item a test case lists
// under "Covers" was reached by a PASSING test.
//
//   await flowStep('PF-02.3');               // a journey test reached this flow step
//   covers('AC-03.2', 'BR-02');              // call right where the test asserts them
//   metric('board-render-500', ms, 'ms', 1000); // a measured value, with its budget
//
// The test's title must carry its test-case id: test('[TC-03] …').
// Markers go to <ASDR_RESULTS_DIR>/coverage/playwright.jsonl.
import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

function tcIds(title: string): string[] {
  const out = new Set<string>();
  for (const m of title.matchAll(/\[TC-(\d+)\]|(?<![A-Za-z0-9])[Tt][Cc][_-](\d+)(?![0-9])/g)) out.add(`TC-${m[1] || m[2]}`);
  return [...out];
}

function write(kind: string, extra: Record<string, unknown>): void {
  const info = test.info();
  const title = info.titlePath.slice(1).join(' › ');
  const dir = path.join(process.env.ASDR_RESULTS_DIR || 'test-results', 'coverage');
  fs.mkdirSync(dir, { recursive: true });
  fs.appendFileSync(path.join(dir, 'playwright.jsonl'),
    JSON.stringify({ framework: 'playwright', test: title, tc: tcIds(title), kind, ...extra }) + '\n');
}

export async function flowStep(id: string): Promise<void> {
  write('step', { items: [id] });
  await test.step(`flow step ${id}`, async () => {});
}

export function covers(...items: string[]): void {
  write('covers', { items });
}

export function metric(name: string, value: number, unit: string, budget?: number): void {
  write('metric', { name, value, unit, budget: budget ?? null });
}
