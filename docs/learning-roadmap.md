# RelayKit Production Learning Roadmap

**Last updated:** October 30, 2026

This roadmap turns RelayKit into a production-backend learning program. It is not a checklist of
technologies to install. Every tool or pattern must solve a failure or limitation that we can
explain, reproduce, test, and observe.

Because RelayKit is also the learner's first backend-heavy Python/FastAPI application, the
[`FastAPI and Python Backend Interview Track`](fastapi-interview-track.md) runs across every phase.
It covers the request lifecycle, ASGI/Uvicorn, Pydantic, dependencies, async Python, transactions,
testing, API optimization, deployment, and interview evidence at the point each concept becomes
real in RelayKit.

## Learning agreement

For every production feature, use this sequence:

1. **Recall the current flow.** Explain where the new feature belongs.
2. **Define the concept simply.** Explain the term without relying on jargon.
3. **Identify the failure.** State what can go wrong without the feature.
4. **Inspect the naive design.** Predict its behavior at each crash or concurrency boundary.
5. **Compare alternatives.** Record the chosen design and its trade-offs.
6. **Implement the smallest version.** The learner writes code unless they explicitly ask Codex to
   implement it.
7. **Test the happy path and motivating failure.** Add concurrency or failure-injection tests when
   the feature requires them.
8. **Observe it.** Add the useful log, metric, or trace rather than debugging blindly.
9. **State the guarantee and its limit.** Avoid claims such as exactly-once HTTP delivery.
10. **Record evidence.** Save commands, test results, measurements, diagrams, and interview notes.

A phase is complete only when the learner can explain it, the behavior works, the important failure
has been tested, and the evidence is recorded.

## Current checkpoint

The following foundation exists now:

- FastAPI application with `POST /v1/endpoints`, `POST /v1/subscriptions`, and `POST /v1/events`.
- Async SQLAlchemy engine, connection pool, session factory, and FastAPI database dependency.
- PostgreSQL models and Alembic migrations for endpoints, subscriptions, events, and deliveries.
- Event ingestion finds matching subscriptions and atomically commits one event plus one pending
  delivery per matching endpoint.
- A valid event with no matching subscriptions is accepted with zero deliveries.
- Unit tests and basic database integration tests exist; `35` tests and Ruff passed on October 30.

This is a **stored workflow**, not yet a complete webhook-delivery system. There is no RabbitMQ
publication, delivery worker, HTTP attempt history, inspection CLI, retry policy, or production
observability yet.

## Phase 0 — Re-establish the developer feedback loop

### Outcome

We can run the API locally, exercise it with Postman, understand failures from logs, and run the
test suite confidently before adding distributed components.

### Topics

- Uvicorn development lifecycle and configuration.
- Postman environments and repeatable requests.
- Structured JSON logs, log levels, request IDs, and exception logging.
- Difference between unit, integration, end-to-end, and failure-injection tests.
- Pytest fixtures, mocks, dependency overrides, and arranging test data.
- Ruff and mypy as fast feedback, not substitutes for behavior tests.

### Work

- Manually test the three current routes with real PostgreSQL data.
- Add request/correlation IDs and a minimal structured logging setup.
- Learn the existing route tests before adding more test code.
- Add API-level integration tests for the stored workflow.
- Correct any contract or migration drift discovered during manual testing.

### Gate

- The learner can trace one Postman request through validation, route, session, transaction, and
  response.
- Logs identify the request and outcome without printing secrets or complete sensitive payloads.
- Unit and integration test commands pass from a clean local setup.

## Phase 1 — Complete the smallest vertical slice

### Outcome

One accepted event reaches one local webhook receiver and can be inspected afterward.

```text
Postman/CLI -> FastAPI -> PostgreSQL -> RabbitMQ -> worker -> receiver
                                      \                     /
                                       delivery + attempt history
```

### Topics

- RabbitMQ exchanges, queues, bindings, routing keys, durable queues, and persistent messages.
- Producer versus consumer responsibilities.
- Async `aio-pika` connections and channels.
- HTTPX client reuse, timeouts, and outgoing webhook contracts.
- Delivery state machine and append-only attempt history.
- CLI as an HTTP client rather than a database client.
- Independently runnable API, worker, receiver, and CLI processes.

### Work

- Design and migrate the delivery-attempt table.
- Define the first RabbitMQ message contract and webhook payload/headers.
- Add RabbitMQ to local Docker Compose only when the message flow begins.
- Publish pending delivery work using the simplest happy-path mechanism.
- Build one delivery worker and a local failure-simulation receiver.
- Add `GET /v1/deliveries/{id}` and a minimal `relay deliveries inspect` command.

### Gate

- One event produces the expected delivery and one recorded successful attempt.
- The receiver observes a stable event ID and delivery ID.
- Inspection reports `SUCCEEDED` and preserves the attempt details.
- We explicitly document that this first mechanism still has a database-to-broker crash window.

