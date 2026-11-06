# RelayKit Progress Journal

This file is the durable handoff between working sessions. It records what was actually decided,
implemented, and verified so that a new session does not have to reconstruct the project from chat
history.

## How to use this journal

At the beginning of each session:

1. Read the latest daily entry and handoff summary.
2. Inspect the repository before assuming a task is complete.
3. Spend the first 10 minutes revising the previous session's concepts, decisions, and open
   questions. The learner should explain the key ideas in their own words before new material begins.
4. Confirm today's target and its definition of done.
5. Do not start the next roadmap item while the current one is unverified.

At the end of each session:

1. Record what was completed, not merely attempted.
2. Record commands and tests that actually passed.
3. Record decisions and the reasoning behind them.
4. Record known failures, shortcuts, and unresolved questions.
5. Write a short next-session handoff.

Use these evidence labels:

- **Planned:** agreed work that has not been completed.
- **In progress:** started but not yet verified.
- **Verified:** supported by repository inspection or a passing check.
- **Blocked:** cannot continue until a named condition is resolved.

Never mark work verified merely because code was written. Verification requires an appropriate test,
command, or manual observation.

## Working agreement

- The learner writes implementation code unless they explicitly ask Codex to implement it.
- Codex may explain, propose designs, review code, and suggest the next small task.
- No dependency installation, infrastructure startup, or application-code modification happens
  without explicit approval.
- Create a directory only when its first real responsibility is introduced. Do not keep speculative
  empty package, migration, infrastructure, or test folders merely to resemble a finished system.
- Teach from first principles: define a term, explain the problem it solves, show the failure without
  it, and only then introduce the production pattern or implementation.
- Do not introduce unexplained jargon or ask the learner to reason from concepts that have not yet
  been taught. Introduce one conceptual layer at a time and check understanding before building on it.
- Exercises are optional learning checks. If the learner asks to skip one, continue without blocking
  progress or treating the skipped exercise as completed evidence.
- When requested, Codex provides concise, copy-ready notes. Codex edits project files only when
  explicitly authorized.
- Each production feature begins with the failure it prevents.
- Each completed feature includes a happy-path test and the motivating failure test where practical.
- PostgreSQL remains the authoritative source of correctness-critical state.
- The resume-ready milestone is feature- and evidence-gated, not a claim that RelayKit is a fully
  mature commercial service or complete merely because a calendar date arrived.

## Current learning roadmap — October 30 reset

The earlier October date plan below is now a **historical planning baseline**. It is superseded by
the competency-gated roadmap in [`docs/learning-roadmap.md`](docs/learning-roadmap.md). We will not
compress reliability, security, observability, or failure testing merely to preserve an expired
calendar checkpoint.

The new definition of progress is:

```text
Understand the problem
        ↓
Reproduce or predict the failure
        ↓
Compare designs and trade-offs
        ↓
Implement the smallest solution
        ↓
Test the happy path and motivating failure
        ↓
Observe it with logs, metrics, or traces
        ↓
Document the guarantee, limitation, and evidence
```

Current phase order:

| Phase | Learning outcome | Gate evidence | Status |
|---|---|---|---|
| 0 | Developer feedback loop | Postman flow, structured logs, understood tests | Current |
| 1 | Smallest complete delivery slice | API -> PostgreSQL -> RabbitMQ -> worker -> receiver -> inspection | Planned |
| 2 | Reliable publication and consumption | Idempotency, outbox, confirms, acknowledgements, retries, crash tests | Planned |
| 3 | Concurrency and latency control | Redis controls, backpressure, multi-worker and load-test evidence | Planned |
| 4 | Production observability | Prometheus, OpenTelemetry, Grafana, traces, alerts, runbook | Planned |
| 5 | Security and multi-tenancy | API keys, tenant isolation, HMAC, SSRF and replay tests | Planned |
| 6 | Deployment and operations | CI, images, HTTPS deployment, backup/recovery and demo | Planned |
| 7 | Resume-depth bridge labs | Measured caching, SSE, S3, RAG/AI, OAuth and optional ClickHouse labs | Planned |

