from pydantic import BaseModel, ConfigDict, Field


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    endpoint_id: str = Field(
        # `endpoint_id` is the internal Python field name.
        # `alias="endpointId"` maps the external camelCase JSON key to it.
        # Client sends `endpointId`; Python accesses it as `request.endpoint_id`.
        alias="endpointId",
        pattern=r"^ep_[0-9a-f]{32}$",
    )
    event_type: str = Field(
        alias="eventType",
        min_length=1,
        max_length=100,
    )


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_by_name=True,
    )

    id: str
    endpoint_id: str = Field(alias="endpointId")
    event_type: str = Field(alias="eventType")
