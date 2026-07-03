from sqlalchemy.orm import Session
from app.models.traffic_record import TrafficRecord


def db_create(db: Session, record):
    # record 自带 project_id(schema 里必填,由 middleware 塞入)—— 不额外传参
    db_record = TrafficRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def db_get(db: Session, record_id: int, project_id: int):
    return db.query(TrafficRecord).filter(
        TrafficRecord.id == record_id,
        TrafficRecord.project_id == project_id,
    ).first()


def db_list(db: Session, project_id: int, limit: int = 100):
    return db.query(TrafficRecord).filter(
        TrafficRecord.project_id == project_id,
    ).order_by(TrafficRecord.created_at.desc()).limit(limit).all()