ClickHouse is deliberately optional and late. PostgreSQL remains authoritative; Prometheus, Tempo,
and Loki first teach metrics, traces, and logs. ClickHouse is added only when a measured
high-cardinality analytics or retention requirement justifies its operational cost.

The cross-cutting [`FastAPI and Python Backend Interview Track`](docs/fastapi-interview-track.md)
must be taught alongside these phases. It covers framework internals, request/resource lifecycles,
async Python, transactions, testing, optimization, scaling, and evidence-based interview answers.
Optimization work must begin with a measured bottleneck and preserve correctness; installing a
cache or adding workers without a baseline does not count as optimization evidence.

## Historical milestone plan — superseded by the current learning roadmap

**Target date:** October 31, 2026

**Target outcome:** A reproducible, deployed portfolio version in which RelayKit accepts events,
persists them, reliably schedules and performs webhook deliveries, protects individual endpoints,
records operational evidence, and demonstrates recovery from selected failures.

**Time assumption:** Approximately 4–6 focused hours per working day, six days per week. Maintain a
weekly buffer or lighter day because debugging infrastructure and deployment is unpredictable.

### Priority order

1. Understand and document one-event data flow.
2. Build the smallest end-to-end vertical slice.
3. Make ingestion, publication, and consumption failure-aware.
4. Add bounded retries, dead-lettering, and webhook security.
5. Add basic tenancy, Redis endpoint protection, and circuit breaking.
6. Add operational evidence through logs, metrics, tests, and load measurements.
7. Deploy the independently runnable processes and rehearse a reproducible demonstration.

If the schedule slips, reduce polish and stretch work before weakening idempotency, the outbox,
acknowledgement safety, retries, tenant isolation, or failure testing.

## October 31 feature scope

### Required product workflow

- Endpoint registration, pause, and resume.
- Event-type subscriptions.
- Asynchronous event publication.
- One event creating multiple deliveries.
- Delivery and attempt history.
- Inspection and controlled replay through the CLI.
- A development receiver that can inject latency and failures and detect duplicate event IDs.

### Required reliability behavior

- Idempotent ingestion with database-enforced conflict handling.
- A transactional outbox with safe claiming, batching, recovery, and publisher confirmations.
- Durable RabbitMQ topology, persistent messages, manual acknowledgements, and worker prefetch.
- Duplicate-message handling and stable event identities.
- Bounded exponential backoff with jitter, maximum attempts, and dead-lettering.
- Demonstrations of broker outage, worker crash/redelivery, endpoint failure, and duplicate work.

### Required security and tenancy

- API-key authentication with stored hashes and revocation.
- Basic account ownership and tenant-scoped queries.
- Tests proving that one account cannot access another account's resources.
- HMAC-signed webhooks with timestamped signatures.
- Payload limits, request timeouts, and basic destination URL validation.

### Required endpoint protection

- Redis-backed per-endpoint concurrency limits with expiring leases.
- Basic per-endpoint request-rate limiting.
- Worker backpressure and protection against a slow endpoint monopolizing processing.
- A focused `CLOSED` / `OPEN` / `HALF_OPEN` circuit breaker.
- Defined conservative behavior when Redis is unavailable.

Redis will be included when local Docker Compose infrastructure is introduced in Phase 2 so its
lifecycle and health are visible. Its application responsibility will then grow incrementally:
first connectivity and health, then concurrency leases, rate limiting, and finally shared
circuit-breaker state. It must never become the only store for accepted events, deliveries,
attempts, or publication intent.

### Required operational evidence

- Structured logs and correlation IDs.
- Health and readiness endpoints.
- Prometheus-style ingestion, delivery, retry, dead-letter, latency, and backlog metrics.
- Unit, integration, end-to-end, concurrency, and selected failure-injection tests.
- A repeatable load-test scenario and measured p50, p95, and p99 results.
- Container images, CI checks, migrations, hosted dependencies, HTTPS, and deployment instructions.
- Separately running API, outbox-publisher, and worker processes.

### Stretch goals

- Basic distributed tracing.
- A hosted metrics dashboard.
- Additional automated crash-point coverage.
- More advanced secret rotation.

### Explicitly outside the October deadline

