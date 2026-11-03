# FastAPI and Python Backend Interview Track

**Last updated:** October 30, 2026

This is a cross-cutting learning track for RelayKit. It exists because this is the learner's first
backend-heavy Python project and first serious FastAPI application. We will not memorize framework
syntax in isolation. Each concept must be connected to a request lifecycle, a failure, a test, and
an interview-quality explanation.

## How to study each FastAPI concept

For every concept, be able to answer five questions:

1. What does it do in plain language?
2. Where does RelayKit use it?
3. What happens without it or when it is misused?
4. How do we test or measure it?
5. What trade-off would I explain in an interview?

## 1. Request lifecycle and ASGI foundation

Learn the path of one request:

```text
Client
  -> TCP/HTTP connection
  -> Uvicorn ASGI server
  -> FastAPI middleware
  -> route matching
  -> dependency resolution
  -> Pydantic request validation
  -> route function
  -> SQLAlchemy session/transaction
  -> response-model validation and serialization
  -> HTTP response
```

### Concepts

- **ASGI:** the interface between an asynchronous Python web server and the web application.
- **Uvicorn:** the server process that accepts network connections and invokes the FastAPI ASGI app.
- **FastAPI application:** owns routes, middleware, exception handlers, OpenAPI configuration, and
  application lifespan hooks.
- **Path operation:** FastAPI's term for a route function associated with an HTTP method and path.
- **Routing:** selecting the function that handles a request such as `POST /v1/events`.
- **Request lifecycle:** everything that happens from receiving the request until the response is
  sent and resources are released.

### RelayKit evidence

- Explain how `POST /v1/events` reaches `publish_event`.
- Identify which failures return `422`, `404`, `409`, `500`, or `202`.
- Trace when the database session is created and closed.

### Interview questions

- What is the difference between FastAPI and Uvicorn?
- What is ASGI, and how does it differ conceptually from WSGI?
- What happens before a FastAPI route function runs?
- Why can an ASGI server handle other I/O while one request is awaiting the database?

## 2. Pydantic and API contracts

### Concepts

- Request models and boundary validation.
- Response models and output filtering/serialization.
- Field aliases for external camelCase and internal snake_case.
- `model_config`, `from_attributes`, and validation by field name.
- Strict versus coercing validation.
- Nested models, enums, constrained fields, custom validators, and schema evolution.
- Difference between a Pydantic API schema and a SQLAlchemy persistence model.

### RelayKit evidence

- `EndpointCreate`, `SubscriptionCreate`, and `EventPublishRequest` validate request boundaries.
- Response schemas prevent returning an arbitrary ORM object shape.
- Invalid input is rejected before the route performs database work.

### Interview questions

- Why keep Pydantic schemas separate from SQLAlchemy models?
- What is the difference between validation and database constraints?
- Why is a database unique constraint still required when Pydantic validates a request?
- What does `response_model` protect?

## 3. Dependency injection and resource lifecycles

### Concepts

- `Depends` declares a value that FastAPI must construct before calling the route.
- Generator dependencies using `yield` divide setup from cleanup.
- One `AsyncSession` per request/task; never share one session across concurrent tasks.
- Dependency caching within one request.
- Dependency overrides for tests.
- Lifespan hooks for process-wide resources such as HTTP clients and broker connections.
- Request-scoped versus process-scoped resources.

### Important distinction

```text
Request-scoped
  database session, authenticated account, correlation ID

Process-scoped
  SQLAlchemy engine/pool, HTTPX client, RabbitMQ connection, telemetry provider
```

### Interview questions

- Why is the engine process-wide but the session request-scoped?
- What executes before and after `yield` in a FastAPI dependency?
- How do dependency overrides make tests easier?
- Why should an HTTP client usually be reused rather than created for every request?

## 4. Async Python in FastAPI

### Concepts

- Coroutines, the event loop, tasks, and cooperative scheduling.
- `async def` does not automatically make work non-blocking.
- `await` is useful when the called operation can yield control during I/O.
- Blocking calls inside an async route can stall the event-loop thread.
- Async database drivers such as `asyncpg` and async HTTP clients such as HTTPX.
- Bounded concurrency with semaphores and queues.
- Cancellation, timeouts, cleanup, and graceful shutdown.
- Multiple processes versus threads versus async tasks.

