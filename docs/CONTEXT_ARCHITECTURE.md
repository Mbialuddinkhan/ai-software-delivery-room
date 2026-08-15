# Critical review of the ASDR performance review — and a context-cost plan

Scope note: I have your report, not the ClientProof repo or the raw transcripts.
Everything below reasons from your evidence. Where I project a saving I say so —
none of my numbers are measurements, and the plan's first deliverable is the
instrument that would let you measure them.

---

## 1. Verdict

Your **diagnosis** is right: context is being burned on re-derivation, and the
system is expensive out of proportion to what it returns on bookkeeping.

Your **proposed remedy** — a central development-manager agent that holds the
knowledge and dependency graph — is half right and, built naively, would make
the problem worse. The evidence for that is in your own report. I'll argue it in
§4 and give the version that works.

---

## 2. Where the review is right (not re-litigated)

- §1.1 is the strongest result in the document and it should lead every future
  version of it. *CI 7/7 green and six genuine defects simultaneously* is the
  single fact that justifies the harness's existence.
- §1.4's reciprocity — two catches each way — is the real proof the
  generator/evaluator split works, not just that a reviewer exists.
- R2 (mechanical pre-flight) is the best cost-per-unit-benefit item in the list.
- R5 (fixture isolation as harness rule, not tribal knowledge) is correct and
  evidence-backed. The non-UTC re-used-cluster finding deserves to be a standing
  rule, not a recommendation.
- R7's two bugs are real. The placeholder-regex use/mention bug is the same class
  of error as authoring rule (a) — you spotted the isomorphism; that's the right
  instinct.

---

## 3. Where I disagree, or where the framing misleads

### 3.1 "Attempt counts are high and rising" (§2.4) — unsupported

Three points, one of which hasn't finished (sprint 7 hasn't built), is not a
trend. Worse, it's confounded: sprint 6/7 also grew to **74 criteria across 18
new files**. Attempts didn't rise because the harness degraded; they rose
because contract size rose. That's your own R4.

Framing this as a trend invites the wrong fix (loosen the loop). The right fix is
R4 (cap the contract). Delete §2.4's trend claim and fold the data into R4 as
evidence for sizing.

### 3.2 "Half the attempts went on bookkeeping" — right cost, wrong conclusion

The implied conclusion is "process criteria are waste." But the sprint-6 record
shows the diff caps were a *proxy for seam discipline*, and the evaluator
eventually replaced the number with **four nominated invariants**, observing the
three cheapest ways to hit the count "narrow the seam by zero bytes."

So the lesson is not *delete process criteria*. It is:

> A process criterion must be either (a) machine-measured, or (b) expressed as an
> invariant. It must never be a number a human or an agent transcribes.

Your R3 gets to a similar place but justifies it on cost. Justify it on
**validity** instead — the line count was measuring documentation the method
mandates, which is a broken instrument regardless of price.

### 3.3 §1.2 and §2.2 contradict each other and the review doesn't reconcile them

§1.2 credits "contracts before code" with moving defects left. §2.2 shows the
first draft of a contract is *systematically unsatisfiable* — seven rule-(b)
violations found by the generator in a single draft, three by the evaluator
against itself.

Both are true. The reconciliation matters because it identifies a cost centre the
review never names: **contract authoring is now the most defect-dense artifact in
the system, and it is gated only by a structural validator.** Six negotiation
rounds across three sprints is a major token sink, and it exists because
`validate_contract.py` checks shape, not satisfiability.

This makes R2 not the second priority but co-equal with R1 — see §6.

### 3.4 The shell finding is under-claimed in one direction and over-claimed in another

**Under-claimed:** you treat "no shell" as a correctness problem. It is also, and
possibly primarily, a **context-cost** problem. An agent without a shell that
needs a line count must read whole files into context. `wc -l` is ~20 tokens; the
file is thousands. Every derived number in sprint 7's contract — eleven per-file
diff bounds, a 110/53/13 census, a derivation of 80 — was paid for **twice**: once
in tokens to read the material, once in error when the derivation was wrong by 60.

If you fix nothing else, fix this, and a large fraction of §2.5's delegation cost
disappears as a side effect.