- React dashboard and AI features.
- Kafka, Kubernetes, and multi-region deployment.
- OAuth, SSO, billing, and complex organization roles.
- Adaptive retry optimization or latency-aware destination failover.
- Comprehensive cloud KMS integration.
- A claim of end-to-end exactly-once HTTP delivery.

## Roadmap and checkpoints

| Phase | Dates | Target | Expected evidence | Status |
|---|---|---|---|---|
| Phase 1 | Oct 4–6 | System design and foundation | Reviewed scope, flow, HLD, failure map, contracts, and initialized `uv` project | In progress — 7/12 outcomes |
| Phase 2 | Oct 7–11 | Local infrastructure, stored workflow, and vertical slice | Docker Compose dependencies are healthy and the CLI-to-receiver integration test succeeds | Planned |
| Phase 3 | Oct 12–18 | Reliable delivery | Idempotency, outbox, confirmation, retry, dead-letter, and crash-window tests | Planned |
| Phase 4 | Oct 19–25 | Security and endpoint protection | Tenant isolation, Redis concurrency/rate, and circuit recovery tests | Planned |
| Phase 5 | Oct 26–31 | Operations and deployment | Hosted system, recorded benchmarks, reviewed documentation, and rehearsed demo | Planned |

### Checkpoint gates

- **October 6 — Design foundation:** the product contract, HLD, failure map, and first contracts are
  reviewed; the Python project foundation is reproducible.
- **October 8 — Stored workflow:** one event transactionally creates the correct delivery records.
- **October 11 — Working vertical slice:** CLI → API → PostgreSQL → RabbitMQ → worker → receiver works.
- **October 18 — Reliable core:** important ingestion, publication, acknowledgement, and retry crash
  windows are understood and tested.
- **October 25 — Protected platform:** basic tenant isolation and endpoint controls work across
  multiple workers.
- **October 29 — Deployed candidate:** public HTTPS API and independently running processes complete
  an end-to-end delivery.
- **October 31 — Resume-ready release:** evidence, measurements, documentation, and demonstration are
  reproducible.

Dates are planning targets, not permission to skip understanding or verification.

Phase 3 is the highest schedule risk. Protect idempotency, the transactional outbox, publisher
confirmation, acknowledgement safety, duplicate handling, retries, and dead-lettering. If it slips,
move HMAC polish or replay-interface polish later rather than weakening the reliability core.

### Phase 1 progress — 7 of 12 outcomes complete

Overall Phase 1 is **58% complete** by its defined outcomes. The conceptual architecture portion is
further along than the repository foundation; no application implementation has started.

Completed:

- [x] Define RelayKit's product purpose and principal non-goals.
- [x] Understand event, endpoint, subscription, delivery, attempt, retry, and dead-letter terms.
- [x] Separate synchronous ingestion from asynchronous delivery and define the meaning of `202`.
- [x] Define the HLD components and independently runnable process boundaries.
- [x] Review the architecture-shaping failure map and planned recovery guarantees.
- [x] Refine beginner-oriented learning notes with examples, diagrams, and revision questions.
- [x] Write and review explicit product acceptance criteria for the first demonstration.

Remaining:

- [ ] Define domain relationships and who owns every delivery-state transition.
- [ ] Define the first HTTP API contracts and error format.
- [ ] Define the RabbitMQ message and outgoing webhook contracts.
- [ ] Break the first vertical slice into an ordered implementation checklist with test evidence.
- [ ] Finish the minimum quality-tool configuration, verify the foundation, and create the first
  intentional Git commit. (`uv`, the virtual environment, and dependencies are already initialized.)

Block 5 is the bridge from architecture to implementation: it defines the first vertical slice and
its contracts. Actual application behavior begins after this design gate, with the stored workflow
in Phase 2.

### Current work item — first vertical-slice demo

The current goal is to design and then implement the smallest complete RelayKit workflow:

```text
Create one Accounting endpoint
        ↓
Subscribe it to payment.completed
        ↓
Publish one payment.completed event
        ↓
Store the event and its delivery
        ↓
Send the delivery work through RabbitMQ
        ↓
A worker sends one HTTP request to a local webhook receiver
        ↓
Record the attempt and successful delivery result
        ↓
Inspect the delivery through the CLI
```

