from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectRole
from app.models.team_member import TeamMember
from app.repositories import project_member as project_member_repo
from app.repositories import team as team_repo
from app.repositories import user as user_repo
from app.schemas.project_member import ProjectMemberCreate, ProjectMemberRoleUpdate
from app.schemas.team_member import TeamMemberCreate
from app.services import team as team_service


def _project_or_404(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def s_list_by_project(db: Session, project_id: int):
    return project_member_repo.db_list_by_project(db, project_id)


def s_list_candidates(
    db: Session,
    project_id: int,
    keyword: str,
    limit: int,
):
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        raise HTTPException(status_code=422, detail="搜索关键词不能为空")
    project = _project_or_404(db, project_id)
    if project.team_id is not None:
        return team_repo.db_candidates(db, project.team_id, normalized_keyword, limit)
    return project_member_repo.db_list_candidates(
        db, project_id, normalized_keyword, limit
    )


def s_add(
    db: Session,
    project_id: int,
    member: ProjectMemberCreate,
):
    if user_repo.db_get_by_id(db, member.user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    project = _project_or_404(db, project_id)
    if project.team_id is not None:
        team_service.s_add(
            db,
            project.team_id,
            TeamMemberCreate(user_id=member.user_id, role=member.role),
        )
        created = project_member_repo.db_get(db, project_id, member.user_id)
        return project_member_repo.db_get_by_id_for_project(db, project_id, created.id)

    existing = project_member_repo.db_get(db, project_id, member.user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="用户已经是项目成员")
    created = project_member_repo.db_create(
        db, project_id, member.user_id, member.role
    )
    return project_member_repo.db_get_by_id_for_project(db, project_id, created.id)


def s_update_role(
    db: Session,
    project_id: int,
    member_id: int,
    update: ProjectMemberRoleUpdate,
):
    membership = project_member_repo.db_get_by_id_for_project(
        db, project_id, member_id
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    if membership.role == ProjectRole.OWNER.value:
        raise HTTPException(status_code=409, detail="项目所有者角色不能修改")

    project = _project_or_404(db, project_id)
    if project.team_id is not None:
        team_membership = (
            db.query(TeamMember)
            .filter(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == membership.user_id,
            )
            .first()
        )
        if team_membership is None:
            raise HTTPException(status_code=409, detail="项目成员与团队成员数据不一致")
        team_service.s_update_role(
            db, project.team_id, team_membership.id, update.role
        )
        return project_member_repo.db_get_by_id_for_project(
            db, project_id, member_id
        )

    return project_member_repo.db_update_role(db, membership, update.role)


def s_remove(db: Session, project_id: int, member_id: int) -> None:
    membership = project_member_repo.db_get_by_id_for_project(
        db, project_id, member_id
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")
    if membership.role == ProjectRole.OWNER.value:
        raise HTTPException(status_code=409, detail="项目所有者不能被移除")

    project = _project_or_404(db, project_id)
    if project.team_id is not None:
        team_membership = (
            db.query(TeamMember)
            .filter(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == membership.user_id,
            )
            .first()
        )
        if team_membership is None:
            raise HTTPException(status_code=409, detail="项目成员与团队成员数据不一致")
        team_service.s_remove(db, project.team_id, team_membership.id)
        return

    project_member_repo.db_delete(db, membership)
