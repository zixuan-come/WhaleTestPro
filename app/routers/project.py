from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authentication import get_current_user
from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectTeamMove, ProjectUpdate
from app.schemas.project_member import ProjectMemberCreate, ProjectMemberOut, ProjectMemberRoleUpdate
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
    team_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return success_response(project_service.s_list(db, current_user.id, team_id), message="查询成功")


@router.get("/{project_id}", response_model=ApiResponse[ProjectOut])
def get_project(
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT, Action.READ, from_path=True)
    ),
):
    return success_response(context.project, message="查询成功")


@router.put("/{project_id}", response_model=ApiResponse[ProjectOut])
def update_project(
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT, Action.WRITE, from_path=True)
    ),
):
    try:
        result = project_service.s_update(db, context.project_id, project)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"项目名 '{project.name}' 已存在")
    return success_response(result, message="项目更新成功")


@router.get("/{project_id}/members", response_model=ApiResponse[list[ProjectMemberOut]])
def list_project_members(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT_MEMBER, Action.READ, from_path=True)
    ),
):
    result = project_member_service.s_list_by_project(db, context.project_id)
    return success_response(result, message="查询成功")


@router.get("/{project_id}/member-candidates", response_model=ApiResponse[list[UserOut]])
def list_project_member_candidates(
    keyword: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT_MEMBER, Action.MANAGE, from_path=True)
    ),
):
    result = project_member_service.s_list_candidates(
        db, context.project_id, keyword, limit
    )
    return success_response(result, message="查询成功")


@router.post("/{project_id}/members", response_model=ApiResponse[ProjectMemberOut], status_code=201)
def add_project_member(
    member: ProjectMemberCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT_MEMBER, Action.MANAGE, from_path=True)
    ),
):
    try:
        result = project_member_service.s_add(db, context.project_id, member)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户已经是项目成员")
    return success_response(result, message="成员添加成功", status_code=201)


@router.patch("/{project_id}/members/{member_id}", response_model=ApiResponse[ProjectMemberOut])
def update_project_member_role(
    member_id: int,
    update: ProjectMemberRoleUpdate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT_MEMBER, Action.MANAGE, from_path=True)
    ),
):
    result = project_member_service.s_update_role(
        db, context.project_id, member_id, update
    )
    return success_response(result, message="成员角色更新成功")


@router.delete("/{project_id}/members/{member_id}", response_model=ApiResponse[None])
def remove_project_member(
    member_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT_MEMBER, Action.MANAGE, from_path=True)
    ),
):
    project_member_service.s_remove(db, context.project_id, member_id)
    return success_response(data=None, message="成员移除成功")


@router.delete("/{project_id}", response_model=ApiResponse[ProjectOut])
def delete_project(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT, Action.OWNER, from_path=True)
    ),
):
    try:
        result = project_service.s_delete(db, context.project_id)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="项目仍有关联资源，暂时无法删除")
    if result is None:
        raise HTTPException(status_code=404, detail=f"项目 id={context.project_id} 不存在")
    return success_response(result, message="项目删除成功")


@router.post("/{project_id}/move-team", response_model=ApiResponse[ProjectOut])
def move_project_team(
    data: ProjectTeamMove,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(
        authorize(Resource.PROJECT, Action.OWNER, from_path=True)
    ),
):
    result = project_service.s_move_team(
        db, context.project_id, data.team_id, context.user.id
    )
    return success_response(result, message="项目已迁移到目标团队")
