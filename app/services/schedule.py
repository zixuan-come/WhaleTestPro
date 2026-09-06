from sqlalchemy.orm import Session
from app.repositories import schedule as schedule_repo
from app.core import scheduler


def s_create(db: Session, schedule, project_id: int):
    obj = schedule_repo.db_create(db, schedule, project_id)
    try:
        scheduler.sync_schedule(obj)
    except Exception:
        try:
            db.delete(obj)
            db.commit()
        except Exception:
            db.rollback()
        raise
    return obj


def s_get(db: Session, schedule_id: int, project_id: int):
    return schedule_repo.db_get(db, schedule_id, project_id)


def s_list(db: Session, project_id: int):
    return schedule_repo.db_list(db, project_id)


def s_update(db: Session, schedule_id: int, schedule, project_id: int):
    obj = schedule_repo.db_update(db, schedule_id, schedule, project_id)
    if obj is not None:
        scheduler.sync_schedule(obj)
    return obj


def s_delete(db: Session, schedule_id: int, project_id: int):
    obj = schedule_repo.db_delete(db, schedule_id, project_id)
    if obj is not None:
        scheduler.remove_schedule(schedule_id)
    return obj

