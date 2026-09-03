from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.base import NamedSchema


class TeamCreate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)


class TeamUpdate(TeamCreate):
    pass


class TeamTransfer(BaseModel):
    user_id: int


class TeamOut(TeamCreate):
    id: int
    owner_id: int
    created_at: datetime
    role: str | None = None
    model_config = ConfigDict(from_attributes=True)

class TeamPermissionUpdate(BaseModel):
    role: str = 'member'
    permission: str
    enabled: bool

class TeamPermissionOut(TeamPermissionUpdate):
    id: int
    team_id: int
    model_config = ConfigDict(from_attributes=True)