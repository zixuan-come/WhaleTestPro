from app.models.schedule import Schedule


def db_create(db, schedule):
    db_schedule = Schedule(**schedule.model_dump())
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


def db_get(db, schedule_id):
    return db.query(Schedule).filter(Schedule.id == schedule_id).first()


def db_list(db):
    return db.query(Schedule).all()


def db_update(db, schedule_id, schedule):
    db_schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if db_schedule is None:
        return None
    for key, value in schedule.model_dump().items():
        setattr(db_schedule, key, value)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


def db_delete(db, schedule_id):
    db_schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if db_schedule is None:
        return None
    db.delete(db_schedule)
    db.commit()
    return db_schedule



