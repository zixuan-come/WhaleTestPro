from app.models.perf import PerfTask

def db_create(db, perf):
    db_perf = PerfTask(**perf.model_dump())
    db.add(db_perf)
    db.commit()
    db.refresh(db_perf)
    return db_perf

def db_get(db, task_id):
    return db.query(PerfTask).filter(PerfTask.id == task_id).first()

def db_list(db):
    return db.query(PerfTask).all()

def db_delete(db, task_id):
    db_task = db.query(PerfTask).filter(PerfTask.id == task_id).first()
    if db_task is None:
        return None
    db.delete(db_task)
    db.commit()
    return db_task


def db_update(db, task_id, **fields):
    db_task = db.query(PerfTask).filter(PerfTask.id == task_id).first()
    if db_task is None:
        return None
    for k, v in fields.items():
        setattr(db_task, k, v)
    db.commit()
    db.refresh(db_task)
    return db_task






