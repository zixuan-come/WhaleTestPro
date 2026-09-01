from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut


class TeamMemberCreate(BaseModel):
    user_id: int
    role: Literal["admin", "member"] = "member"


class TeamMemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"]


class TeamMemberOut(BaseModel):
    id: int
    team_id: int
    user_id: int
    role: str
    created_at: datetime
    user: UserOut
    model_config = ConfigDict(from_attributes=True)
