from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.authorization import ProjectContext, authorize
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.response import ApiResponse, success_response
from app.schemas.traffic_record import TrafficRecordOut
from app.services import traffic_record as traffic_record_service
from app.services import traffic_capture
from app.repositories import traffic_record as records


router = APIRouter(prefix="/traffic/records", tags=["traffic"])
capture_router = APIRouter(prefix="/traffic/capture", tags=["traffic"])


@capture_router.get("")
def capture_state(db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.READ))):
    return success_response(traffic_capture.state(db, context.project_id, context.user.id))


@capture_router.post("/start")
def capture_start(db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.EXECUTE))):
    return success_response(traffic_capture.start(db, context.project_id, context.user.id))


@capture_router.post("/stop")
def capture_stop(db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.EXECUTE))):
    return success_response(traffic_capture.stop(db, context.project_id, context.user.id))


@router.get("", response_model=ApiResponse[list[TrafficRecordOut]])
def list_records(
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    capture_id: str | None = Query(None, max_length=36),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.TRAFFIC, Action.READ)),
):
    return success_response(
        records.db_list(db, context.project_id, limit, offset, capture_id),
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
