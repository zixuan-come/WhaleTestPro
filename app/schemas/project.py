from pydantic import ConfigDict, Field
from datetime import datetime
from app.schemas.base import NamedSchema


class ProjectCreate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)
    team_id: int | None = None

class ProjectUpdate(ProjectCreate):
    pass


class ProjectOut(ProjectCreate):
    id: int
    team_id: int | None = None
    team_name: str | None = None
    team_role: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
