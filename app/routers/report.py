from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.report import (
    ReportOut,
    ReportPage,
    ScenarioReportDetail,
    ScenarioReportPage,
)
from app.services import report as report_service
from app.core.deps import get_current_project
from app.models.project import Project

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/scenarios", response_model=ScenarioReportPage)
def list_scenario_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    return report_service.s_scenario_page(
        db,
        current_project.id,
        page,
        page_size,
    )


@router.get("/scenarios/{scenario_report_id}", response_model=ScenarioReportDetail)
def get_scenario_report(
    scenario_report_id: int,
    db: Session = Depends(get_db),
    current_project: Project = Depends(get_current_project),
):
    report = report_service.s_scenario_get(
        db,
        scenario_report_id,
        current_project.id,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"场景报告 id={scenario_report_id} 不存在",
        )
    return report


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
