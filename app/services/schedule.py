from sqlalchemy.orm import Session
from app.repositories import schedule as schedule_repo
from app.core import scheduler


def s_create(db: Session, schedule, project_id: int):
    obj = schedule_repo.db_create(db, schedule, project_id)
    # sync_schedule 会读 obj.project_id 塞进 celery args,定时触发的任务就能带上 pid
    scheduler.sync_schedule(obj)
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
