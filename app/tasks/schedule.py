from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.services import schedule as schedule_service
from app.core.execution_context import triggered_by
from app.repositories import schedule as schedule_repo
from app.services import regression as regression_service
from app.schemas.regression import RegressionRun, RegressionSelection


@celery_app.task
def reconcile_schedule_outbox():
    db = SessionLocal()
    try:
        pending = schedule_service.reconcile_pending(db)
        desired = schedule_service.reconcile_desired(db)
        return {"synced": pending["synced"], "repaired": desired["repaired"], "failed": pending["failed"] + desired["failed"]}
    finally:
        db.close()


@celery_app.task
def scheduled_regression(*, project_id=None, schedule_id=None):
    """Execute the current persisted selection; queued messages contain no targets."""
    if project_id is None or schedule_id is None:
        raise ValueError("定时执行必须指定所属项目和定时任务")
    db = SessionLocal()
    try:
        current = schedule_repo.db_get(db, schedule_id, project_id)
        if current is None or not current.enabled:
            return {"skipped": True, "reason": "定时任务已停用或删除"}
        if current.env_id is None:
            raise ValueError("定时任务未配置执行环境，请编辑后重新启用")
        if current.selection is not None:
            targets = current.selection
        elif current.suite_id is not None:
            targets = {"mode": "suite", "ids": [current.suite_id]}
        else:
            raise ValueError("定时任务未选择测试内容，请编辑后重新启用")
        selection = RegressionSelection(**targets, env_id=current.env_id)
        plan = regression_service.preview(db, project_id, selection)
        with triggered_by("scheduled"):
            return regression_service.run(db, project_id, RegressionRun(
                **selection.model_dump(), preview_key=plan["preview_key"], notify=current.notify), report_name=current.name)
    finally:
        db.close()
