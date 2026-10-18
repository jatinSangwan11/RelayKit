from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.database.session import async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session: # we are not using await here coz async with hides the await inside
        yield session

# this is more explaicit verison of it 
# async def get_session() -> AsyncGenerator[AsyncSession]:
#     session = async_session_factory()

#     try:
#         yield session
#     finally:
#         await session.close()


"""
1. HTTP request arrives
2. FastAPI starts get_session()
3. Session factory creates Session A
4. Execution reaches yield
5. Session A is given to the route
6. get_session() pauses
7. Route uses Session A
8. Route commits its transaction
9. Route produces its response
10. FastAPI resumes get_session()
11. Execution leaves async with
12. Session A is closed
13. Its connection returns to the pool
"""