from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.report import ReportOut
from app.services import report as report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    return report_service.s_get(db, report_id)


@router.get("", response_model=list[ReportOut])
def list_report(db: Session = Depends(get_db)):
    return report_service.s_list(db)






