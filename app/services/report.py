from sqlalchemy.orm import Session
from app.repositories import report as report_repo


def s_get(db: Session, report_id: int, project_id: int):
    return report_repo.db_get(db, report_id, project_id)


def s_list(db: Session, project_id: int):
    return report_repo.db_list(db, project_id)
