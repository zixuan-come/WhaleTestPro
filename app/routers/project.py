from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberOut,
    ProjectMemberRoleUpdate,
)
from app.schemas.user import UserOut
from app.services import project as project_service
from app.services import project_member as project_member_service
from app.core.deps import (
    get_current_project_admin_or_owner,
    get_current_project_member,
    get_current_project_owner,
    get_current_user,
)
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # unique=True 冲突时数据库抛 IntegrityError,catch 后转成 409 Conflict
    # 不 catch 的话前端拿到 500,看不出是"重名"还是"服务真挂了"
    try:
        return project_service.s_create(db, project, current_user.id)
    except IntegrityError:
        db.rollback()  # 失败事务必须回滚,否则同一 session 后续查询都会报错
        raise HTTPException(status_code=409, detail=f"项目名 '{project.name}' 已存在")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.s_list(db, current_user.id)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = project_service.s_get(db, project_id, current_user.id)
    # Repository 查不到返 None,Router 层转成 404
    # 不转的话 response_model 会拿 None 去校验 → Pydantic 失败 → 崩 500
    if p is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return p


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project_owner),
):
    try:
        return project_service.s_update(db, current_project.id, project)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"项目名 '{project.name}' 已存在",
        )


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut])
def list_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(get_current_project_member),
):
    return project_member_service.s_list_by_project(
        db,
        current_membership.project_id,
    )


@router.get(
    "/{project_id}/member-candidates",
    response_model=list[UserOut],
)
def list_project_member_candidates(
    project_id: int,
    keyword: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(
        get_current_project_admin_or_owner,
    ),
):
    return project_member_service.s_list_candidates(
        db,
        current_membership.project_id,
        keyword,
        limit,
    )


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: int,
    member: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(
        get_current_project_admin_or_owner,
    ),
):
    try:
        return project_member_service.s_add(
            db,
            current_membership.project_id,
            member,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户已经是项目成员")


@router.patch(
    "/{project_id}/members/{member_id}",
    response_model=ProjectMemberOut,
)
def update_project_member_role(
    project_id: int,
    member_id: int,
    update: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(
        get_current_project_admin_or_owner,
    ),
):
    return project_member_service.s_update_role(
        db,
        current_membership.project_id,
        member_id,
        update,
    )


@router.delete(
    "/{project_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_membership: ProjectMember = Depends(
        get_current_project_admin_or_owner,
    ),
):
    project_member_service.s_remove(
        db,
        current_membership.project_id,
        member_id,
    )


@router.delete("/{project_id}", response_model=ProjectOut)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project_owner),
):
    p = project_service.s_delete(db, current_project.id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"项目 id={project_id} 不存在")
    return p
