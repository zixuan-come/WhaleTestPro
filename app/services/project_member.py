from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.project_member import ProjectRole
from app.repositories import project_member as project_member_repo
from app.repositories import user as user_repo
from app.schemas.project_member import ProjectMemberCreate, ProjectMemberRoleUpdate


def s_list_by_project(
    db: Session,
    project_id: int,
):
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

    return project_member_repo.db_list_candidates(
        db,
        project_id,
        normalized_keyword,
        limit,
    )


def s_add(
    db: Session,
    project_id: int,
    member: ProjectMemberCreate,
):
    user = user_repo.db_get_by_id(db, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    existing = project_member_repo.db_get(db, project_id, member.user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="用户已经是项目成员")

    return project_member_repo.db_create(
        db,
        project_id,
        member.user_id,
        member.role,
    )


def s_update_role(
    db: Session,
    project_id: int,
    member_id: int,
    update: ProjectMemberRoleUpdate,
):
    membership = project_member_repo.db_get_by_id_for_project(
        db,
        project_id,
        member_id,
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")

    if membership.role == ProjectRole.OWNER.value:
        raise HTTPException(status_code=409, detail="项目所有者角色不能修改")

    return project_member_repo.db_update_role(
        db,
        membership,
        update.role,
    )


def s_remove(
    db: Session,
    project_id: int,
    member_id: int,
) -> None:
    membership = project_member_repo.db_get_by_id_for_project(
        db,
        project_id,
        member_id,
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="项目成员不存在")

    if membership.role == ProjectRole.OWNER.value:
        raise HTTPException(status_code=409, detail="项目所有者不能被移除")

    project_member_repo.db_delete(db, membership)
