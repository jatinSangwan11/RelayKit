# RelayKit Current Implementation Contract

**Last updated:** October 15, 2026  
**Status:** Design locked for the first vertical slice; Python foundation and API/database
dependencies are installed, application behavior has not been implemented.

This file records what RelayKit is implementing now. It prevents the current contract from being
silently changed while the vertical slice is being built. Later production refinements must be
recorded explicitly instead of being mixed into the first slice.

## Current project foundation

- `uv` initialized the project with Python 3.13.
- `.venv` contains the reviewed API, database, migration, testing, linting, and type-checking tools.
- `uv.lock` records the exact resolved dependency graph.
- Runtime imports, Ruff, mypy, pytest, and pytest-asyncio have been verified.
- PostgreSQL 17 is running locally in Docker and passed its health check and `SELECT 1` test.
- No FastAPI route, database model, migration, CLI command, or test has been implemented yet.

Local PostgreSQL:

```text
Compose service: postgres
Container:       relaykit-postgres-1
Image:           postgres:17-alpine
Host address:    127.0.0.1:55433
Container port:  5432
Database:        relaykit
Username:        relaykit
Volume:          relaykit_postgres_data
```

The nonstandard host port `55433` avoids an existing local PostgreSQL server on `5432` and an
unrelated Docker project on `55432`. RelayKit's application connection URL will be:

```text
postgresql+asyncpg://relaykit:relaykit_dev_password@localhost:55433/relaykit
```

Installed API/database runtime dependencies:

```text
fastapi
uvicorn
pydantic
pydantic-settings
sqlalchemy
asyncpg
alembic
```

Installed development dependencies:

```text
pytest
pytest-asyncio
ruff
mypy
```

Deferred until CLI implementation:

```text
typer
httpx
rich
```

## Current implementation goal

Build the smallest complete happy-path workflow:

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

The CLI is an HTTP client for the RelayKit API. It does not connect directly to PostgreSQL or
RabbitMQ.

## Locked command and API contracts

### 1. Create an endpoint

CLI command:

```bash
relay endpoints create \
  --name accounting \
  --url http://localhost:4000/webhooks
```

HTTP request:

```http
POST /v1/endpoints
Content-Type: application/json
```

```json
{
  "name": "accounting",
  "url": "http://localhost:4000/webhooks"
}
```

Successful response:

```http
HTTP/1.1 201 Created
Content-Type: application/json
```

```json
{
  "id": "ep_123",
  "name": "accounting",
  "url": "http://localhost:4000/webhooks",
  "status": "active"
}
```

The CLI prints the endpoint ID for later commands.

#### Locked endpoint rules

The API generates the endpoint ID in this form:

```text
ep_<UUID version 4 hex value>
```

For example:

```text
ep_7d97782aec814cda95d570c9c38386dd
```

`ep_123` remains a shortened documentation example.

The endpoint database record contains:

```text
id          Primary key; RelayKit-generated endpoint ID
name        Required, trimmed, maximum 100 characters, globally unique in the first slice
url         Required, valid HTTP or HTTPS URL; localhost is allowed for development
status      Set by the server to active
created_at  Set when the record is created
```

The first-slice uniqueness rule is `UNIQUE(name)`. When accounts are introduced, this will become
uniqueness within an account, conceptually `UNIQUE(account_id, name)`.

Creation succeeds only after the database transaction commits. The API must not return `201
Created` for an endpoint that has not been durably stored.

#### Endpoint creation errors

The first slice uses FastAPI's normal `detail` response shape rather than introducing the final
RelayKit-wide error contract prematurely.

| Situation | Where detected | Result |
|---|---|---|
| A required CLI option is missing | CLI | Command fails before making an HTTP request |
| Name is empty or longer than 100 characters | API validation | `422 Unprocessable Entity` |
| URL is malformed or is not HTTP/HTTPS | API validation | `422 Unprocessable Entity` |
| Endpoint name already exists | PostgreSQL unique constraint/API | `409 Conflict` |
| RelayKit API cannot be reached | CLI | Friendly connection error and non-zero exit status |
| Unexpected server or database failure | API | `500 Internal Server Error` without exposing internal details |

