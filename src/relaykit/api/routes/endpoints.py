from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.dependencies.database import get_session
from relaykit.api.schemas.endpoint import EndpointCreate, EndpointResponse
from relaykit.database.models.endpoint import Endpoint

router = APIRouter(prefix="/v1/endpoints", tags=["endpoints"])

_UNIQUE_VIOLATION_SQLSTATE = "23505"
_ENDPOINT_NAME_CONSTRAINT = "endpoints_name_key"


def _is_duplicate_endpoint_name(error: IntegrityError) -> bool:
    database_error = error.orig
    driver_error = getattr(database_error, "orig", None)

    return bool(
        getattr(database_error, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE
        and getattr(driver_error, "constraint_name", None)
        == _ENDPOINT_NAME_CONSTRAINT
    )


@router.post(
    "",
    response_model=EndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint(
    request: EndpointCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Endpoint:
    endpoint = Endpoint(
        id=f"ep_{uuid4().hex}",
        name=request.name,
        url=str(request.url),
        status="active",
    )
    session.add(endpoint) # SQLAlchemy tracks it as pending, no network op

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()

        if _is_duplicate_endpoint_name(error):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An endpoint named '{request.name}' already exists.",
            ) from error

        raise

    return endpoint # the function returns SQLAlchemy object, but FASTAPI returns it as RESPONSE MODEL


# we are also returning invalid request 422 in the route when pydantic validation failedm FASTAPI automatically return it

"""
Duplicate-error lifecycle:

1. session.commit() attempts INSERT
2. PostgreSQL rejects duplicate name
3. SQLAlchemy raises IntegrityError
4. Our except block catches it
5. await session.rollback() runs
6. HTTPException(409) is raised
7. Route stops executing
8. FastAPI resumes/cleans up get_session()
9. async with closes the session
10. FastAPI sends the 409 response
"""