## Phase 2 — Make publication and consumption reliable

### Outcome

Accepted work survives API, publisher, broker, and worker failures without silent loss.

### Learning sequence

1. **Idempotent ingestion**
   - Request identity, payload fingerprints, unique constraints, same-key/same-payload behavior,
     and same-key/different-payload conflict.
2. **Transactional outbox**
   - The database-to-broker dual-write failure, one-transaction publication intent, batching,
     row claiming, locks, leases, and crash recovery.
3. **Publisher confirmations**
   - What broker acceptance proves and why it does not prove webhook success.
4. **Manual consumer acknowledgements**
   - Acknowledge only after the database outcome is durable.
5. **Duplicate work handling**
   - At-least-once transport, stable identities, database conditions, and idempotent consumers.
6. **Retries and dead-lettering**
   - Retry classification, exponential backoff, jitter, maximum attempts, retry scheduling, poison
     messages, and terminal failure.
7. **Controlled replay**
   - Preserve history and create an auditable new execution rather than mutating arbitrary state.

### Required failure tests

- API crashes after the event transaction commits but before responding.
- RabbitMQ is unavailable while ingestion continues.
- Outbox publisher crashes before and after broker confirmation.
- Worker crashes before acknowledgement.
- Worker sends the webhook but crashes before recording success.
- The same message is delivered more than once.
- The endpoint times out or returns retryable and permanent errors.

### Gate

- No accepted event is silently lost in the tested crash windows.
- Duplicate transport does not create duplicate logical delivery state transitions.
- Attempt history explains every retry and dead-letter decision.
- The documented guarantee is “at-least-once transport with stable identities,” not exactly once.

## Phase 3 — Learn concurrency, backpressure, and latency

### Outcome

Multiple workers process deliveries concurrently without allowing one slow endpoint to monopolize
the system or overload dependencies.

### Topics

- Async I/O versus threads versus processes.
- Shared-state races between independent workers.
- Optimistic conditions, row locks, `SKIP LOCKED`, leases, and atomic state transitions.
- Worker-level semaphores and bounded task creation.
- RabbitMQ prefetch and fair work distribution.
- Backpressure from HTTP, database, queue, and connection-pool limits.
- Rate versus concurrency.
- p50, p95, p99, throughput, saturation, and coordinated omission.

### Redis progression

Redis is introduced as temporary coordination, never as the only source of correctness:

1. Connectivity and health behavior.
2. Expiring per-endpoint concurrency leases.
3. Per-endpoint request-rate limiting.
4. Shared circuit-breaker state: `CLOSED`, `OPEN`, and `HALF_OPEN`.
5. Conservative behavior during Redis outages.

### Evidence

- A slow endpoint does not block an unrelated healthy endpoint.
- Two worker processes respect the configured endpoint concurrency limit.
- Load tests record throughput and ingestion/delivery latency percentiles.
- A before/after experiment explains the impact of prefetch, pool limits, client reuse, or batching.

## Phase 4 — Build production observability

### Outcome

We can answer: “What failed, where, for whom, since when, and how badly?” without reading random
terminal output.

### Build in this order

1. **Structured logs**
   - `request_id`, `event_id`, `delivery_id`, `attempt_number`, outcome, duration, and `trace_id`.
   - Redaction rules for API keys, signatures, secrets, and payload data.
2. **Prometheus metrics**
   - Ingestion and delivery latency histograms.
   - Accepted events, successful attempts, failures, retries, and dead letters.
   - Outbox backlog, queue depth, in-flight work, and database-pool pressure.
3. **OpenTelemetry traces**
   - Propagate trace context through API -> PostgreSQL -> outbox -> RabbitMQ -> worker -> HTTPX.
   - Learn spans, parent/child relationships, sampling, baggage, and asynchronous trace links.
4. **OpenTelemetry Collector**
   - Receive, batch, enrich, filter, and export telemetry independently of application code.
5. **Grafana stack**
   - Prometheus for metrics, Tempo for traces, Loki for logs, and Grafana for correlation,
     dashboards, alerts, and runbooks.
6. **SLOs and alerts**
   - Availability and latency objectives, error budgets, actionable alerts, and alert fatigue.

### Cardinality rule

Do not use `event_id`, `delivery_id`, full URLs, or unbounded tenant values as Prometheus labels.
Those identities belong in logs and traces. Metrics use bounded dimensions such as route, outcome,
status class, and worker role.

### ClickHouse decision

ClickHouse is a later analytical store, not an initial correctness dependency. Add it only after a
measured need for high-volume, high-cardinality delivery analytics or longer operational retention.
If introduced, send derived attempt/telemetry data asynchronously and keep PostgreSQL authoritative.
The learning exercise should compare query shape, ingestion volume, retention cost, and operational
complexity against PostgreSQL and the Grafana stack.

### Gate

- One trace follows an event across process and queue boundaries.
- A Grafana dashboard shows latency, throughput, errors, retries, dead letters, and backlog.
- An injected endpoint failure produces a useful log, metric, trace, and actionable alert.
- A short runbook explains how to diagnose the failure.

