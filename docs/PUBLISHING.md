# Publishing ASDR

The repository is both the plugin and its own marketplace: `.claude-plugin/`
holds `plugin.json` (the plugin) and `marketplace.json` (the catalog that
lists the plugin and its companions). Users need one `marketplace add` and
one `install`; the install pulls UI UX Pro Max in automatically.

## What users run

```text
/plugin marketplace add Mbialuddinkhan/ai-software-delivery-room
/plugin install ai-software-delivery-room@asdr
/reload-plugins
/ai-software-delivery-room:asdr        (or just /asdr if no other plugin claims it)
```

The install output ends with the dependencies it added; expect
`ui-ux-pro-max` there. Note that `claude plugin update` does NOT install a
dependency that a new version declares for the first time — an existing
3.2.x user who updates sees "failed to load" with the error
`Dependency "ui-ux-pro-max@asdr" is not installed` until they run
`claude plugin install ui-ux-pro-max@asdr` once (observed on Claude Code
2.1.178). Say so in the release notes of any version that adds a dependency. Ponytail is listed in the same marketplace but
disabled by default: `/plugin install ponytail@asdr` if wanted, plus the
`PONYTAIL_SUBAGENT_MATCHER` setting from `docs/COMPANIONS.md`.

Team rollout without per-user steps — commit to a project's
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "asdr": { "source": { "source": "github", "repo": "Mbialuddinkhan/ai-software-delivery-room" } }
  },
  "enabledPlugins": { "ai-software-delivery-room@asdr": true }
}
```

## One-time setup (done in 3.2.1 / 3.3.0)

- `.claude-plugin/marketplace.json` — marketplace name `asdr` (not on the
  reserved list; not `npm`/`pip`/`github`/etc.). Entries:
  `ai-software-delivery-room` (source `./`, `dependencies: ["ui-ux-pro-max"]`),
  `ui-ux-pro-max` (github source pinned by `sha`), `ponytail` (pinned,
  `defaultEnabled: false`).
- `.claude-plugin/plugin.json` — `dependencies`, `license`, `repository`
  added. `version` lives ONLY here; the marketplace entry for
  ASDR deliberately has no `version` (Claude Code silently prefers
  plugin.json, so a stale duplicate would mask releases).
- No hooks. The update check runs only inside `/asdr` (Phase 0 step 5);
  `scripts/check_updates.py --hook` is available if you ever want a
  SessionStart notice, but ASDR ships without one.
- Keep executables under `scripts/`, never a top-level `bin/` (claude.ai
  org distribution rejects it).

## Release checklist (every version)

1. Bump `version` in `.claude-plugin/plugin.json` — users only get an
   update when this string changes.
2. Add the `## [x.y.z]` section at the top of `CHANGELOG.md`. The first
   ~12 lines of that section are what `check_updates.py` shows users as
   "what it adds", so lead with benefits, not internals.
3. Bump `metadata.version` in every `skills/*/SKILL.md` to match.
4. Validate: `claude plugin validate .` (checks marketplace.json and the
   local plugin's plugin.json). Then
   `claude plugin validate ./skills` and `./agents` for frontmatter.
5. Test locally before pushing:
   ```text
   /plugin marketplace add ./ai-software-delivery-room
   /plugin install ai-software-delivery-room@asdr
   ```
   Confirm the install summary lists `ui-ux-pro-max`, then run one
   `/asdr` through Phase 0 and check `.harness/companions.json` shows
   `uupm.installed: true`.
6. Commit, then tag with the dependency-resolution convention:
   `claude plugin tag --push` → creates `ai-software-delivery-room--v3.3.0`
   (it refuses if plugin.json and the marketplace entry disagree or the
   tree is dirty). Also fine: `git tag ai-software-delivery-room--v3.3.0 && git push --tags`.
7. Push `main`. Users see the update on their next `/plugin marketplace
   update asdr` or, if they enabled auto-update for the marketplace in
   `/plugin`, automatically. Their next `/asdr` run shows what the update adds.

## Re-pinning a companion

`ui-ux-pro-max` and `ponytail` are pinned by commit SHA so a user's ASDR
install cannot change under them when upstream pushes. To take a new
upstream version:

1. `git ls-remote https://github.com/nextlevelbuilder/ui-ux-pro-max-skill HEAD`
   (or a tag) → new SHA.
2. Update `sha` and `version` in the marketplace entry.
3. Re-run the UUPM smoke test: `python3 scripts/uupm_design_system.py`
   against a scratch project — the CLI flags (`--design-system -p -f
   markdown`) are the contract; if they moved, fix the wrapper.
4. Bump ASDR's own `version` (a companion change is an ASDR release) and
   follow the release checklist.

`check_updates.py` reports when upstream has moved past the pin, with the
note that the maintainer must re-pin — that message is meant for you.

## Getting into Anthropic's directories

Two tiers, both at Anthropic's discretion:

- **Community marketplace** (`anthropics/claude-plugins-community`,
  installed as `@claude-community`): submit through the in-app form at
  claude.ai → Settings → Plugins → Submit (also reachable as
  clau.de/plugin-directory-submission). Give the public GitHub repo at the
  exact commit you validated. Pull requests against that repo are closed
  automatically; everything flows through the form. After approval their
  CI mirrors pushes to your repo, so routine releases do not need
  resubmission.
- **Official marketplace** (`claude-plugins-official`): curated by
  Anthropic; the form does not put you there. Track record in the
  community tier is the realistic path.

What reviewers look for, based on their published expectations: one
coherent job end to end (ASDR qualifies), clean `claude plugin validate`,
version in `plugin.json` matching the changelog and git tag, no secrets,
hooks that fail open, and a README that shows a reproducible example
rather than private client material. Never advertise an "Anthropic
Verified" badge you have not been granted.

Independent of either directory, the `asdr` marketplace on your own repo
is a complete distribution channel; the directories add discovery, not
capability.