**Over-claimed:** the review frames the shell gap as an environmental nuisance.
It's a capability change. Without a shell, *the evaluator is a reviewer, not a
verifier.* Its verdicts in those sprints are code-reading opinions with unusually
good discipline — which is exactly what it said itself: *"Nothing in this
contract is measured."* That belongs in §4's bottom line, not §2.

### 3.5 The buried headline

`CARRY-FORWARD: live-call-unverified` has been open **since sprint 2**, and the
review discloses it in the last three lines, labelled a caveat.

On a product whose named failure mode is *one person receiving two telephone
calls*, seven sprints of verdicts earned against Postgres rows and a simulated
carrier is not a caveat. It is the top risk item, and it is *harness-induced*:
the system optimises what it can grade, so effort flowed to diff bookkeeping —
gradeable, low-value — while the highest-risk surface stayed ungraded because
it's hard to grade.

That is the most important sentence in this review and it isn't in your review.
Any context-efficiency work that doesn't also fix *what gets graded* will simply
make you cheaply confident about the wrong things.

---

## 4. The development-manager proposal, critically

Your instinct — "something should hold the knowledge and dependency graph so 50
agents stop rebuilding it" — is correct about the disease.

The naive cure (a central agent that knows everything and brokers between
specialists) fails for four reasons, each visible in your own data:

1. **Subagents share no context.** Whatever the manager knows must be
   *serialised into each subagent's prompt anyway*. The manager doesn't reduce
   what gets sent; it just moves where it's assembled. Token cost unchanged.
2. **It adds a hop.** manager → specialist → manager is three invocations where
   you had one. With 50 subagent runs already dominating cost, adding a
   coordination round-trip per task is the wrong direction.
3. **It becomes the most expensive agent in the system.** To broker well it must
   read broadly, every time it's called, and it's called constantly. You'd be
   creating a new context bottleneck to solve a context problem.
4. **It centralises hallucination.** Your report already documents derived
   numbers being wrong — a cap wrong by 60, then wrong again the other way. A
   manager whose job is to *summarise* state for everyone else propagates one
   bad derivation into every downstream agent. Today those errors are caught
   because two roles derive independently and disagree. A single authoritative
   summariser removes exactly that check.

**The fix is the artifact, not the agent.** What you actually want is:

> A machine-maintained graph and a machine-generated per-task context pack, so
> each agent receives a small, scoped, *measured* brief instead of reading the
> repository to rebuild one.

A script can't hallucinate a dependency edge. An agent can.

If a manager role survives this, it survives as a **thin dispatcher**: it runs
the graph scripts, assembles packs, enforces budgets, and holds *no knowledge
between invocations* — its memory is the files. That's a librarian, not an
oracle, and it's cheap. See Phase 3.

**One thing you already have that you're not using:** v3.1 shipped
`.harness/traceability.json` mapping outcome → requirement → use case → sprint →
criteria → tests → status. That is roughly 80% of the dependency graph you're
asking for. Don't build a second knowledge structure beside it — extend it with
file/module edges. One graph, or you'll be reconciling two.

---

## 5. Where the context actually goes (ranked)

From your evidence, in descending order:

| # | Driver | Evidence | Fixed by |
|---|---|---|---|
| 1 | **Derivation without a shell** — reading files to compute what a command returns | eleven diff bounds, a census, a derivation of 80, none measured; one wrong by 60 | Phase 0 |
| 2 | **Re-derivation per agent** — each re-reads contract, eval reports, repo | §2.5, "each agent re-reads … before writing anything" | Phase 1 + 2 |
| 3 | **Negotiation rounds** — every round re-reads everything | 6 rounds / 3 sprints; first drafts systematically unsatisfiable | Phase 1 (pre-flight) |
| 4 | **Unscoped briefs** — agent reads broadly because it can't tell what's relevant | "wide passes exhausted their budgets; the narrow ones finished" | Phase 2 |
| 5 | **Re-verification of uncommitted work** | "uncommitted output from a context-exhausted agent is the most expensive failure mode" | Phase 2 |

Note that #1 causes part of #2 and #3. That's why sequencing matters.

---

## 6. The plan

Priority is by *measured cost removed per unit of build effort*, not by elegance.

### Phase 0 — Make measurement possible (do this first, alone if you must)