## Phase 5 — Add security and multi-tenancy

### Outcome

RelayKit isolates customer data, authenticates producers, and sends verifiable webhooks safely.

### Topics and work

- Account model, API-key generation, hashing, lookup, revocation, and rotation.
- Tenant-scoped queries and tests proving cross-tenant access is impossible.
- HMAC signatures, timestamps, replay windows, constant-time comparison, and secret rotation.
- Destination URL validation and SSRF protection.
- Payload-size limits, timeouts, allowed redirects, and response-body retention limits.
- Encryption at rest for endpoint secrets and the boundary between application encryption and KMS.
- Audit logging and least-privilege database/deployment credentials.
- Threat modelling: assets, actors, trust boundaries, abuse cases, and mitigations.

### Gate

- Cross-tenant tests fail safely.
- A receiver verifies valid signatures and rejects tampered, expired, or replayed requests.
- Private-network and unsafe destination attempts are rejected according to the documented policy.

## Phase 6 — Operate and deploy the system

### Outcome

Someone other than the author can build, migrate, deploy, observe, recover, and demonstrate RelayKit.

### Topics and work

- Separate container images or commands for API, publisher, and worker.
- Configuration validation and Twelve-Factor principles.
- Liveness, readiness, dependency health, and degraded states.
- Graceful shutdown: stop intake, drain work, finish or release claims, close resources.
- CI checks for formatting, linting, types, unit tests, and integration tests.
- Migration strategy, backward-compatible schema changes, and rollback planning.
- HTTPS, reverse proxy/load balancer, horizontal scaling, and stateless API instances.
- PostgreSQL backup/restore rehearsal and RabbitMQ/Redis recovery expectations.
- Deployment runbook, incident checklist, architecture diagram, and reproducible demo script.

### Gate

- A clean environment can deploy the documented version.
- Migrations and independently runnable processes start successfully.
- A public HTTPS demo completes an end-to-end delivery.
- Backup/restore and one selected incident recovery are rehearsed.
- Resume claims use measured results from recorded load and failure tests.

## Phase 7 — Resume-depth bridge labs

These labs cover important resume and backend-roadmap topics that should not be forced into the
RelayKit correctness path.

| Lab | What it teaches | Connection |
|---|---|---|
| Cache a read-heavy delivery summary | Cache-aside, TTL, invalidation, stampede protection, hit rate, p95 measurement | GamesPro Redis/latency work |
| `relay deliveries tail` with SSE | Streaming HTTP, reconnects, ordering, backpressure, SSE versus WebSockets | GamesPro real-time escalation |
| S3 payload/archive export | Object keys, metadata, presigned URLs, multipart uploads, lifecycle rules | Verse asset storage |
| RAG diagnostic assistant | Embeddings, chunking, retrieval evaluation, vector stores, grounding | GamesPro RAG work |
| AI failure summarizer | Keep AI outside the delivery-critical path; evaluate accuracy and fallback behavior | Verse agent/LLM work |
| OAuth/OIDC theory and small integration | Identity provider, tokens, scopes, sessions, RBAC | GamesPro SSO work |
| ClickHouse delivery analytics | Columnar storage, partitions, high-cardinality queries, retention | Advanced observability/analytics |
| Jenkins-to-CI comparison | Pipelines, artifacts, environments, approvals, rollback | Verse deployment work |

Each lab gets its own question, baseline, implementation, test, measurement, and interview summary.
It does not become a required production dependency merely because it appears on a resume or
playlist.

## Daily session format

Assume a focused session, not a fixed amount of code:

```text
10 minutes       Learner-led revision
15 minutes       Confirm today's one observable outcome
30–60 minutes    Concept, motivating failure, and trade-offs
90–180 minutes   Pairwise learner-led implementation
30–60 minutes    Tests, failure experiment, and debugging
15 minutes       Notes, evidence, and next-session handoff
```

Every session should end with:

- what the learner can now explain;
- what behavior was verified;
- what remains incomplete;
- the exact next smallest task;
- the commands and evidence needed to resume without relying on chat memory.

Each completed feature also adds one entry to the interview evidence ledger: the problem, naive
failure, chosen design, trade-off, relevant test, operational evidence, and a two-minute spoken
explanation. This prevents interview preparation from becoming a separate memorization exercise.

## Immediate next session

1. Spend 10 minutes revising the current ingestion transaction and three implemented routes.
2. Run the API and manually exercise endpoint -> subscription -> event using Postman.
3. Learn structured logging, correlation IDs, and exception logging.
4. Add only the minimum developer logging needed to diagnose those requests.
5. Review the existing unit tests and add API/database integration coverage for the stored workflow.
6. Stop and record evidence before beginning RabbitMQ.

After that gate passes, begin Phase 1 with the delivery-attempt model and RabbitMQ message contract.
