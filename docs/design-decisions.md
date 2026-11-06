# RelayKit Design Decisions

This file records product and architecture decisions that affect RelayKit's behavior. The goal is
to preserve the reasoning, alternatives, and trade-offs—not only the final choice.

Each decision is kept in a collapsible section so this file remains useful as the project grows.

Decision statuses:

```text
Proposed    We are still discussing the decision.
Accepted    The decision is approved and should guide implementation.
Superseded  A later decision has replaced it.
```

<details>
<summary><strong>DD-001 — Handling events with no matching subscriptions</strong></summary>

### Status

**Proposed** — awaiting confirmation before implementation.

### Date

October 20, 2026

### Question

What should RelayKit do when a producer submits a valid event, but no endpoint is currently
subscribed to that event type?

Example request:

```http
POST /v1/events
Content-Type: application/json
```

```json
{
  "type": "payment.completed",
  "data": {
    "paymentId": "pay_123"
  }
}
```

Current subscriptions:

```text
order.created → Shipping
user.deleted  → Analytics
```

There is no matching subscription for `payment.completed`.

### Important distinction

An event and a delivery represent different facts:

```text
Event
└── payment.completed happened

Delivery
└── RelayKit must notify one particular endpoint about that event
```

A valid event can therefore exist with zero deliveries.

### Option A — Reject the event

Behavior:

```text
Receive valid event
      ↓
Find zero matching subscriptions
      ↓
Store nothing
      ↓
Return a non-success response
```

#### Advantages

- Avoids storing events that currently have no delivery work.
- Immediately tells the producer that nobody is subscribed.
- May expose a subscription-configuration mistake quickly.

#### Disadvantages

- Couples producer success to subscriber configuration.
- An accidental unsubscribe can make valid producer requests fail.
- Producers may repeatedly retry an event that cannot currently create deliveries.
- RelayKit loses the audit record showing that the producer submitted the event.
- It becomes harder to distinguish “producer never sent it” from “no subscription existed.”

Example failure sequence:

```text
Accounting accidentally unsubscribes from payment.completed
      ↓
Producer submits a valid payment.completed event
      ↓
RelayKit finds zero matching subscriptions and rejects it
      ↓
Producer retries even though its event was valid
```

### Option B — Accept and store the event

Behavior:

```text
Receive valid event
      ↓
Store one event
      ↓
Find zero matching subscriptions
      ↓
Create zero deliveries
      ↓
Return 202 Accepted
```

Example response:

```json
{
  "eventId": "evt_123",
  "deliveryIds": [],
  "status": "accepted"
}
```

#### Advantages

- Keeps producers independent from subscriber configuration.
- Preserves an audit trail that the event was received.
- Makes missing-subscription incidents easier to investigate.
- Avoids producer retry loops caused only by a configuration change.
- Preserves the domain rule that an event is a fact, not a delivery outcome.

#### Disadvantages

- Stores events that may never create delivery work.
- Requires retention rules as event volume grows.
- A `202` response might hide a missing subscription unless RelayKit exposes useful logs, metrics,
  or inspection tools.

### Recommendation

Choose **Option B**: accept and store a valid event even when it has no matching subscriptions.

The producer's responsibility is to report that something happened. Subscription configuration
determines who should be notified; it should not determine whether the event itself is valid.

### Proposed behavior and guarantee

```text
Valid event + zero matching subscriptions
        ↓
Persist one event
        ↓
Persist zero deliveries
        ↓
Return 202 with deliveryIds: []
```

Subscriptions are evaluated when the event is ingested. Adding a subscription later does not
automatically create a delivery for an older event.

### Consequences and later improvements

- Record the count of matching subscriptions in structured logs and metrics.
- Make zero-delivery events visible through inspection tools.
- Define an event-retention policy before production deployment.
- Consider an optional warning or alert for unexpected zero-delivery events.
- Manual replay or backfill must be an explicit controlled operation; it is not automatic.

</details>

<details>
<summary><strong>DD-003 — Durable delivery-attempt history in the first vertical slice</strong></summary>

### Status

**Accepted for the learning vertical slice** — the lease/recovery portion must be completed before
the system is described or deployed as production-ready.

