from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.perf import PerfTaskCreate, PerfTaskOut, PerfRunOut, PerfRunClear
from app.repositories import perf as perf_repo, project as project_repo
from app.schemas.response import ApiResponse, success_response
from app.services import perf as perf_service
from app.tasks.perf import run_perf_task


router = APIRouter(prefix="/perf/tasks", tags=["perf"])


@router.post("", response_model=ApiResponse[PerfTaskOut], status_code=201)
def create_task(
    perf: PerfTaskCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.WRITE)),
):
    return success_response(
        perf_service.s_create(db, perf, context.project_id),
        message="压测任务创建成功",
        status_code=201,
    )


@router.get("/{task_id}", response_model=ApiResponse[PerfTaskOut])
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.READ)),
):
    result = perf_service.s_get(db, task_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[PerfTaskOut]])
def list_task(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.READ)),
):
    return success_response(perf_service.s_list(db, context.project_id), message="查询成功")


@router.delete("/{task_id}", response_model=ApiResponse[None])
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.WRITE)),
):
    try:
        result = perf_service.s_delete(db, task_id, context.project_id)
    except perf_service.PerfRunBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except perf_service.PerfControlUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    return success_response(data=None, message="压测任务删除成功")


@router.post("/{task_id}/stop", response_model=ApiResponse[PerfTaskOut])
def stop_task(
    task_id: int,
    execution_id: str | None = None,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.EXECUTE)),
):
    try:
        task = perf_service.s_cancel(db, task_id, context.project_id, execution_id)
    except perf_service.PerfRunBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在或不可停止")
    return success_response(perf_repo.annotate_runs(db, [task])[0], message="压测任务已停止")


@router.post("/{task_id}/run", response_model=ApiResponse[PerfTaskOut])
def run_task(
    task_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.EXECUTE)),
):
    celery_task_id = str(uuid4())
    try:
        task = perf_service.s_mark_queued(
            db,
            task_id,
            context.project_id,
            celery_task_id,
        )
    except perf_service.PerfRunBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except perf_service.PerfControlUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    try:
        run_perf_task.apply_async(
            args=(task_id, context.project_id),
            task_id=celery_task_id,
        )
    except Exception:
        perf_service.s_mark_failed(db, task_id, context.project_id, celery_task_id)
        raise HTTPException(status_code=503, detail="压测任务入队失败，请稍后重试")
    return success_response(perf_repo.annotate_runs(db, [task])[0], message="压测任务已进入队列")


def _run_out(run):
    return PerfRunOut(id=run.id, task_id=run.task_id, status=run.status, created_at=run.created_at,
                      result=PerfTaskOut(**{**run.snapshot, "latest_run_id": run.id}))


@router.get("/{task_id}/runs", response_model=ApiResponse[dict])
def list_runs(task_id: int, offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100),
              db: Session = Depends(get_db),
              context: ProjectContext = Depends(authorize(Resource.PERF, Action.READ))):
    if perf_service.s_get(db, task_id, context.project_id) is None:
        raise HTTPException(status_code=404, detail="压测任务不存在")
    page = perf_repo.db_list_runs(db, task_id, context.project_id, offset, limit)
    return success_response({"total": page["total"], "items": [_run_out(row) for row in page["items"]]})


@router.get("/{task_id}/runs/{run_id}", response_model=ApiResponse[PerfRunOut])
def get_run(task_id: int, run_id: int, db: Session = Depends(get_db),
            context: ProjectContext = Depends(authorize(Resource.PERF, Action.READ))):
    run = perf_repo.run_query(db, task_id, context.project_id).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return success_response(_run_out(run))


@router.post("/{task_id}/runs/clear", response_model=ApiResponse[dict])
def clear_runs(task_id: int, selection: PerfRunClear, db: Session = Depends(get_db),
               context: ProjectContext = Depends(authorize(Resource.PERF, Action.WRITE))):
    try:
        count = perf_service.s_clear_runs(db, task_id, context.project_id, selection)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except perf_service.PerfControlUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if count is None:
        raise HTTPException(status_code=404, detail="压测任务不存在")
    return success_response({"deleted": count}, message="执行记录已清理，任务配置已保留")


@router.put("/{task_id}", response_model=ApiResponse[PerfTaskOut])
def update_task(task_id: int, config: PerfTaskCreate, db: Session = Depends(get_db),
                context: ProjectContext = Depends(authorize(Resource.PERF, Action.WRITE))):
    if project_repo.db_lock_project(db, context.project_id) is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="压测任务不存在")
    task = perf_repo.db_get_for_update(db, task_id, context.project_id)
    if task is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="压测任务不存在")
    if task.status in {"queued", "running"}:
        db.rollback()
        raise HTTPException(status_code=409, detail="请结束当前执行后再修改配置")
    perf_repo._sync_run(db, task_id, context.project_id)
    return success_response(perf_repo.db_update(db, task_id, context.project_id, **config.model_dump()))
