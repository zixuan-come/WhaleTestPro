from sqlalchemy.orm import Session
from app.repositories import project as project_repo
from app.schemas.project import ProjectCreate


def s_create(db: Session, project: ProjectCreate):
    return project_repo.db_create(db, project)


def s_get(db: Session, project_id: int):
    return project_repo.db_get(db, project_id)


def s_list(db: Session):
    return project_repo.db_list(db)


def s_delete(db: Session, project_id: int):
    return project_repo.db_delete(db, project_id)
