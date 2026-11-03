import pytest  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError

from relaykit.api.schemas.event import EventPublishRequest, EventPublishResponse

EVENT_ID = f"evt_{'a' * 32}"
DELIVERY_ID = f"del_{'b' * 32}"


def test_event_publish_request_maps_type_alias_and_trims_value() -> None:
    # API clients send `type`; application code should receive the clearer
    # Python attribute `event_type` after validation.
    request = EventPublishRequest.model_validate(
        {
            "type": "  payment.completed  ",
            "data": {"paymentId": "pay_123", "amount": 4999},
        }
    )

    assert request.event_type == "payment.completed"
    assert request.data == {"paymentId": "pay_123", "amount": 4999}


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {}},
        {"type": "   ", "data": {}},
        {"type": "a" * 101, "data": {}},
        {"type": "payment.completed", "data": []},
    ],
)
def test_event_publish_request_rejects_invalid_payload(
    payload: dict[str, object],
) -> None:
    # FastAPI turns this Pydantic ValidationError into HTTP 422 and does not
    # call the route, so invalid requests cannot create database rows.
    with pytest.raises(ValidationError):
        EventPublishRequest.model_validate(payload)


def test_event_publish_request_requires_public_type_alias() -> None:
    # The public contract accepts `type`; `event_type` remains an internal
    # Python and PostgreSQL name.
    with pytest.raises(ValidationError):
        EventPublishRequest.model_validate(
            {
                "event_type": "payment.completed",
                "data": {},
            }
        )


def test_event_publish_response_serializes_camel_case_aliases() -> None:
    response = EventPublishResponse(
        event_id=EVENT_ID,
        delivery_ids=[DELIVERY_ID],
        status="accepted",
    )

    # FastAPI serializes response models by alias, producing the locked public
    # API contract while Python continues to use snake_case.
    assert response.model_dump(by_alias=True) == {
        "eventId": EVENT_ID,
        "deliveryIds": [DELIVERY_ID],
        "status": "accepted",
    }


def test_event_publish_response_allows_zero_deliveries() -> None:
    response = EventPublishResponse(
        event_id=EVENT_ID,
        delivery_ids=[],
        status="accepted",
    )

    assert response.delivery_ids == []


def test_event_publish_response_rejects_unknown_status() -> None:
    # Literal["accepted"] protects the response contract from accidental
    # values such as `pending` or `completed`.
    with pytest.raises(ValidationError):
        EventPublishResponse.model_validate(
            {
                "eventId": EVENT_ID,
                "deliveryIds": [],
                "status": "completed",
            }
        )