The first demonstration is successful when one event is accepted, one delivery is created, the
local receiver observes the webhook, the worker records HTTP `200`, and delivery inspection reports
`SUCCEEDED` with one attempt.

This first slice is a happy-path learning baseline. It does not yet claim production reliability.
Idempotent ingestion, the transactional outbox, publisher confirms, retries, dead-lettering, Redis
endpoint controls, HMAC signing, and deployment will be introduced in later hardening steps after
their motivating failures are examined.

Before implementation, review the proposed CLI commands as contracts rather than treating their
syntax as final. Decide each command's inputs, validation, API request, output, identifiers, and
failure behavior. In particular, determine how endpoint references are resolved and how the user
obtains the delivery identifier later passed to `relay deliveries inspect`.

## Daily timebox

Use this as a guideline rather than a reason to continue when concentration has fallen:

```text
10 minutes      Revision of the previous session
45–60 minutes   Concept, failure case, and design
2–3 hours       Learner-led implementation
60–90 minutes   Testing, debugging, and review
20–30 minutes   Documentation and next-session handoff
```

Infrastructure and deployment days may need longer contiguous blocks. Any benchmark number must be
measured and recorded before appearing in project or resume material.

## Current verified state

- A local Git repository exists.
- The original project idea and accumulated learning content are preserved in the refined `notes.md`.
- The `uv` Python 3.13 project, virtual environment, lockfile, and minimum endpoint-related package
  areas now exist.
- The reviewed API/database runtime and development dependencies are installed and verified.
- PostgreSQL 17 runs in Docker on `127.0.0.1:55433`, persists to a named volume, and has passed its
  health check and a `SELECT 1` connectivity check.
- `notes.md` contains refined beginner-oriented revision notes, diagrams, examples, and the current
  architecture-level failure map.
- The FastAPI application exposes `POST /v1/endpoints`, `POST /v1/subscriptions`, and
  `POST /v1/events`.
- Async SQLAlchemy settings, engine, session factory, FastAPI dependency, and PostgreSQL integration
  tests exist.
- Alembic migrations and SQLAlchemy models exist for endpoints, subscriptions, events, and
  deliveries.
- Publishing an event finds matching subscriptions and commits the event and its pending deliveries
  together. A valid event with no subscriptions is accepted with zero deliveries.
- On October 30, `uv run pytest -q` passed **35 tests** and `uv run ruff check src tests` reported
  **All checks passed**.
- RabbitMQ publication, the delivery worker, attempt history, CLI inspection, retries, security,
  Redis controls, and production observability have not been implemented.

## Daily entry template

Copy this section for each new working day.

### YYYY-MM-DD — Short session title

**10-minute revision**

- Previous concepts recalled:
- Misunderstandings corrected:
- Open question carried forward:

**Today's target**

State one observable outcome for the session.

**Concepts learned**

- Concept:
- Problem it solves:
- Failure without it:
- Trade-off:

**Decisions made**

- Decision:
- Reason:
- Alternatives considered:

**Work completed**

- [ ] Item

**Evidence**

- Command or test:
- Result:
- Manual observation:

**Known gaps or failures**

- Gap:
- Consequence:
- Planned resolution:

**Questions to revisit**

- Question:

**Next-session handoff**

- Start here:
- Do not assume:
- Next smallest task:
- Relevant files:

## Daily log

### 2026-11-04 — Structured logging foundation

**Today's target**

Understand Python's logging pipeline, decide RelayKit's initial production-compatible logging
architecture, and implement the central JSON formatter/configuration without starting request
middleware prematurely.

**Concepts learned**

- A named logger creates and routes a `LogRecord`; a handler chooses the destination; a formatter
  chooses the output representation; a filter may enrich or reject the record.
- Logger hierarchy is based on dot-separated names. `relaykit` is the top-level application logger,
  while Python's root logger is a separate logger above all named loggers.
- Logger levels filter near the source; handler levels independently control what a destination
  emits. `INFO` accepts records whose severity is greater than or equal to `INFO`.
