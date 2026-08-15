from sqlalchemy.orm import Session
from app.repositories import project as project_repo
from app.schemas.project import ProjectCreate, ProjectUpdate


def s_create(db: Session, project: ProjectCreate, owner_id: int):
    return project_repo.db_create(db, project, owner_id)


def s_get(db: Session, project_id: int, user_id: int):
    return project_repo.db_get_for_user(db, project_id, user_id)


def s_list(db: Session, user_id: int):
    return project_repo.db_list_for_user(db, user_id)


def s_update(db: Session, project_id: int, project: ProjectUpdate):
    return project_repo.db_update(db, project_id, project)


def s_delete(db: Session, project_id: int):
    return project_repo.db_delete(db, project_id)
