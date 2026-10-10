import logging
from types import SimpleNamespace

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.core import scheduler
from app.models.schedule import Schedule
from app.repositories import schedule as schedule_repo
from app.repositories import schedule_sync as sync_repo
from app.repositories import environment as env_repo
from app.repositories import suite as suite_repo


logger = logging.getLogger(__name__)


def _payload_schedule(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(**payload)


def process_sync_event(db: Session, schedule_id: int) -> bool:
    """Apply one persistent event; RedBeat operations are safe to retry."""
    event = sync_repo.db_get_for_update(db, schedule_id)
    if event is None:
        return True

    try:
        if event.action == "delete":
            scheduler.remove_schedule(event.schedule_id)
        elif event.action == "sync" and event.payload is not None:
            scheduler.sync_schedule(_payload_schedule(event.payload))
        else:
            raise ValueError(f"未知的调度同步动作: {event.action}")
    except Exception as exc:
        event.attempts += 1
        event.last_error = str(exc)[:500]
        schedule = db.get(Schedule, schedule_id)
        if schedule is not None:
            schedule.sync_status = "error"
            schedule.sync_error = event.last_error
        db.commit()
        logger.warning(
            "RedBeat sync failed for schedule %s (attempt %s): %s",
            schedule_id,
            event.attempts,
            exc,
        )
        return False

    schedule = db.get(Schedule, schedule_id)
    if schedule is not None:
        schedule.sync_status = "synced"
        schedule.sync_error = None
    db.delete(event)
    db.commit()
    return True


def reconcile_pending(db: Session, limit: int = 100) -> dict[str, int]:
    schedule_ids = sync_repo.db_pending_ids(db, limit=limit)
    synced = 0
    failed = 0
    for schedule_id in schedule_ids:
        if process_sync_event(db, schedule_id):
            synced += 1
        else:
            failed += 1
    return {"synced": synced, "failed": failed}


def reconcile_desired(db: Session, batch_size: int = 100) -> dict[str, int]:
    """Restore lost RedBeat entries even after their outbox event was drained."""
    repaired = failed = 0
    last_id = 0
    while True:
        ids = [row[0] for row in db.query(Schedule.id).filter(
            Schedule.id > last_id
        ).order_by(Schedule.id).limit(batch_size).all()]
        if not ids:
            break
        for schedule_id in ids:
            schedule = db.query(Schedule).filter(Schedule.id == schedule_id).with_for_update().first()
            if schedule is None:
                db.rollback()
                continue
            try:
                in_sync = scheduler.schedule_is_synced(schedule)
            except Exception:
                db.rollback()
                failed += 1
                continue
            if in_sync:
                db.commit()
                continue
            sync_repo.db_enqueue_sync(db, schedule)
            db.commit()
            if process_sync_event(db, schedule_id):
                repaired += 1
            else:
                failed += 1
        last_id = ids[-1]
    return {"repaired": repaired, "failed": failed}


def _validate_references(db, data, project_id):
    if env_repo.db_get(db, data.env_id, project_id) is None:
        raise HTTPException(status_code=404, detail="环境不存在或不属于当前项目")
    if data.suite_id is not None and suite_repo.db_get(db, data.suite_id, project_id) is None:
        raise HTTPException(status_code=404, detail="测试套件不存在或不属于当前项目")


def _commit_and_try_sync(db: Session, obj: Schedule) -> Schedule:
    db.commit()
    schedule_id = obj.id
    process_sync_event(db, schedule_id)
    refreshed = db.get(Schedule, schedule_id)
    return refreshed if refreshed is not None else obj


def s_create(db: Session, schedule, project_id: int):
    try:
        _validate_references(db, schedule, project_id)
        obj = schedule_repo.db_create(db, schedule, project_id)
        return _commit_and_try_sync(db, obj)
    except Exception:
        db.rollback()
        raise


def s_get(db: Session, schedule_id: int, project_id: int):
    return schedule_repo.db_get(db, schedule_id, project_id)


def s_list(db: Session, project_id: int):
    return schedule_repo.db_list(db, project_id)


def s_update(db: Session, schedule_id: int, schedule, project_id: int):
    try:
        current = schedule_repo.db_get(db, schedule_id, project_id)
        if current is None:
            return None
        # Omitted optional fields retain their existing value, including suite_id.
        effective = SimpleNamespace(**{
            **sync_repo.schedule_payload(current),
            **schedule.model_dump(exclude_unset=True),
        })
        _validate_references(db, effective, project_id)
        obj = schedule_repo.db_update(db, schedule_id, schedule, project_id)
        if obj is None:
            return None
        return _commit_and_try_sync(db, obj)
    except Exception:
        db.rollback()
        raise


def s_delete(db: Session, schedule_id: int, project_id: int):
    try:
        obj = schedule_repo.db_delete(db, schedule_id, project_id)
        if obj is None:
            return None
        db.commit()
        process_sync_event(db, schedule_id)
        return obj
    except Exception:
        db.rollback()
        raise

