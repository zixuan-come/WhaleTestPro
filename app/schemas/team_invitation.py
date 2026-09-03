from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.schemas.user import UserOut

class TeamInvitationCreate(BaseModel):
    user_id: int
    role: Literal['admin', 'member'] = 'member'

class TeamInvitationOut(BaseModel):
    id: int
    team_id: int
    inviter_id: int
    invitee_id: int
    role: str
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    inviter: UserOut
    invitee: UserOut
    model_config = ConfigDict(from_attributes=True)
