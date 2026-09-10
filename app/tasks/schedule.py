from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import execution as execution_service
from app.services import suite as suite_service


@celery_app.task
def scheduled_regression(project_id=None, tag=None, suite_id=None):
    """
    Celery Beat 定时触发的回归任务。

    执行优先级:
    1. 如果 suite_id 有值，运行测试套件
    2. 否则按 tag 运行回归（旧逻辑，向后兼容）

    多项目全链路已就位:
    - project_id: sync_schedule 从 schedule.project_id 塞进 args 带过来
    - run_regression/run_suite 内部严格按项目过滤
    - 生成的 report 也带上正确的 project_id
    """
    db = SessionLocal()
    try:
        if suite_id is not None:
            # 新逻辑：运行测试套件
            suite_service.run_suite(db, suite_id, project_id)
        else:
            # 旧逻辑：按 tag 运行回归
            execution_service.run_regression(db, tag=tag, notify=True, project_id=project_id)
    finally:
        db.close()

