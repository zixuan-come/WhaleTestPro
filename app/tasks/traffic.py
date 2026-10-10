from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.schemas.traffic_record import TrafficRecordCreate
from app.services import traffic_record as traffic_record_service
from app.core.recording_policy import is_recordable_path

# 脱敏字段清单：命中这些 key（不分大小写）的值在落库前打码，否则录制=隐私泄露
SENSITIVE_KEYS = {"password", "passwd", "pwd", "token", "authorization",
                  "cookie", "secret", "phone", "mobile", "id_card", "idcard",
                  "hashed_password", "access_token", "refresh_token", "secret_key",
                  "set-cookie", "x-shadow-authorization", "api_key", "apikey"}
MASK = "***"


def _mask(data):
    if isinstance(data, list):
        return [_mask(value) for value in data]
    if not isinstance(data, dict):
        return data
    masked = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS:
            masked[k] = MASK
        else:
            masked[k] = _mask(v)
    return masked


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
