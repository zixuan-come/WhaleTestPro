from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Literal

from app.core.authorization import ProjectContext, authorize, is_allowed
from app.core.permissions import Action, Resource
from app.database import get_db
from app.schemas.report import ReportOut, ReportPage, ScenarioReportDetail, ScenarioReportPage
from app.schemas.response import ApiResponse, success_response
from app.services import report as report_service
from app.repositories import execution_report as execution_reports
from app.schemas.execution_report import ExecutionReportPage, ExecutionReportDetail, ReportKind
from app.schemas.report_folder import ReportFolderName, ReportFolderOut, ReportFolderPage, ReportSelection, ReportMove
from app.services import report_management


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/folders", response_model=ApiResponse[ReportFolderPage])
def list_folders(db: Session = Depends(get_db), context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ))):
    return success_response({**report_management.folder_page(db, context.project_id),
        "can_manage": is_allowed(context, Resource.REPORT, Action.WRITE)})


@router.post("/folders", response_model=ApiResponse[ReportFolderOut], status_code=201)
def create_folder(payload: ReportFolderName, db: Session = Depends(get_db),
                  context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.save_folder(db, context.project_id, payload.name), message="目录已创建")


@router.put("/folders/{folder_id}", response_model=ApiResponse[ReportFolderOut])
def rename_folder(folder_id: int, payload: ReportFolderName, db: Session = Depends(get_db),
                  context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.save_folder(db, context.project_id, payload.name, folder_id), message="目录已更新")


@router.delete("/folders/{folder_id}", response_model=ApiResponse[dict])
def remove_folder(folder_id: int, db: Session = Depends(get_db),
                  context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.delete_folder(db, context.project_id, folder_id), message="目录已删除，报告已保留")


@router.post("/executions/move", response_model=ApiResponse[dict])
def move_reports(payload: ReportMove, db: Session = Depends(get_db),
                 context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.move_reports(db, context.project_id, payload.report_ids, payload.folder_id), message="报告已归档")


@router.post("/executions/delete", response_model=ApiResponse[dict])
def remove_reports(payload: ReportSelection, db: Session = Depends(get_db),
                   context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.delete_reports(db, context.project_id, payload.report_ids), message="报告已删除")


@router.delete("/executions/{report_id}", response_model=ApiResponse[dict])
def remove_report(report_id: str, db: Session = Depends(get_db),
                  context: ProjectContext = Depends(authorize(Resource.REPORT, Action.WRITE))):
    return success_response(report_management.delete_reports(db, context.project_id, [report_id]), message="报告已删除")


@router.get("/executions", response_model=ApiResponse[ExecutionReportPage])
def list_execution_reports(
    kind: ReportKind | Literal["all"] = "case",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=100), status: Literal["all", "passed", "failed"] = "all",
    date_from: date | None = None, date_to: date | None = None,
    folder_id: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    if folder_id:
        report_management.get_folder(db, context.project_id, folder_id)
    return success_response(execution_reports.db_page(
        db, context.project_id, kind=kind, page=page, page_size=page_size,
        q=q.strip(), status=status, date_from=date_from, date_to=date_to, folder_id=folder_id,
    ), message="查询成功")


@router.get("/executions/{report_id}", response_model=ApiResponse[ExecutionReportDetail])
def get_execution_report(
    report_id: str,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    result = execution_reports.db_get(db, context.project_id, report_id)
    if result is None:
        raise HTTPException(404, "执行报告不存在")
    return success_response(result, message="查询成功")


@router.get("/scenarios", response_model=ApiResponse[ScenarioReportPage])
def list_scenario_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    return success_response(
        report_service.s_scenario_page(db, context.project_id, page, page_size),
        message="查询成功",
    )


@router.get("/scenarios/{scenario_report_id}", response_model=ApiResponse[ScenarioReportDetail])
def get_scenario_report(
    scenario_report_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    report = report_service.s_scenario_get(db, scenario_report_id, context.project_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"场景报告 id={scenario_report_id} 不存在")
    return success_response(report, message="查询成功")


@router.get("/{report_id}", response_model=ApiResponse[ReportOut])
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    result = report_service.s_get(db, report_id, context.project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"报告 id={report_id} 不存在")
    return success_response(result, message="查询成功")


@router.get("", response_model=ApiResponse[ReportPage])
def list_report(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    context: ProjectContext = Depends(authorize(Resource.REPORT, Action.READ)),
):
    return success_response(
        report_service.s_page(db, context.project_id, page, page_size),
        message="查询成功",
    )
