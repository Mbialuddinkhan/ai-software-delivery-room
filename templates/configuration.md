# Configurable decisions — <Product>

<!-- docs/03f-configuration.md — written by the solution-architect in design
(Phase 1 step 6c), after the architecture and portability decisions, from the
feature list's "Decisions with options" (docs/02c-features.md §Decisions) and
its own technical choices. The USER decides each row. Plain language: the
reader is a business owner. Every cost figure is an estimate. Validate with:
  python3 .harness/scripts/validate_configurability.py -->

## 01 · How to read this

Every decision with more than one sensible answer is one of three types:

- **configure** — cheap to build both, reversible, business-level (pricing
  plans, approval limits, workflow steps, notifications, a feature on or off per
  customer). Built as a setting with a safe default, a rule for who may change
  it, a change log and a test for every allowed value.
- **prepare** — an expensive technical choice (database, cloud, payment
  provider, one application or microservices). One option is built now, behind
  a clean connection point, so the other can be added later at a known cost.
- **decide-once** — hard to reverse (the data model, how customers' data is
  separated, a regulatory choice). Decided here; no switch.

Rule (so the recommendation can be checked): recommend **configure** only when
building every option adds no more than **15%** to that feature's build and
test cost AND does not split the data model. Otherwise recommend prepare or
decide-once. The user may still choose configure; record that they did.

## 02 · Decision register

| ID | Decision | Options | Type recommended | Extra cost to build all options | Splits the data model? | Why | Decided by | Decision |
|---|---|---|---|---|---|---|---|---|
| DEC-01 | <who approves a refund> | <fixed limit; per-customer limit> | <configure\|prepare\|decide-once> | <8%> | <no> | <one line> | <name, date> | <configure\|prepare\|decide-once> |

## 03 · Settings (decisions decided as configure)

One row per setting. "Allowed values" is a comma-separated list, or a range
`min..max`. Every allowed value needs a test case (a range: its minimum, its
maximum and the default), tested from the side of the user the setting affects.

| ID | Decision | Setting key | Default | Allowed values | Who can change it | Takes effect | Owner | Review by | Tests |
|---|---|---|---|---|---|---|---|---|---|
| CFG-01 | DEC-01 | <refunds.approval_limit> | <100> | <50, 100, 250> | <Admin> | <immediately> | <Product owner> | <YYYY-MM-DD> | <TC-14, TC-15, TC-16> |

## 04 · Prepared options (decisions decided as prepare)

| Decision | Built now | Prepared for | Connection point | Estimated cost to switch later |
|---|---|---|---|---|
| DEC-02 | <PostgreSQL> | <a managed cloud database> | <the repository interface in src/data/> | <3–5 days> |

## 05 · Settings that interact

List settings whose values change each other's behaviour, and how they are
tested: every value once, plus every pair of values for settings that interact
(pairwise), not every combination.

| Settings | How they interact | Test approach |
|---|---|---|
| <CFG-01, CFG-03> | <…> | <pairwise: TC-20, TC-21> |

## 06 · Removing settings

A setting nobody changes is a permanent cost and a known source of incidents.
On or before its review date the owner keeps it (new date), makes the current
value permanent and removes the switch, or removes the feature. The release
gate fails while a review date has passed.
