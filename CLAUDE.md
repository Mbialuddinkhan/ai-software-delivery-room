# AI Software Delivery Room — repository charter

This repository IS the plugin. Nothing here is a project built with ASDR; it
is the source of the agents, skills, scripts and templates that get installed
into other projects. Keep that distinction when editing.

## Layout

| Path | What it is |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest (name, version) — the version users see |
| `.claude-plugin/marketplace.json` | One-plugin marketplace `asdr` so Claude Code can install from this repo |
| `agents/*.md` | The 17 agent definitions (frontmatter `name` must equal the filename) |
| `skills/*/SKILL.md` | The 6 orchestrator skills; `metadata.version` tracks the plugin version |
| `scripts/*.py` | The state machine, validators and context-discipline scripts; copied into each project's `.harness/scripts/` by `init_asdr.py` |
| `templates/` | Fill-in templates; copied into each project's `.harness/templates/` |
| `docs/` | Operating manual, triad design, context-architecture review |
| `tests/` | Unit tests for the scripts — `python3 -m unittest discover tests` |

Runtime state (`.harness/`, `sprints.json`, `CLAUDE.md` inside a target
project) is created by `scripts/init_asdr.py`; it does not live in this repo.

## Rules for changes

1. Scripts are zero-dependency Python 3 and must degrade gracefully (a missing
   tool yields a note, never a crash). Every new check gets a test that fires
   it on a true positive and a test that shows it does not block a valid input.
2. A change to any agent role boundary (who may ratify, pass, release) is a
   design change — record it in `docs/` and `CHANGELOG.md`, not just the agent file.
3. Bump the version in three places together: `plugin.json`, `marketplace.json`,
   and every `skills/*/SKILL.md` `metadata.version`. Add a `CHANGELOG.md` entry.
4. Before pushing: `python3 -m py_compile scripts/*.py`,
   `python3 -m unittest discover tests`, and `claude plugin validate .`.

## Releasing

- Push `main` and tag `vX.Y.Z`.
- Claude Code users update with `claude plugin marketplace update asdr` then
  `claude plugin update ai-software-delivery-room@asdr`.
- Cowork takes a `.plugin` zip of: `.claude-plugin agents skills scripts
  templates docs tests README.md CHANGELOG.md .gitignore` (no `.git`).
