from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.schedule import ScheduleCreate, ScheduleOut
from app.schemas.response import ApiResponse, success_response
from app.services import schedule as schedule_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/schedules", tags=["schedule"])


@router.post("", response_model=ApiResponse[ScheduleOut], status_code=201)
def create_schedule(
    schedule: ScheduleCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return success_response(
        schedule_service.s_create(db, schedule, current_project.id),
        message="定时任务创建成功",
        status_code=201,
    )


@router.get("/{schedule_id}", response_model=ApiResponse[ScheduleOut])
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    s = schedule_service.s_get(db, schedule_id, current_project.id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(s, message="查询成功")


@router.get("", response_model=ApiResponse[list[ScheduleOut]])
def list_schedule(
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return success_response(schedule_service.s_list(db, current_project.id), message="查询成功")


@router.put("/{schedule_id}", response_model=ApiResponse[ScheduleOut])
def update_schedule(
    schedule_id: int,
    schedule: ScheduleCreate,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    s = schedule_service.s_update(db, schedule_id, schedule, current_project.id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(s, message="定时任务更新成功")


@router.delete("/{schedule_id}", response_model=ApiResponse[None])
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    s = schedule_service.s_delete(db, schedule_id, current_project.id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(data=None, message="定时任务删除成功")
