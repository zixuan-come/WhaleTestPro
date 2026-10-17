from datetime import datetime
from typing import Literal
from pydantic import AliasPath, BaseModel, ConfigDict, Field
from app.schemas.user import UserOut

class TeamInvitationCreate(BaseModel):
    user_id: int
    role: Literal['admin', 'member'] = 'member'

class TeamInvitationOut(BaseModel):
    id: int
    team_id: int
    team_name: str = Field(validation_alias=AliasPath('team', 'name'))
    inviter_id: int
    invitee_id: int
    role: str
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    inviter: UserOut
    invitee: UserOut
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TeamInvitationPage(BaseModel):
    items: list[TeamInvitationOut]
    total: int
    page: int
    page_size: int
    total_pages: int
