# Build ladder (generator, BUILD mode)

<!-- Carried inside ASDR so no external plugin is needed. Adapted from the
"ladder" in DietrichGebert/ponytail (MIT, v4.10.0) — the seven rungs are
theirs; the contract-first rules around them are ASDR's. If the Ponytail
plugin is ALSO installed and scoped to the generator, the two agree; if it
is installed unscoped, ASDR stops before Phase 3 (docs/COMPANIONS.md). -->

## Where the ladder applies

Only to HOW a ratified criterion is satisfied. Never to WHETHER. A
criterion in a `Status: ratified` contract is never skipped, deferred,
or "YAGNI'd" in BUILD mode — that argument belonged in NEGOTIATE (see
generator step 3d) and the evaluator has already ruled on it.

## The seven rungs — stop at the first that holds

For each criterion, after you have read every file the change touches and
traced the real flow end to end:

1. **Already in this codebase?** A helper, type, util, or pattern that
   exists here → reuse it. Re-implementing what is two files away is the
   most common slop. (Graphify, when present, makes this a query.)
2. **Standard library does it?** Use it.
3. **Native platform feature covers it?** `<input type="date">` over a
   picker library, CSS over JS, a DB constraint over app code.
4. **An already-installed dependency solves it?** Use it. Never add a new
   dependency for what a few lines do — `preflight_contract.py`'s new-file
   budget and the security doc's dependency rules apply.
5. **Can it be one line?** One line.
6. **Only then:** the minimum code that works.
7. **Leave one runnable check** for every non-trivial path (a branch, a
   loop, a parser, a money or security path): the smallest test that fails
   if the logic breaks. Trivial one-liners need none.

## Rules

- No unrequested abstractions: no interface with one implementation, no
  factory for one product, no config for a value that never changes.
- No scaffolding "for later"; later can scaffold for itself.
- Deletion over addition; boring over clever.
- Fewest files, shortest working diff — once you understand the change.
  The smallest diff in the wrong place is a second bug, not laziness.
- Bug fix = root cause. Grep every caller before editing; one guard in
  the shared function beats a guard in each caller.
- Mark a deliberate simplification with a known ceiling with a comment
  naming the ceiling and the upgrade path:
  `# ladder: global lock — per-account locks if throughput matters`.

## Never simplified away

Input validation at a trust boundary. Error handling that prevents data
loss. Any control in `docs/05-security.md`. Any item from
`docs/03b-design-system.md` §9. Any allowlist row in `docs/04-agent-design.md`
§13.2. Anything the contract names. The evaluator grades these; a
"skipped" note is not a substitute.

## Output

Code first. Then at most three lines in the sprint build log:
`skipped: <X>, add when <Y>`. No essays.
