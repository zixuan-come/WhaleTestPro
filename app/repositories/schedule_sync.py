from sqlalchemy.orm import Session

from app.models.schedule import Schedule
from app.models.schedule_sync_outbox import ScheduleSyncOutbox


def schedule_payload(schedule: Schedule) -> dict:
    return {
        "id": schedule.id,
        "project_id": schedule.project_id,
        "cron": schedule.cron,
        "tag": schedule.tag,
        "suite_id": schedule.suite_id,
        "env_id": schedule.env_id,
        "enabled": schedule.enabled,
    }


def db_enqueue_sync(db: Session, schedule: Schedule) -> ScheduleSyncOutbox:
    event = db.get(ScheduleSyncOutbox, schedule.id)
    if event is None:
        event = ScheduleSyncOutbox(schedule_id=schedule.id)
        db.add(event)
    event.action = "sync"
    event.payload = schedule_payload(schedule)
    event.attempts = 0
    event.last_error = None
    schedule.sync_status = "pending"
    schedule.sync_error = None
    return event


def db_enqueue_delete(db: Session, schedule_id: int) -> ScheduleSyncOutbox:
    event = db.get(ScheduleSyncOutbox, schedule_id)
    if event is None:
        event = ScheduleSyncOutbox(schedule_id=schedule_id)
        db.add(event)
    event.action = "delete"
    event.payload = None
    event.attempts = 0
    event.last_error = None
    return event


def db_get_for_update(db: Session, schedule_id: int) -> ScheduleSyncOutbox | None:
    return (
        db.query(ScheduleSyncOutbox)
        .filter(ScheduleSyncOutbox.schedule_id == schedule_id)
        .with_for_update()
        .first()
    )


def db_pending_ids(db: Session, limit: int = 100) -> list[int]:
    return [
        schedule_id
        for (schedule_id,) in (
            db.query(ScheduleSyncOutbox.schedule_id)
            .order_by(ScheduleSyncOutbox.updated_at.asc())
            .limit(limit)
            .all()
        )
    ]
