from typing import cast
from unittest.mock import AsyncMock

import pytest  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.routes.subscriptions import create_subscription
from relaykit.api.schemas.subscription import SubscriptionCreate
from relaykit.database.models.endpoint import Endpoint

ENDPOINT_ID = f"ep_{'a' * 32}"
EVENT_TYPE = "payment.completed"
UNIQUE_CONSTRAINT = "uq_subscriptions_event_type_endpoint_id"
FOREIGN_KEY_CONSTRAINT = "fk_subscriptions_endpoint_id_endpoints"


class FakeDriverError(Exception):
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class FakeDatabaseError(Exception):
    def __init__(self, sqlstate: str, constraint_name: str) -> None:
        self.sqlstate = sqlstate
        self.orig = FakeDriverError(constraint_name)


def make_integrity_error(
    sqlstate: str,
    constraint_name: str,
) -> IntegrityError:
    # Reproduce the error shape produced by SQLAlchemy's asyncpg adapter. This
    # lets the unit tests exercise our SQLSTATE and constraint-name mapping.
    return IntegrityError(
        statement="INSERT INTO subscriptions ...",
        params={},
        orig=FakeDatabaseError(sqlstate, constraint_name),
    )


def make_request() -> SubscriptionCreate:
    return SubscriptionCreate.model_validate(
        {
            "endpointId": ENDPOINT_ID,
            "eventType": EVENT_TYPE,
        }
    )


def make_endpoint() -> Endpoint:
    return Endpoint(
        id=ENDPOINT_ID,
        name="accounting",
        url="http://localhost:4000/webhooks",
        status="active",
    )


@pytest.mark.asyncio
async def test_create_subscription_commits_and_returns_subscription() -> None:
    # Arrange: the referenced endpoint exists and database operations succeed.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.get.return_value = make_endpoint()
    session = cast(AsyncSession, session_mock)

    # Act: call the route function directly with its validated request.
    subscription = await create_subscription(make_request(), session)

    # Assert: the route looked up the endpoint, staged one row, and committed.
    session_mock.get.assert_awaited_once_with(Endpoint, ENDPOINT_ID)
    session_mock.add.assert_called_once_with(subscription)
    session_mock.commit.assert_awaited_once_with()
    session_mock.rollback.assert_not_awaited()
    assert subscription.id.startswith("sub_")
    assert len(subscription.id) == 36
    assert subscription.endpoint_id == ENDPOINT_ID
    assert subscription.event_type == EVENT_TYPE


@pytest.mark.asyncio
async def test_create_subscription_returns_404_when_endpoint_is_missing() -> None:
    # Arrange: a primary-key lookup returns None, meaning no endpoint exists.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.get.return_value = None
    session = cast(AsyncSession, session_mock)

    # Act and assert: the route stops before staging or committing a row.
    with pytest.raises(HTTPException) as captured_error:
        await create_subscription(make_request(), session)

    assert captured_error.value.status_code == status.HTTP_404_NOT_FOUND
    assert captured_error.value.detail == f"Endpoint '{ENDPOINT_ID}' was not found."
    session_mock.add.assert_not_called()
    session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_subscription_rolls_back_duplicate_subscription() -> None:
    # Arrange: PostgreSQL rejects the endpoint/event pair's unique constraint.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.get.return_value = make_endpoint()
    session_mock.commit.side_effect = make_integrity_error(
        "23505",
        UNIQUE_CONSTRAINT,
    )
    session = cast(AsyncSession, session_mock)

    with pytest.raises(HTTPException) as captured_error:
        await create_subscription(make_request(), session)

    # A failed commit leaves the session unusable until it is rolled back.
    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value.status_code == status.HTTP_409_CONFLICT
    assert captured_error.value.detail == (
        f"Endpoint '{ENDPOINT_ID}' is already subscribed to '{EVENT_TYPE}'."
    )


@pytest.mark.asyncio
async def test_create_subscription_handles_endpoint_deleted_during_commit() -> None:
    # Arrange: the lookup succeeds, but a concurrent delete causes PostgreSQL's
    # foreign-key constraint to reject the later INSERT.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.get.return_value = make_endpoint()
    session_mock.commit.side_effect = make_integrity_error(
        "23503",
        FOREIGN_KEY_CONSTRAINT,
    )
    session = cast(AsyncSession, session_mock)

    with pytest.raises(HTTPException) as captured_error:
        await create_subscription(make_request(), session)

    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value.status_code == status.HTTP_404_NOT_FOUND
    assert captured_error.value.detail == f"Endpoint '{ENDPOINT_ID}' was not found."


@pytest.mark.asyncio
async def test_create_subscription_reraises_unknown_integrity_error() -> None:
    # Arrange: simulate a database constraint failure the route does not know
    # how to translate into a safe public HTTP error.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.get.return_value = make_endpoint()
    integrity_error = make_integrity_error("23505", "another_constraint")
    session_mock.commit.side_effect = integrity_error
    session = cast(AsyncSession, session_mock)

    with pytest.raises(IntegrityError) as captured_error:
        await create_subscription(make_request(), session)

    # We still clean the failed transaction, but do not hide unknown failures.
    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value is integrity_error