### Misuse to recognize

```text
async route + blocking database/HTTP/file/CPU call
        -> event loop is blocked
        -> unrelated requests wait
        -> tail latency grows
```

CPU-heavy work should normally move to a process, worker, or specialized service. Long-running I/O
work that does not belong in the request should move to RabbitMQ workers.

### Interview questions

- When should a FastAPI route use `async def`?
- What happens if synchronous blocking code runs inside `async def`?
- Is concurrency the same as parallelism?
- How would you limit 1,000 webhook tasks so they do not exhaust connections or memory?

## 5. Errors, middleware, and cross-cutting behavior

### Concepts

- `HTTPException` for expected client-visible HTTP outcomes.
- Exception handlers for stable application-wide error formats.
- Middleware for request IDs, timing, access logs, CORS, and selected security behavior.
- Why business rules should not be hidden inside generic middleware.
- Exception chaining and safe error messages.
- Rollback before re-raising database exceptions.
- Correlation IDs versus trace IDs.

### Interview questions

- When would you use middleware rather than a dependency?
- How do you avoid leaking database errors or secrets to clients?
- What should be logged when a request fails?
- Why must a failed transaction be rolled back before reusing a session?

## 6. Transactions and API correctness

### Concepts

- Session versus transaction versus connection.
- Flush versus commit versus rollback versus refresh.
- Atomic event-and-delivery creation.
- Isolation, concurrent requests, race conditions, and database constraints.
- Short transaction boundaries.
- Idempotency and retry-safe APIs.
- Correct status codes: `201`, `202`, `404`, `409`, `422`, and `500`.

### Interview questions

- Why does RelayKit return `202` for event ingestion?
- Why must the event and its delivery responsibilities commit atomically?
- Why is “check, then insert” not sufficient to prevent duplicates?
- What is the difference between an API retry and a database transaction retry?

## 7. Testing FastAPI applications

### Test layers

| Layer | Purpose | RelayKit example |
|---|---|---|
| Schema unit test | Validate one contract quickly | Reject malformed endpoint IDs |
| Route unit test | Exercise route decisions with mocked dependencies | Roll back when commit fails |
| API integration test | Exercise ASGI routing, validation and responses | `POST /v1/events` returns `202` |
| Database integration test | Verify real PostgreSQL constraints/transactions | Duplicate subscription returns conflict |
| End-to-end test | Cross process and infrastructure boundaries | Event reaches receiver through RabbitMQ |
| Failure-injection test | Prove recovery behavior | Worker crashes before acknowledgement |
| Load test | Measure capacity and latency | p95 ingestion under configured concurrency |

### Concepts

- Arrange, act, assert.
- Pytest fixtures and fixture scope.
- Async tests and event-loop handling.
- FastAPI dependency overrides.
- Test isolation and database cleanup.
- Mock only the boundary the test is not trying to verify.
- Contract tests for RabbitMQ messages and outgoing webhooks.

### Interview questions

- Why is a mocked route test insufficient for database correctness?
- What should an integration test use a real PostgreSQL instance for?
- How would you test a FastAPI dependency?
- How do you keep tests deterministic when retries and time are involved?

## 8. API optimization: reason before technique

Optimization begins with a measured bottleneck. “FastAPI is fast” is not a capacity guarantee.

### Step 1 — Define the measurement

- Throughput: requests or events completed per second.
- Latency: p50, p95, and p99, not only an average.
- Error rate and timeout rate.
- Saturation: CPU, memory, event-loop lag, database pool, queue backlog, and downstream capacity.
- Separate ingestion latency from queue-to-first-attempt and end-to-end delivery latency.

### Step 2 — Locate the bottleneck

- Trace the request.
- Inspect query plans and slow-query logs.
- Inspect pool wait time and utilization.
- Profile CPU and memory when CPU is actually suspected.
- Compare application time with database, broker, and downstream HTTP time.
- Reproduce the workload with controlled load tests.

### Step 3 — Apply the smallest relevant technique

#### Application and event loop

- Use async clients for I/O and remove blocking calls from the event loop.
- Reuse process-wide HTTP and broker connections.
- Bound concurrency instead of creating unlimited tasks.
- Move long-running delivery work out of the API request.
- Avoid unnecessary serialization and large response bodies.

