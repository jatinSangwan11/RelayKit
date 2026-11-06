# RelayKit Learning Notes

These are beginner-friendly revision notes for the design and implementation of RelayKit. They
record concepts we have actually discussed. Detailed algorithms will be added immediately before
their implementation instead of being guessed upfront.

## 1. What RelayKit does

RelayKit is a hosted, headless webhook-delivery platform with a developer-first CLI.

Suppose an e-commerce application completes a payment. Accounting and Analytics need to know about
it. The producer submits the fact to RelayKit, and RelayKit accepts responsibility for delivering an
HTTP webhook to every matching subscribed endpoint.

```text
E-commerce application
        |
        | POST /v1/events
        | payment.completed
        v
     RelayKit
        |
        ├──> Accounting endpoint
        └──> Analytics endpoint
```

The producer does not wait for the destination endpoints. RelayKit stores the work, responds
quickly, and performs delivery asynchronously.

If an endpoint is temporarily unavailable, RelayKit records the failure and retries according to
policy. If the allowed attempts are exhausted, that delivery becomes dead-lettered for inspection
or controlled replay.

## 2. Core terminology



### Producer

The application that tells RelayKit that something happened.

Example: an e-commerce backend submits `payment.completed`.

### Event

A fact that already happened.

```json
{
  "type": "payment.completed",
  "data": {
    "paymentId": "pay_123",
    "amount": 4999
  }
}
```

An event does not become false because webhook delivery fails. The payment is still complete.

### Published or submitted event

When we say the producer publishes an event, we mean it submits the event to RelayKit's API. To
avoid confusing this with RabbitMQ publication, these notes generally use **submit** or **ingest**.

### Ingestion

The API operation from receiving an event request until RelayKit durably accepts it and returns a
response.

### Webhook

An HTTP request RelayKit sends to inform another application about an event.

### Endpoint

A registered destination URL, for example:

```text
https://accounting.example.com/webhooks
```



### Subscription

A rule connecting one event type to one endpoint.

```text
Accounting endpoint subscribes to payment.completed
```

Only matching subscriptions create deliveries. If Shipping subscribes only to `order.shipped`, a
`payment.completed` event does not create a Shipping delivery.

### Delivery

RelayKit's overall responsibility to send one event to one endpoint.

```text
One event + two matching endpoints = two deliveries
```



### Attempt

One individual HTTP request made while fulfilling a delivery.

```text
Delivery to Analytics
├── Attempt 1: HTTP 503
├── Attempt 2: timeout
└── Attempt 3: HTTP 200
```

This is one delivery, three attempts, and a final delivery state of `SUCCEEDED`.

### Retry

Another attempt made after a retryable failure.

### Dead-lettered delivery

A delivery that exhausted its attempt policy or encountered a permanent failure and now requires
inspection or controlled replay.

### Worker

A long-running background process that performs webhook deliveries.

### Queue

A durable waiting area for active work. RelayKit uses RabbitMQ.

## 3. Event, delivery, and attempt relationship

```text
Event: payment.completed
│
├── Delivery to Accounting
│   └── Attempt 1: HTTP 200
│
└── Delivery to Analytics
    ├── Attempt 1: HTTP 503
    ├── Attempt 2: timeout
    └── Attempt 3: HTTP 200
```

Totals:

```text
Events:     1
Deliveries: 2
Attempts:   4
```

Separate delivery records are necessary because endpoints can have different outcomes, retry
counts, latency, timeouts, rate limits, and final states.

Attempt history is preserved so operators can understand failures, enforce maximum attempts,
calculate metrics, and inspect behavior through the CLI or a future dashboard. RelayKit should
store useful metadata without retaining unnecessarily large or sensitive response bodies.

## 4. Delivery state machine

```text
PENDING
   |
   v
DELIVERING
   |
   ├──> SUCCEEDED
   |
   ├──> RETRY_SCHEDULED
   |          |
   |          v
   |       DELIVERING
   |
   └──> DEAD_LETTERED
```

- `PENDING`: the delivery exists, but no HTTP attempt has started.
- `DELIVERING`: a worker currently owns an attempt.
- `SUCCEEDED`: the endpoint returned a successful response, normally an HTTP `2xx`.
- `RETRY_SCHEDULED`: an attempt failed, attempts remain, and another attempt is scheduled.
- `DEAD_LETTERED`: no more automatic attempts will be made.

`SUCCEEDED` and `DEAD_LETTERED` are terminal states for automatic processing.

### Maximum attempts

Use the unambiguous setting `maximum_attempts`. The initial request counts as attempt one.

```text
maximum_attempts = 3

Attempt 1: initial request
Attempt 2: first retry
Attempt 3: second retry
```

If attempt 3 fails, the delivery becomes `DEAD_LETTERED`. There is no automatic attempt 4.

`maximum_retries = 3` would mean one initial request plus three retries, producing four total
attempts. RelayKit avoids this wording.

## 5. Retryable and permanent failures

Not every failure should be retried.


