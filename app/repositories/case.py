from sqlalchemy.orm import Session
from app.models.case import Case


def db_create(db: Session, case, project_id: int):
    db_case = Case(**case.model_dump(), project_id=project_id)
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


def db_get(db: Session, case_id: int, project_id: int):
    return db.query(Case).filter(
        Case.id == case_id,
        Case.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(Case).filter(Case.project_id == project_id).all()


def db_delete(db: Session, case_id: int, project_id: int):
    db_case = db.query(Case).filter(
        Case.id == case_id,
        Case.project_id == project_id,
    ).first()
    if db_case is None:
        return None
    db.delete(db_case)
    db.commit()
    return db_case
