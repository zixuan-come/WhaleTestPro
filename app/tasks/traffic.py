from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.schemas.traffic_record import TrafficRecordCreate
from app.services import traffic_record as traffic_record_service

# 脱敏字段清单：命中这些 key（不分大小写）的值在落库前打码，否则录制=隐私泄露
SENSITIVE_KEYS = {"password", "passwd", "pwd", "token", "authorization",
                  "cookie", "secret", "phone", "mobile", "id_card", "idcard"}
MASK = "***"


def _mask(data):
    # 只对 dict 递归打码；headers/body 不是 dict（None/list/标量）就原样返回
    if not isinstance(data, dict):
        return data
    masked = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS:
            masked[k] = MASK
        elif isinstance(v, dict):
            masked[k] = _mask(v)
        else:
            masked[k] = v
    return masked


@celery_app.task
def record_traffic(record_dict):
    # 消费者：从 MQ 取出一条流量，脱敏后落 MySQL（慢活在 worker 后台干，不拖累业务请求）
    record_dict["request_headers"] = _mask(record_dict.get("request_headers"))
    record_dict["request_body"] = _mask(record_dict.get("request_body"))
    db = SessionLocal()
    try:
        record = TrafficRecordCreate(**record_dict)
        traffic_record_service.s_create(db, record)
    finally:
        db.close()
