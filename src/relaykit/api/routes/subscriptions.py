from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.dependencies.database import get_session
from relaykit.api.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
)
from relaykit.database.models.endpoint import Endpoint
from relaykit.database.models.subscription import Subscription

router = APIRouter(prefix="/v1/subscriptions", tags=["subscriptions"])

_UNIQUE_VIOLATION_SQLSTATE = "23505"
_FOREIGN_KEY_VIOLATION_SQLSTATE = "23503"
_SUBSCRIPTION_UNIQUE_CONSTRAINT = "uq_subscriptions_event_type_endpoint_id"
_SUBSCRIPTION_ENDPOINT_FOREIGN_KEY = (
    "fk_subscriptions_endpoint_id_endpoints"
)


def _matches_constraint(
    error: IntegrityError,
    *,
    sqlstate: str,
    constraint_name: str,
) -> bool:
    database_error = error.orig
    driver_error = getattr(database_error, "orig", None)

    return bool(
        getattr(database_error, "sqlstate", None) == sqlstate
        and getattr(driver_error, "constraint_name", None) == constraint_name
    )


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    request: SubscriptionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Subscription:
    endpoint = await session.get(Endpoint, request.endpoint_id)

    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Endpoint '{request.endpoint_id}' was not found.",
        )

    subscription = Subscription(
        id=f"sub_{uuid4().hex}",
        endpoint_id=request.endpoint_id,
        event_type=request.event_type,
    )
    session.add(subscription)

    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()

        if _matches_constraint(
            error,
            sqlstate=_UNIQUE_VIOLATION_SQLSTATE,
            constraint_name=_SUBSCRIPTION_UNIQUE_CONSTRAINT,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Endpoint '{request.endpoint_id}' is already subscribed "
                    f"to '{request.event_type}'."
                ),
            ) from error

        if _matches_constraint(
            error,
            sqlstate=_FOREIGN_KEY_VIOLATION_SQLSTATE,
            constraint_name=_SUBSCRIPTION_ENDPOINT_FOREIGN_KEY,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint '{request.endpoint_id}' was not found.",
            ) from error

        raise

    return subscription
