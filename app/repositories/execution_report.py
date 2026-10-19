"""One paginated view of explicit runs and unlinked historical reports."""
from datetime import datetime, time, timedelta

from sqlalchemy import and_, case, func, literal, select, union_all

from app.models.case import Case
from app.models.execution_report import ExecutionReport
from app.models.report import TestReport
from app.models.scenario_report import ScenarioReport
from app.models.report_folder import ReportFolderItem


def _catalog(project_id):
    runs = select(
        literal("run").label("storage"), ExecutionReport.id.label("number"),
        ExecutionReport.kind.label("kind"), ExecutionReport.name.label("name"),
        ExecutionReport.passed.label("passed"), ExecutionReport.status.label("status"),
        ExecutionReport.trigger_source.label("trigger_source"),
        ExecutionReport.environment_name.label("environment_name"),
        ExecutionReport.duration_ms.label("duration_ms"), ExecutionReport.created_at.label("created_at"),
        ReportFolderItem.folder_id.label("folder_id"),
    ).outerjoin(ReportFolderItem, and_(ReportFolderItem.project_id == project_id,
        ReportFolderItem.storage == "run", ReportFolderItem.report_id == ExecutionReport.id)
    ).where(ExecutionReport.project_id == project_id, ExecutionReport.parent_id.is_(None))
    historical = select(
        literal("legacy").label("storage"), TestReport.id.label("number"),
        case((TestReport.execution_type == "suite", "suite"), else_="case").label("kind"),
        case((TestReport.execution_type == "suite", func.coalesce(TestReport.suite_name, "历史套件报告")),
             else_=func.coalesce(Case.name, "历史用例报告（名称未记录）")).label("name"),
        TestReport.passed.label("passed"), literal("completed").label("status"),
        literal(None).label("trigger_source"), literal(None).label("environment_name"),
        literal(None).label("duration_ms"), TestReport.created_at.label("created_at"),
        ReportFolderItem.folder_id.label("folder_id"),
    ).outerjoin(Case, and_(Case.id == TestReport.case_id, Case.project_id == TestReport.project_id)
    ).outerjoin(ReportFolderItem, and_(ReportFolderItem.project_id == project_id,
        ReportFolderItem.storage == "legacy", ReportFolderItem.report_id == TestReport.id)).where(
        TestReport.project_id == project_id, TestReport.execution_report_id.is_(None),
    )
    scenarios = select(
        literal("scenario").label("storage"), ScenarioReport.id.label("number"),
        literal("scenario").label("kind"), ScenarioReport.scenario_name.label("name"),
        ScenarioReport.passed.label("passed"), literal("completed").label("status"),
        literal(None).label("trigger_source"), literal(None).label("environment_name"),
        ScenarioReport.duration_ms.label("duration_ms"), ScenarioReport.created_at.label("created_at"),
        ReportFolderItem.folder_id.label("folder_id"),
    ).outerjoin(ReportFolderItem, and_(ReportFolderItem.project_id == project_id,
        ReportFolderItem.storage == "scenario", ReportFolderItem.report_id == ScenarioReport.id)
    ).where(ScenarioReport.project_id == project_id, ScenarioReport.execution_report_id.is_(None))
    return union_all(runs, historical, scenarios).subquery()


def _item(row):
    values = dict(row)
    values["id"] = f"{values.pop('storage')}-{values.pop('number')}"
    values["historical"] = not values["id"].startswith("run-")
    return values


def _run_item(row):
    return {"id": f"run-{row.id}", "kind": row.kind, "name": row.name, "passed": row.passed,
            "status": row.status, "trigger_source": row.trigger_source,
            "environment_name": row.environment_name, "duration_ms": row.duration_ms,
            "created_at": row.created_at, "historical": False}


def db_page(db, project_id, *, kind, page, page_size, q="", status="all", date_from=None, date_to=None, folder_id=None):
    catalog = _catalog(project_id)
    query = select(catalog)
    if kind != "all":
        query = query.where(catalog.c.kind == kind)
    if folder_id == 0:
        query = query.where(catalog.c.folder_id.is_(None))
    elif folder_id is not None:
        query = query.where(catalog.c.folder_id == folder_id)
    if q:
        query = query.where(catalog.c.name.contains(q, autoescape=True))
    if status != "all":
        query = query.where(catalog.c.passed.is_(status == "passed"))
    # UI date inputs are calendar dates in Asia/Shanghai; storage uses naive UTC.
    if date_from:
        query = query.where(catalog.c.created_at >= datetime.combine(date_from, time.min) - timedelta(hours=8))
    if date_to:
        query = query.where(catalog.c.created_at < datetime.combine(date_to, time.min) + timedelta(days=1, hours=-8))
    filtered = query.subquery()
    total, passed, failed = db.execute(select(
        func.count(), func.coalesce(func.sum(case((filtered.c.passed.is_(True), 1), else_=0)), 0),
        func.coalesce(func.sum(case((filtered.c.passed.is_(False), 1), else_=0)), 0),
    ).select_from(filtered)).one()
    rows = db.execute(select(filtered).order_by(
        filtered.c.created_at.desc(), filtered.c.storage, filtered.c.number.desc(),
    ).offset((page - 1) * page_size).limit(page_size)).mappings().all()
    return {"items": [_item(row) for row in rows], "total": total, "passed_count": int(passed),
            "failed_count": int(failed), "running_count": total - int(passed) - int(failed),
            "pass_rate": int(passed) / total if total else 0, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0}


def db_get(db, project_id, report_id):
    try:
        storage, raw_id = report_id.split("-", 1)
        number = int(raw_id)
        if number <= 0:
            return None
    except (ValueError, AttributeError):
        return None
    if storage == "run":
        row = db.query(ExecutionReport).filter_by(id=number, project_id=project_id).first()
        if row is None:
            return None
        children = db.query(ExecutionReport).filter_by(parent_id=number, project_id=project_id).order_by(ExecutionReport.id).all()
        detail = dict(row.detail or {})
        # A deleted/missing selection fails before a child execution can start.
        # Keep that failure visible beside the children which actually ran.
        result = detail.get("result")
        if row.kind in {"suite", "regression"} and isinstance(result, dict):
            linked = {(child.kind, child.object_id) for child in children}
            missing = []
            for item in result.get("results", []):
                kind = item.get("type", "case")
                number = item.get("id", item.get("case_id"))
                if (kind, number) not in linked:
                    label = "场景" if kind == "scenario" else "用例"
                    missing.append({**item, "name": item.get("name") or f"{label} #{number}"})
            if missing:
                detail["unexecuted_items"] = missing
        folder_id = db.query(ReportFolderItem.folder_id).filter_by(project_id=project_id, storage="run", report_id=row.id).scalar()
        return {**_run_item(row), "folder_id": folder_id, "detail": detail, "children": [_run_item(child) for child in children]}
    catalog = _catalog(project_id)
    item = db.execute(select(catalog).where(catalog.c.storage == storage, catalog.c.number == number)).mappings().first()
    if item is None:
        return None
    if storage == "scenario":
        from app.repositories.scenario_report import db_get as get_scenario
        from app.schemas.report import ScenarioReportDetail
        row = get_scenario(db, number, project_id)
        detail = {"steps": ScenarioReportDetail.model_validate(row).model_dump(mode="json")["steps"]}
    else:
        row = db.query(TestReport).filter_by(id=number, project_id=project_id).first()
        detail = {"result": row.detail}
        if isinstance(row.detail, dict) and row.detail.get("step"):
            detail["steps"] = [row.detail["step"]]
    return {**_item(item), "detail": detail, "children": []}
