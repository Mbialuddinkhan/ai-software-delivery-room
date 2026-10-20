# Microservice standards (ASDR 3.8)

Used only when the architecture decision (docs/03c-architecture-options.md) is
microservices. The generator builds to these; the evaluator and critic check
them; `validate_services.py` enforces the parts a script can see.

## 1. Every service runs standalone

- Its own repository folder (`services/<name>/`), its own data store, its own
  container image and its own Compose profile. `docker compose --profile
  <name> up` starts the service, its database and **mocks** of every service it
  calls (generated from the provider's contract, e.g. Prism for OpenAPI) — never
  the real neighbours.
- It starts with nothing but environment variables. Configuration comes from
  the environment (12-factor); secrets come through the secrets port, never from
  files in the repository.
- `/health/live` (process is up) and `/health/ready` (its own dependencies
  answer) on every service; the orchestrator, Compose and every cloud use them.

## 2. Business logic never touches a cloud SDK

Ports and adapters: the domain code depends on small interfaces (ports) such as
`OrderRepository`, `EventPublisher`, `FileStore`, `Secrets`. Each port has one
adapter per target — local, and one per production cloud in
docs/03d-portability.md. The adapter is chosen at start-up from configuration.

```ts
// ports/event-publisher.ts
export interface EventPublisher { publish(type: string, data: object, key?: string): Promise<void>; }

// adapters/events.nats.ts      (local and portable)
// adapters/events.eventbridge.ts (AWS)   adapters/events.eventgrid.ts (Azure)   adapters/events.pubsub.ts (GCP)

// main.ts — the only place that knows which one
const publisher = adapters.events[process.env.EVENTS_ADAPTER ?? "nats"](config);
```

```python
# ports.py
class FileStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...

# adapters: s3_compatible.py (local MinIO/SeaweedFS and AWS S3), azure_blob.py, gcs.py
```

The same tests run against every adapter (an adapter contract test per port):
the local adapter in every build, the cloud adapters in the cloud test run.

## 3. Services talk only through versioned contracts

- HTTP: OpenAPI in `contracts/<service>.openapi.yaml`. Events: AsyncAPI or a
  CloudEvents JSON schema in `contracts/<service>-events.*`.
- Every pair is a `CT-xx` row in docs/03e-services.md with a test case. The
  provider's tests prove it honours the contract; the consumer's tests run
  against a mock generated from it.
- A breaking change is a new version (`/v2`, `order.placed.v2`); the old one
  stays until every consumer has moved.
- No shared database tables. Another service's data is read through its API or
  kept as a local copy fed by its events.

## 4. Events are reliable

- Publish through an outbox (write the event in the same transaction as the
  data, a relay sends it) so a crash cannot lose or invent an event.
- Consumers are idempotent: every event has an id; a repeat is ignored.
- Every message carries a correlation id; every log line and trace includes it.

## 5. Observable everywhere

OpenTelemetry for traces, metrics and logs in every service. Locally they go to
the OpenTelemetry Collector + Jaeger in Compose; on each cloud to its native
backend through the same collector configuration (see the catalogue).

## 6. Sprints still slice through whole journeys

A sprint delivers a user-visible journey end to end, even when it crosses
three services. The first sprint is a walking skeleton: every service, its
health checks, one contract each, the Compose file and the pipeline — thin, but
deployed to the test cloud.
