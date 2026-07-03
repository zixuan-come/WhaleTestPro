from sqlalchemy.orm import Session
from app.repositories import traffic_record as traffic_record_repo


def s_create(db: Session, record):
    # record.project_id 由 middleware 塞入,repo 直接 dump 即可
    return traffic_record_repo.db_create(db, record)


def s_get(db: Session, record_id: int, project_id: int):
    return traffic_record_repo.db_get(db, record_id, project_id)


def s_list(db: Session, project_id: int, limit: int = 100):
    return traffic_record_repo.db_list(db, project_id, limit)