### Date

November 6, 2026

### Question

What should RelayKit store for each outgoing webhook request, and which failure guarantees should
the first vertical slice provide before retries and processing leases are implemented?

### Problem

A delivery row records the responsibility to notify one endpoint, but it cannot preserve the
history of several independent HTTP requests. Keeping only the latest status loses the evidence
needed for debugging, retry decisions, CLI inspection, metrics, and customer support.

There is also an unavoidable ambiguity when a worker sends a webhook and dies before storing the
result. The destination may have processed the request even though RelayKit has no durable result.

### Decision

Create one durable `delivery_attempts` row for every actual HTTP request. An attempt begins as
`in_progress` in a short PostgreSQL transaction, the HTTP call runs outside that transaction, and a
second short transaction records `succeeded` or `failed` together with the delivery transition.

The initial state vocabulary is:

```text
in_progress -> succeeded
            -> failed
            -> abandoned (recovery path added during hardening)
```

The schema will include a unique `(delivery_id, attempt_number)` constraint plus basic range and
status checks. Diagnostic errors must be safe and bounded. Arbitrary endpoint response bodies will
not be stored.

### Alternatives considered

#### Store only the final status on `deliveries`

Rejected. It destroys attempt history and cannot explain retries, timeouts, response codes, or
worker-crash ambiguity.

#### Keep one attempt row and overwrite it for every retry

Rejected. It has the same audit problem and makes attempt counts and historical latency unreliable.

#### Hold one database transaction open during the HTTP request

Rejected. A slow external endpoint would occupy a connection and retain transactional resources
for an unbounded network wait, reducing throughput and increasing contention.

#### Implement leases, retries, dead-lettering, and replay immediately

Deferred. Those mechanisms are required for production, but adding their algorithms before one
attempt can be observed end to end would hide the core model from a first-time backend learner.

### Initial guarantee

For a worker outcome that RelayKit observes normally, PostgreSQL will preserve the individual
attempt and its relationship to the delivery. Retrying later will create another attempt rather
than rewriting history.

### Explicit non-guarantee

The first slice does not yet automatically recover a worker that dies with an `in_progress`
attempt. It also does not prevent a duplicate external side effect after the endpoint processes a
request but the worker dies before storing success. These require processing leases, redelivery,
stable webhook identifiers, and receiver-side idempotency.

### Production-hardening gate

Before deployment is called production-ready, RelayKit must:

1. add a time-bounded processing lease and atomic recovery rule;
2. mark expired attempts `abandoned` without pretending the endpoint outcome is known;
3. make duplicate broker messages safe;
4. acknowledge RabbitMQ only after the database outcome commits;
5. use stable event and delivery identifiers across retries;
6. test worker death before HTTP, during HTTP, and after HTTP but before the result commit.

### Consequences

- CLI inspection and later observability can show every attempt.
- The schema carries more rows and needs retention/index planning at scale.
- The simple slice remains understandable, but its crash-recovery limitation must remain visible.
- Later retry and lease work extends the model instead of replacing its history.

</details>

<details>
<summary><strong>DD-004 — Separate delivery state from message-publication state</strong></summary>

### Status

**Accepted for the target architecture** — the outbox states are documented now but implemented
only during transactional-outbox hardening.

### Date

November 6, 2026

### Problem

A delivery status and an outbox status answer different questions. Treating database `QUEUED` as
the worker's required claim state introduces a race: RabbitMQ may deliver a confirmed message
before the publisher finishes changing the delivery row to `QUEUED`.

### Decision

Keep the state machines separate:

```text
Delivery: PENDING -> DELIVERING -> SUCCEEDED / RETRY_SCHEDULED / DEAD_LETTERED
Outbox:   PENDING -> PUBLISHING -> PUBLISHED
Broker:   contains the actual waiting message
```

A worker receiving a message must atomically claim an eligible delivery in PostgreSQL. The RabbitMQ
message alone does not authorize the HTTP request. The claim and creation of the `in_progress`
attempt must commit in the same database transaction.

### Alternatives considered

#### Require delivery status `QUEUED`

