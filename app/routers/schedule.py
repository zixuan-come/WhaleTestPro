from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.schedule import ScheduleCreate, ScheduleOut
from app.services import schedule as schedule_service

router = APIRouter(prefix="/schedules", tags=["schedule"])


@router.post("", response_model=ScheduleOut)
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    return schedule_service.s_create(db, schedule)


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    return schedule_service.s_get(db, schedule_id)


@router.get("", response_model=list[ScheduleOut])
def list_schedule(db: Session = Depends(get_db)):
    return schedule_service.s_list(db)


@router.put("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, schedule: ScheduleCreate, db: Session = Depends(get_db)):
    return schedule_service.s_update(db, schedule_id, schedule)


@router.delete("/{schedule_id}", response_model=ScheduleOut)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    return schedule_service.s_delete(db, schedule_id)











