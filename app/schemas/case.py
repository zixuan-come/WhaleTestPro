from pydantic import BaseModel, ConfigDict

class CaseCreate(BaseModel):
    name: str
    interface_id: int
    expected_status: int
    extract_rules: dict | None = None
    assertions: list | None = None
    setup_sql: list | None = None
    teardown_sql: list | None = None
    datasets: list | None = None
    retries: int | None = 0
    tags: list | None = None


class CaseOut(CaseCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)




