# Seeded-defect eval suite

Measures what the harness actually catches, instead of claiming it.

Each folder under `cases/` holds an artifact with ONE known defect seeded in
it (`case.json` names the defect and the check that should catch it), plus one
clean control artifact that must NOT fire. Two layers:

- **mechanical** — the validators and gates. Run anywhere, free:
  `python3 evals/run_seeded.py`. Runs in CI on every build; `--gate` fails on
  any defect that was caught at the baseline and escapes now.
- **agent** — the reviewer roles (critic, evaluator, security-compliance).
  Run live inside a Claude session (`--live` prints the tasks; give the
  reviewer only the listed files and never name the defect), then record the
  outcome: `run_seeded.py record --case SD-A2 --role security-compliance
  --caught yes|no --model opus --family claude`. Per-family results make the
  cross-family reviewer question (brief 3.2) measurable instead of argued.

Outputs: `results.json`, `CATCH-RATES.md` (published table), `baseline.json`
(regression reference, update deliberately with `--update-baseline`),
`escape-log.md` (one line per release via `--release vX.Y.Z` — brief 8.2).

Honesty rules: an unmeasured cell prints "not yet measured", never a number;
a 100% mechanical rate means the KNOWN classes are covered, not that defects
don't exist — new escape classes become new cases in the release that fixes
them.