- Central configuration does not mean passing one global logger object around. Modules call
  `logging.getLogger(__name__)` and records propagate to the RelayKit handler.
- A bare `*` in a function signature makes following parameters keyword-only; `*args` and
  `**kwargs` collect additional positional and named arguments respectively.
- Middleware begins before FastAPI/Pydantic validation, which is why request correlation must be
  established there rather than inside individual routes.

**Decisions made**

- Use Python standard-library logging before considering `structlog`.
- Emit one-line structured JSON to stdout; a collector and durable log store come later.
- Configure the `relaykit` application logger centrally and stop propagation before the Python root
  logger to avoid duplicate output.
- Validate incoming request IDs later and store request context in a `ContextVar`; do not use a
  shared global variable across concurrent requests.
- Record the architecture and trade-offs as accepted decision `DD-002`.

**Work completed**

- [x] Added beginner logging and request-correlation notes to `notes.md`.
- [x] Added `DD-002 — Structured application logging to stdout`.
- [x] Added the `relaykit.observability` package.
- [x] Implemented `JsonFormatter` with UTC timestamps, stable envelope fields, custom context,
  compact JSON output, and exception/stack serialization.
- [x] Implemented idempotent `configure_logging()` with validated log levels, one managed stdout
  handler, JSON formatting, and duplicate-handler prevention.
- [x] Wired logging configuration into the FastAPI entry point.
- [x] Added focused unit tests for formatting, exceptions, idempotency, and invalid levels.

**Evidence**

- Focused logging tests: `4 passed`.
- Complete test suite: `39 passed`.
- Ruff: all checks passed.
- mypy: no issues found in 26 source files.

**Known gaps or failures**

- No request-ID `ContextVar`, enrichment filter, or request middleware exists yet.
- Current routes do not emit domain logs, so the new pipeline does not yet produce RelayKit request
  completion records.
- `INFO`, `relaykit-api`, and `development` currently come from configuration-function defaults
  rather than validated environment settings.
- Uvicorn's own logs remain separately configured and may appear beside RelayKit JSON output.
- No collector or durable log store exists; terminal/stdout output is not durable.

**Next-session handoff**

- Begin with a short revision of logger versus handler versus formatter versus filter.
- Implement `relaykit/observability/context.py` with get/set/reset functions and `ContextVar` tokens.
- Implement `RequestContextFilter`, attach it to the managed handler, and test context isolation and
  reset behavior.
- Do not start request middleware until the context/filter layer is verified.
- Relevant files: `src/relaykit/observability/logging.py`,
  `tests/unit/observability/test_logging.py`, `docs/design-decisions.md`, and `notes.md`.

### 2026-11-03 — Local developer flow and FastAPI boundary validation

**Today's target**

Verify the stored workflow manually through Postman, connect observed HTTP behavior to FastAPI
concepts, and then introduce structured request logging.

**Concepts learned**

- A Postman workspace organizes collections and environments; an environment stores reusable local
  values such as `baseUrl` and generated resource IDs.
- `201 Created` is an HTTP request outcome, while an endpoint's `active` value is domain state.
- FastAPI validates a declared Pydantic request model before invoking the route function.
- `422 Unprocessable Entity` means the JSON was parseable but did not satisfy the request schema;
  the invalid request did not reach application database work.
- `409 Conflict` means the request was structurally valid but conflicted with current database state.
- PostgreSQL data persists across FastAPI and Postman restarts. Two existing matching subscriptions
  correctly produced two deliveries for one accepted event.

**Work completed**

- [x] Verified the PostgreSQL container is healthy on `127.0.0.1:55433`.
- [x] Verified Alembic database revision and repository head are both `8dad0503a377`.
- [x] Started FastAPI with Uvicorn and confirmed all three routes in `/docs`.
- [x] Created and activated the `RelayKit Local` Postman environment.
- [x] Created an endpoint and a `payment.completed` subscription through Postman.
- [x] Published one event and observed two pending deliveries for two matching subscriptions.
- [x] Verified duplicate endpoint behavior returns `409`.
- [x] Verified invalid endpoint input returns `422`.

**Current continuation**

