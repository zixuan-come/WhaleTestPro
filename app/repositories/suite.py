from sqlalchemy.orm import Session
from app.models.suite import TestSuite
from app.schemas.suite import SuiteCreate, SuiteUpdate


def db_create(db: Session, suite: SuiteCreate, project_id: int):
    db_suite = TestSuite(
        name=suite.name,
        description=suite.description,
        project_id=project_id,
        type=suite.type,
        scenario_ids=suite.scenario_ids or [],
        case_ids=suite.case_ids or [],
        tags=suite.tags or [],
    )
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)
    return db_suite


def db_get(db: Session, suite_id: int, project_id: int):
    return db.query(TestSuite).filter(
        TestSuite.id == suite_id,
        TestSuite.project_id == project_id
    ).first()


def db_list(db: Session, project_id: int, skip: int = 0, limit: int = 100):
    return db.query(TestSuite).filter(
        TestSuite.project_id == project_id
    ).offset(skip).limit(limit).all()


def db_update(db: Session, suite_id: int, project_id: int, suite_update: SuiteUpdate):
    db_suite = db_get(db, suite_id, project_id)
    if not db_suite:
        return None

    update_data = suite_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_suite, key, value)

    db.commit()
    db.refresh(db_suite)
    return db_suite


def db_delete(db: Session, suite_id: int, project_id: int):
    db_suite = db_get(db, suite_id, project_id)
    if not db_suite:
        return False

    db.delete(db_suite)
    db.commit()
    return True
