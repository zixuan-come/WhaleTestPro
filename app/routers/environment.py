from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.environment import EnvironmentCreate, EnvironmentOut
from app.services import environment as env_service
from app.core.deps import get_current_project
from app.models.project import Project


router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("", response_model=EnvironmentOut, status_code=201)
def create_environment(
    env: EnvironmentCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return env_service.s_create(db, env, current_project.id)


@router.get("/{env_id}", response_model=EnvironmentOut)
def get_environment(
    env_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    e = env_service.s_get(db, env_id, current_project.id)
    if e is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return e


@router.get("", response_model=list[EnvironmentOut])
def list_environment(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return env_service.s_list(db, current_project.id)


@router.put("/{env_id}", response_model=EnvironmentOut)
def update_environment(
    env_id: int,
    env: EnvironmentCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    e = env_service.s_update(db, env_id, env, current_project.id)
    if e is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return e


@router.delete("/{env_id}", response_model=EnvironmentOut)
def delete_environment(
    env_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    e = env_service.s_delete(db, env_id, current_project.id)
    if e is None:
        raise HTTPException(status_code=404, detail=f"环境 id={env_id} 不存在")
    return e
