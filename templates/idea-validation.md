# Idea Validation

<!-- Save as: docs/00a-idea-validation.md · Written by: product-owner (VALIDATE mode)
Inputs: docs/validation/seed.md, docs/validation/desk-evidence.md,
.harness/validation.json, docs/validation/panel/ (roster, responses, digest,
followups), and docs/validation/mirofish/report-<n>.md and interviews-<n>.json
when MiroFish ran.

Rules:
- Every claim cites its evidence: `desk:D-xx`, `panel:<scenario>-r<n>-Pxx`
  (a response file), `panel:followup-Pxx`, `panel:digest`, `sim:report-1
  §<heading>`, `sim:interview <key>`, or `validation:<dotted.key>` for a
  number (e.g. `validation:panel.scenarios.base.r1.intent.no`). A number with
  no citation is not evidence.
- Panel and MiroFish are ONE kind of evidence: synthetic opinion from
  language-model personas. They surface objections, confusion, switching
  barriers and competitor comparisons. They cannot show demand, willingness
  to pay or market size, and their agreement with each other is not
  corroboration. A hypothesis with only synthetic support is at most
  `weakly supported`.
- Panel intent shares are shaped by the roster quotas (sceptics and
  non-buyers are required). Never quote an absolute share as a finding;
  compare scenarios WITHIN the panel (`validation:panel.deltas.*`).
- Desk evidence outranks synthetic evidence when they disagree; say which
  way they disagreed.
- §6 is required whatever the recommendation: the real-world tests that would
  confirm or kill the idea cheaply. -->

## 1. Summary

<Three sentences: what was tested, what the evidence says, the recommendation.>

## 2. What ran

- Desk research: <number of sources, date range>
- Panel: <personas, rounds, scenarios, follow-ups — each as `validation:panel.<key>`;
  a second panel's spread as `validation:panel_variance.<key>`; or "not run: <reason>">
- MiroFish: <runs, rounds completed of cap, agents, interviews — as
  `validation:mirofish.<key>`; or "not run: <reason>">
- Evidence class: <desk-only | panel+desk | mirofish+desk | panel+mirofish+desk>

## 3. Hypotheses

| Id | Hypothesis | Result | Evidence | Confidence |
|---|---|---|---|---|
| H-01 | <from seed §6> | supported / weakly supported / weakened / refuted / untested | <citations> | high / medium / low |

## 3b. Scenarios (only if the panel ran any)

<For each SC-xx: what changed, and the within-panel shift — same-persona
movement and the change in objections — each as `validation:panel.deltas.<SC>.<key>`.
Say what the shift suggests and what real-world test would confirm it.
"None run" is valid.>

## 4. Objections and risks (ranked)

| # | Objection | Segments raising it | What is behind it (follow-ups) | Evidence | Can the product answer it? |
|---|---|---|---|---|---|
| 1 | <…> | S-01, S-03 | <root cause from panel:followup-Pxx> | <citations> | <yes — how / partly / no> |

## 5. Pivots worth considering

<Only pivots the evidence points to; each with its citation. "None" is a valid answer.>

## 6. Real-world tests before or during the build

<Cheap tests on real people. Each: the hypothesis it tests, the method, the
sample, the pass threshold, the cost and time.>

| Test | Tests | Method | Pass if | Cost / time |
|---|---|---|---|---|
| RW-01 | H-01 | <e.g. 8 discovery calls with S-01 owners> | <e.g. ≥5 of 8 name it unprompted> | <…> |

## 7. Limits of this validation

<What the synthetic lanes could not show, seed biases you noticed, segments
missing, anything the reader must not over-trust. Answer EVERY flag raised in
`validation:panel.flags` (implausible_positivity, herding, homogeneous,
thin_segments, echo_heavy, static_round2): what it means for this result and
how you discounted it. Name the personas in `validation:panel.echo.personas`
and cite the desk rows behind their objections instead. Report any scenario
delta with `within_noise: true` as "no detectable difference". If two panels
ran, state their spread (`validation:panel_variance`). Never cite panel
results whose `status` is not `complete`.>

## 8. Recommendation

```yaml
recommendation: proceed | pivot | stop
evidence_class: desk-only | panel+desk | mirofish+desk | panel+mirofish+desk
hypotheses_supported: [H-xx, ...]
hypotheses_refuted: [H-xx, ...]
top_objections: ["<objection 1>", "<objection 2>", "<objection 3>"]
real_world_tests: [RW-01, ...]
reason: "<one sentence>"
```
