# Companions

Third-party skills ASDR uses. UI UX Pro Max installs with ASDR (a dependency
on the `asdr` marketplace entry); the rest are detected in Phase 0 step 4
(`.harness/companions.json`) and used only when present. Version checks run in
Phase 0 step 5. Full install notes and the reasoning behind each rule:
`docs/COMPANIONS.md` in the plugin repo.

| Companion | Used in | Rule |
|---|---|---|
| UI UX Pro Max | `design-system` stage (row 5b) | Installed automatically with ASDR from the `asdr` marketplace (Claude Code); absent in Cowork unless added separately, in which case 03b is hand-written from the template. It drafts tokens and the checklist; the executor reviews fit; stage-qa grades fit against docs/01 |
| Build ladder (built in) | generator BUILD mode | `templates/build-ladder.md`; YAGNI objections go in NEGOTIATE, never skip a ratified criterion |
| Ponytail (optional) | generator only | Listed in the `asdr` marketplace, disabled by default; needs `PONYTAIL_SUBAGENT_MATCHER='^generator$'` |
| Graphify | brownfield entry, post-sprint `--update` | Navigation aid only; never a measurement source |
| RTK | none (warned, not used) | Compresses evidence commands; `facts:` keys are the only measured numbers |

## Rules in the sprint loop

- **UI sprints**: the generator copies the relevant §9 checklist lines from
  `docs/03b-design-system.md` into the contract as criteria and reads §4–§6
  tokens before writing any component. A UI contract with none of §9 in it is
  incomplete; send it back in negotiation.
- **Build ladder**: the generator reads `.harness/templates/build-ladder.md`
  in BUILD mode; it does not need the Ponytail plugin.
- **Ponytail (if installed anyway)**: only the generator may run under it, and
  only in BUILD mode against a ratified contract. If `companions.json` shows
  `ponytail.installed: true` and `scoped_to_generator: false`, STOP before the
  first sprint and tell the user to set `PONYTAIL_SUBAGENT_MATCHER='^generator$'`
  and restart, or disable the plugin. A YAGNI ladder inside the critic, judge,
  evaluator or security-compliance is an independent reviewer told to do less
  reviewing.
- **Graphify** (optional): on brownfield entry run `/graphify . --update` once
  before Phase 1 so `build_graph.py` and the packs see the existing code; after
  each sprint the evaluator marks `done`, `--update` is cheap (AST only). Never
  substitute a graphify query for `emit_facts.py` as a measurement.
- **RTK**: if `companions.json` shows it installed, remind the evaluator and
  stage-qa every invocation that shell output is compressed and only `facts:`
  keys count as evidence.
