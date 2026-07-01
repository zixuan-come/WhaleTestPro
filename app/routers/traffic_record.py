from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.traffic_record import TrafficRecordOut
from app.services import traffic_record as traffic_record_service

router = APIRouter(prefix="/traffic/records", tags=["traffic"])


@router.get("", response_model=list[TrafficRecordOut])
def list_records(limit: int = 100, db: Session = Depends(get_db)):
    return traffic_record_service.s_list(db, limit)


@router.get("/{record_id}", response_model=TrafficRecordOut)
def get_record(record_id: int, db: Session = Depends(get_db)):
    return traffic_record_service.s_get(db, record_id)
