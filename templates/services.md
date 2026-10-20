# Services — <Product>

<!-- docs/03e-services.md — solution-architect, only when the architecture
decision is microservices (docs/03c-architecture-options.md → B). The rules
validate_services.py enforces:
  - every service owns its data; no table or collection belongs to two services;
  - every synchronous call and every consumed event has a contract (CT-xx) with
    a contract file and a test case;
  - no cycle of synchronous calls;
  - every service runs standalone: its own data store and stubs of what it calls;
  - every building block a service uses has an adapter for local and for each
    production cloud in docs/03d-portability.md.
Contract files live in contracts/ (OpenAPI for HTTP, AsyncAPI or a CloudEvents
JSON schema for events). -->

## 01 · Services

| Service | Responsibility | Owns data | Calls (sync) | Publishes | Consumes | Standalone run |
|---|---|---|---|---|---|---|
| <svc-catalog> | <products, prices> | <products, prices> | <none> | <catalog.price-changed> | <none> | <compose profile catalog: own postgres> |
| <svc-orders> | <baskets, orders> | <baskets, orders> | <svc-catalog> | <order.placed> | <catalog.price-changed> | <compose profile orders: own postgres + catalog stub> |

## 02 · Contracts

| ID | Provider | Consumer | Kind | Contract file | Test case |
|---|---|---|---|---|---|
| <CT-01> | <svc-catalog> | <svc-orders> | <http> | <contracts/catalog.openapi.yaml> | <TC-21> |
| <CT-02> | <svc-catalog> | <svc-orders> | <event: catalog.price-changed> | <contracts/catalog-events.asyncapi.yaml> | <TC-22> |

A contract change that breaks a consumer is a new version (`/v2`, `.v2` event
type); the old one stays until every consumer has moved.

## 03 · Adapters

One row per service and building block it uses (block names from
`.harness/templates/cloud/catalogue.json`).

| Service | Block | Port (interface in the code) | Local | AWS | Azure | GCP |
|---|---|---|---|---|---|---|
| <svc-orders> | <relational-db> | <OrderRepository> | <postgres container> | <Amazon RDS for PostgreSQL> | <Azure Database for PostgreSQL – Flexible Server> | <Cloud SQL for PostgreSQL> |

Leave a cloud's column "n/a" when it is not a production cloud in the portability decision.

## 04 · How a journey crosses the services

For each Must process flow (docs/02d-process-flows.md), the services each step
touches, in order — this is how sprints are sliced and what the contract tests
must cover.

| Flow | Steps → services |
|---|---|
| <PF-01> | <1 svc-catalog → 2 svc-orders (CT-01) → 3 svc-orders publishes order.placed> |
