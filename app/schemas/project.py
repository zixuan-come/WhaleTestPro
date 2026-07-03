from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)