- Test an unknown endpoint subscription and observe `404`.
- Test duplicate subscription behavior and observe `409`.
- Test a valid event with no matching subscriptions and observe `202` with zero deliveries.
- Then begin structured logging and correlation IDs.

### 2026-10-30 — Production learning-roadmap reset

**Today's target**

Realign the project plan with the implementation that now exists and expand it into a deep,
production-grade learning curve covering the resume and backend-roadmap topics without creating a
tool-collection architecture.

**Decisions made**

- Replace expired date gates with competency gates requiring explanation, implementation, failure
  testing, observability, and recorded evidence.
- Complete the developer feedback loop before RabbitMQ: Postman, structured logs, and understood
  unit/integration tests.
- Introduce Prometheus, OpenTelemetry, Grafana, Tempo, and Loki progressively after the multi-process
  delivery path exists.
- Keep ClickHouse optional until high-cardinality analytics or retention creates a measured need.
- Cover S3, RAG, OAuth/OIDC, SSE, and advanced analytics as focused bridge labs instead of forcing
  them into RelayKit's correctness path.
- Add a FastAPI/Python backend interview track that follows the real request lifecycle and records
  evidence for framework concepts, async behavior, testing, optimization, and scaling.

**Evidence**

- `uv run pytest -q`: 35 passed.
- `uv run ruff check src tests`: all checks passed.
- Repository inspection confirms three write routes and four current domain tables.

**Next-session handoff**

- Start with the mandatory 10-minute revision.
- Manually exercise endpoint -> subscription -> event using Postman and real PostgreSQL rows.
- Teach and add minimal structured developer logging with request/correlation IDs.
- Review existing tests and add API/database integration coverage before beginning RabbitMQ.
- For every feature, capture one interview explanation: problem, failure, design, trade-off, test,
  measurement, and limitation.
- Detailed sequence: `docs/learning-roadmap.md`.

### 2026-09-28 — Project orientation and working method

**Today's target**

Establish the learning approach, explain the scaffold, and define the path to a deployed October 31
portfolio release without beginning application implementation.

**Concepts learned**

- A data flow follows one event through the system.
- A high-level design describes major components and communication boundaries.
- A low-level design is created immediately before implementing a specific feature.
- A vertical slice is one small workflow running through all required system layers.
- Production hardening should be motivated and verified through concrete failure cases.

**Decisions made**

- RelayKit will be learned and built incrementally rather than generated as a complete system.
- The first implementation target will be one end-to-end delivery workflow.
- The learner will implement application code; Codex will mentor and review unless explicitly asked
  to make changes.
- `uv` will manage the Python project and run commands; Uvicorn will serve the FastAPI application.
- The target was expanded from an October 12 reliable-core demo to an October 31 deployed,
  resume-ready portfolio version with additional focused work hours.
- React, AI, Kubernetes, Kafka, multi-region operation, OAuth, SSO, and billing are outside the
  October deadline.

**Work completed**

- [x] Initialized the local Git repository.
- [x] Created the empty repository directory scaffold.
- [x] Preserved the original `notes.md`.
- [x] Defined an initial daily roadmap through October 12.
- [x] Added this progress journal.
- [x] Replanned the milestone around an October 31 deployed, resume-ready scope.

**Evidence**

- Repository inspection showed only `notes.md` and tracked-directory placeholders before this
  journal was added.
- No dependency installation or application implementation command was run.

**Known gaps or failures**

- Product acceptance criteria have not yet been written in detail.
- The happy-path data flow and failure map have not yet been reviewed.
- The expanded October 31 plan is aggressive and may require cutting stretch goals after each
  checkpoint review.

**Questions to revisit**

- What exact behavior must be durable before the API returns `202 Accepted`?
- Which exact deployment provider and hosted data services best fit the final topology and budget?
- Which stretch goals should be removed first if a required checkpoint slips?

**Next-session handoff**

- Start with one `payment.completed` event and two subscribed endpoints.
- Do not begin Python implementation.
- Describe synchronous and asynchronous steps and the crash behavior at each boundary.
- Turn the reviewed answers into product-scope and data-flow documents only after agreement.