| Result             | Likely meaning                      | Initial policy                                |
| ------------------ | ----------------------------------- | --------------------------------------------- |
| HTTP `2xx`         | Request succeeded                   | `SUCCEEDED`                                   |
| HTTP `503`         | Service temporarily unavailable     | Retry                                         |
| Timeout            | Endpoint may be slow or unavailable | Retry                                         |
| Connection refused | Endpoint temporarily unreachable    | Retry                                         |
| HTTP `429`         | Too many requests                   | Retry and respect `Retry-After` when valid    |
| HTTP `400`         | Invalid request                     | Usually permanent                             |
| HTTP `401`         | Authentication or signature problem | Usually permanent until configuration changes |
| HTTP `404`         | URL may be incorrect                | Usually permanent                             |


A delivery becomes dead-lettered when either:

```text
Maximum attempts are exhausted
             OR
A permanent failure is detected
```

Exact classification rules will be designed and tested during retry implementation.

## 6. Synchronous ingestion and asynchronous delivery



### Synchronous work

Synchronous work happens before the API returns `202 Accepted`:

```text
Validate request
      ↓
Authenticate producer
      ↓
Find matching subscriptions
      ↓
Store event and delivery responsibilities durably
      ↓
Return 202 Accepted
```

Subscription matching happens during ingestion so the recipients are based on the subscription set
that existed when the event was accepted.

Creating a delivery record means remembering future work. It does not mean making an HTTP request.

### Asynchronous work

```text
Queue delivery work
      ↓
Worker receives work
      ↓
Worker sends webhook
      ↓
Record attempt
      ↓
Complete, retry, or dead-letter delivery
```

The producer can disconnect after receiving `202`; delivery continues on the hosted platform.

### Meaning of `202 Accepted`

`202` means:

> RelayKit durably accepted responsibility for processing the event asynchronously.

It does not mean:

- RabbitMQ already received every message.
- A worker already started.
- A webhook already succeeded.
- Every endpoint will eventually succeed.
- An external receiver will process the event exactly once.



### Latency categories

Ingestion latency:

```text
API receives request → API returns 202
```

Queue-to-attempt latency:

```text
Delivery accepted → first webhook attempt begins
```

Webhook-attempt latency:

```text
HTTP request begins → response or timeout
```

A slow destination should increase delivery latency, not ingestion latency.

## 7. Database transaction

A transaction groups database operations into an all-or-nothing unit.

```text
BEGIN TRANSACTION

Insert event
Insert Accounting delivery
Insert Analytics delivery

COMMIT
```

If every operation succeeds, `COMMIT` makes them durable. If any operation fails, `ROLLBACK`
discards all changes from that transaction.

Valid outcomes:

```text
All records stored
       OR
No records stored
```

Invalid partial state to prevent:

```text
Event stored
Accounting delivery stored
Analytics delivery missing
```

RelayKit returns `202` only after the required transaction commits.

The payment may still have occurred in the producer's system if RelayKit fails. What failed is
RelayKit's acceptance of the event, not the payment itself.

## 8. High-level architecture

```text
Producer Application                         Developer
        |                                        |
        | HTTPS                                  | CLI command
        v                                        v
                 ┌─────────────────────────┐
                 │      FastAPI API        │
                 └────────────┬────────────┘
                              |
                              | durable transaction
                              v
                 ┌─────────────────────────┐
                 │      PostgreSQL         │
                 │ events, deliveries,     │
                 │ attempts, outbox        │
                 └────────────┬────────────┘
                              |
                              | due publication records
                              v
                 ┌─────────────────────────┐
                 │   Outbox Publisher      │
                 └────────────┬────────────┘
                              |
                              | confirmed publication
                              v
                 ┌─────────────────────────┐
                 │       RabbitMQ          │
                 └────────────┬────────────┘
                              |
                              | delivery message
                              v
                 ┌─────────────────────────┐
                 │    Delivery Workers     │──────> Redis
                 └────────────┬────────────┘        temporary coordination
                              |
                              | signed HTTP webhook
                              v
                 Customer Webhook Endpoint
```



### Component responsibilities


| Component        | Primary responsibility                                          |
| ---------------- | --------------------------------------------------------------- |
| FastAPI API      | Validate, authenticate, ingest, and expose read/inspection APIs |
| PostgreSQL       | Store authoritative permanent state                             |
| Outbox publisher | Transfer committed publication intent to RabbitMQ               |
| RabbitMQ         | Distribute active delivery work to workers                      |
| Delivery worker  | Perform webhook attempts and record outcomes                    |
| Redis            | Coordinate temporary endpoint limits across workers             |
| CLI              | Control the platform through the HTTP API                       |


Inspection APIs are read endpoints such as:

```text
GET /v1/deliveries/{delivery_id}
GET /v1/events/{event_id}
```

They let the CLI or a future dashboard inspect state without connecting directly to PostgreSQL.

### PostgreSQL, RabbitMQ, and Redis ownership


| PostgreSQL            | RabbitMQ                           | Redis                              |
| --------------------- | ---------------------------------- | ---------------------------------- |
| Events                | Active delivery messages           | Concurrency leases                 |
| Deliveries            | Unacknowledged worker work         | Rate-limit counters                |
| Attempts              | Technical dead-letter messages     | Circuit-breaker state              |
| Outbox records        | Routing and work distribution      | Temporary endpoint health          |
| Accounts and API keys | Not authoritative business history | Not authoritative business history |




