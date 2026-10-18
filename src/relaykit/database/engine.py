from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from relaykit.settings import settings

engine: AsyncEngine = create_async_engine(
    str(settings.database_url),
)


async def dispose_engine() -> None:
    await engine.dispose()