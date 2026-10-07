from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from app.schemas.base import NamedSchema


class ProjectCreate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)
    team_id: int = Field(
        ...,
        gt=0,
        description="所属团队 ID；创建项目前必须先创建或加入团队",
    )


class ProjectUpdate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)


class ProjectOut(ProjectCreate):
    id: int
    team_id: int
    team_name: str | None = None
    team_role: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ProjectTeamMove(BaseModel):
    team_id: int
