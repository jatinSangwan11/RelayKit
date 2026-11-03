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
