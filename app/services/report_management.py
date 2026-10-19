"""Project-scoped report organization and atomic removal of owned evidence."""
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.execution_report import ExecutionReport
from app.models.report import TestReport
from app.models.scenario_report import ScenarioReport, ScenarioReportStep
from app.models.report_folder import ReportFolder, ReportFolderItem
from app.repositories.execution_report import _catalog


def get_folder(db, project_id, folder_id, *, lock=False):
    if not 0 < folder_id <= 2147483647:
        raise HTTPException(404, "报告目录不存在或已删除")
    query = db.query(ReportFolder).filter_by(id=folder_id, project_id=project_id)
    if lock:
        query = query.populate_existing().with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(404, "报告目录不存在或已删除")
    return row


def folder_page(db, project_id):
    catalog = _catalog(project_id)
    counts = dict(db.execute(select(catalog.c.folder_id, func.count()).group_by(catalog.c.folder_id)).all())
    folders = db.query(ReportFolder).filter_by(project_id=project_id).order_by(ReportFolder.id.desc()).all()
    return {"items": [{"id": row.id, "name": row.name, "count": counts.get(row.id, 0)} for row in folders],
            "total": sum(counts.values()), "unfiled": counts.get(None, 0)}


def save_folder(db, project_id, name, folder_id=None):
    try:
        row = get_folder(db, project_id, folder_id, lock=True) if folder_id is not None else ReportFolder(project_id=project_id)
        row.name = name
        row.name_key = unicodedata.normalize("NFKC", name).casefold()
        db.add(row)
        db.flush()
        catalog = _catalog(project_id)
        result = {"id": row.id, "name": row.name,
                  "count": db.execute(select(func.count()).select_from(catalog).where(catalog.c.folder_id == row.id)).scalar_one()}
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "当前项目已有同名目录，请换一个名称") from None
    except Exception:
        db.rollback()
        raise


def delete_folder(db, project_id, folder_id):
    try:
        row = get_folder(db, project_id, folder_id, lock=True)
        removed = db.query(ReportFolderItem).filter_by(project_id=project_id, folder_id=folder_id).delete(synchronize_session=False)
        db.delete(row)
        db.commit()
        return {"deleted": 1, "unfiled": removed}
    except Exception:
        db.rollback()
        raise


def _roots(db, project_id, references):
    groups = {"run": [], "legacy": [], "scenario": []}
    for reference in dict.fromkeys(references):
        if not re.fullmatch(r"(run|legacy|scenario)-[1-9][0-9]{0,18}", reference):
            raise HTTPException(404, "所选报告不存在或无权操作")
        storage, number = reference.split("-", 1)
        if int(number) > 9223372036854775807:
            raise HTTPException(404, "所选报告不存在或无权操作")
        groups[storage].append(int(number))
    rows = {}
    for storage, model in (("run", ExecutionReport), ("legacy", TestReport), ("scenario", ScenarioReport)):
        if not groups[storage]:
            continue
        query = db.query(model).filter(model.project_id == project_id, model.id.in_(groups[storage]))
        query = query.filter(model.parent_id.is_(None)) if storage == "run" else query.filter(model.execution_report_id.is_(None))
        found = query.order_by(model.id).populate_existing().with_for_update().all()
        if len(found) != len(groups[storage]):
            raise HTTPException(404, "所选报告不存在、已删除或无权操作，请刷新后重试")
        rows[storage] = found
    return rows


def move_reports(db, project_id, references, folder_id):
    try:
        if folder_id is not None:
            get_folder(db, project_id, folder_id, lock=True)
        roots = _roots(db, project_id, references)
        moved = 0
        for storage, rows in roots.items():
            for report in rows:
                query = db.query(ReportFolderItem).filter_by(project_id=project_id, storage=storage, report_id=report.id)
                item = query.first()
                if folder_id is None:
                    query.delete(synchronize_session=False)
                elif item is not None:
                    item.folder_id = folder_id
                else:
                    db.add(ReportFolderItem(project_id=project_id, storage=storage, report_id=report.id, folder_id=folder_id))
                moved += 1
        db.commit()
        return {"moved": moved, "folder_id": folder_id}
    except Exception:
        db.rollback()
        raise


def _descendants(db, project_id, roots):
    found = {row.id: row for row in roots}
    frontier = list(found)
    while frontier:
        children = db.query(ExecutionReport).filter(ExecutionReport.project_id == project_id,
            ExecutionReport.parent_id.in_(frontier)).order_by(ExecutionReport.id).populate_existing().with_for_update().all()
        frontier = [row.id for row in children if row.id not in found]
        found.update((row.id, row) for row in children)
    return list(found.values())


def _remove_memberships(db, project_id, storage, numbers):
    if numbers:
        db.query(ReportFolderItem).filter(ReportFolderItem.project_id == project_id,
            ReportFolderItem.storage == storage, ReportFolderItem.report_id.in_(numbers)).delete(synchronize_session=False)


def delete_reports(db, project_id, references):
    try:
        roots = _roots(db, project_id, references)
        runs = _descendants(db, project_id, roots.get("run", []))
        if any(row.passed is None or row.status in {"running", "pending", "queued"} for row in runs):
            raise HTTPException(409, "所选报告或其执行明细仍在运行，请结束后再删除")
        run_ids = [row.id for row in runs]
        old_ids = [row.id for row in roots.get("legacy", [])]
        scenario_ids = [row.id for row in roots.get("scenario", [])]
        if run_ids:
            old_ids += [number for (number,) in db.query(TestReport.id).filter(
                TestReport.project_id == project_id, TestReport.execution_report_id.in_(run_ids)).all()]
            scenario_ids += [number for (number,) in db.query(ScenarioReport.id).filter(
                ScenarioReport.project_id == project_id, ScenarioReport.execution_report_id.in_(run_ids)).all()]
        if scenario_ids:
            # Explicitly clean evidence even on databases without FK cascades enabled.
            db.query(ScenarioReportStep).filter(ScenarioReportStep.report_id.in_(scenario_ids)).delete(synchronize_session=False)
            db.query(ScenarioReport).filter(ScenarioReport.project_id == project_id, ScenarioReport.id.in_(scenario_ids)).delete(synchronize_session=False)
        if old_ids:
            db.query(TestReport).filter(TestReport.project_id == project_id, TestReport.id.in_(old_ids)).delete(synchronize_session=False)
        if run_ids:
            db.query(ExecutionReport).filter(ExecutionReport.project_id == project_id, ExecutionReport.id.in_(run_ids)).delete(synchronize_session=False)
        for storage, numbers in (("run", run_ids), ("legacy", old_ids), ("scenario", scenario_ids)):
            _remove_memberships(db, project_id, storage, numbers)
        db.commit()
        return {"deleted": sum(len(rows) for rows in roots.values())}
    except Exception:
        db.rollback()
        raise
