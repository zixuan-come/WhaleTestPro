from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.perf import PerfTaskCreate, PerfTaskOut
from app.services import perf as perf_service
from app.tasks.perf import run_perf_task
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/perf/tasks", tags=["perf"])


@router.post("", response_model=PerfTaskOut, status_code=201)
def create_task(
    perf: PerfTaskCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return perf_service.s_create(db, perf, current_project.id)


@router.get("/{task_id}", response_model=PerfTaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    t = perf_service.s_get(db, task_id, current_project.id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    return t


@router.get("", response_model=list[PerfTaskOut])
def list_task(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return perf_service.s_list(db, current_project.id)


@router.delete("/{task_id}", response_model=PerfTaskOut)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    t = perf_service.s_delete(db, task_id, current_project.id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    return t


@router.post("/{task_id}/run", response_model=PerfTaskOut)
def run_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    task = perf_service.s_mark_running(db, task_id, current_project.id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"压测任务 id={task_id} 不存在")
    # pid 一起传给 celery worker,s_run 里所有 repo 调用都强制带 pid,不留信任漏洞
    run_perf_task.delay(task_id, current_project.id)
    return task
