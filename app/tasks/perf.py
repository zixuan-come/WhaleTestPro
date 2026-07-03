from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import perf as perf_service


@celery_app.task
def run_perf_task(task_id, project_id):
    """
    压测 Celery 任务。project_id 从 router 层沿链路传下来,s_run 内部所有 repo 调用
    都强制带 pid — 相当于把"多租户隔离"贯彻到 celery worker 里,不留信任漏洞。
    """
    db = SessionLocal()
    try:
        perf_service.s_run(db, task_id, project_id)
    finally:
        db.close()