## 9. Modules, packages, processes, and microservices

- **Module:** generally one Python file, such as `models.py`.
- **Package:** a directory containing related importable modules, such as `relaykit.worker`.
- **Process:** a running program with its own memory, managed by the operating system.
- **Microservice:** an independently operated service with a strong API, ownership, deployment, and
usually data-ownership boundary.

RelayKit is one modular Python codebase with independently runnable processes:

```text
One Git repository
└── relaykit Python package
    ├── API process
    ├── Outbox-publisher process
    ├── Worker process(es)
    └── CLI process
```

This is not a collection of endpoint, subscription, event, and delivery microservices. Those domain
objects participate in the same workflow and database transactions, so separating them now would
add network failures without a useful ownership boundary.

## 10. Concurrency model

RelayKit plans to use multiple worker processes with asynchronous I/O tasks inside each process:

```text
Worker process A
└── asyncio event loop
    ├── Delivery task 1
    ├── Delivery task 2
    └── Delivery task 3

Worker process B
└── asyncio event loop
    ├── Delivery task 4
    ├── Delivery task 5
    └── Delivery task 6
```

- Threads inside one process share memory.
- Separate processes have separate memory.
- An ordinary Python thread lock cannot coordinate separate worker processes.
- PostgreSQL and Redis provide coordination across workers.

Thread-safe and atomic are not synonyms:

- **Thread-safe:** safe for concurrent threads that share process memory.
- **Atomic:** an operation appears to occur completely or not at all, without another operation
observing an intermediate state.

For delivery claiming, the combined state check and transition must be atomic across all workers:

```text
Change QUEUED → DELIVERING
only if the current status is still QUEUED
```



## 11. Failure map

For every boundary, ask:

1. What durable state exists before the operation?
2. What durable state exists afterward?
3. Can the operation safely repeat?
4. What happens if the process crashes halfway through?
5. How is unfinished work discovered?

```text
Producer → API → PostgreSQL → Publisher → RabbitMQ → Worker → Endpoint
```



### 11.1 API crashes before database commit

The request exists only in temporary API memory. Nothing is durably accepted, and RelayKit must not
return `202`. The producer observes an error, timeout, or disconnect and retries later.

**Guarantee:** no `202` is returned for work that was never stored.

### 11.2 API crashes after commit but before returning `202`

The event and deliveries remain in PostgreSQL, but the producer does not know the request succeeded.
It retries using the same idempotency key.

```text
Same key + same payload      → return original event
Same key + different payload → 409 Conflict
```

PostgreSQL will enforce a uniqueness rule such as:

```text
UNIQUE(account_id, idempotency_key)
```

A separate check followed by an insert is not enough because concurrent requests can race.

### 11.3 PostgreSQL commits but RabbitMQ never receives work

Naive dual write:

```text
1. Store event and deliveries in PostgreSQL
2. Publish delivery work to RabbitMQ
```

If RelayKit crashes between the steps, the delivery exists but no worker knows about it. This is the
database-broker dual-write problem.

#### Transactional outbox

The API stores everything in one PostgreSQL transaction:

```text
Event
├── Accounting delivery
│   └── Accounting outbox record
└── Analytics delivery
    └── Analytics outbox record
```

An outbox record means:

> This delivery still needs to be published to RabbitMQ.

The outbox publisher finds unpublished rows, sends their delivery IDs to RabbitMQ, waits for broker
confirmation, and marks the rows published.

Analogy:

```text
Event      = original order
Delivery   = package for one destination
Outbox     = durable pickup tray
RabbitMQ   = transportation network
Worker     = delivery driver
```



### 11.4 Outbox publisher crashes around publication

Publisher sequence:

```text
Read unpublished row
      ↓
Publish to RabbitMQ
      ↓
Receive publisher confirmation
      ↓
Mark row published
```

If it crashes before publishing, the row remains unpublished and can be retried.

If it crashes after RabbitMQ accepts the message but before PostgreSQL is updated, the row may be
published again. Duplicate RabbitMQ messages are therefore expected.

This is one reason RelayKit provides at-least-once delivery rather than exactly-once delivery.

### 11.5 Duplicate messages and atomic claiming

If a delivery is already `SUCCEEDED` or `DEAD_LETTERED`, the worker skips the HTTP request and
acknowledges the duplicate message.

A status read alone is insufficient:

```text
Worker A reads QUEUED
Worker B reads QUEUED
Both send the webhook
```

The check and claim must be one atomic operation so only one worker changes:

```text
QUEUED → DELIVERING
```



### 11.6 RabbitMQ consumer acknowledgement

An acknowledgement means the worker tells RabbitMQ:

> This message was handled safely and may be removed.

```text
RabbitMQ sends message
      ↓
Worker performs delivery work
      ↓
Worker commits the outcome to PostgreSQL
      ↓
Worker acknowledges the message
```

If the worker disconnects before acknowledgement, RabbitMQ can redeliver the message.

- Publisher confirmation: RabbitMQ tells the publisher it accepted a message.
- Consumer acknowledgement: the worker tells RabbitMQ it safely handled a message.



