from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class FieldError(ApiModel):
    field: str
    message: str


class ApiError(ApiModel):
    code: str
    message: str
    field_errors: list[FieldError] | None = None


class ApiErrorEnvelope(ApiModel):
    error: ApiError
    request_id: UUID


class CountMeta(ApiModel):
    count: int
