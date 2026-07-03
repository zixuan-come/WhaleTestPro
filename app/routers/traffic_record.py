from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.traffic_record import TrafficRecordOut
from app.services import traffic_record as traffic_record_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/traffic/records", tags=["traffic"])


@router.get("", response_model=list[TrafficRecordOut])
def list_records(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return traffic_record_service.s_list(db, current_project.id, limit)


@router.get("/{record_id}", response_model=TrafficRecordOut)
def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    r = traffic_record_service.s_get(db, record_id, current_project.id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"流量记录 id={record_id} 不存在")
    return r
