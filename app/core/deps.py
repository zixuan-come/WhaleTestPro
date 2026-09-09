"""Shared dependencies.

Project authorization lives in ``app.core.authorization``. Authentication
names remain re-exported here for compatibility with existing callers.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authentication import get_current_user, login_rate_limit, oauth2_scheme
from app.core.authorization import ProjectContext, require_project
from app.database import get_db
from app.models.project import Project
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


def get_current_project(
    context: ProjectContext = Depends(require_project),
) -> Project:
    """Compatibility dependency for read-only callers."""
    return context.project


def get_current_team_member(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TeamMember:
    membership = (
        db.query(TeamMember)
        .filter(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="团队不存在或无权访问",
        )
    return membership


def get_current_team_admin_or_owner(
    membership: TeamMember = Depends(get_current_team_member),
) -> TeamMember:
    if membership.role not in (TeamRole.OWNER.value, TeamRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有团队所有者或管理员可以执行此操作",
        )
    return membership
