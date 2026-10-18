import pytest  # pyright: ignore[reportMissingImports]
from sqlalchemy import text

from relaykit.database.engine import dispose_engine, engine


@pytest.mark.asyncio
async def test_database_connection() -> None:
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))

        assert result.scalar_one() == 1
    finally:
        await dispose_engine()