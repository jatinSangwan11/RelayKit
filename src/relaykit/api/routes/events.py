from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from relaykit.api.dependencies.database import get_session
from relaykit.api.schemas.event import EventPublishRequest, EventPublishResponse
from relaykit.database.models.delivery import Delivery
from relaykit.database.models.event import Event
from relaykit.database.models.subscription import Subscription

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.post(
    "",
    response_model=EventPublishResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def publish_event(
    request: EventPublishRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventPublishResponse:
    event = Event(
        id=f"evt_{uuid4().hex}",
        event_type=request.event_type,
        data=request.data,
    )

    try:
        endpoint_ids = (
            await session.scalars( # I selected one scalar column. Just give me the actual values from that column.
                select(Subscription.endpoint_id)
                .where(Subscription.event_type == request.event_type)
                .order_by(Subscription.endpoint_id)
            )
        ).all()

        deliveries = [
            Delivery(
                id=f"del_{uuid4().hex}",
                event_id=event.id,
                endpoint_id=endpoint_id,
                status="pending",
            )
            for endpoint_id in endpoint_ids
        ]

        session.add(event)
        await session.flush()

        session.add_all(deliveries)
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    return EventPublishResponse(
        event_id=event.id,
        delivery_ids=[delivery.id for delivery in deliveries],
        status="accepted",
    )



""" 
Sure — here’s the short note with the same example flow.

### `session.scalars()` + `.all()` example

Suppose the query is:

```python
stmt = select(Subscription.endpoint_id)
```

And PostgreSQL returns:

```text
endpoint_id
-----------
ep_1
ep_2
ep_3
```

If you use:

```python
result = await session.execute(stmt)
rows = result.all()
```

you get row-like values:

```python
[
    ("ep_1",),
    ("ep_2",),
    ("ep_3",),
]
```

Because `execute()` returns rows.

But if you use:

```python
result = await session.scalars(stmt)
```

SQLAlchemy extracts the first selected value from each row:

```text
ep_1
ep_2
ep_3
```

Then:

```python
endpoint_ids = result.all()
```

collects those values together:

```python
[
    "ep_1",
    "ep_2",
    "ep_3",
]
```

So remember this flow:

```text
PostgreSQL result

ep_1
ep_2
ep_3

      ↓ session.execute()

("ep_1",)
("ep_2",)
("ep_3",)

      ↓ session.scalars()

ep_1
ep_2
ep_3

      ↓ .all()

["ep_1", "ep_2", "ep_3"]
```

In short:

```text
execute()
→ rows

scalars()
→ individual values instead of row wrappers

.all()
→ collect all those values
```

So for this:

```python
endpoint_ids = (
    await session.scalars(
        select(Subscription.endpoint_id)
    )
).all()
```

the final result is simply:

```python
endpoint_ids = ["ep_1", "ep_2", "ep_3"]
```

"""