from types import SimpleNamespace

import pytest  # pyright: ignore[reportMissingImports]
from pydantic import ValidationError

from relaykit.api.schemas.endpoint import EndpointCreate, EndpointResponse


def test_endpoint_create_trims_name_and_accepts_localhost() -> None:
    endpoint = EndpointCreate(
        name="  accounting  ",
        url="http://localhost:4000/webhooks",
    )

    assert endpoint.name == "accounting"
    assert str(endpoint.url) == "http://localhost:4000/webhooks"


@pytest.mark.parametrize("name", ["   ", "a" * 101])
def test_endpoint_create_rejects_invalid_name(name: str) -> None:
    with pytest.raises(ValidationError):
        EndpointCreate(name=name, url="http://localhost:4000/webhooks")


def test_endpoint_create_rejects_non_http_url() -> None:
    with pytest.raises(ValidationError):
        EndpointCreate(name="accounting", url="ftp://localhost/webhooks")


def test_endpoint_response_reads_and_validates_object_attributes() -> None:
    endpoint_row = SimpleNamespace(
        id="ep_123",
        name="accounting",
        url="http://localhost:4000/webhooks",
        status="active",
    )

    response = EndpointResponse.model_validate(endpoint_row)

    assert response.model_dump(mode="json") == {
        "id": "ep_123",
        "name": "accounting",
        "url": "http://localhost:4000/webhooks",
        "status": "active",
    }


def test_endpoint_response_rejects_invalid_stored_url() -> None:
    endpoint_row = SimpleNamespace(
        id="ep_123",
        name="accounting",
        url="not-a-url",
        status="active",
    )

    with pytest.raises(ValidationError):
        EndpointResponse.model_validate(endpoint_row)
