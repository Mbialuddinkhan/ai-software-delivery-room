# Companions — the third-party skills ASDR uses

How each one reaches the user:

| Companion | Delivery | Why this way |
|---|---|---|
| UI UX Pro Max | **Dependency** of the `ai-software-delivery-room` plugin in the `asdr` marketplace; installs with ASDR, pinned to a commit SHA | Pure data + Python, no hooks, no network; safe to force-install |
| Build ladder | **Built in** (`templates/build-ladder.md`, adapted from Ponytail, MIT) | The value is the text, not the plugin; carrying it avoids Ponytail's SubagentStart hook reaching the reviewers |
| Ponytail | Listed in the `asdr` marketplace, `defaultEnabled: false`, one command to install | Hooks affect every subagent; a user must opt in and scope it |
| Graphify | Detected only (pip/uv tool, not a Claude plugin) | Cannot be a plugin dependency; ASDR offers `pip install graphifyy` on brownfield entry |
| RTK | Detected, warned, never installed | Compresses evidence commands |

ASDR does not vendor any companion's code. `scripts/detect_companions.py`
(Phase 0 step 4) finds what the host session has installed and writes
`.harness/companions.json`; the orchestrator, generator, evaluator and
stage-qa read that file. All four projects are MIT-licensed and update
often, so vendoring would mean maintaining forks.

## UI UX Pro Max — design-system stage

Repo: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

```text
/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill
/plugin install ui-ux-pro-max@ui-ux-pro-max-skill
```

What ASDR uses: `scripts/search.py "<query>" --design-system -p "<name>"
-f markdown`. It is an offline Python lookup over a static dataset (styles,
palettes with contrast pairs, font pairings, landing patterns, a pre-delivery
checklist). No network, no LLM.

How it is wired: `scripts/uupm_design_system.py` runs it and writes a draft
`docs/03b-design-system.md` under a provenance header; the
`design-system` stage (executor: solution-architect) reviews fit and fills
§1, §7, §10; stage-qa grades fit against `docs/01-product-brief.md`.

Known limitation (why fit review is mandatory): the pattern match is by
keyword. A query for a "B2B SaaS voice-AI dashboard" returned a
hero-plus-features landing page in glassmorphism. Tokens and checklist were
usable; the layout pattern was wrong for the product. The critic has a
mandatory High finding for a pattern that does not match the brief.

Detection: `.claude/skills/ui-ux-pro-max/scripts/search.py` (project),
`~/.claude/skills/ui-ux-pro-max/scripts/search.py`, or anywhere under
`~/.claude/plugins/`. Override with `UUPM_SEARCH=/path/to/search.py`.

## Ponytail — generator only

Repo: https://github.com/DietrichGebert/ponytail

```text
/plugin marketplace add DietrichGebert/ponytail
```

What it does: injects a YAGNI ladder (does this need to exist → reuse →
stdlib → native → installed dep → one line → minimum) via three hooks:
SessionStart, UserPromptSubmit and **SubagentStart**. The SubagentStart hook
is the problem: by default it injects the ladder into every subagent ASDR
spawns, including the critic, judge, evaluator, stage-qa and
security-compliance. An independent reviewer told to "do less" is no longer
independent, and ASDR's whole design is that no author grades its own work.

Required setting (project-level so it travels with the repo):

```json
// .claude/settings.json
{
  "env": {
    "PONYTAIL_SUBAGENT_MATCHER": "^generator$"
  }
}
```

Restart the session after changing it; hooks inherit the environment at
launch. `detect_companions.py` reports `scoped_to_generator: true|false`
and the orchestrator stops before the first sprint if it is false.

Rules once scoped (in `agents/generator.md`):

- NEGOTIATE mode is where rung 1 (YAGNI) belongs. A criterion the generator
  thinks is speculative gets a one-line objection with the requirement ID
  checked; the evaluator decides.
- Once a contract is ratified, no criterion is skipped. Rungs 2–7 govern
  how, never whether.
- Never simplified away: trust-boundary validation, data-loss error
  handling, controls from `docs/05-security.md`, accessibility items from
  `docs/03b-design-system.md` §9, anything the contract names.

Expectation management: the "-54% code" headline is Haiku 4.5, n=4, twelve
tasks on one repo. ASDR's `preflight_contract.py` new-file budget already
removes part of the over-build that Ponytail targets, so measure the delta
on your own sprints (`facts:` keys: files added, LOC added) before assuming
the number.

## Graphify — optional navigation aid

Repo: https://github.com/Graphify-Labs/graphify

```bash
uv tool install graphifyy   # or: pipx install graphifyy
graphify install            # registers /graphify with the assistant
```

Overlap: ASDR v3.2 already builds a dependency graph (`build_graph.py`) and
budgeted context packs for greenfield work. Graphify adds value in two
places:

- Brownfield entry: `/graphify . --update` before Phase 1 so the packs and
  the generator's "already in this codebase?" check have the existing code
  mapped. Code parsing is tree-sitter AST, local, no LLM cost.
- Post-sprint: `--update` after each `done` is cheap and keeps the graph
  current for security-final and documentation in Phase 4.

Hard rule: a graphify query is navigation, never measurement. Numbers come
from `emit_facts.py` only.

## RTK — detected, warned, not used

Repo: https://github.com/enixCode/rtk-plugin (install:
`/plugin marketplace add enixCode/plugins` then
`/plugin install rtk-plugin@enix`)

What it does: a PreToolUse hook prefixes supported Bash commands with the
`rtk` binary, which compresses their output 60–90%.

Why ASDR does not use it:

- The rewrite list includes `pytest`, `jest`, `vitest`, `playwright`, `git`,
  `grep`, `cat`, `head`, `tail`, `diff`, `curl` — the evaluator's evidence
  commands. Lossy compression in the ground-truth path is the wrong trade for
  a harness whose point is that claims are verified.
- `bootstrap-rtk.mjs` downloads a release binary with no checksum or
  signature check and runs `rtk init -g`, so it is global to the machine,
  not scoped to ASDR.
- `python3` is not on the rewrite list, so `emit_facts.py` is unaffected.

If you keep it installed anyway: `detect_companions.py` warns, and the
orchestrator reminds evaluator and stage-qa every invocation that only
`facts:` keys are evidence. That rule already exists in v3.2; RTK just makes
it load-bearing.

## AX (agentexecutor.io) — a runtime target, not a companion

Repo: https://github.com/google/ax (Apache-2.0, API `v1alpha1`)

AX is not a Claude Code skill; it is a declarative control plane that runs
agent tasks in sandboxes on Kubernetes + Agent Substrate. It enters ASDR as
the **Tier 3 reference runtime** in `docs/04-agent-design.md` §13 and as the
schema of `templates/agent-runtime.yaml`. The ai-architect chooses a tier
per agent; devops writes `deploy/agents/<agent>.yaml` only for T3 agents.
The four primitives (Task, Workspace, Gateway, Model) are used as the design
vocabulary for every tier, so a T1 Lambda and a T3 AX task are specified the
same way and differ only in the mapping column.
