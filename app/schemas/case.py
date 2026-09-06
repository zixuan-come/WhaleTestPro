from pydantic import ConfigDict, Field
from app.schemas.base import NamedSchema

class CaseCreate(NamedSchema):
    interface_id: int
    expected_status: int
    extract_rules: dict | None = None
    assertions: list | None = None
    setup_sql: list | None = None
    teardown_sql: list | None = None
    datasets: list | None = None
    retries: int | None = Field(default=0, ge=0)
    tags: list | None = None


class CaseUpdate(CaseCreate):
    pass


class CaseOut(CaseCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)




