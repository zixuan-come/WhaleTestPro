from datetime import datetime

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from app.models.perf import PerfTask


def db_create(db: Session, perf, project_id: int):
    db_perf = PerfTask(**perf.model_dump(), project_id=project_id)
    db.add(db_perf)
    db.commit()
    db.refresh(db_perf)
    return db_perf


def db_get(db: Session, task_id: int, project_id: int):
    return db.query(PerfTask).filter(
        PerfTask.id == task_id,
        PerfTask.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(PerfTask).filter(PerfTask.project_id == project_id).all()


def db_delete(db: Session, task_id: int, project_id: int):
    db_task = db.query(PerfTask).filter(
        PerfTask.id == task_id,
        PerfTask.project_id == project_id,
    ).first()
    if db_task is None or db_task.status not in {"pending", "done", "failed", "cancelled"}:
        return None
    deleted = db.query(PerfTask).filter(
        PerfTask.id == task_id,
        PerfTask.project_id == project_id,
        # The service checked/cleaned this exact state, not a later terminal state.
        PerfTask.status == db_task.status,
    ).delete(synchronize_session=False)
    if not deleted:
        db.rollback()
        return None
    db.commit()
    return db_task


def db_update(db: Session, task_id: int, project_id: int, **fields):
    db_task = db.query(PerfTask).filter(
        PerfTask.id == task_id,
        PerfTask.project_id == project_id,
    ).first()
    if db_task is None:
        return None
    for k, v in fields.items():
        setattr(db_task, k, v)
    db.commit()
    db.refresh(db_task)
    return db_task


def db_update_if_status(db: Session, task_id: int, project_id: int, expected_status: str, **fields):
    updated = (
        db.query(PerfTask)
        .filter(
            PerfTask.id == task_id,
            PerfTask.project_id == project_id,
            PerfTask.status == expected_status,
        )
        .update(fields, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        return None
    db.commit()
    return db_get(db, task_id, project_id)


def db_update_if_status_in(
    db: Session,
    task_id: int,
    project_id: int,
    expected_statuses: tuple[str, ...],
    **fields,
):
    updated = (
        db.query(PerfTask)
        .filter(
            PerfTask.id == task_id,
            PerfTask.project_id == project_id,
            PerfTask.status.in_(expected_statuses),
        )
        .update(fields, synchronize_session=False)
    )
    if updated == 0:
        db.rollback()
        return None
    db.commit()
    return db_get(db, task_id, project_id)


def db_touch_heartbeat(
    db: Session,
    task_id: int,
    project_id: int,
    heartbeat_at: datetime,
):
    return db_update_if_status(
        db,
        task_id,
        project_id,
        "running",
        heartbeat_at=heartbeat_at,
    )


def db_fail_stale(
    db: Session,
    queued_before: datetime,
    running_before: datetime,
    finished_at: datetime,
    project_id: int | None = None,
) -> list[tuple[int, int, str]]:
    """Atomically fail queued/running tasks whose worker progress is stale."""
    query = db.query(PerfTask).filter(
        or_(
            and_(
                PerfTask.status == "queued",
                or_(
                    PerfTask.queued_at <= queued_before,
                    PerfTask.queued_at.is_(None),
                ),
            ),
            and_(
                PerfTask.status == "running",
                or_(
                    func.coalesce(
                        PerfTask.heartbeat_at,
                        PerfTask.started_at,
                        PerfTask.queued_at,
                    ) <= running_before,
                    and_(
                        PerfTask.heartbeat_at.is_(None),
                        PerfTask.started_at.is_(None),
                        PerfTask.queued_at.is_(None),
                    ),
                ),
            ),
        )
    )
    if project_id is not None:
        query = query.filter(PerfTask.project_id == project_id)
    stale_candidates = query.all()

    failed: list[tuple[int, int, str]] = []
    for task in stale_candidates:
        if task.status == "queued":
            stale_filter = or_(
                PerfTask.queued_at <= queued_before,
                PerfTask.queued_at.is_(None),
            )
            reason = "压测任务排队超时，Celery Worker 未及时开始执行"
        else:
            stale_filter = or_(
                func.coalesce(
                    PerfTask.heartbeat_at,
                    PerfTask.started_at,
                    PerfTask.queued_at,
                ) <= running_before,
                and_(
                    PerfTask.heartbeat_at.is_(None),
                    PerfTask.started_at.is_(None),
                    PerfTask.queued_at.is_(None),
                ),
            )
            reason = "压测任务心跳超时，Celery Worker 可能已经退出"

        updated = (
            db.query(PerfTask)
            .filter(
                PerfTask.id == task.id,
                PerfTask.project_id == task.project_id,
                PerfTask.status == task.status,
                stale_filter,
            )
            .update(
                {
                    "status": "failed",
                    "finished_at": finished_at,
                    "failure_reason": reason,
                },
                synchronize_session=False,
            )
        )
        if updated:
            failed.append((task.id, task.project_id, task.status))

    db.commit()
    return failed
