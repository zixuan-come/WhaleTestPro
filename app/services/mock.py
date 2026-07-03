from sqlalchemy.orm import Session
from app.repositories import mock as mock_repo


def s_create(db: Session, mock, project_id: int):
    return mock_repo.db_create(db, mock, project_id)


def s_get(db: Session, mock_id: int, project_id: int):
    return mock_repo.db_get(db, mock_id, project_id)


def s_list(db: Session, project_id: int):
    return mock_repo.db_list(db, project_id)


def s_update(db: Session, mock_id: int, mock, project_id: int):
    return mock_repo.db_update(db, mock_id, mock, project_id)


def s_delete(db: Session, mock_id: int, project_id: int):
    return mock_repo.db_delete(db, mock_id, project_id)


def s_match(db: Session, project_id: int, path: str, method: str):
    return mock_repo.db_match(db, project_id, path, method)