### 11.7 Endpoint succeeds but worker crashes before recording success

The endpoint may have processed the request, but PostgreSQL still shows an unfinished delivery.
After redelivery, another worker may send the HTTP request again.

RelayKit cannot atomically combine an external HTTP side effect with a PostgreSQL commit. It sends
stable identifiers so receivers can deduplicate repeated requests:

```http
X-Relay-Event-Id: evt_123
X-Relay-Delivery-Id: del_456
X-Relay-Attempt: 2
```

**Guarantee:** at-least-once transport with stable identities, not exactly-once processing inside an
external application.

### 11.8 RabbitMQ is unavailable

The API can continue accepting work while PostgreSQL has safe capacity because unpublished outbox
rows remain durable. The publisher retries with controlled delay, workers eventually become idle,
and read APIs may remain available.

After recovery, the publisher sends the backlog in controlled batches.

A long outage grows the outbox table, so RelayKit needs backpressure. It may reject new ingestion
with `503` before storage capacity becomes unsafe.

**Guarantee:** work that already received `202` remains durably recorded.

### 11.9 PostgreSQL is unavailable

PostgreSQL is authoritative, so RelayKit cannot safely accept new events.

- API returns `503`, never `202`.
- Outbox publisher pauses because it cannot claim or update rows.
- Workers must not acknowledge messages whose outcomes cannot be recorded.
- Consumers should pause or retry carefully rather than creating a rapid requeue loop.

Health terminology:

- **Liveness:** is the process running?
- **Readiness:** can it safely perform its responsibility?

During a PostgreSQL outage, a process may be live but not ready.

### 11.10 Redis responsibility and failure

Redis will be present in local infrastructure early, but its application responsibilities grow only
when the motivating features are implemented:

```text
Initial infrastructure → connectivity and health
Concurrency phase      → endpoint concurrency leases
Rate-limit phase       → request-rate counters
Circuit phase          → shared circuit state
```

Redis is never the only store for events, deliveries, attempts, or outbox records.

#### Concurrency slot

A slot is logical permission to start one HTTP request. If Accounting permits three concurrent
requests, at most three unfinished Accounting requests may hold slots.

Multiple worker processes cannot coordinate this with private in-memory counters. Redis gives them a
shared atomic view.

#### Circuit breaker

A circuit breaker temporarily stops requests to an unhealthy endpoint:

```text
CLOSED    → requests allowed
OPEN      → requests temporarily blocked
HALF_OPEN → limited recovery probe
```

Redis can share this temporary state across workers.

If Redis is unavailable, the conservative policy is to let existing requests finish but defer new
outbound webhook attempts. Deferral is not an attempt because no HTTP request occurred.

**Guarantee:** Redis failure may increase delivery latency, but it does not erase accepted work or
knowingly violate endpoint-protection limits.

### 11.11 Destination endpoint is unavailable

After every HTTP request, the worker records an attempt and classifies its result.

```text
Success                           → SUCCEEDED
Permanent failure                 → DEAD_LETTERED
Retryable + attempts remain       → RETRY_SCHEDULED
Retryable + no attempts remaining → DEAD_LETTERED
```



#### Exponential backoff and jitter

Example:

```text
Attempt 1 fails → wait about 5 seconds
Attempt 2 fails → wait about 10 seconds
Attempt 3 fails → wait about 20 seconds
Attempt 4 fails → DEAD_LETTERED
```

Jitter adds small random variation so many deliveries do not retry simultaneously.

The worker should not keep thousands of sleeping tasks. It records a durable future publication:

```text
Record failed attempt
      ↓
Set RETRY_SCHEDULED
      ↓
Create outbox record with available_at
      ↓
Commit PostgreSQL transaction
      ↓
Acknowledge current RabbitMQ message
```

When `available_at` arrives, the publisher sends the delivery to RabbitMQ again.

### 11.12 Worker crashes after claiming a delivery

The delivery could remain stuck in `DELIVERING` after its worker disappears. RelayKit uses temporary
ownership:

```text
status: DELIVERING
claimed_by: worker_7
lease_expires_at: 10:05:00
```

While the lease is valid, another worker must not process the delivery. If the owner crashes, the
lease expires and another worker may reclaim it. A healthy worker may renew a lease during long
processing.

- RabbitMQ redelivers unacknowledged work.
- PostgreSQL protects business state.
- The lease permits recovery from abandoned ownership.

**Guarantee:** a crashed worker cannot permanently own a delivery.

### 11.13 Malformed or poison RabbitMQ message

The worker may expect:

```json
{
  "schemaVersion": 1,
  "deliveryId": "del_123"
}
```

Invalid JSON, a missing delivery ID, or an unsupported version will not become valid by repeatedly
requeueing it. Such a permanently failing message is a poison message.

```text
Main queue
    |
    | invalid permanent message
    v
Technical dead-letter queue
```

Two distinct meanings:

- Business dead-letter: a webhook delivery exhausted its policy; stored in PostgreSQL.
- Technical dead-letter: a broker message could not be processed; stored in a RabbitMQ DLQ.

