from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authentication import get_current_user
from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectOut, ProjectTeamMove, ProjectUpdate
from app.schemas.response import ApiResponse, success_response
from app.services import project as project_service


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
