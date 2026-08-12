from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.user import UserOut


class ProjectMemberCreate(BaseModel):
    user_id: int
    role: Literal["admin", "member"] = "member"


class ProjectMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"]


class ProjectMemberOut(BaseModel):
    id: int
    project_id: int
    user_id: int
    role: str
    created_at: datetime
    user: UserOut

    model_config = ConfigDict(from_attributes=True)