Nothing else in this plan pays off properly until facts are measured rather than
derived.

1. **Give build + evaluation agents a shell.** If that's within your control,
   this is a one-line environment change with the largest single return.
2. **If it isn't: move all measurement to CI and emit a facts artifact.**
   New file: `.harness/facts.json`, written by CI, never by an agent:
   ```json
   {
     "commit": "…", "generated_at": "…",
     "diff_stat": { "src/tools.ts": {"added": 112, "removed": 8, "net_nonblank": 104 } },
     "file_census": { "unit": 110, "integration": 53, "e2e": 13 },
     "expect_delta": { "…": 0 },
     "test_results": { "passed": 73, "failed": 0, "suites": [...] },
     "coverage": { … }
   }
   ```
   Agents **read** it and cite it. They never compute it.
3. **Contract rule (new, enforced):** *no numeric criterion may be graded except
   by citing a key in `facts.json`.* This mechanically kills `RP 1(i)` — the
   criterion asking the builder to transcribe `git diff --stat` — and every
   future instance of that class.
4. **Change the diff-cap unit** to non-blank, non-comment lines, since you have
   the empirical result already (221/67/32/9/44 → 112/28/9/1/25). Emit both from
   CI; grade on the second.

### Phase 1 — Stop paying for unsatisfiable first drafts

`scripts/preflight_contract.py`, run **before** the evaluator ever sees a draft.
Machine-checkable rule-(b) violations, all drawn from real instances in your run:

- an asserted HTTP status that contradicts the route's actual `return` (grep the route)
- a "must equal zero" clause whose own criterion mandates an edit to that file
- a numeric bound with no derivation line, or no `facts.json` key
- a cited `file:line` that doesn't resolve
- a regex constraint over a payload another criterion requires to contain a match
- a time bound asserted against a fixture clock the harness clamps
- a floor on a resource count that a strictly better implementation would fail
  (e.g. "≥3 DB reads" — flag every `>=` on a cost metric; you want a ceiling)

You estimated this catches ≥8 of 11. Even at half that, it removes negotiation
rounds, which are the third-largest context sink.

Also enforce here (your R4, as machine rules):
- **≤7 criteria may name any single integration file** (sprint 7 had one named by
  seventeen — one `beforeAll` slip fails all seventeen and you can't tell a
  product defect from a fixture bug)
- **budget new files, not just criteria** — file count drives fixture-isolation
  risk, which is where sprints 5 and 6 bled

### Phase 2 — Generated context packs (the real answer to your question)

This is where the "knowledge and dependency graph" idea becomes concrete, as
files and scripts rather than an agent.

1. **Extend `.harness/traceability.json`** with a `graph` section:
   ```json
   "graph": {
     "modules": { "voice/tools": { "files": ["src/tools.ts", …],
                                   "depends_on": ["db/lead"], "owned_by": ["FR-12"] } },
     "file_to_requirements": { "src/tools.ts": ["FR-12","FR-14"] },
     "file_to_criteria":     { "src/tools.ts": ["sprint-07#3", …] },
     "fixture_risk":         { "tests/int/book.spec.ts": ["PhoneNumber","slotKey"] }
   }
   ```
2. **`scripts/build_graph.py`** — regenerates the graph from the repo + matrix.
   Deterministic, cheap, runs in CI. No agent writes this.
3. **`scripts/make_context_pack.py --task <id>`** — emits a single scoped brief:
   the relevant matrix rows, the relevant files (paths, not contents), the
   `facts.json` slice, the last verdict for those criteria, the fixture-risk
   notes for the files in scope, and the stopping point. This *replaces* "go read
   the contract and the eval reports and the repo."
4. **`.harness/state-digest.md`** — a short rolling state file (≤1 page,
   machine-regenerated): current sprint, attempt, open carry-forwards, last
   verdict per criterion group. Agents read this instead of a stack of eval
   reports. This is the durable state file from your R6.
5. **Hard context budget per brief.** If a generated pack exceeds the budget, the
   task is too big — **fail at planning time, not mid-task**. This converts your
   "agents exhausted their budget and returned partial work" from a silent,
   expensive runtime failure into a cheap upfront split signal.