#### PostgreSQL

- Add indexes based on query patterns and verify with `EXPLAIN`/`EXPLAIN ANALYZE`.
- Keep transactions short and avoid holding connections during unrelated network calls.
- Size the connection pool against PostgreSQL capacity and the number of application processes.
- Eliminate N+1 queries and fetch only required columns.
- Batch work where it preserves correctness and improves measured throughput.

#### API contract and network

- Paginate unbounded list endpoints.
- Enforce payload and response-size limits.
- Reuse keep-alive connections.
- Use compression only when payload size and CPU trade-offs justify it.
- Use caching only for suitable read paths with a defined invalidation policy.

#### Process and system scaling

- Add Uvicorn worker processes only after understanding memory, connection-pool multiplication, and
  statelessness.
- Scale API and delivery workers independently.
- Use queue depth, latency, and saturation to guide worker scaling.
- Apply backpressure rather than accepting unlimited in-memory work.

### Optimization traps

- Adding Redis before identifying a cacheable bottleneck.
- Increasing database-pool size until PostgreSQL is overwhelmed.
- Creating more server workers while multiplying every process-wide connection pool.
- Reporting average latency while p99 is unacceptable.
- Benchmarking only the route function rather than the deployed request path.
- Removing correctness checks for a small latency improvement.
- Claiming improvement without recording the workload, baseline, configuration, and result.

### Interview answer structure

When asked “How did you optimize this API?”, answer:

```text
1. Workload and symptom
2. Measurement and baseline
3. Evidence locating the bottleneck
4. Change and trade-off
5. Correctness/regression tests
6. Measured result
7. Remaining limit
```

## 9. Production FastAPI topics to learn later

- Application lifespan and startup/shutdown failures.
- Health, readiness, and degraded-health endpoints.
- Authentication dependencies and tenant context.
- CORS and trusted proxy behavior.
- Rate limiting and abuse protection.
- OpenAPI customization and API versioning.
- Distributed trace propagation.
- Graceful shutdown with in-flight requests.
- Deployment behind a reverse proxy/load balancer.
- Security headers, TLS termination, and forwarded headers.

## Current FastAPI checkpoint

Already encountered:

- `FastAPI`, `APIRouter`, route decorators, status codes, `response_model`.
- Pydantic request/response schemas, aliases, and ORM attribute reading.
- `Depends`, an async generator database dependency, and one session per request.
- Async SQLAlchemy queries, flush, commit, rollback, and database exceptions.
- `HTTPException` for expected `404` and `409` outcomes.
- Unit tests with `AsyncMock` and basic database integration tests.

Manually verified through Postman on November 3:

- A valid endpoint request passes Pydantic validation, reaches the route, commits to PostgreSQL, and
  returns `201 Created`.
- A duplicate but structurally valid endpoint reaches the route/database boundary and returns
  `409 Conflict` after PostgreSQL enforces uniqueness.
- An invalid endpoint body returns `422 Unprocessable Entity` during FastAPI/Pydantic request
  validation. The route function does not execute, so it performs no application database work.
- Event ingestion returns `202 Accepted` with one event ID and one delivery ID per matching
  subscription; existing persistent data produced two matching deliveries in the manual exercise.

Interview distinction:

```text
422 -> request does not satisfy the declared API schema
409 -> request satisfies the schema but conflicts with current resource state
```

Next learning block:

1. Run the full request lifecycle through Postman.
2. Add structured request logging and correlation IDs.
3. Learn API-level integration testing and dependency overrides.
4. Introduce lifespan-managed resources when RabbitMQ and HTTPX are added.
5. Measure performance only after the complete delivery path provides a meaningful workload.

## Interview evidence ledger

For each completed phase, record:

- one architecture diagram;
- one failure scenario and recovery explanation;
- one important code path the learner can explain line by line;
- one unit or integration test the learner can recreate;
- one log/metric/trace screenshot where relevant;
- one measured performance result with its methodology;
- one trade-off and one rejected alternative;
- one concise two-minute interview explanation.

The goal is not to memorize answers. The goal is to have enough implementation and evidence that
the answers are natural descriptions of work the learner understands.
