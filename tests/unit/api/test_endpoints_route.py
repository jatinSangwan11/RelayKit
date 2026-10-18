from typing import cast
from unittest.mock import AsyncMock

import pytest  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.routes.endpoints import create_endpoint
from relaykit.api.schemas.endpoint import EndpointCreate


class FakeDriverError(Exception):
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class FakeDatabaseError(Exception):
    sqlstate = "23505"

    def __init__(self, constraint_name: str) -> None:
        self.orig = FakeDriverError(constraint_name)


def make_integrity_error(constraint_name: str) -> IntegrityError:
    return IntegrityError(
        statement="INSERT INTO endpoints ...",
        params={},
        orig=FakeDatabaseError(constraint_name),
    )


@pytest.mark.asyncio
async def test_create_endpoint_commits_and_returns_endpoint() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    session = cast(AsyncSession, session_mock)
    request = EndpointCreate(
        name="accounting",
        url="http://localhost:4000/webhooks",
    )

    endpoint = await create_endpoint(request, session)

    session_mock.add.assert_called_once_with(endpoint)
    session_mock.commit.assert_awaited_once_with()
    session_mock.rollback.assert_not_awaited()
    assert endpoint.id.startswith("ep_")
    assert len(endpoint.id) == 35
    assert endpoint.name == "accounting"
    assert endpoint.url == "http://localhost:4000/webhooks"
    assert endpoint.status == "active"


@pytest.mark.asyncio
async def test_create_endpoint_rolls_back_duplicate_name() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    session_mock.commit.side_effect = make_integrity_error("endpoints_name_key")
    session = cast(AsyncSession, session_mock)
    request = EndpointCreate(
        name="accounting",
        url="http://localhost:4000/webhooks",
    )

    with pytest.raises(HTTPException) as captured_error:
        await create_endpoint(request, session)

    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value.status_code == status.HTTP_409_CONFLICT
    assert captured_error.value.detail == (
        "An endpoint named 'accounting' already exists."
    )


@pytest.mark.asyncio
async def test_create_endpoint_reraises_unexpected_integrity_error() -> None:
    session_mock = AsyncMock(spec=AsyncSession)
    integrity_error = make_integrity_error("another_constraint")
    session_mock.commit.side_effect = integrity_error
    session = cast(AsyncSession, session_mock)
    request = EndpointCreate(
        name="accounting",
        url="http://localhost:4000/webhooks",
    )

    with pytest.raises(IntegrityError) as captured_error:
        await create_endpoint(request, session)

    session_mock.rollback.assert_awaited_once_with()
    assert captured_error.value is integrity_error
