from sqlalchemy import and_
from sqlalchemy.orm import Session
from app.models.case import Case
from app.models.report import TestReport


def _report_data(report, case_name):
    return {
        "id": report.id,
        "case_id": report.case_id,
        "case_name": case_name,
        "passed": report.passed,
        "detail": report.detail,
        "created_at": report.created_at,
    }


def db_create(db: Session, case_id: int, passed: bool, detail, project_id: int):
    db_report = TestReport(case_id=case_id, passed=passed, detail=detail, project_id=project_id)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def db_get(db: Session, report_id: int, project_id: int):
    row = (
        db.query(TestReport, Case.name)
        .outerjoin(
            Case,
            and_(
                Case.id == TestReport.case_id,
                Case.project_id == TestReport.project_id,
            ),
        )
        .filter(
            TestReport.id == report_id,
            TestReport.project_id == project_id,
        )
        .first()
    )
    return _report_data(*row) if row else None


def db_page(db: Session, project_id: int, offset: int, limit: int):
    base_query = db.query(TestReport).filter(TestReport.project_id == project_id)
    reports = (
        db.query(TestReport, Case.name)
        .outerjoin(
            Case,
            and_(
                Case.id == TestReport.case_id,
                Case.project_id == TestReport.project_id,
            ),
        )
        .filter(TestReport.project_id == project_id)
        .order_by(TestReport.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = base_query.count()
    passed_count = base_query.filter(TestReport.passed.is_(True)).count()

    return {
        "items": [_report_data(*row) for row in reports],
        "total": total,
        "passed_count": passed_count,
        "failed_count": total - passed_count,
    }