Rejected as a correctness guard. It duplicates broker/publication state and creates ordering races
between publisher database updates and fast consumers.

#### Use an in-process Python lock

Rejected. It cannot coordinate separate worker processes, containers, replicas, or machines.

#### Read status and update it in separate statements without a guarded write

Rejected. Concurrent workers can both read `PENDING` and both call the endpoint. Ownership requires
a conditional update such as `UPDATE ... WHERE status = 'pending' RETURNING ...`.

### Consequences

- PostgreSQL remains the authoritative source of delivery ownership.
- The outbox independently proves publication progress.
- A duplicate message cannot create permission for a second HTTP request by itself.
- A worker crash after claiming still requires a later processing-lease recovery mechanism.
- RabbitMQ acknowledgement behavior for already claimed or completed deliveries remains part of
  Block 3 and must be tested before production use.

</details>

<details>
<summary><strong>DD-002 — Structured application logging to stdout</strong></summary>

### Status

**Accepted** — implement before RabbitMQ is introduced.

### Date

November 4, 2026

### Question

How should RelayKit produce useful, safe, and production-compatible logs while the system still runs
locally and has no external log collector?

### Problem

Uvicorn's default access line can show that a request returned `202`, but it cannot answer:

- Which application logs belong to that request?
- Which event or delivery was involved?
- How long did the request take inside RelayKit?
- At which boundary did an unexpected failure occur?
- How can a client-reported failure be found in concurrent logs?

Unstructured `print()` calls would make these problems worse because they have no standard severity,
context, filtering, exception handling, or machine-readable structure.

### Decision

RelayKit will use Python's standard `logging` package with one central application configuration.
RelayKit-owned logs will be emitted as structured JSON to standard output.

```text
RelayKit module
    ↓ named child logger
LogRecord
    ↓ propagation
relaykit application handler
    ↓ request-context filter
JSON formatter
    ↓
stdout
    ↓
terminal today / container log collector later
```

Each module obtains its own named logger:

```python
logger = logging.getLogger(__name__)
```

Modules must not call `basicConfig()` or attach their own console handlers. The central
configuration owns levels, handlers, filters, and formatting.

### Initial implementation

Create the following responsibilities only when implementation begins:

```text
relaykit/observability/context.py
    Request ID ContextVar

relaykit/observability/logging.py
    JSON formatter, request-context filter, central configuration

relaykit/api/middleware/request_logging.py
    request ID validation/generation, timing, response header, access/failure log
```

The request middleware will:

1. Read `X-Request-ID`.
2. Reuse it only when it matches `[A-Za-z0-9._-]{1,64}`; otherwise generate
   `req_<UUID version 4 hex>`.
3. Store it in a `ContextVar` before FastAPI routing, dependencies, and Pydantic validation.
4. Measure elapsed time with a monotonic clock.
5. Add the request ID to the response header.
6. Emit one structured completion record for handled responses.
7. Emit an exception record with a stack trace for unexpected failures.
8. Clear the context in every exit path so it cannot leak into later asynchronous work.

The initial common fields are:

```text
timestamp       UTC ISO-8601 timestamp
level           DEBUG / INFO / WARNING / ERROR / CRITICAL
service         relaykit-api
environment     development initially
logger          named source logger
event           stable machine-readable event name
message         human-readable explanation
requestId       request correlation ID when available
```

The HTTP completion record additionally includes:

```text
method
path            path only; exclude the query string
statusCode
durationMs
```

Domain records may later add safe identifiers such as `eventId`, `deliveryId`, `eventType`, and
`deliveryCount`.

### Security and privacy rules

Do not log:

- Authorization headers or API keys.
- Webhook secrets or signatures.
- Database credentials.
- Complete request or event payloads.
- Full destination URLs or query strings that may contain secrets.
- Arbitrary response bodies from customer endpoints.

Request IDs are untrusted input. Their length and characters must be validated before including
them in response headers or logs. Redaction is a secondary protection; sensitive values should not
be logged in the first place.

### Levels