**Guarantee:** a permanently invalid broker message does not loop forever and starve healthy work.

### 11.14 Graceful shutdown

A planned shutdown should stop taking new work, finish safe in-flight work when possible, and leave
unfinished work recoverable.

API:

```text
Mark unready → stop new requests → finish active transactions → close resources → exit
```

Worker:

```text
Stop consuming → finish in-flight deliveries → commit → acknowledge → close → exit
```

Publisher:

```text
Stop claiming → finish or release batch → close resources → exit
```

If the grace period expires, RabbitMQ redelivers unacknowledged messages and processing leases
eventually expire.

The exact signals, grace periods, connection order, and forced-timeout behavior are intentionally
deferred until implementation.

## 12. Current guarantees and non-guarantees

Planned guarantees:

- `202` only after required durable state commits.
- Accepted delivery work remains discoverable during RabbitMQ outages.
- Producer retries do not create another logical event.
- Duplicate broker messages do not corrupt internal delivery state.
- Worker crashes leave unacknowledged work recoverable.
- Retries are durable rather than in-memory timers.
- PostgreSQL remains authoritative when Redis is unavailable.

Explicit non-guarantees:

- RelayKit cannot guarantee exactly-once processing inside an external application.
- Temporary dependency outages may increase latency.
- `202` does not promise that every destination will eventually return success.
- The system does not have unlimited backlog capacity.



## 13. First vertical slice

The first implementation proves one complete path:

```text
Create endpoint
      ↓
Create subscription
      ↓
Submit event
      ↓
Store event and delivery
      ↓
Publish delivery work
      ↓
Worker sends webhook
      ↓
Record attempt and result
      ↓
Inspect delivery through CLI
```

Initial inclusion:

- One development account without authentication
- Endpoint and subscription creation
- Event ingestion
- PostgreSQL event and delivery records
- RabbitMQ message
- One worker and one attempt
- Success or terminal failure
- Basic CLI and development receiver
- One end-to-end integration test

Temporarily excluded from the learning slice:

- Idempotency
- Transactional outbox
- Retries
- Redis endpoint controls
- Circuit breaker
- API-key authentication and tenant isolation
- HMAC signatures
- Hosted deployment

The direct database/RabbitMQ gap is deliberately temporary and must be replaced before deployment.
Redis can exist in local infrastructure from the beginning, but it does not gain correctness or
coordination responsibilities until those features are taught and implemented.

## 14. Ten-minute revision checklist

At the beginning of the next session, explain these without reading first:

1. Event versus delivery versus attempt.
2. What `202 Accepted` guarantees and does not guarantee.
3. Synchronous ingestion versus asynchronous delivery.
4. Why events and deliveries need an all-or-nothing transaction.
5. API, PostgreSQL, publisher, RabbitMQ, worker, Redis, and CLI responsibilities.
6. Publisher confirmation versus consumer acknowledgement.
7. Why the transactional outbox prevents stranded accepted work.
8. Why duplicate publication is still possible.
9. Atomic delivery claim versus an ordinary status check.
10. Why RelayKit promises at-least-once rather than exactly-once HTTP processing.

pydantic-settings
└── Reads and validates DATABASE_URL

SQLAlchemy
├── Models and queries
├── AsyncSession
├── Transactions
└── Connection pool

asyncpg
└── Communicates with PostgreSQL

Alembic
└── Tracks and applies schema changes

PostgreSQL
└── Stores authoritative data

Docker
└── Runs PostgreSQL in an isolated local container

The general architecture used by many backends is:

```
Application - FastAPI
    ↓
ORM or query library    - SQL alchemy
    ↓ 
Database driver -       asyncpg
    ↓
Database server -       PostgreSQL
```

What happens during one API request?
1. Uvicorn receives an HTTP request.
2. FastAPI selects the route handler.
3. FastAPI creates one AsyncSession for that request.
4. The session requests a connection from the engine’s pool.
5. SQLAlchemy creates the SQL statement.
6. asyncpg sends it through localhost:55433.
7. Docker forwards it to container port 5432.
8. PostgreSQL executes it.
9. asyncpg receives the result.
10. SQLAlchemy converts the result into Python data.
11. The transaction commits or rolls back.
12. The session returns the connection to the pool.
13. FastAPI returns the HTTP response.
Returning the connection to the pool normally does not close it. It keeps the connection ready for another request.

## 15. Concepts: Pydantic schemas and aliases

RelayKit uses two different kinds of models:

```text
Pydantic schema
└── Validates and translates data at the API boundary

SQLAlchemy model
└── Represents a database table and persists rows in PostgreSQL
```

Pydantic calls its classes models, but these notes call them **schemas** to distinguish them from
SQLAlchemy database models.

### Why aliases are needed

The public JSON API uses camelCase, while Python and PostgreSQL use snake_case:

```text
Public JSON     Python and PostgreSQL
endpointId  ↔   endpoint_id
eventType   ↔   event_type
```

An alias connects these two names without creating two separate fields:

```python
# `endpoint_id` is the internal Python field name.
# `alias="endpointId"` maps the public camelCase JSON key to it.
endpoint_id: str = Field(alias="endpointId")
```

