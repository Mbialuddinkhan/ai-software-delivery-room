# Design System

<!-- Save as: docs/03b-design-system.md · Written by: solution-architect
Only produced when the product has a UI surface (web, mobile, desktop,
embedded). This is the single source of truth every UI sprint builds to;
its checklist (§9) becomes contract criteria.

Two ways this gets written:
  (a) UI UX Pro Max is installed → the orchestrator runs
      `python3 .harness/scripts/uupm_design_system.py` which drafts §2–§6
      and §8–§9 from the product brief. The draft is KEYWORD-MATCHED, not
      reasoned: the executor must review fit against docs/01 and record
      the review in §10. stage-qa grades fit, not formatting.
  (b) Not installed → the executor fills every section by hand from
      docs/01 and docs/02.
Either way, no <placeholder> may remain. -->

## 1. Product context (from docs/01, docs/02)

- Product type: <e.g. B2B SaaS dashboard / consumer mobile app / marketing site>
- Industry / domain: <…>
- Primary audience and device: <who, on what screen, how often>
- Brand constraints given by the user: <existing palette, fonts, logo — or "none">
- Requirement IDs that constrain the UI: <NFR-xx accessibility, NFR-xx performance, EC-xx>

## 2. Layout pattern

- Pattern: <name>
- Why it fits §1 (one line, cite the product type): <…>
- Section order: <1. … 2. … 3. …>
- Primary CTA placement: <…>

## 3. Visual style

- Style: <name>
- Keywords: <…>
- Mode support: <light / dark / both — and which is default>
- Performance cost: <low / medium / high — what drives it>
- Accessibility risk and required mitigations: <…>

## 4. Color tokens

| Role | Hex | CSS variable | Contrast vs its "on" pair |
|---|---|---|---|
| Primary | `#…` | `--color-primary` | <n>:1 |
| On Primary | `#…` | `--color-on-primary` | — |
| Secondary | `#…` | `--color-secondary` | <n>:1 |
| Accent / CTA | `#…` | `--color-accent` | <n>:1 |
| Background | `#…` | `--color-background` | — |
| Foreground | `#…` | `--color-foreground` | <n>:1 vs background |
| Card / Card foreground | `#…` / `#…` | `--color-card` / `--color-card-foreground` | <n>:1 |
| Muted / Muted foreground | `#…` / `#…` | `--color-muted` / `--color-muted-foreground` | <n>:1 |
| Border | `#…` | `--color-border` | — |
| Destructive / On destructive | `#…` / `#…` | `--color-destructive` / `--color-on-destructive` | <n>:1 |
| Ring (focus) | `#…` | `--color-ring` | visible on background and card |

Every text/background pair ≥ 4.5:1; large text ≥ 3:1. Cite the ratio.

## 5. Typography

- Heading font: <name> — fallback stack: <…>
- Body font: <name> — fallback stack: <…>
- Scale: <e.g. 12 / 14 / 16 / 20 / 24 / 32 / 48 px, line-height 1.5 body, 1.2 headings>
- Load strategy: <self-hosted / Google Fonts link, `font-display: swap`>

## 6. Spacing, radius, motion

- Spacing scale: <4 / 8 / 12 / 16 / 24 / 32 / 48 / 64>
- Radius: <sm / md / lg values>
- Shadows: <levels>
- Motion: <durations, easing; every animation has a `prefers-reduced-motion` static state>

## 7. Component inventory

One row per component the use cases need (walk docs/02b and cite the UC).

| Component | Used by (UC ids) | States required | Source (own / library) |
|---|---|---|---|
| <Button> | <UC-01, UC-04> | default, hover, focus, disabled, loading | <…> |

## 8. Anti-patterns (do not ship)

- <e.g. emoji as icons — use SVG (Heroicons / Lucide)>
- <e.g. AI-purple gradients, harsh animations, dark-mode-only>
- <…>

## 9. Pre-delivery checklist (→ UI sprint contract criteria)

Every line is ONE testable assertion; the generator copies the relevant
lines into each UI sprint contract and the evaluator grades them.

- [ ] No emoji used as an icon anywhere in `src/` (grep evidence).
- [ ] Every clickable element has `cursor: pointer` and a visible focus state.
- [ ] Text contrast ≥ 4.5:1 for every token pair in §4 (cite tool output).
- [ ] `prefers-reduced-motion` respected: no animation runs when set.
- [ ] Layout verified at 375 / 768 / 1024 / 1440 px with no horizontal scroll.
- [ ] Fonts load with a fallback stack; no FOIT > 100 ms.
- [ ] All colors reference §4 CSS variables; no hard-coded hex in components.
- [ ] <product-specific items>

## 10. Provenance and fit review

- Drafted by: <uupm search.py vX.Y.Z / hand-written>
- Query used: <…>
- Executor's fit review: <does the pattern/style match §1? what was changed
  from the draft and why — quote the brief line that drove each change>
- Open questions for the user: <…>
