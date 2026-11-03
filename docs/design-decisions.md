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
