from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.perf import PerfTaskCreate, PerfTaskOut
from app.services import perf as perf_service
from app.tasks.perf import run_perf_task

router = APIRouter(prefix="/perf/tasks", tags=["perf"])

@router.post("", response_model=PerfTaskOut)
def create_task(perf:PerfTaskCreate, db: Session = Depends(get_db)):
    return perf_service.s_create(db, perf)


@router.get("/{task_id}", response_model=PerfTaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    return perf_service.s_get(db, task_id)


@router.get("", response_model=list[PerfTaskOut])
def list_task(db: Session = Depends(get_db)):
    return perf_service.s_list(db)


@router.delete("/{task_id}", response_model=PerfTaskOut)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    return perf_service.s_delete(db, task_id)


@router.post("/{task_id}/run", response_model=PerfTaskOut)
def run_task(task_id: int, db: Session = Depends(get_db)):
    task = perf_service.s_mark_running(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    run_perf_task.delay(task_id)
    return task







