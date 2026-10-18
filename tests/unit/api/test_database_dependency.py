from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from unittest.mock import AsyncMock

import pytest  # pyright: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.dependencies import database


@pytest.mark.asyncio
async def test_get_session_keeps_context_open_until_dependency_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_events: list[str] = []
    fake_session = cast(AsyncSession, AsyncMock(spec=AsyncSession))

    @asynccontextmanager
    async def fake_session_factory() -> AsyncIterator[AsyncSession]:
        lifecycle_events.append("opened")
        try:
            yield fake_session
        finally:
            lifecycle_events.append("closed")

    monkeypatch.setattr(database, "async_session_factory", fake_session_factory)

    dependency = database.get_session()
    yielded_session = await anext(dependency)

    assert yielded_session is fake_session
    assert lifecycle_events == ["opened"]

    await dependency.aclose()

    assert lifecycle_events == ["opened", "closed"]
