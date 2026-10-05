# Browser tests, live runs, published results and user manuals

Everything here runs from the project root with `.harness/scripts/`.

## Running the tests

`python3 .harness/scripts/run_tests.py` runs every suite in
`.harness/test-config.json` (Playwright, Cypress, Selenium or any JUnit-writing
runner). It starts the app once, gives every framework the same run folder
`.harness/test-results/<run_id>/`, parses all JUnit, links each test to its
screenshots, videos and traces, and writes `summary.json` and `latest.json`
(`facts:test_runs.*` after `emit_facts.py`). A suite that exits non-zero or
writes no results counts as failed.

| Flag | Use |
|---|---|
| `--live` | The user wants to watch: headed browser, 400 ms per action, one worker |
| `--slowmo 900` | Slower live demo |
| `--tours` | Only the manual-tour specs (refresh screenshots) |
| `--suite NAME` | One framework |
| `--label TEXT` | Report title, e.g. `sprint-02-attempt-1` or `v1.2.0` |

### Live in front of the user

Use `--live` whenever the user asks to watch, and offer it at the end of
every sprint that delivered a flow. Live needs a screen:

- **Claude Code on the user's computer**: the browser opens on their screen.
- **Cowork**: the session runs in a cloud sandbox with no screen, so
  `run_tests.py` switches to *recorded* mode (headless, video on) and says so.
  Publish the report (below) so the user can play the videos. If the user's
  computer is linked to the session and has the project and its test
  dependencies, the same command run there through the computer's shell opens
  a real browser on their screen.
- **CI / SSH**: recorded, always.

## Publishing results (private by default)

After every evaluated sprint and at release:

    python3 .harness/scripts/publish_test_report.py --label <label>

It reads `.harness/publish.json` (seeded private by init):

| Key | Default | Effect |
|---|---|---|
| `repo` | true | `docs/test-reports/<label>/index.html` with evidence; history page `docs/test-reports/index.html`; commit them with the sprint |
| `ci_artifacts` | true | the CI workflow uploads the run folder and the report |
| `claude_artifact` | true | writes `<run>/report-artifact.html`: one file, images embedded, no doctype |
| `github_pages` | false | **public**. Only the user may turn it on, per project; then the CI pages job deploys `docs/test-reports/` |

When `claude_artifact` is on and the session has an Artifact tool, publish the
printed `report-artifact.html` as a private page (title "<Product> Test
Report", update the same artifact each time so the link stays stable) and give
the user the link. Without that tool, tell the user the repo path instead.
Never make a report public on your own.

## User manuals

1. Tours: tests ending in `.tour.spec.ts` (Playwright), `.tour.cy.js`
   (Cypress) or marked `@pytest.mark.tour` (Selenium) call the manual helper
   at each moment a manual should show. Each call outlines the element in red,
   saves a 1280×800 screenshot and records the step with URL and commit in
   `.harness/manual/tours/<tour>.json`.
2. The documentation agent writes `docs/manuals/manual.json`: one explanation
   per step, a "Getting started" and an "Advanced" manual per persona, and the
   four tiers (Beginner, Everyday user, Power user, Administrator).
3. `python3 .harness/scripts/build_manual.py --version <v>` writes HTML + PDF
   per manual to `docs/manuals/<v>/` with an index, a version/commit banner and
   "What is new" from `CHANGELOG.md`. It fails on missing explanations, missing
   screenshots, and screenshots from a commit other than HEAD (`--allow-stale`
   only for drafts). `--artifact FILE` also writes all manuals as one private
   page; publish it like the report.

Manuals are rebuilt at every release by the release-manager from a fresh run
on the release commit, so screenshots always match the shipped build.

## Proof that the product works end to end

`python3 .harness/scripts/validate_product_map.py [--gate]` follows lifecycle →
process flow → step → use case → feature → requirement → test case →
automated test → latest result, and writes `docs/product-map.md`. Tests are
matched to test cases by the `[TC-xx]` prefix in their titles (`test_tc_xx_…`
in pytest). `--gate` requires every Must flow's journey and exception tests to
have passed on the latest run.

## Run metrics

`python3 .harness/scripts/run_metrics.py` writes `docs/run-metrics.md`:
agent invocations, evaluations and negotiation rounds per sprint, stage QA
rounds, context-pack sizes and test-run history. Run it at the end of Phase 3
and Phase 5 and show the user the table.
