from app.repositories import schedule as schedule_repo
from app.core import scheduler


def s_create(db, schedule):
    obj = schedule_repo.db_create(db, schedule)
    scheduler.sync_schedule(obj)
    return obj


def s_get(db, schedule_id):
    return schedule_repo.db_get(db, schedule_id)


def s_list(db):
    return schedule_repo.db_list(db)


def s_update(db, schedule_id, schedule):
    obj = schedule_repo.db_update(db, schedule_id, schedule)
    if obj is not None:
        scheduler.sync_schedule(obj)
    return obj


def s_delete(db, schedule_id):
    obj = schedule_repo.db_delete(db, schedule_id)
    if obj is not None:
        scheduler.remove_schedule(schedule_id)
    return obj