There is still only one logical field. The client uses `endpointId`, while application code uses
`request.endpoint_id`.

### Complete request-to-response example

The client sends:

```json
{
  "endpointId": "ep_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "eventType": "payment.completed"
}
```

The request schema validates the JSON and translates its aliases:

```python
class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    endpoint_id: str = Field(
        alias="endpointId",
        pattern=r"^ep_[0-9a-f]{32}$",
    )
    event_type: str = Field(
        alias="eventType",
        min_length=1,
        max_length=100,
    )
```

After validation, the route uses normal Python names:

```python
request.endpoint_id
request.event_type
```

It creates a SQLAlchemy object, which also uses snake_case:

```python
subscription = Subscription(
    id="sub_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    endpoint_id=request.endpoint_id,
    event_type=request.event_type,
)
```

The response schema can read that SQLAlchemy object:

```python
class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
    )

    id: str
    endpoint_id: str = Field(alias="endpointId")
    event_type: str = Field(alias="eventType")
```

The configuration means:

- `from_attributes=True`: Pydantic may read values from object attributes such as
  `subscription.endpoint_id`, rather than requiring only a dictionary.
- `validate_by_name=True`: Pydantic may read the internal Python names `endpoint_id` and
  `event_type`. This is needed because `alias` affects validation as well as serialization.
- `alias="endpointId"`: FastAPI can serialize the public response field as `endpointId`.

FastAPI returns:

```json
{
  "id": "sub_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "endpointId": "ep_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "eventType": "payment.completed"
}
```

The complete lifecycle is:

```text
Incoming camelCase JSON
        ↓ request alias translation and validation
Python request fields in snake_case
        ↓ create and save SQLAlchemy object
Database attributes in snake_case
        ↓ from_attributes + validate_by_name
Pydantic response fields in snake_case
        ↓ FastAPI serializes aliases
Outgoing camelCase JSON
```

If a route has `response_model=SubscriptionResponse`, a returned SQLAlchemy object or dictionary
is validated by Pydantic before FastAPI sends it. Without a response model, a raw dictionary is
normally returned with the exact keys supplied by the route.

### Alias variants

```text
alias                 Input and output name
validation_alias      Input name only
serialization_alias   Output name only
```

For a response-only schema, `serialization_alias="endpointId"` is another valid design. It affects
only output and therefore may remove the need for `validate_by_name=True`. RelayKit's current schema
uses `alias` together with `validate_by_name=True`, which is also valid.

### Revision rule

```text
Keep Python and PostgreSQL names in snake_case.
Use Pydantic aliases for the public camelCase API contract.
```

## 16. Structured logging and request correlation

> **Goal:** Make RelayKit's behavior understandable when many requests run concurrently, without
> exposing secrets or tying the application directly to a logging vendor.

### 16.1 Why `print()` is insufficient

```python
print("Event accepted")
```

This produces text, but it does not provide a standard severity, source logger, structured fields,
filtering, request correlation, or reliable exception stack trace.

Python logging instead produces a `LogRecord` that can be filtered, enriched, formatted, and sent
to a selected destination.

### 16.2 Python logging pipeline

```text
Application calls logger.info(...)
        ↓
Named Logger creates a LogRecord
        ↓
Logger/handler level checks
        ↓
Filter may enrich or reject the record
        ↓
Handler chooses the destination
        ↓
Formatter converts the record to JSON
        ↓
Handler writes to stdout
        ↓
Terminal today; collector and log storage later
```

The responsibilities are:

| Part | Responsibility |
|---|---|
| Logger | Entry point that creates and routes a logging event |
| LogRecord | In-memory representation of the event and its fields |
| Level | Severity such as `INFO`, `WARNING`, or `ERROR` |
| Filter | Rejects a record or adds context such as `requestId` |
| Handler | Selects the destination, initially stdout |
| Formatter | Converts the accepted record into structured JSON |

`INFO` is a severity, not the identity of the event:

```python
logger.info(
    "Event accepted",
    extra={
        "event": "event_accepted",
        "event_id": "evt_123",
        "delivery_count": 2,
    },
)
```

```text
INFO             How important is it?
event_accepted   What happened?
Event accepted   How do we describe it to a human?
```

### 16.3 Central configuration and named loggers

RelayKit configures logging once. Each module still requests its own named logger:

```python
logger = logging.getLogger(__name__)
```

Example hierarchy:

```text
Python root logger
└── relaykit
    └── relaykit.api
        └── relaykit.api.routes
            └── relaykit.api.routes.events
```

The hierarchy is based on dot-separated logger names. Python is not walking repository directories,
although `__name__` naturally produces names matching the package structure.

Child modules do not create their own console handlers. Records propagate to the centrally
configured RelayKit handler. This avoids inconsistent formats and duplicate log lines.

### 16.4 Request lifecycle and middleware order

Custom middleware begins before Pydantic request validation:

```text
Client sends request
        ↓
Uvicorn accepts HTTP
        ↓
Request middleware starts
        ├── validates or generates request ID
        ├── stores it in ContextVar
        └── starts monotonic timer
        ↓
Routing, dependencies, and Pydantic validation
        ↓
Route and database work
        ↓
Response validation and serialization
        ↓
Request middleware resumes
        ├── adds X-Request-ID response header
        ├── records status and duration
        └── clears request context
        ↓
Uvicorn sends response
```

