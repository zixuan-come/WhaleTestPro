from pydantic import ConfigDict
from datetime import datetime
from app.schemas.base import NamedSchema

class ProjectCreate(NamedSchema):
    description: str | None = None


class ProjectUpdate(ProjectCreate):
    pass


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)



