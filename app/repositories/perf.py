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
    if db_task is None:
        return None
    db.delete(db_task)
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
