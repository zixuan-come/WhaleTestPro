from app.models.report import TestReport

def db_create(db, case_id, passed, detail):
    db_report = TestReport(case_id=case_id, passed=passed, detail=detail)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report


def db_get(db, report_id):
    return db.query(TestReport).filter(TestReport.id == report_id).first()


def db_list(db):
    return db.query(TestReport).order_by(TestReport.id.desc()).all()


