# TaskBoard — ASDR reference project

A small team to-do board (plain HTML/JS, no build step) that carries every
artifact ASDR 3.6 produces, so you can see them working together and copy
the patterns. CI runs it end to end on every push.

| What | Where |
|---|---|
| Requirements (FR, NFR, acceptance criteria, business rules, edge cases), use cases | `docs/02-requirements.md`, `docs/02b-use-cases.md` |
| Feature list (with the roles each admin setting affects) | `docs/02c-features.md` |
| End-to-end process flows (+ lifecycle map) | `docs/02d-process-flows.md` |
| Test cases (28, each tagged in a test title, each with the items it covers) | `docs/02e-test-cases.md` |
| Playwright tests, manual tours, saved logins, accessibility, keyboard, performance, cross-role | `e2e/playwright/` (`journeys.spec.ts`, `delete-permission.spec.ts`, `keyboard.spec.ts`, `performance.spec.ts`, `a11y.spec.ts`, `auth.setup.ts`, `tours/`) |
| Cypress tests + tour | `cypress/e2e/` |
| Selenium (pytest) tests + tour | `e2e/selenium/` |
| Suites for `run_tests.py` | `test-config.json` |
| Manual spec (4 persona manuals + 4 tiers) | `docs/manuals/manual.json` |
| A worked assessment of the app as if it were a client's existing system (v3.6) | `docs/assess/` (intake, as-is processes, findings T-01…T-05, opportunities, technical review) |

## Run it

```bash
npm install
npx playwright install chromium
python3 -m pip install selenium pytest

python3 ../../scripts/run_tests.py --config test-config.json          # all three frameworks
python3 ../../scripts/run_tests.py --config test-config.json --live   # watch it in a browser
python3 ../../scripts/validate_product_map.py --gate                  # every journey and item proven?
python3 ../../scripts/publish_test_report.py --label demo             # docs/test-reports/demo/
python3 ../../scripts/build_manual.py --review-page review.html       # read the wording, then --approve all
python3 ../../scripts/build_manual.py                                 # docs/manuals/1.1.0/ (HTML + PDF, screen diffs)
```

Every test marks what it proves: `flowStep('PF-02.3')` at each process-flow
step and `covers('AC-03.2', …)` at the assertion that proves an item
(`metric(...)` records a measured value such as NFR-02's render time). The
gate then checks that every documented item — all 81 here — was reached by a
passing test, and `docs/product-map.md` shows the matrix.

The assessment and the dashboard:

```bash
python3 ../../scripts/assess_scan.py --target app --out docs/assess/evidence    # whatever scanners are installed
python3 ../../scripts/validate_assessment.py --root . --strict                  # every claim has evidence
python3 ../../scripts/build_assess_report.py                                    # docs/assess/report/ (HTML + PDF)
python3 ../../scripts/build_dashboard.py                                        # docs/dashboard/ (HTML + PDF)
```

The app itself: `python3 -m http.server 4173 --directory app`, then open
http://localhost:4173.

Generated output (`.harness/`, `docs/test-reports/`, `docs/manuals/<version>/`,
`docs/product-map.md`, `docs/dashboard/`, `docs/assess/evidence/`, `docs/assess/report/`)
is not committed.
