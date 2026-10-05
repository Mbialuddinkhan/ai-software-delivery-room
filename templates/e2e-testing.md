# End-to-End Testing Plan

<!-- Save as: docs/08-e2e-testing.md · Written by: devops
How this project's browser tests run, how a person watches them live, where
the results are published, and how the user manuals are produced from them.
Fill the <placeholders> for THIS project. The working reference is the
TaskBoard sample in the ASDR repo: examples/sample-app/. -->

## 1. Frameworks

ASDR supports three browser frameworks side by side. All three write JUnit,
screenshots and (Playwright, Cypress) video into one run folder, so the report
and the release gate treat them the same.

| Framework | Use it for | Template in `.harness/templates/e2e/` |
|---|---|---|
| Playwright (default) | journey tests, manual tours, multi-tab, downloads | `playwright/` (config + `asdr-manual.ts`) |
| Cypress | teams that already use it; component-heavy UIs | `cypress/` (config + `asdr-manual.js` + plugin) |
| Selenium (pytest) | browsers or grids Playwright can't drive; existing Selenium suites | `selenium/` (`conftest.py`, `asdr_manual.py`, `pytest.ini`) |

- Decision for this project: <Playwright for journeys and tours; add Cypress/Selenium only with a reason>
- Services with no UI: API-level E2E via <pytest + httpx / supertest>, still JUnit.

## 2. Test cases drive the tests

Every test implements a test case from `docs/02e-test-cases.md`, and its
title starts with the id: `test('[TC-03] …')`, `it('[TC-03] …')`, or
`def test_tc_03_…` in pytest. That is how `validate_product_map.py` proves each
process flow works end to end. Journey test cases are one test each that walks
the whole flow.

## 3. Folder structure

```
playwright.config.ts                 # from templates/e2e/playwright/
e2e/playwright/
  asdr-manual.ts                     # copied unchanged
  journeys.spec.ts                   # [TC-xx] journey tests, one per process flow
  <area>.spec.ts                     # functional / exception / edge tests
  tours/<tour>.tour.spec.ts          # manual tours (also real tests)
cypress.config.js, cypress/          # only if Cypress is used
e2e/selenium/                        # only if Selenium is used
.harness/test-config.json            # the suites run_tests.py runs
```

## 4. The suite list — `.harness/test-config.json`

```json
{
  "schema": 1,
  "product": "<Product name>",
  "app": { "start_cmd": "<npm run dev>", "url": "<http://localhost:3000>", "ready_timeout_s": 60 },
  "suites": [
    { "name": "playwright", "framework": "playwright",
      "cmd": "npx playwright test", "live_cmd": "npx playwright test --headed",
      "tours_cmd": "npx playwright test --project=manual",
      "junit": ["junit/playwright.xml"], "html_report": "playwright/html/index.html" }
  ]
}
```

## 5. Running

| What | Command |
|---|---|
| Everything, headless (CI, every sprint) | `python3 .harness/scripts/run_tests.py` |
| Live, in front of the user | `python3 .harness/scripts/run_tests.py --live` (headed, 400 ms per action, one worker) |
| Slower live demo | `python3 .harness/scripts/run_tests.py --live --slowmo 900` |
| Only the manual tours | `python3 .harness/scripts/run_tests.py --tours` |
| One framework | `python3 .harness/scripts/run_tests.py --suite cypress` |

Live mode needs a screen. On the user's own computer (Claude Code, or a
terminal) the browser opens and they watch every click. In Cowork's cloud
sandbox, in CI and over SSH there is no screen, so the run switches to
"recorded": headless with video, and the videos are in the report. The
summary records which mode ran.

## 6. Publishing results — private by default

`python3 .harness/scripts/publish_test_report.py [--label <sprint or version>]`
reads `.harness/publish.json`:

| Target | Default | Where |
|---|---|---|
| Repo | on | `docs/test-reports/<label>/` + history at `docs/test-reports/index.html` |
| CI artifacts | on | the workflow uploads the run folder and report |
| Private claude.ai page | on | single-file report the orchestrator publishes as a private Artifact |
| GitHub Pages | **off** | public; turn on only by the user's choice for this project |

## 7. User manuals from the same run

Tours are tests that call the manual helper at each moment a manual should
show. Each call outlines the element the user acts on and saves a screenshot
with the step's URL and commit. `docs/manuals/manual.json` (documentation
agent) gives every step its explanation and groups steps into manuals:
one per persona (Getting started + Advanced) and four by experience
(Beginner, Everyday user, Power user, Administrator).
`python3 .harness/scripts/build_manual.py --version <version>` writes HTML and
PDF for each to `docs/manuals/<version>/`, and refuses screenshots taken from a
different commit than the release.

## 8. Rules

- Every user-facing acceptance criterion and every test case has a browser test; no criterion ships unwatched.
- The FULL suite runs every sprint (regression) and again at the release gate.
- A suite that produces no JUnit results counts as failed.
- The evaluator cites screenshot/video paths from the run's `summary.json` as evidence.
- Manuals are rebuilt from a fresh run at every release; never edit their screenshots by hand.