Duplicate-name response:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json
```

```json
{
  "detail": "An endpoint named 'accounting' already exists."
}
```

The PostgreSQL unique constraint is the final concurrency protection. An optional friendly lookup
may improve the common error path, but it cannot replace the database constraint because two API
requests can race between checking and inserting.

### 2. Create a subscription

CLI command:

```bash
relay subscriptions create \
  --endpoint-id ep_123 \
  --event-type payment.completed
```

The first slice uses the explicit endpoint ID. Resolving an endpoint by a convenient name is a
possible later CLI refinement.

HTTP request:

```http
POST /v1/subscriptions
Content-Type: application/json
```

```json
{
  "endpointId": "ep_123",
  "eventType": "payment.completed"
}
```

The exact successful response for subscription creation still needs to be discussed before this
command is implemented.

### 3. Publish an event

CLI command:

```bash
relay events publish \
  --type payment.completed \
  --data '{"paymentId":"pay_123","amount":4999}'
```

HTTP request:

```http
POST /v1/events
Content-Type: application/json
```

```json
{
  "type": "payment.completed",
  "data": {
    "paymentId": "pay_123",
    "amount": 4999
  }
}
```

Successful response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
```

```json
{
  "eventId": "evt_123",
  "deliveryIds": ["del_123"],
  "status": "accepted"
}
```

Returning `deliveryIds` makes the first demonstration easy to inspect. Whether it remains in the
long-term public contract will be reviewed after the first slice.

### 4. Inspect a delivery

CLI command:

```bash
relay deliveries inspect del_123
```

HTTP request:

```http
GET /v1/deliveries/del_123
```

This request has no body.

Successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{
  "id": "del_123",
  "eventId": "evt_123",
  "endpointId": "ep_123",
  "status": "succeeded",
  "attempts": [
    {
      "attemptNumber": 1,
      "httpStatus": 200
    }
  ]
}
```

## Minimum validation in the first slice

The first slice validates the generic RelayKit request envelope:

- Required fields must be present.
- Endpoint `name` is trimmed, must be non-empty, and has a maximum length of 100 characters.
- Endpoint `url` must be a valid HTTP or HTTPS URL; localhost is allowed for development.
- Event `type` must be a string.
- Event `data` must be a JSON object.
- A subscription cannot reference an endpoint that does not exist.
- CLI `--data` input must contain valid JSON.
- Inspecting an unknown delivery ID returns HTTP `404`.

RelayKit does not yet understand or validate the business-specific meaning of fields such as
`paymentId` or `amount`.

## Post-vertical-slice refinements

These are intentionally postponed until the happy-path slice works. Each will be introduced by
first examining the failure or risk it solves.

### Validation hardening

- Payload-size limits.
- Event-type naming rules.
- Endpoint URL security and server-side request forgery protection.
- Stronger duplicate endpoint and subscription rules.
- Standard error-response contract.
- Rules for safely storing response metadata and bodies.
- Optional customer-defined validation for event-specific data.

### Authentication and tenant security

- API-key authentication.
- Account ownership and tenant-isolation checks.
- Secure API-key storage and rotation.
- Endpoint-secret protection.

### Delivery correctness and security

- Idempotency keys for event ingestion.
- Transactional outbox and publisher confirms.
- Duplicate-message handling and stable receiver identifiers.
- Retries and dead-lettering.
- HMAC webhook signatures.
- Redis-backed concurrency limits, rate limits, and circuit breakers.

## Implementation method

Before coding, establish a lightweight contract for all four commands so the complete journey fits
together. Then implement and verify one command or capability at a time:

```text
Agree on the complete thin-slice contract
        ↓
Discuss endpoint creation in detail
        ↓
Implement and test endpoint creation
        ↓
Discuss, implement, and test subscription creation
        ↓
Discuss, implement, and test event publication
        ↓
Discuss, implement, and test delivery execution
        ↓
Discuss, implement, and test delivery inspection
        ↓
Run the complete end-to-end demonstration
        ↓
Introduce production refinements one motivated failure at a time
```

The next active discussion is `relay endpoints create`: its domain meaning, database record,
minimum validation, success response, and failure behavior.


1. Initialize the project with uv               X
2. Add only endpoint-related dependencies       X
3. Create the minimum required directories      X
4. Configure the PostgreSQL connection          CONTAINER READY; APPLICATION CONFIG PENDING
5. Create the endpoints database model
6. Create the first Alembic migration
7. Create the Pydantic request/response models
8. Implement POST /v1/endpoints
9. Implement relay endpoints create
10. Test success and failure cases
