from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import decode_access_token
from app.repositories import user as user_repo
from app.repositories import project as project_repo
from app.repositories import project_member as project_member_repo
from app.models.project_member import ProjectMember, ProjectRole
from app.models.team_member import TeamMember, TeamRole
from app.models.team_permission import TeamPermission
from app.core.blacklist import is_blacklisted
from app.core.ratelimit import check_rate_limit
from app.models.project import Project
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = user_repo.db_get_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def login_rate_limit(request: Request):
    ip = request.client.host
    if not check_rate_limit(f"login:{ip}", limit=5, window_seconds=60):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )


def get_current_project(
    request: Request,
    x_project_id: int = Header(..., alias="X-Project-Id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    """
    多项目依赖:从 HTTP header X-Project-Id 读当前项目,校验存在后返回 Project 对象。
    router 里一句 Depends(get_current_project) 就能拿到当前 project,项目不存在自动 404。
    """
    project = project_repo.db_get_for_user(
        db,
        x_project_id,
        current_user.id,
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 id={x_project_id} 不存在",
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        path = request.url.path
        execution_path = path.endswith("/run") or path.startswith("/traffic/replay/") or path.endswith("/chain")
        if not execution_path:
            membership = db.query(TeamMember).filter(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id).first() if project.team_id else None
            legacy = project_member_repo.db_get(db, project.id, current_user.id) if membership is None else None
            role = membership.role if membership else (legacy.role if legacy else None)
            configurable = False
            if membership is not None and membership.role == TeamRole.MEMBER.value:
                permission = "content.write"
                if path.startswith("/interfaces"): permission = "interface.write"
                elif path.startswith("/cases"): permission = "case.write"
                elif path.startswith("/environments"): permission = "environment.write"
                elif path.startswith("/mock"): permission = "mock.write"
                elif path.startswith("/schedules"): permission = "schedule.write"
                elif path.startswith("/perf"): permission = "perf.write"
                elif path.startswith("/scenarios"): permission = "scenario.write"
                configurable = db.query(TeamPermission).filter(TeamPermission.team_id == project.team_id, TeamPermission.role == TeamRole.MEMBER.value, TeamPermission.permission == permission, TeamPermission.enabled.is_(True)).first() is not None
            if role not in (TeamRole.OWNER.value, TeamRole.ADMIN.value, ProjectRole.OWNER.value, ProjectRole.ADMIN.value) and not configurable:
                raise HTTPException(status_code=403, detail="你是团队成员，无权修改项目内容")
    return project


def get_current_project_member(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectMember:
    membership = project_member_repo.db_get(
        db,
        project_id,
        current_user.id,
    )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"项目 id={project_id} 不存在或无权访问",
        )

    return membership


def get_current_project_admin_or_owner(
    membership: ProjectMember = Depends(get_current_project_member),
) -> ProjectMember:
    if membership.role not in (
        ProjectRole.OWNER.value,
        ProjectRole.ADMIN.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有项目所有者或管理员可以管理项目成员",
        )

    return membership


def get_current_project_owner(
    membership: ProjectMember = Depends(get_current_project_member),
) -> Project:
    if membership.role != ProjectRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有项目所有者可以执行此操作",
        )

    return membership.project

# Team-level permission dependencies. Legacy project dependencies remain for backward compatibility.
def get_current_team_member(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TeamMember:
    membership = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == current_user.id).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="团队不存在或无权访问")
    return membership


def get_current_team_admin_or_owner(
    membership: TeamMember = Depends(get_current_team_member),
) -> TeamMember:
    if membership.role not in (TeamRole.OWNER.value, TeamRole.ADMIN.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有团队所有者或管理员可以执行此操作")
    return membership


def get_current_project_member_team(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> ProjectMember:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None: raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    team_membership = db.query(TeamMember).filter(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id).first() if project.team_id else None
    if team_membership is None: raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在或无权访问")
    legacy = project_member_repo.db_get(db, project_id, current_user.id)
    if legacy is None: raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在或无权访问")
    return legacy

def get_current_project_member_team_admin_or_owner(membership: ProjectMember = Depends(get_current_project_member_team)) -> ProjectMember:
    if membership.role not in (ProjectRole.OWNER.value, ProjectRole.ADMIN.value): raise HTTPException(status_code=403, detail="只有团队所有者或管理员可以管理项目成员")
    return membership

def get_current_project_admin_or_owner_team(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None: raise HTTPException(status_code=404, detail=f'项目 id={project_id} 不存在')
    membership = db.query(TeamMember).filter(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id).first() if project.team_id else None
    if membership is not None:
        if membership.role not in (TeamRole.OWNER.value, TeamRole.ADMIN.value): raise HTTPException(status_code=403, detail='你是团队成员，无权修改项目详情或管理成员')
        return project
    legacy = project_member_repo.db_get(db, project_id, current_user.id)
    if legacy is None or legacy.role not in (ProjectRole.OWNER.value, ProjectRole.ADMIN.value): raise HTTPException(status_code=403, detail='你是团队成员，无权修改项目详情或管理成员')
    return project

def get_current_project_team_admin_or_owner(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Project:
    return get_current_project_admin_or_owner_team(project_id, db, current_user)

def get_current_project_owner_team(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None: raise HTTPException(status_code=404, detail=f'项目 id={project_id} 不存在')
    membership = db.query(TeamMember).filter(TeamMember.team_id == project.team_id, TeamMember.user_id == current_user.id).first() if project.team_id else None
    if membership is not None:
        if membership.role != TeamRole.OWNER.value: raise HTTPException(status_code=403, detail='只有团队所有者可以执行此操作')
        return project
    legacy = project_member_repo.db_get(db, project_id, current_user.id)
    if legacy is None or legacy.role != ProjectRole.OWNER.value: raise HTTPException(status_code=403, detail='只有团队所有者可以执行此操作')
    return project
