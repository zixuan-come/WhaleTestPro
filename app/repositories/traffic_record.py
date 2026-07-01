from app.models.traffic_record import TrafficRecord


def db_create(db, record):
    db_record = TrafficRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record


def db_get(db, record_id):
    return db.query(TrafficRecord).filter(TrafficRecord.id == record_id).first()


def db_list(db, limit=100):
    return db.query(TrafficRecord).order_by(TrafficRecord.created_at.desc()).limit(limit).all()
