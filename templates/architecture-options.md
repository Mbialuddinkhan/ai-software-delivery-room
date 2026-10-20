# Architecture options — <Product>

<!-- docs/03c-architecture-options.md — written by the solution-architect BEFORE
docs/03-architecture.md, from the brief, business case, requirements and process
flows. The user decides; nothing is designed until they have. Plain language:
the reader is a business owner. Every cost and time figure is an estimate and is
written as a range. Validate with:
  python3 .harness/scripts/validate_architecture_options.py -->

## 01 · What drives the choice

Score each criterion 0 (no), 1 (somewhat) or 2 (clearly yes), with the evidence
from the documents. Do not guess; a criterion with no evidence scores 0.

| # | Criterion | Score | Evidence (document + quoted line) |
|---|---|---|---|
| C1 | Parts of the system need to scale separately (load differs by 10× or more) | <0-2> | <…> |
| C2 | Separate teams will own separate parts, now or within a year | <0-2> | <…> |
| C3 | Parts must be released on different schedules | <0-2> | <…> |
| C4 | A failure in one part must not take the others down | <0-2> | <…> |
| C5 | Parts have different compliance, security or data-residency rules | <0-2> | <…> |
| C6 | Parts need different technology (language, runtime, database) | <0-2> | <…> |
| C7 | Parts will be sold, reused or replaced on their own | <0-2> | <…> |
| C8 | The team (or the client's team) already runs distributed systems in production | <0-2> | <…> |

Rule (stated so the recommendation can be checked): a total of 8 or more with at
least two of C1–C4 scored 2 points to microservices; 4–7 points to a modular
monolith with service-ready boundaries (split later, when a criterion becomes
real); 3 or less points to a modular monolith. The architect may argue against
the rule, in writing, under the recommendation.

## 02 · Options

### Option A — Modular monolith with service-ready boundaries

One deployable application, split inside into modules that own their data and
talk through interfaces, so any module can later become a service.

- Pros: <…>
- Cons: <…>
- Business impact: <time to first release, monthly running cost, speed of change later, reliability, team needed, what leaving a cloud would cost>
- Build cost: <range, e.g. USD 40k–60k> (estimate)
- Run cost per month: <range per environment> (estimate)
- When it wins: <…>

### Option B — Microservices

Independent services, each with its own data, released and scaled on its own,
talking through versioned contracts (HTTP APIs and events).

- Pros: <…>
- Cons: <…>
- Business impact: <…>
- Build cost: <range> (estimate)
- Run cost per month: <range> (estimate)
- When it wins: <…>

### Option C — Serverless-first (only when it fits)

Mostly managed functions and services; little to run, priced per use, more
tied to one cloud.

- Pros: <…>
- Cons: <…>
- Business impact: <…>
- Build cost: <range> (estimate)
- Run cost per month: <range> (estimate)
- When it wins: <…>

## 03 · Side by side

| | A · Modular monolith | B · Microservices | C · Serverless-first |
|---|---|---|---|
| Time to first release | <…> | <…> | <…> |
| Build cost (estimate) | <…> | <…> | <…> |
| Run cost per month (estimate) | <…> | <…> | <…> |
| Effort to operate | <…> | <…> | <…> |
| Scaling | <…> | <…> | <…> |
| Speed of change after year one | <…> | <…> | <…> |
| Team needed | <…> | <…> | <…> |
| Cost of moving cloud later | <…> | <…> | <…> |
| Main risk | <…> | <…> | <…> |

Assumptions behind the figures: <users, load, data volume, team rate, regions, pricing source and date>

## 04 · Recommendation

Recommended: <A | B | C> — <why, in two or three sentences, tied to the scores>.
What would change it: <the criterion or fact that would flip the choice>.

## 05 · Decision

- Decision: <pending | A | B | C>
- Decided by: <name>, <date>
- Services (Option B): <how many, or "see docs/03e-services.md">
- Notes: <anything the user added>
