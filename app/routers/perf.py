from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.perf import PerfTaskCreate, PerfTaskOut
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
    result = perf_service.s_delete(db, task_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    return success_response(data=None, message="压测任务删除成功")


@router.post("/{task_id}/stop", response_model=ApiResponse[PerfTaskOut])
def stop_task(
    task_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.EXECUTE)),
):
    task = perf_service.s_cancel(db, task_id, context.project_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在或不可停止")
    return success_response(task, message="压测任务已停止")


@router.post("/{task_id}/run", response_model=ApiResponse[PerfTaskOut])
def run_task(
    task_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.PERF, Action.EXECUTE)),
):
    task = perf_service.s_mark_running(db, task_id, context.project_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    try:
        run_perf_task.delay(task_id, context.project_id)
    except Exception:
        perf_service.s_mark_failed(db, task_id, context.project_id)
        raise HTTPException(status_code=503, detail="压测任务入队失败，请稍后重试")
    return success_response(task, message="压测任务已启动")
