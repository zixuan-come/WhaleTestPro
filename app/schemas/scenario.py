from datetime import datetime
from pydantic import ConfigDict
from app.schemas.base import NamedSchema


class ScenarioCreate(NamedSchema):
    description: str | None = None
    case_ids: list[int] = []


class ScenarioOut(ScenarioCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
