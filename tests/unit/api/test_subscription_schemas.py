from types import SimpleNamespace

import pytest  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError

from relaykit.api.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
)

ENDPOINT_ID = f"ep_{'a' * 32}"
SUBSCRIPTION_ID = f"sub_{'b' * 32}"


def test_subscription_create_maps_aliases_and_trims_event_type() -> None:
    # API clients send camelCase keys. Pydantic should expose clean snake_case
    # attributes to the Python route after validation.
    request = SubscriptionCreate.model_validate(
        {
            "endpointId": ENDPOINT_ID,
            "eventType": "  payment.completed  ",
        }
    )

    assert request.endpoint_id == ENDPOINT_ID
    assert request.event_type == "payment.completed"


@pytest.mark.parametrize(
    "payload",
    [
        {"endpointId": "ep_too-short", "eventType": "payment.completed"},
        {"endpointId": ENDPOINT_ID, "eventType": "   "},
        {"endpointId": ENDPOINT_ID, "eventType": "a" * 101},
    ],
)
def test_subscription_create_rejects_invalid_input(
    payload: dict[str, str],
) -> None:
    # FastAPI uses this same Pydantic validation before the route runs. A
    # ValidationError here becomes an HTTP 422 response at the API boundary.
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(payload)


def test_subscription_create_requires_public_aliases() -> None:
    # The public request contract is camelCase. Internal snake_case names are
    # intentionally not accepted from API clients by this request schema.
    with pytest.raises(ValidationError):
        SubscriptionCreate.model_validate(
            {
                "endpoint_id": ENDPOINT_ID,
                "event_type": "payment.completed",
            }
        )


def test_subscription_response_reads_object_and_serializes_aliases() -> None:
    # This object has the same attribute names as a SQLAlchemy Subscription.
    subscription_row = SimpleNamespace(
        id=SUBSCRIPTION_ID,
        endpoint_id=ENDPOINT_ID,
        event_type="payment.completed",
    )

    response = SubscriptionResponse.model_validate(subscription_row)

    # FastAPI serializes response models with aliases, so the client receives
    # camelCase even though Python and PostgreSQL use snake_case.
    assert response.model_dump(by_alias=True) == {
        "id": SUBSCRIPTION_ID,
        "endpointId": ENDPOINT_ID,
        "eventType": "payment.completed",
    }