### 2026-10-04 — Domain flow, process boundaries, and failure reasoning

**10-minute revision**

- This was the first detailed learning session, so no previous implementation was revised.
- The session began by grounding terminology in one `payment.completed` example.
- The original teaching pace was corrected after advanced patterns were introduced before their
  motivating problems had been explained.

**Today's target**

Understand RelayKit's event journey, major process boundaries, and initial failure behavior without
writing application code.

**Concepts learned**

- An event is an accepted fact; a delivery is RelayKit's responsibility to one endpoint; an attempt
  is one HTTP request made for a delivery.
- Subscription matching creates one independent delivery per matching endpoint.
- `202 Accepted` means RelayKit durably accepted asynchronous responsibility, not that webhooks have
  already succeeded.
- Ingestion latency ends at the `202` response; endpoint response time belongs to delivery latency.
- A database transaction protects the event and its delivery responsibilities from partial writes.
- API, outbox publisher, worker, and CLI are independently runnable processes in one modular Python
  codebase, not separate domain microservices.
- A module is generally a Python file, a package groups importable modules, and a process is a running
  program with its own memory.
- RelayKit's planned concurrency model is multiple worker processes with multiple asynchronous I/O
  tasks inside each process; ordinary in-memory thread locks cannot coordinate separate workers.
- A transactional outbox is a durable PostgreSQL reminder that committed delivery work still needs
  publication to RabbitMQ.
- Publisher confirms cover publisher-to-broker acceptance; consumer acknowledgements cover
  broker-to-worker completion.
- Duplicate publication is expected around publisher crash windows. Delivery claiming must combine
  its state check and transition atomically across workers.
- PostgreSQL is authoritative. RabbitMQ distributes active work. Redis will coordinate temporary
  endpoint controls and will gain responsibilities incrementally as those features are introduced.

**Decisions made**

- Return `202` only after the event and its delivery responsibilities are durably committed.
- Capture the matching subscription set during ingestion so accepted delivery responsibilities do
  not depend on later subscription changes.
- Use `maximum_attempts`, where the initial request counts as attempt one, rather than the ambiguous
  phrase `maximum_retries`.
- Preserve append-only attempt history for debugging, metrics, and auditability.
- Use manual RabbitMQ consumer acknowledgements only after the relevant database outcome is durable.
- Do not claim exactly-once HTTP processing; use stable identities and at-least-once transport.
- Include Redis with PostgreSQL and RabbitMQ when Phase 2 local Docker Compose infrastructure is
  created, but add connectivity, concurrency, rate, and circuit responsibilities one feature at a
  time rather than making correctness depend on it prematurely.
- Begin every future session with a 10-minute learner-led revision.

**Work completed**

- [x] Inspected the repository and verified that no implementation or dependencies exist.
- [x] Defined event, endpoint, subscription, delivery, and attempt terminology through examples.
- [x] Discussed the initial delivery state machine and retryable versus permanent failures.
- [x] Distinguished synchronous ingestion work from asynchronous delivery work.
- [x] Defined the API, PostgreSQL, publisher, RabbitMQ, worker, Redis, and CLI responsibilities.
- [x] Completed the architecture-level failure map for API, database, broker-publication, worker,
  dependency, destination, poison-message, and shutdown scenarios.
- [x] Added learner-written explanations and failure notes to `notes.md`.
- [x] Refined `notes.md` into structured revision material with HLD and failure diagrams.
- [x] Measured Phase 1 against explicit outcomes: 6 of 12 are complete.
- [x] Updated the mentoring rules and project handoff journal.
- [x] Removed the speculative empty directory scaffold at the learner's request; future directories
  will be created only when the corresponding responsibility is introduced.

**Evidence**

- Repository inspection still shows no Python application code, project dependency configuration, or
  Git commits.
- The empty API, CLI, database, domain, messaging, worker, outbox, settings, observability,
  migration, infrastructure, documentation, and test placeholders were removed without deleting
  any implementation or learning content.
- `notes.md` now contains the learner's October 4 terminology, data-flow, HLD, and failure notes.
- Understanding was checked conversationally using delivery-count, attempt-state, latency-boundary,
  idempotency, and worker-coordination scenarios.

