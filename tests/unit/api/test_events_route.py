from collections.abc import Sequence
from typing import cast
from unittest.mock import AsyncMock

import pytest  # pyright: ignore[reportMissingImports]
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.routes.events import publish_event
from relaykit.api.schemas.event import EventPublishRequest
from relaykit.database.models.delivery import Delivery
from relaykit.database.models.event import Event

ACCOUNTING_ENDPOINT_ID = f"ep_{'a' * 32}"
ANALYTICS_ENDPOINT_ID = f"ep_{'b' * 32}"


class FakeScalarResult:
    def __init__(self, values: Sequence[str]) -> None:
        self._values = values

    def all(self) -> Sequence[str]:
        return self._values


def make_request() -> EventPublishRequest:
    return EventPublishRequest.model_validate(
        {
            "type": "payment.completed",
            "data": {"paymentId": "pay_123", "amount": 4999},
        }
    )


@pytest.mark.asyncio
async def test_publish_event_creates_event_and_delivery_per_endpoint() -> None:
    # Arrange: two subscriptions match the event type.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.scalars.return_value = FakeScalarResult(
        [ACCOUNTING_ENDPOINT_ID, ANALYTICS_ENDPOINT_ID]
    )
    session = cast(AsyncSession, session_mock)

    # Act: call the route directly with an already validated request.
    response = await publish_event(make_request(), session)

    # Assert: the subscription lookup happened once and the complete unit of
    # work was flushed and committed without a rollback.
    session_mock.scalars.assert_awaited_once()
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_awaited_once_with()
    session_mock.rollback.assert_not_awaited()

    event = session_mock.add.call_args.args[0]
    deliveries = session_mock.add_all.call_args.args[0]

    assert isinstance(event, Event)
    assert event.id.startswith("evt_")
    assert len(event.id) == 36
    assert event.event_type == "payment.completed"
    assert event.data == {"paymentId": "pay_123", "amount": 4999}

    assert len(deliveries) == 2
    assert all(isinstance(delivery, Delivery) for delivery in deliveries)
    assert [delivery.endpoint_id for delivery in deliveries] == [
        ACCOUNTING_ENDPOINT_ID,
        ANALYTICS_ENDPOINT_ID,
    ]
    assert all(delivery.event_id == event.id for delivery in deliveries)
    assert all(delivery.status == "pending" for delivery in deliveries)

    assert response.event_id == event.id
    assert response.delivery_ids == [delivery.id for delivery in deliveries]
    assert response.status == "accepted"


@pytest.mark.asyncio
async def test_publish_event_accepts_event_with_zero_subscriptions() -> None:
    # An event remains a valid fact even when the subscription lookup returns
    # no endpoints, so the route stores one event and creates zero deliveries.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.scalars.return_value = FakeScalarResult([])
    session = cast(AsyncSession, session_mock)

    response = await publish_event(make_request(), session)

    session_mock.add.assert_called_once()
    session_mock.add_all.assert_called_once_with([])
    session_mock.flush.assert_awaited_once_with()
    session_mock.commit.assert_awaited_once_with()
    session_mock.rollback.assert_not_awaited()
    assert response.delivery_ids == []
    assert response.status == "accepted"


@pytest.mark.asyncio
async def test_publish_event_rolls_back_and_reraises_database_failure() -> None:
    # The event may have been flushed, but it is still uncommitted. A commit
    # failure must roll back the event and every delivery as one unit.
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.scalars.return_value = FakeScalarResult([ACCOUNTING_ENDPOINT_ID])
    database_error = SQLAlchemyError("database unavailable")
    session_mock.commit.side_effect = database_error
    session = cast(AsyncSession, session_mock)

    with pytest.raises(SQLAlchemyError) as captured_error:
        await publish_event(make_request(), session)

    session_mock.flush.assert_awaited_once_with()
    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value is database_error
