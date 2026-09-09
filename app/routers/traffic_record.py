from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.schemas.traffic_record import TrafficRecordOut
from app.services import traffic_record as traffic_record_service


router = APIRouter(prefix="/traffic/records", tags=["traffic"])


@router.get("", response_model=ApiResponse[list[TrafficRecordOut]])
def list_records(
    limit: int = 100,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.READ)),
):
    return success_response(
        traffic_record_service.s_list(db, context.project_id, limit),
        message="查询成功",
    )


@router.get("/{record_id}", response_model=ApiResponse[TrafficRecordOut])
def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.READ)),
):
    result = traffic_record_service.s_get(db, record_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"流量记录 id={record_id} 不存在")
    return success_response(result, message="查询成功")
