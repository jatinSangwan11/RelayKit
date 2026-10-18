from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EndpointCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl    # accepts: http, https, localhost


class EndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: HttpUrl
    status: str
