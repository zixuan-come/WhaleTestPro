"""Explicit project authorization based on a single resolved context."""

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authentication import get_current_user
from app.core.permissions import Action, Resource, WRITE_PERMISSION_BY_RESOURCE
from app.database import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember, ProjectRole
from app.models.team_member import TeamMember, TeamRole
from app.models.team_permission import TeamPermission
from app.models.user import User


@dataclass(frozen=True)
class ProjectContext:
    project: Project
    user: User
    role: str
    team_membership: TeamMember | None
    legacy_membership: ProjectMember | None
    enabled_permissions: frozenset[str]

    @property
    def project_id(self) -> int:
        return self.project.id

    @property
    def team_id(self) -> int | None:
        return self.project.team_id


def resolve_project_context(
    db: Session,
    project_id: int,
    user: User,
) -> ProjectContext | None:
    """Resolve membership without allowing legacy rows to elevate team access."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return None

    legacy = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
        .first()
    )

    if project.team_id is not None:
        team_membership = (
            db.query(TeamMember)
            .filter(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user.id,
            )
            .first()
        )
        if team_membership is None:
            return None
        role = team_membership.role
        permission_rows = (
            db.query(TeamPermission.permission)
            .filter(
                TeamPermission.team_id == project.team_id,
                TeamPermission.role == role,
                TeamPermission.enabled.is_(True),
            )
            .all()
        )
        enabled_permissions = frozenset(row[0] for row in permission_rows)
    else:
        if legacy is None:
            return None
        team_membership = None
        role = legacy.role
        enabled_permissions = frozenset()

    return ProjectContext(
        project=project,
        user=user,
        role=role,
        team_membership=team_membership,
        legacy_membership=legacy,
        enabled_permissions=enabled_permissions,
    )


def is_allowed(context: ProjectContext, resource: Resource, action: Action) -> bool:
    if context.role in (TeamRole.OWNER.value, ProjectRole.OWNER.value):
        return True
    if context.role in (TeamRole.ADMIN.value, ProjectRole.ADMIN.value):
        return action is not Action.OWNER
    if context.role not in (TeamRole.MEMBER.value, ProjectRole.MEMBER.value):
        return False
    if action in (Action.READ, Action.EXECUTE):
        return True
    if action is Action.WRITE:
        permission = WRITE_PERMISSION_BY_RESOURCE.get(resource)
        return permission is not None and permission in context.enabled_permissions
    return False


def _context_or_404(db: Session, project_id: int, user: User) -> ProjectContext:
    context = resolve_project_context(db, project_id, user)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 id={project_id} 不存在或无权访问",
        )
    return context


def require_project(
    x_project_id: int = Header(..., alias="X-Project-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectContext:
    return _context_or_404(db, x_project_id, current_user)


def require_project_from_path(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectContext:
    return _context_or_404(db, project_id, current_user)


def authorize(
    resource: Resource,
    action: Action,
    *,
    from_path: bool = False,
) -> Callable[..., ProjectContext]:
    resolver = require_project_from_path if from_path else require_project

    def dependency(
        context: ProjectContext = Depends(resolver),
    ) -> ProjectContext:
        if not is_allowed(context, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权执行 {resource.value}.{action.value} 操作",
            )
        return context

    dependency.__name__ = f"authorize_{resource.value}_{action.value}"
    return dependency
