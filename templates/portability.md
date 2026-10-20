# Portability and cloud services — <Product>

<!-- docs/03d-portability.md — written by devops after the architecture decision,
from docs/03-architecture.md and .harness/templates/cloud/catalogue.json. The
user decides. Get prices from the vendors' own tools when the session has them
(AWS MCP Server, Azure MCP Server, Google Cloud pricing) or their calculators,
and say which and when. Every figure is an estimate, written as a range.
Validate with: python3 .harness/scripts/validate_portability.py -->

- Test cloud (chosen at the start, .harness/cloud.json): <aws | azure | gcp | none>
- Clouds the client may run on: <one or more of aws, azure, gcp — or "not decided">

## 01 · Building blocks this product needs

Only the blocks the architecture uses. Names from the catalogue.

| Block | Needed for | Portable choice | AWS | Azure | GCP | Local (standalone) |
|---|---|---|---|---|---|---|
| <relational-db> | <orders, accounts> | <PostgreSQL> | <Amazon RDS for PostgreSQL> | <Azure Database for PostgreSQL – Flexible Server> | <Cloud SQL for PostgreSQL> | <postgres container> |

## 02 · Strategies

### S1 — Portable core

Containers, PostgreSQL, Valkey, S3-compatible storage and open messaging on every
cloud; thin adapters only where a cloud has no portable equivalent (identity,
secrets, observability).

- Pros: <…>
- Cons: <…>
- Business impact: <running cost, effort to operate, cost of moving cloud later, hiring>
- Monthly run cost: AWS <range> · Azure <range> · GCP <range> (estimates)

### S2 — Native services behind adapters

Each block uses the cloud's managed service; every service talks to it through
its own interface, with one adapter per cloud and one for local.

- Pros: <…>
- Cons: <…>
- Business impact: <…>
- Monthly run cost: AWS <range> · Azure <range> · GCP <range> (estimates)

### S3 — Single-cloud native

The best managed services of one cloud, used directly; no adapters.

- Pros: <…>
- Cons: <…>
- Business impact: <…>
- Monthly run cost: <cloud> <range> (estimate)

## 03 · Cost comparison

| Strategy | AWS / month | Azure / month | GCP / month | Build effort | Cost of moving cloud later | Effort to operate |
|---|---|---|---|---|---|---|
| S1 | <…> | <…> | <…> | <…> | <…> | <…> |
| S2 | <…> | <…> | <…> | <…> | <…> | <…> |
| S3 | <…> | <…> | <…> | <…> | <…> | <…> |

- Assumptions: <users, requests, data volume, environments, regions, hours a day>
- Prices from: <tool or calculator>, <date>

## 04 · Recommendation

Recommended: <S1 | S2 | S3> on <cloud(s)> — <why>.
Per-block exceptions: <e.g. "document-db: Firestore on GCP only, with a PostgreSQL adapter elsewhere">
What would change it: <…>

## 05 · Decision

- Decision: <pending | S1 | S2 | S3>
- Production cloud(s): <aws | azure | gcp, …>
- Per-block choices (if different from the strategy): <…>
- Decided by: <name>, <date>
