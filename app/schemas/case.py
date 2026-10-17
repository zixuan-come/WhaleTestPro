from pydantic import ConfigDict, Field, field_serializer
from typing import Any
from app.schemas.base import NamedSchema
from app.schemas.request_config import RequestOverrides

class CaseCreate(NamedSchema):
    interface_id: int
    expected_status: int
    extract_rules: dict | None = None
    assertions: list | None = None
    setup_sql: list | None = None
    teardown_sql: list | None = None
    datasets: list[dict[str, Any]] | None = None
    retries: int | None = Field(default=0, ge=0)
    tags: list | None = None
    request_overrides: RequestOverrides | None = None

    @field_serializer("request_overrides")
    def serialize_request_overrides(self, value):
        # Preserve the distinction between inheriting a field and clearing it.
        return value.model_dump(exclude_unset=True) if value is not None else None


class CaseUpdate(CaseCreate):
    pass


class CaseOut(CaseCreate):
    # Historical invalid rows remain inspectable, but cannot be written again.
    datasets: list | None = None
    id: int
    model_config = ConfigDict(from_attributes=True)




