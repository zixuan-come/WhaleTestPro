from app.models.case import Case


def db_create(db, case):
    db_case = Case(**case.model_dump())
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


def db_get(db, case_id):
    return db.query(Case).filter(Case.id == case_id).first()


def db_list(db):
    return db.query(Case).all()


def db_delete(db, case_id):
    db_case = db.query(Case).filter(Case.id == case_id).first()
    if db_case is None:
        return None
    db.delete(db_case)
    db.commit()
    return db_case



