from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.report import ReportOut, ReportPage
from app.services import report as report_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    r = report_service.s_get(db, report_id, current_project.id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"报告 id={report_id} 不存在")
    return r


@router.get("", response_model=ReportPage)
def list_report(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return report_service.s_page(db, current_project.id, page, page_size)
