from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import execution as execution_service


@celery_app.task
def scheduled_regression(tag=None):
    db = SessionLocal()
    try:
        execution_service.run_regression(db, tag=tag, notify=True)
    finally:
        db.close()
















