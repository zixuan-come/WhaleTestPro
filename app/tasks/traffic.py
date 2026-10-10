from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.schemas.traffic_record import TrafficRecordCreate
from app.services import traffic_record as traffic_record_service
from app.core.recording_policy import is_recordable_path
from app.core.redaction import mask_sensitive as _mask


@celery_app.task
def record_traffic(record_dict):
    # Also discard unsafe messages that were already queued before deployment.
    if not is_recordable_path(record_dict["path"]):
        return
    # 消费者：从 MQ 取出一条流量，脱敏后落 MySQL（慢活在 worker 后台干，不拖累业务请求）
    record_dict["request_headers"] = _mask(record_dict.get("request_headers"))
    record_dict["request_body"] = _mask(record_dict.get("request_body"))
    record_dict["response_body"] = _mask(record_dict.get("response_body"))
    db = SessionLocal()
    try:
        record = TrafficRecordCreate(**record_dict)
        traffic_record_service.s_create(db, record)
    finally:
        db.close()
