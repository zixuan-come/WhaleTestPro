from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from app.models.perf import PerfTask, PerfRun
from app.core.perf_history import RESULT_FIELDS, DATE_FIELDS, run_snapshot, execution_key


def _sync_run(db, task_id, project_id):
    values = db.execute(select(PerfTask.__table__).where(
        PerfTask.id == task_id, PerfTask.project_id == project_id)).mappings().first()
    if values is None or values["status"] == "pending":
        return
    key = execution_key(values)
    run = db.query(PerfRun).filter_by(task_id=task_id, project_id=project_id, execution_key=key).first()
    if run is None:
        run = PerfRun(task_id=task_id, project_id=project_id, execution_key=key,
                      created_at=values["queued_at"] or values["started_at"] or datetime.utcnow())
        db.add(run)
    run.status = values["status"]
    snapshot = run_snapshot(values)
    run.snapshot = ({**run.snapshot, **{field: snapshot[field] for field in RESULT_FIELDS}}
                    if run.snapshot else snapshot)


def _owned_update(db, query, task_id, project_id):
    owner = db.info.get("perf_execution")
    if owner and owner[:2] == (task_id, project_id):
        query = query.filter(PerfTask.celery_task_id == owner[2])
    return query


def annotate_runs(db, tasks):
    if not tasks:
        return tasks
    ids = [task.id for task in tasks]
    rows = db.query(PerfRun.task_id, func.max(PerfRun.id), func.count(PerfRun.id)).filter(
        PerfRun.task_id.in_(ids), PerfRun.project_id == tasks[0].project_id).group_by(PerfRun.task_id).all()
    summaries = {task_id: (latest, count) for task_id, latest, count in rows}
    for task in tasks:
        task.latest_run_id, task.history_count = summaries.get(task.id, (None, 0))
    return tasks


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


def db_get_for_update(db: Session, task_id: int, project_id: int):
    return (db.query(PerfTask).filter(PerfTask.id == task_id, PerfTask.project_id == project_id)
            .populate_existing().with_for_update().first())


def db_list(db: Session, project_id: int):
    return db.query(PerfTask).filter(PerfTask.project_id == project_id).all()


def db_delete(db: Session, task_id: int, project_id: int):
    db_task = db.query(PerfTask).filter(
        PerfTask.id == task_id,
        PerfTask.project_id == project_id,
    ).first()
    if db_task is None or db_task.status not in {"pending", "done", "failed", "cancelled"}:
        return None
    db.query(PerfRun).filter_by(task_id=task_id, project_id=project_id).delete(synchronize_session=False)
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
    db.flush()
    _sync_run(db, task_id, project_id)
    db.commit()
    db.refresh(db_task)
    return db_task


def db_update_if_status(db: Session, task_id: int, project_id: int, expected_status: str, **fields):
    updated = (
        _owned_update(db, db.query(PerfTask), task_id, project_id)
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
    if set(fields) != {"heartbeat_at"}:
        _sync_run(db, task_id, project_id)
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
        _owned_update(db, db.query(PerfTask), task_id, project_id)
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
    _sync_run(db, task_id, project_id)
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
            _sync_run(db, task.id, task.project_id)
            failed.append((task.id, task.project_id, task.status))

    db.commit()
    return failed


def run_query(db, task_id, project_id):
    return db.query(PerfRun).filter_by(task_id=task_id, project_id=project_id)


def db_list_runs(db, task_id, project_id, offset, limit):
    query = run_query(db, task_id, project_id)
    return {"total": query.count(), "items": query.order_by(PerfRun.id.desc()).offset(offset).limit(limit).all()}


def db_clear_runs(db, task, selection):
    query = run_query(db, task.id, task.project_id)
    selected = query.filter(PerfRun.id.in_(selection.run_ids)) if selection.run_ids else query.filter(
        PerfRun.status.notin_(("queued", "running")))
    runs = selected.with_for_update().all()
    if selection.run_ids and len(runs) != len(selection.run_ids):
        raise LookupError("执行记录不存在，请刷新后重试")
    if any(run.status in {"queued", "running"} for run in runs):
        raise ValueError("正在排队或运行的记录不能清理")
    deleted_ids = [run.id for run in runs]
    # A task is a reusable definition; cleaning the newest result restores the
    # previous result mirror without changing its current configuration.
    current_key = execution_key({"id": task.id, "celery_task_id": task.celery_task_id})
    if any(run.execution_key == current_key for run in runs):
        remaining = query.filter(PerfRun.id.notin_(deleted_ids)).order_by(PerfRun.id.desc()).first()
        values = remaining.snapshot if remaining else {}
        for field in RESULT_FIELDS:
            value = values.get(field)
            if field in DATE_FIELDS and value:
                value = datetime.fromisoformat(value)
            setattr(task, field, value if field != "status" else value or "pending")
    if deleted_ids:
        query.filter(PerfRun.id.in_(deleted_ids)).delete(synchronize_session=False)
    db.commit()
    return len(deleted_ids)
