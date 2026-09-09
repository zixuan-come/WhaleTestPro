from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.environment import EnvironmentCreate, EnvironmentOut
from app.schemas.response import ApiResponse, success_response
from app.services import environment as env_service


router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("", response_model=ApiResponse[EnvironmentOut], status_code=201)
def create_environment(
    env: EnvironmentCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.ENVIRONMENT, Action.WRITE)),
):
    return success_response(
        env_service.s_create(db, env, context.project_id),
        message="环境创建成功",
        status_code=201,
    )


@router.get("/{env_id}", response_model=ApiResponse[EnvironmentOut])
def get_environment(
    env_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.ENVIRONMENT, Action.READ)),
):
    result = env_service.s_get(db, env_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[EnvironmentOut]])
def list_environment(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.ENVIRONMENT, Action.READ)),
):
    return success_response(env_service.s_list(db, context.project_id), message="查询成功")


@router.put("/{env_id}", response_model=ApiResponse[EnvironmentOut])
def update_environment(
    env_id: int,
    env: EnvironmentCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.ENVIRONMENT, Action.WRITE)),
):
    result = env_service.s_update(db, env_id, env, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return success_response(result, message="环境更新成功")


@router.delete("/{env_id}", response_model=ApiResponse[EnvironmentOut])
def delete_environment(
    env_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.ENVIRONMENT, Action.WRITE)),
):
    result = env_service.s_delete(db, env_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return success_response(result, message="环境删除成功")
