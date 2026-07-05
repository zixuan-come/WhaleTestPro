from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ScenarioCreate(BaseModel):
    name: str
    description: str | None = None
    case_ids: list[int] = []


class ScenarioOut(ScenarioCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
