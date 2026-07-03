from sqlalchemy.orm import Session
from app.repositories import environment as env_repo


def s_create(db: Session, env, project_id: int):
    return env_repo.db_create(db, env, project_id)


def s_get(db: Session, env_id: int, project_id: int):
    return env_repo.db_get(db, env_id, project_id)


def s_list(db: Session, project_id: int):
    return env_repo.db_list(db, project_id)


def s_update(db: Session, env_id: int, env, project_id: int):
    return env_repo.db_update(db, env_id, env, project_id)


def s_delete(db: Session, env_id: int, project_id: int):
    return env_repo.db_delete(db, env_id, project_id)
