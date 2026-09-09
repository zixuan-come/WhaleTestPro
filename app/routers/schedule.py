from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.schemas.schedule import ScheduleCreate, ScheduleOut
from app.services import schedule as schedule_service


router = APIRouter(prefix="/schedules", tags=["schedule"])


@router.post("", response_model=ApiResponse[ScheduleOut], status_code=201)
def create_schedule(
    schedule: ScheduleCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCHEDULE, Action.WRITE)),
):
    return success_response(
        schedule_service.s_create(db, schedule, context.project_id),
        message="定时任务创建成功",
        status_code=201,
    )


@router.get("/{schedule_id}", response_model=ApiResponse[ScheduleOut])
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCHEDULE, Action.READ)),
):
    result = schedule_service.s_get(db, schedule_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[list[ScheduleOut]])
def list_schedule(
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCHEDULE, Action.READ)),
):
    return success_response(schedule_service.s_list(db, context.project_id), message="查询成功")


@router.put("/{schedule_id}", response_model=ApiResponse[ScheduleOut])
def update_schedule(
    schedule_id: int,
    schedule: ScheduleCreate,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCHEDULE, Action.WRITE)),
):
    result = schedule_service.s_update(db, schedule_id, schedule, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(result, message="定时任务更新成功")


@router.delete("/{schedule_id}", response_model=ApiResponse[None])
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.SCHEDULE, Action.WRITE)),
):
    result = schedule_service.s_delete(db, schedule_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"定时任务 id={schedule_id} 不存在")
    return success_response(data=None, message="定时任务删除成功")