Because middleware starts first, even a `404`, `409`, or `422` response can be correlated with a
request ID. Generating the ID only inside a route would miss requests that never reach that route.

### 16.5 Why use `ContextVar`?

A normal global variable is unsafe when requests overlap:

```text
Request A stores req_A globally
Request B overwrites it with req_B
Request A logs again and incorrectly uses req_B
```

A `ContextVar` associates the request ID with the current asynchronous execution context:

```text
Request A task → req_A
Request B task → req_B
```

The middleware must reset the context on success and failure so it cannot leak into later work.

### 16.6 Incoming request IDs are untrusted

The client may send:

```http
X-Request-ID: client-request-123
```

RelayKit reuses it only when it satisfies a small allowed-character and length policy. Otherwise,
RelayKit generates:

```text
req_<UUID version 4 hex>
```

This prevents control characters or excessively long values from corrupting logs and responses.

### 16.7 Initial JSON record

```json
{
  "timestamp": "2026-11-04T10:30:15.125Z",
  "level": "INFO",
  "service": "relaykit-api",
  "environment": "development",
  "logger": "relaykit.api.middleware.request_logging",
  "event": "http_request_completed",
  "message": "HTTP request completed",
  "requestId": "req_abc123",
  "method": "POST",
  "path": "/v1/events",
  "statusCode": 202,
  "durationMs": 18.42
}
```

Do not log complete request bodies, event data, authorization headers, API keys, webhook secrets,
database credentials, query strings, or arbitrary endpoint responses.

### 16.8 Current and future architecture

Current development setup:

```text
relaykit-api
    ↓ structured JSON
stdout
    ↓
terminal
```

Future production setup:

```text
API / publisher / worker
        ↓ structured JSON to stdout
container runtime
        ↓
collector
        ↓
Loki or another log store
        ↓
Grafana
```

The application does not initially write rotating files or send logs directly to a vendor. A slow
or unavailable logging backend must not become part of the HTTP correctness path.

### 16.9 Simple production trade-off

Structured stdout logging is portable, searchable, and compatible with containers. The cost is that
JSON is less pleasant to read directly, logging has runtime/storage cost, excessive fields create
noise and privacy risk, and stdout is not durable until a collector stores it elsewhere.

A request ID connects logs for one HTTP request. It is not a distributed trace. OpenTelemetry trace
IDs will later connect API, outbox, RabbitMQ, worker, database, and outgoing webhook operations.

### 16.10 Interview summary

> RelayKit uses centrally configured Python logging. Each module emits through a named child logger.
> Records propagate to an application handler, where a request-context filter enriches them from a
> `ContextVar`; a JSON formatter serializes them to stdout. Request middleware establishes the
> correlation ID before Pydantic validation, measures duration, adds the ID to responses, and clears
> context afterward. Containers can later forward the same stdout records to a collector and Loki
> without coupling route code to a logging vendor.

### 16.11 Revision questions

1. What is the difference between a logger, handler, filter, and formatter?
2. Why does middleware create the request ID before Pydantic validation?
3. Why is a global variable unsafe for request context?
4. Why must incoming request IDs be validated?
5. Why does RelayKit write to stdout instead of application-managed files?
6. What can a request ID correlate, and what still requires distributed tracing?

### 16.12 Concrete request path versus route template

Suppose RelayKit registers:

```python
router = APIRouter(prefix="/v1/deliveries")


@router.get("/{delivery_id}")
async def inspect_delivery(delivery_id: str):
    ...
```

The registered route template is:

```text
/v1/deliveries/{delivery_id}
```

A client sends a concrete request:

```http
GET /v1/deliveries/del_123
```

The lifecycle is:

```text
Uvicorn creates the HTTP ASGI scope
    path = /v1/deliveries/del_123
        ↓
Request middleware calls call_next(request)
        ↓
Starlette matches the concrete path against:
    /v1/deliveries/{delivery_id}
        ↓
FastAPI extracts:
    request.path_params["delivery_id"] = "del_123"
        ↓
Starlette associates the matched route object with request.scope
        ↓
The route executes and produces a response
        ↓
call_next returns to middleware
        ↓
Middleware reads request.scope["route"].path
        ↓
Access log records:
    /v1/deliveries/{delivery_id}
```

The middleware does not change routing, the extracted ID, business logic, or response. It changes
only the access-log representation.

```text
Concrete path used for routing:
    /v1/deliveries/del_123

Generalized template used in access log:
    /v1/deliveries/{delivery_id}
```

The template groups all delivery-inspection requests, avoids automatically logging unique resource
IDs, and prevents high-cardinality path dimensions in future metrics. An intentional domain log can
still include `deliveryId` when that identifier is actually needed.

For an unmatched request such as `/does-not-exist`, there is no matched route object. The middleware
therefore falls back to `request.url.path` and records `/does-not-exist` with status `404`.

### 16.13 WSGI and ASGI

