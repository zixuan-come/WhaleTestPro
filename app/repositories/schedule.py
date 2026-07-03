from sqlalchemy.orm import Session
from app.models.schedule import Schedule


def db_create(db: Session, schedule, project_id: int):
    db_schedule = Schedule(**schedule.model_dump(), project_id=project_id)
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


def db_get(db: Session, schedule_id: int, project_id: int):
    return db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int):
    return db.query(Schedule).filter(Schedule.project_id == project_id).all()


def db_update(db: Session, schedule_id: int, schedule, project_id: int):
    db_schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.project_id == project_id,
    ).first()
    if db_schedule is None:
        return None
    for key, value in schedule.model_dump().items():
        setattr(db_schedule, key, value)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


def db_delete(db: Session, schedule_id: int, project_id: int):
    db_schedule = db.query(Schedule).filter(
        Schedule.id == schedule_id,
        Schedule.project_id == project_id,
    ).first()
    if db_schedule is None:
        return None
    db.delete(db_schedule)
    db.commit()
    return db_schedule
