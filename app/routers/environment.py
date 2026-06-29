from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.environment import EnvironmentCreate, EnvironmentOut
from app.services import environment as env_service


router = APIRouter(prefix="/environments", tags=["environments"])


@router.post("", response_model=EnvironmentOut)
def create_environment(env: EnvironmentCreate, db: Session = Depends(get_db)):
    return env_service.s_create(db, env)


@router.get("/{env_id}", response_model=EnvironmentOut)
def get_environment(env_id: int, db: Session = Depends(get_db)):
    return env_service.s_get(db, env_id)


@router.get("", response_model=list[EnvironmentOut])
def list_environment(db: Session = Depends(get_db)):
    return env_service.s_list(db)


@router.put("/{env_id}", response_model=EnvironmentOut)
def update_environment(env_id: int, env: EnvironmentCreate, db: Session = Depends(get_db)):
    return env_service.s_update(db, env_id, env)


@router.delete("/{env_id}", response_model=EnvironmentOut)
def delete_environment(env_id: int, db: Session = Depends(get_db)):
    return env_service.s_delete(db, env_id)
