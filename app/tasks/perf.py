from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import perf as perf_service


@celery_app.task
def run_perf_task(task_id):
    db = SessionLocal()
    try:
        perf_service.s_run(db, task_id)
    finally:
        db.close()







