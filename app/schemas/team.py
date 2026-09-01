from datetime import datetime
from pydantic import ConfigDict, Field
from app.schemas.base import NamedSchema


class TeamCreate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)


class TeamUpdate(TeamCreate):
    pass


class TeamOut(TeamCreate):
    id: int
    owner_id: int
    created_at: datetime
    role: str | None = None
    model_config = ConfigDict(from_attributes=True)
