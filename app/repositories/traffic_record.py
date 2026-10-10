from sqlalchemy.orm import Session
from sqlalchemy import not_, or_
from app.models.traffic_record import TrafficRecord
from app.core.recording_policy import RECORD_SKIP_PREFIXES


def _visible_records(db):
    # Do not expose historical team/auth records incorrectly assigned to a
    # project. Keep the rows for administrator audit instead of deleting data.
    return db.query(TrafficRecord).filter(not_(or_(
        *(TrafficRecord.path.startswith(prefix) for prefix in RECORD_SKIP_PREFIXES)
    )))


def db_create(db: Session, record):
    # record 自带 project_id(schema 里必填,由 middleware 塞入)—— 不额外传参
    db_record = TrafficRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def db_get(db: Session, record_id: int, project_id: int):
    return _visible_records(db).filter(
        TrafficRecord.id == record_id,
        TrafficRecord.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int, limit: int = 100):
    return _visible_records(db).filter(
        TrafficRecord.project_id == project_id,
    ).order_by(TrafficRecord.created_at.desc()).limit(limit).all()
