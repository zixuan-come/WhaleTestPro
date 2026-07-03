from sqlalchemy.orm import Session
from app.models.report import TestReport


def db_create(db: Session, case_id: int, passed: bool, detail, project_id: int):
    db_report = TestReport(case_id=case_id, passed=passed, detail=detail, project_id=project_id)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def db_get(db: Session, report_id: int, project_id: int):
    return db.query(TestReport).filter(
        TestReport.id == report_id,
        TestReport.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(TestReport).filter(
        TestReport.project_id == project_id,
    ).order_by(TestReport.id.desc()).all()
