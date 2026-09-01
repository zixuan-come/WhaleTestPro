from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import (
    get_current_project_admin_or_owner,
    get_current_project_member,
    get_current_project_owner,
    get_current_user,
)
from app.database import get_db
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberRoleUpdate,
)
from app.schemas.response import ApiResponse, success_response
from app.schemas.user import UserOut
from app.services import project as project_service
from app.services import project_member as project_member_service


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ApiResponse[ProjectOut], status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = project_service.s_create(db, project, current_user.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"项目名 '{project.name}' 已存在")
    return success_response(result, message="项目创建成功", status_code=201)


@router.get("", response_model=ApiResponse[list[ProjectOut]])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success_response(project_service.s_list(db, current_user.id), message="查询成功")


@router.get("/{project_id}", response_model=ApiResponse[ProjectOut])
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = project_service.s_get(db, project_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return success_response(result, message="查询成功")


@router.put("/{project_id}", response_model=ApiResponse[ProjectOut])
def update_project(
    project_id: int,
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project_admin_or_owner_team),
):
    try:
        result = project_service.s_update(db, current_project.id, project)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"项目名 '{project.name}' 已存在")
    return success_response(result, message="项目更新成功")


@router.get("/{project_id}/members", response_model=ApiResponse[list[ProjectMemberOut]])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_member),
):
    result = project_member_service.s_list_by_project(db, current_membership.project_id)
    return success_response(result, message="查询成功")


@router.get("/{project_id}/member-candidates", response_model=ApiResponse[list[UserOut]])
def list_project_member_candidates(
    project_id: int,
    keyword: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_admin_or_owner),
):
    result = project_member_service.s_list_candidates(
        db, current_membership.project_id, keyword, limit
    )
    return success_response(result, message="查询成功")


@router.post("/{project_id}/members", response_model=ApiResponse[ProjectMemberOut], status_code=201)
def add_project_member(
    project_id: int,
    member: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_admin_or_owner),
):
    try:
        result = project_member_service.s_add(db, current_membership.project_id, member)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户已经是项目成员")
    return success_response(result, message="成员添加成功", status_code=201)


@router.patch("/{project_id}/members/{member_id}", response_model=ApiResponse[ProjectMemberOut])
def update_project_member_role(
    project_id: int,
    member_id: int,
    update: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_admin_or_owner),
):
    result = project_member_service.s_update_role(
        db, current_membership.project_id, member_id, update
    )
    return success_response(result, message="成员角色更新成功")


@router.delete("/{project_id}/members/{member_id}", response_model=ApiResponse[None])
def remove_project_member(
    project_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_admin_or_owner),
):
    project_member_service.s_remove(db, current_membership.project_id, member_id)
    return success_response(data=None, message="成员移除成功")


@router.delete("/{project_id}", response_model=ApiResponse[ProjectOut])
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project_admin_or_owner_team),
):
    try:
        result = project_service.s_delete(db, current_project.id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="项目仍有关联资源，暂时无法删除")
    if result is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return success_response(result, message="项目删除成功")