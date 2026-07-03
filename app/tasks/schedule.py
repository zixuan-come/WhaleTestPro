from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import execution as execution_service


@celery_app.task
def scheduled_regression(project_id=None, tag=None):
    """
    Celery Beat 定时触发的回归任务。多项目全链路已就位:
    - project_id: sync_schedule 从 schedule.project_id 塞进 args 带过来
    - run_regression 内部 case_repo.db_list(db, project_id) 严格按项目过滤
    - 生成的 report 也带上正确的 project_id
    """
    db = SessionLocal()
    try:
        execution_service.run_regression(db, tag=tag, notify=True, project_id=project_id)
    finally:
        db.close()