6. **Agents commit their own work** (your R6). Uncommitted output from an
   exhausted agent is your most expensive failure mode; a commit makes partial
   work recoverable instead of re-verifiable.

### Phase 3 — The delivery-manager role, thin

Only after Phases 0–2 exist. Its charter, deliberately narrow:

- runs `build_graph.py`, `make_context_pack.py`, `preflight_contract.py`
- assembles and dispatches briefs; enforces budgets and stopping points
- updates `state-digest.md`
- **holds no knowledge between invocations** — its memory is the files
- **grades nothing, approves nothing, summarises no document into prose**

That last constraint is the important one. The moment the manager starts
producing authoritative prose summaries, you've reintroduced the single-point
hallucination risk and removed the independent-derivation check that caught the
evaluator's off-by-60.

### Phase 4 — Fix what gets graded (the buried headline)

- Promote `live-call-unverified` from a carry-forward to a **release-blocking
  gate**. The risk-manager already has the authority; give it the rule.
- Add one behavioural criterion class that can only be satisfied by a real or
  recorded-carrier call. If it can't be automated yet, it becomes a **named
  manual gate with a human signature**, not a silent carry-forward.
- Rationale: a harness that grades only what's cheap to grade will keep producing
  well-evidenced confidence about the wrong surface.

### Phase 5 — Small fixes (your R7, correct as written)

- `validate_contract.py` placeholder regex: use/mention. Require placeholders to
  be matched only inside the criterion slot, or switch to a sentinel token that
  can't appear in prose.
- Single canonical sprint goal. `sprints.json` holds it; the contract *references*
  it. Whichever you pick, delete the other copy — two copies will disagree again.

---

## 7. What I'd advise against building

- **A manager that reviews or approves.** You already have stage-qa, evaluator,
  critic, judge, risk-manager and now product-integrity-qa. Another reviewer adds
  cost and regress, not assurance.
- **Agent-written summaries as the shared knowledge layer.** Machine-extracted
  facts only. Your own evidence is that derived numbers were wrong twice.
- **Running every reviewer on every stage.** The rigor dial exists — `standard`
  for normal sprints, `paranoid` only for compliance-critical surfaces (here:
  the call path).
- **Loosening the loop to reduce attempts.** The attempt count is a contract-size
  symptom. Cap the contract instead.

---

## 8. How you'll know it worked

Instrument before optimising, or the next review is opinion too. Track per sprint:

| Metric | Today (from your report) | Target direction |
|---|---|---|
| Negotiation rounds to ratification | 1 → 2 → 3 | ↓ (Phase 1) |
| Attempts to pass | 2 → 5 | ↓, and never at the cap |
| Criteria graded by `facts.json` citation | ~0 | → 100% of numeric criteria |
| Subagent runs per sprint | ~17/sprint (50 / 3) | ↓ |
| Mean brief size at dispatch | unmeasured | measured, then ↓ |
| Partial/exhausted agent returns | "several" | → 0 |
| Rule-(b) violations reaching the evaluator | 11 in one run | ↓ (Phase 1) |

The first three are the honest scoreboard. If Phase 0–2 lands and negotiation
rounds and attempts don't fall, the thesis in this document is wrong and you
should say so in the next review.

---

## 9. Sequence

```
Phase 0  shell / facts.json + "cite a fact key" rule     ← do first, highest return
Phase 1  preflight_contract.py + size caps               ← co-equal; kills rounds
Phase 2  graph + context packs + state digest + budgets  ← the actual context fix
Phase 3  thin delivery-manager (dispatcher only)         ← only after 0–2
Phase 4  live-call gate                                  ← independent, do in parallel
Phase 5  two small validator/state bugs                  ← anytime, cheap
```

Phases 0 and 1 are where the money is. Phase 2 is what you asked for and is worth
doing. Phase 3 is worth doing *last*, small, and only if 0–2 haven't already
solved it — which they might.

---

## 10. The one-line version

Your review's own closing sentence is the strategy: *agents were asked to measure
things they had no ability to measure.* Fix measurement first (Phase 0), stop
paying for unsatisfiable contracts second (Phase 1), and only then build the
knowledge graph — **as files a script maintains, not as an agent that
remembers.**
