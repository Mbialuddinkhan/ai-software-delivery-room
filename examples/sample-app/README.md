# TaskBoard — ASDR reference project

A small team to-do board (plain HTML/JS, no build step) that carries every
artifact ASDR 3.4 produces, so you can see them working together and copy
the patterns. CI runs it end to end on every push.

| What | Where |
|---|---|
| Requirements, use cases | `docs/02-requirements.md`, `docs/02b-use-cases.md` |
| Feature list | `docs/02c-features.md` |
| End-to-end process flows (+ lifecycle map) | `docs/02d-process-flows.md` |
| Test cases (21, each tagged in a test title) | `docs/02e-test-cases.md` |
| Playwright tests, manual tours, saved logins, accessibility | `e2e/playwright/` (`journeys.spec.ts`, `a11y.spec.ts`, `auth.setup.ts`, `tours/`) |
| Cypress tests + tour | `cypress/e2e/` |
| Selenium (pytest) tests + tour | `e2e/selenium/` |
| Suites for `run_tests.py` | `test-config.json` |
| Manual spec (4 persona manuals + 4 tiers) | `docs/manuals/manual.json` |

## Run it

```bash
npm install
npx playwright install chromium
python3 -m pip install selenium pytest

python3 ../../scripts/run_tests.py --config test-config.json          # all three frameworks
python3 ../../scripts/run_tests.py --config test-config.json --live   # watch it in a browser
python3 ../../scripts/validate_product_map.py --gate                  # every journey proven?
python3 ../../scripts/publish_test_report.py --label demo             # docs/test-reports/demo/
python3 ../../scripts/build_manual.py --review-page review.html       # read the wording, then --approve all
python3 ../../scripts/build_manual.py                                 # docs/manuals/1.1.0/ (HTML + PDF, screen diffs)
```

The app itself: `python3 -m http.server 4173 --directory app`, then open
http://localhost:4173.

Generated output (`.harness/`, `docs/test-reports/`, `docs/manuals/<version>/`,
`docs/product-map.md`) is not committed.
