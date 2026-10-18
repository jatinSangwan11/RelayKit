import pytest  # pyright: ignore[reportMissingImports]
from sqlalchemy import text

from relaykit.database.engine import dispose_engine
from relaykit.database.session import async_session_factory


@pytest.mark.asyncio
async def test_database_session() -> None:
    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
    finally:
        await dispose_engine()