- `DEBUG`: detailed diagnostic state disabled in normal production operation.
- `INFO`: expected lifecycle events, successful requests, and expected client errors.
- `WARNING`: recoverable abnormal behavior such as a scheduled retry or degraded dependency.
- `ERROR`: a RelayKit operation failed unexpectedly.
- `CRITICAL`: the process cannot operate safely.

An expected `404`, `409`, or `422` is not automatically an application error. The HTTP completion
record carries its status without producing an unnecessary exception stack trace.

### Alternatives considered

#### `print()` statements

Rejected. They lack levels, context propagation, structured fields, centralized configuration, and
reliable exception information.

#### Add `structlog` immediately

Deferred. It provides a strong structured-logging API, but the current requirements can be met with
the standard library. Adding it now would add a dependency before RelayKit has a limitation that
justifies it. We can reconsider if context binding or processor composition becomes cumbersome.

#### Write rotating files inside the application

Rejected. Files inside containers are difficult to aggregate across replicas and introduce
rotation, retention, persistence, and disk-management responsibilities into the application.

#### Send logs directly from RelayKit to Loki or ClickHouse

Rejected for the initial system. A storage outage or slow network must not block request handling,
and every process should not need vendor-specific shipping logic. A collector will own forwarding
later.

### Production trade-offs in simple words

#### Benefits

- JSON is searchable by fields instead of fragile text matching.
- Request IDs connect concurrent log records to one request.
- stdout works locally and in containers.
- The future collector can forward the same output without changing route code.
- Central configuration prevents every module from inventing its own format.

#### Costs and limitations

- JSON is harder for a human to scan directly in a terminal.
- Logging too much increases storage cost, noise, and possible privacy exposure.
- Logging synchronously to stdout still consumes some request time under very high volume.
- A request ID correlates one HTTP request; it is not yet a distributed trace across queues and
  processes.
- Local stdout disappears when the terminal or container is gone until a collector and durable log
  store are added.
- Uvicorn's own logs may initially use a different format; they must later be normalized or handled
  separately to avoid mixed and duplicate access logs.

### Initial middleware limitation

The first request-logging implementation will use FastAPI's function-style HTTP middleware. This is
a deliberate learning and scope decision: it makes the before/after request lifecycle, `call_next`,
context setup, response headers, timing, exception logging, and cleanup directly understandable.

Function-style HTTP middleware is sufficient for RelayKit's current small JSON request/response
API, but it is not treated as the final answer for every ASGI workload. It relies on Starlette's
HTTP middleware abstraction and has trade-offs around streaming responses, lower-level ASGI
message control, context propagation behavior, and some additional middleware overhead.

RelayKit currently has no streaming endpoint, so introducing pure ASGI middleware now would add
complexity without solving an observed requirement. Before adding streaming responses, very large
response bodies, specialized disconnect handling, or latency-sensitive lower-level behavior, we
must re-evaluate the middleware using controlled tests.

Possible later design:

```text
ASGI scope / receive / send
        ↓
Pure RelayKit ASGI middleware
        ↓
FastAPI application
```

A move to pure ASGI middleware must preserve the same externally tested guarantees: request-ID
validation/generation, context isolation, correlation headers, completion/failure logs, timing, and
cleanup on every exit path. It will be adopted only when a concrete failure or measured bottleneck
justifies the extra complexity.

### Future production path

```text
relaykit-api ────────┐
relaykit-outbox ─────┼──> stdout ──> OpenTelemetry Collector/Vector ──> Loki
relaykit-worker ─────┘                                             └──> Grafana
```

Later work will add service/process identity, trace IDs, sampling and retention policy, collector
buffering, centralized storage, dashboards, and alerts. ClickHouse remains optional for measured
high-cardinality analytics or retention needs; PostgreSQL remains authoritative for RelayKit data.

### Verification requirements

- A successful and a handled-error response contain `X-Request-ID`.
- Missing and invalid request IDs are replaced safely; valid IDs are preserved.
- Concurrent requests retain separate request IDs.
- Completion logs include method, path, status, and duration.
- Unexpected exceptions include a stack trace and correlation context.
- Reconfiguring or reloading does not duplicate handlers or log lines.
- Tests verify that request bodies and secrets are not emitted.
- Postman can match the response header to the terminal JSON record.

</details>