WSGI and ASGI are interface specifications between a Python web server and a Python web
application. They are not frameworks and they are not databases.

#### WSGI — Web Server Gateway Interface

WSGI defines a synchronous request/response interface:

```text
Client
    ↓
WSGI server
    ↓ calls synchronous application
Python web application
    ↓ returns response bytes
WSGI server
    ↓
Client
```

Conceptual WSGI callable:

```python
def application(environ, start_response):
    ...
    return [b"response body"]
```

`environ` contains request information. `start_response` starts the HTTP response. The callable is
synchronous: while it waits on blocking work, that worker/thread cannot process another request.
Concurrency is normally achieved using multiple processes, threads, or additional runtime
techniques. WSGI was designed primarily for traditional HTTP request/response applications and does
not natively model WebSocket connections.

#### ASGI — Asynchronous Server Gateway Interface

ASGI defines an asynchronous, event-based interface:

```text
Client
    ↓
ASGI server such as Uvicorn
    ↓ calls async application
FastAPI/Starlette ASGI application
    ↓ awaits I/O and sends ASGI response events
ASGI server
    ↓
Client
```

Conceptual ASGI callable:

```python
async def application(scope, receive, send):
    ...
```

The three arguments are:

```text
scope
    Connection/request metadata such as protocol type, method, path, and headers.

receive
    Async function used to receive request-body or disconnect events.

send
    Async function used to send response-start and response-body events.
```

ASGI supports HTTP, WebSocket, and application lifespan events. During network I/O, an ASGI task can
`await`, allowing the event loop to run other tasks on the same thread.

RelayKit's current relationship is:

```text
Postman/client
    ↓ HTTP
Uvicorn
    ASGI server: accepts network connections
        ↓ ASGI scope/receive/send
FastAPI/Starlette
    ASGI application: middleware, routing, validation, dependencies, routes
        ↓
RelayKit business and database logic
```

FastAPI's function-style middleware provides the higher-level `Request` and `call_next` abstraction,
so RelayKit does not directly manipulate raw `receive` and `send` messages yet.

ASGI does not automatically make all code non-blocking. Blocking database, HTTP, file, sleep, or
CPU-heavy work inside an async route can still block the event-loop thread. RelayKit must use async
drivers for I/O, move delivery work to workers, bound concurrency, and move CPU-heavy work to
appropriate processes or services.

#### What if RelayKit did not use Uvicorn?

FastAPI creates an ASGI application object, but it does not normally open a TCP port, accept network
connections, parse HTTP bytes, or drive the ASGI lifecycle by itself. Without Uvicorn, RelayKit
would still need another ASGI-compatible server or platform runtime.

```text
No ASGI server
    ↓
FastAPI app object can be imported or called in-process
    ↓
Nothing listens on http://127.0.0.1:8000
```

Possible architecture with a different server:

```text
Client
    ↓
Another ASGI server
    ↓ scope / receive / send
FastAPI application
```

Nginx and Docker do not replace an ASGI server:

```text
Nginx/load balancer
    reverse proxy and optional TLS termination
        ↓
ASGI server
    runs the network/application interface
        ↓
FastAPI

Docker
    packages and runs the ASGI-server process
```

A traditional WSGI-only server cannot directly provide FastAPI's complete ASGI behavior without an
adapter, and an adapter can limit async, WebSocket, streaming, lifespan, cancellation, or disconnect
behavior.

Tests may call the FastAPI ASGI application through an in-process ASGI transport without opening a
real network port. That verifies application behavior but does not replace end-to-end testing of the
deployed ASGI server.

Do not confuse `uv` and Uvicorn:

```text
uv
    Manages the Python project, dependencies, environment, and command execution.

Uvicorn
    Opens the network port and hosts the FastAPI ASGI application.

FastAPI
    Defines middleware, routes, validation, dependencies, and responses.
```

In this command:

```bash
uv run uvicorn relaykit.api.main:app
```

`uv run` launches a command inside RelayKit's managed environment. `uvicorn` is the command that
serves HTTP. `relaykit.api.main:app` identifies the FastAPI application object.

#### Short comparison

| Topic | WSGI | ASGI |
|---|---|---|
| Application callable | Synchronous | Asynchronous |
| Main shape | `application(environ, start_response)` | `application(scope, receive, send)` |
| HTTP | Yes | Yes |
| WebSocket model | Not native | Native |
| Lifespan events | Not part of WSGI | Supported |
| I/O concurrency | Usually workers/threads or other techniques | Async event-loop tasks |
| RelayKit | Not used for the FastAPI app | Uvicorn and FastAPI use ASGI |

#### Interview revision

1. What problem do WSGI and ASGI solve between a Python server and application?
2. What are `scope`, `receive`, and `send` in ASGI?
3. What is the difference between Uvicorn and FastAPI?
4. What would happen if RelayKit imported `app = FastAPI()` without running an ASGI server?
5. Why do Nginx and Docker not replace Uvicorn?
6. Why does ASGI support I/O concurrency but not automatically make blocking code non-blocking?
7. How does a concrete path become a generalized route template in the access log?
8. What is the difference between `uv` and Uvicorn in `uv run uvicorn ...`?