**Known gaps or failures**

- Phase 1 design documents have not yet been created or reviewed.
- The architecture-level failure map is complete; feature-level failure algorithms remain deferred
  until their implementation work.
- API and message contracts, database schema, and exact state-transition ownership remain undefined.
- Processing-lease, retry-scheduling, rate-limit, and circuit-breaker algorithms are intentionally
  deferred until their implementation phases.
- The purpose and shape of delivery inspection APIs still needs a direct explanation.
- No initial Git commit exists, so all current files remain untracked.

**Questions to revisit**

- Should manual replay create a new linked delivery or a new execution generation on the existing
  delivery?
- What response metadata can be stored safely without retaining sensitive or excessively large
  endpoint bodies?
- What exact conservative behavior should each worker use during a Redis outage?

**Next-session handoff**

- Spend the first 10 minutes revising event/delivery/attempt, `202`, process boundaries, outbox,
  publisher confirms, consumer acknowledgements, and atomic delivery claims.
- Begin Block 5 by writing the October demonstration acceptance criteria.
- Define state-transition ownership and the first HTTP, RabbitMQ, and webhook contracts.
- Convert the vertical slice into an ordered implementation and evidence checklist.
- Initialize the `uv` foundation only after those contracts are reviewed.
- Relevant files: `notes.md` and `progress.md`.

### 2026-10-15 — Return, revision, and vertical-slice restart

**Today's target**

Restore the earlier architecture context, define the first vertical-slice demonstration precisely,
and review its CLI/API contracts before any implementation begins.

**Work completed**

- [x] Re-inspected the repository and verified that it contains only the learning records.
- [x] Completed a short revision of event, delivery, attempt, `202 Accepted`, component boundaries,
  publisher confirms, consumer acknowledgements, the outbox crash window, and at-least-once delivery.
- [x] Defined the first vertical-slice demo as one successful `payment.completed` delivery to one
  local Accounting endpoint, followed by CLI inspection.
- [x] Locked the lightweight CLI/API contracts and the first-slice versus hardening scope in
  `current.md`.
- [x] Completed the detailed design for `relay endpoints create`, including IDs, validation,
  uniqueness, transaction boundary, and errors.
- [x] Initialized the Python 3.13 project with `uv` and created only the currently required package
  areas.
- [x] Installed and verified the API/database runtime and development dependencies.
- [x] Started PostgreSQL 17 in Docker on local port `55433`; its health check and `SELECT 1` passed.

**Current todo**

- [x] Review the four example CLI commands as lightweight user-facing contracts.
- [x] Finalize the detailed `relay endpoints create` contract.
- [ ] Decide the inputs, outputs, identifiers, validation, and error behavior for each command.
- [ ] Map each CLI command to its initial HTTP method, path, headers, request payload, success
  response, and error response.
- [ ] Define the minimum database records and delivery-state transitions required by the slice.
- [ ] Define the initial RabbitMQ message plus the outgoing webhook payload and headers.
- [ ] Turn the agreed design into an ordered, learner-led implementation checklist.
- [x] Initialize the `uv` project after the endpoint contract is understood.
- [ ] Learn the PostgreSQL → asyncpg → SQLAlchemy layers and how a connection is established.
- [ ] Implement typed `DATABASE_URL` settings, the async engine, and per-task session factory.
- [ ] Verify the application-side database connection before creating the endpoint model.

**Important scope rule**

The example CLI commands are illustrative, not finalized. No command syntax or behavior becomes an
implementation requirement until it has been discussed and recorded as an agreed contract. The
first slice still includes minimum boundary validation for required fields and basic types; advanced
validation, authentication, payload limits, and idempotency belong to later hardening steps.

**Next-session handoff**

- Begin with a short revision of the Docker port mapping and how the database URL was constructed.
- Explain PostgreSQL, database drivers, `asyncpg`, SQLAlchemy, engines, connection pools, sessions,
  and transactions from first principles.
- Only after the learner understands those layers, implement typed settings and test the
  application-side connection.
- Do not create the endpoint model or migration before the connection foundation is understood and
  verified.
