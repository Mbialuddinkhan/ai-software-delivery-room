# Companions — the third-party skills ASDR uses

How each one reaches the user:

| Companion | Delivery | Why this way |
|---|---|---|
| UI UX Pro Max | **Dependency** of the `ai-software-delivery-room` plugin in the `asdr` marketplace; installs with ASDR, pinned to a commit SHA | Pure data + Python, no hooks, no network; safe to force-install |
| Build ladder | **Built in** (`templates/build-ladder.md`, adapted from Ponytail, MIT) | The value is the text, not the plugin; carrying it avoids Ponytail's SubagentStart hook reaching the reviewers |
| Ponytail | Listed in the `asdr` marketplace, `defaultEnabled: false`, one command to install | Hooks affect every subagent; a user must opt in and scope it |
| Graphify | Detected only (pip/uv tool, not a Claude plugin) | Cannot be a plugin dependency; ASDR offers `pip install graphifyy` on brownfield entry |
| RTK | Detected, warned, never installed | Compresses evidence commands |
| MiroFish | Detected; optionally installed at a pinned commit by `mirofish_stack.py` into `~/.asdr/mirofish/` and called over HTTP | AGPL-3.0, Python + Node + a graph store; cannot be a plugin dependency and is never vendored or patched |

ASDR does not vendor any companion's code. `scripts/detect_companions.py`
(Phase 0 step 4) finds what the host session has installed and writes
`.harness/companions.json`; the orchestrator, generator, evaluator and
stage-qa read that file. The plugin companions are MIT-licensed and update
often, so vendoring would mean maintaining forks. MiroFish is AGPL-3.0, which
is one more reason ASDR only ever talks to it over HTTP.

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

## MiroFish — idea validation by swarm simulation (optional)

Repo: https://github.com/666ghj/MiroFish (AGPL-3.0). Offline fork using
Ollama + Neo4j instead of a cloud LLM and Zep Cloud:
https://github.com/nikmcfly/MiroFish-Offline

What it does: builds a knowledge graph from seed documents, generates
agent personas from it, runs a Twitter/Reddit-style simulation on CAMEL-AI's
OASIS, and writes a report; agents can be interviewed afterwards.

**ASDR's own panel comes first.** Since v3.9 `validate` runs a native
synthetic panel (`scripts/panel.py`) by default. It takes MiroFish's useful
ideas — evidence-grounded personas, memory, one measured round of social
exposure, "what if" scenarios, follow-up interviews — without its scale or
infrastructure. MiroFish is the optional heavy lane.

**Let ASDR run it (Claude Code on your machine):**

```bash
python3 .harness/scripts/mirofish_stack.py doctor --flavor offline      # or cloud
python3 .harness/scripts/mirofish_stack.py up --flavor offline          # prints what it will download; add --yes once you agree
python3 .harness/scripts/mirofish_stack.py down                          # stop; `purge --yes` removes everything
```

- `cloud` = the original, at the pinned commit. Set `MIROFISH_LLM_API_KEY`,
  `MIROFISH_LLM_BASE_URL`, `MIROFISH_LLM_MODEL`, `MIROFISH_ZEP_API_KEY` in your
  shell first; the seed goes to that provider and Zep Cloud.
- `offline` = the fork, at its pinned commit: Neo4j in Docker and your own
  Ollama (on a Mac, Docker cannot use the GPU, so ASDR points the container at
  the Ollama app instead of running Ollama in Docker). The fork states 16 GB RAM
  minimum, 32 GB recommended; `--model qwen2.5:7b` for smaller machines.
  `--pull-models` pulls the models after you agree — check their sizes on
  ollama.com/library first.
- Every port is bound to 127.0.0.1. The API has no authentication; never
  expose it.
- Not available from Cowork: the sandbox has no Docker and `localhost` there
  is not your computer.

**Or run it yourself (Docker is quickest):**

```bash
git clone https://github.com/666ghj/MiroFish && cd MiroFish
cp .env.example .env     # LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME (any OpenAI-format API), ZEP_API_KEY
docker compose up -d     # backend on :5001, UI on :3000
export MIROFISH_URL=http://localhost:5001   # only if not the default
python3 .harness/scripts/mirofish_validate.py --check
```

How ASDR uses it: `detect_companions.py` probes `$MIROFISH_URL/health`;
the `validate` skill writes a market seed, asks the user before uploading
it, and `mirofish_validate.py` drives the API end to end (rounds capped,
resumable) and records `.harness/validation.json`.

What to expect from it, plainly:

- **It is synthetic opinion.** The personas come from our own seed, so a
  seed that argues for the product produces agents that agree. The critic is
  told to look for exactly that. Use it to find objections, confusion and
  competitor comparisons before a real customer conversation, not to size
  demand or price.
- **It is expensive and slow.** Every persona and every round is LLM calls;
  MiroFish's own README advises starting under 40 rounds. ASDR defaults to
  20 and one run.
- **Your seed leaves the machine.** It goes to the LLM provider in
  MiroFish's `.env` and to Zep Cloud (unless you run the offline fork).
- **Licence.** ASDR contains no MiroFish code. If you modify MiroFish and
  serve it to others over a network, the AGPL applies to that deployment.

Hard rule: simulated numbers are `validation:` keys, never `facts:` keys,
and no hypothesis is "supported" on simulation alone.

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
