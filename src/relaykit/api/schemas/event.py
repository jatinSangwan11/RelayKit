from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventPublishRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: str = Field(
        alias="type",
        min_length=1,
        max_length=100,
    )
    data: dict[str, object]


class EventPublishResponse(BaseModel):
    model_config = ConfigDict(validate_by_name=True)

    event_id: str = Field(alias="eventId")
    delivery_ids: list[str] = Field(alias="deliveryIds")
    status: Literal["accepted"]
