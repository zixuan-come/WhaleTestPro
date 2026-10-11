from app.core.celery_app import celery_app
from app.database import SessionLocal
from app.schemas.traffic_record import TrafficRecordCreate
from app.services import traffic_record as traffic_record_service
from app.core.recording_policy import is_recordable_path
from app.core.redaction import mask_sensitive as _mask, mask_record_payload
from app.core import metrics
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError


class TrafficRecordingError(RuntimeError):
    """Low-sensitivity task error; never carries SQL or message parameters."""


@celery_app.task(bind=True, max_retries=3, ignore_result=True)
def record_traffic(self, record_dict):
    # Also discard unsafe messages that were already queued before deployment.
    if (isinstance(record_dict, dict) and isinstance(record_dict.get("path"), str)
            and not is_recordable_path(record_dict["path"])):
        return
    db, failure, rollback_ok = None, None, False
    safe_record = None
    try:
        safe_record = mask_record_payload(dict(record_dict))
        record = TrafficRecordCreate(**safe_record)
        db = SessionLocal()
        # No post-COMMIT refresh: a SELECT deadlock after a successful write
        # must not make the consumer insert the same record again.
        traffic_record_service.s_create(db, record, refresh=False)
    except Exception as exc:
        failure = exc
        if db is not None:
            try:
                db.rollback()
                rollback_ok = True
            except Exception:
                pass
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as exc:
                failure = failure or exc
                rollback_ok = False

    if failure is None:
        return
    metrics.traffic_record_persist_failures.inc()
    safe_error = TrafficRecordingError(f"流量录制保存失败，错误类型：{type(failure).__name__}")
    # Only confirmed rollback-safe MySQL errors. Never retry a disconnected
    # COMMIT (2006/2013), validation errors or integrity violations.
    code = (getattr(getattr(failure, "orig", None), "args", ()) or (None,))[0]
    retryable = isinstance(failure, OperationalError) and code in {1205, 1213}
    if retryable and rollback_ok and self.request.retries < self.max_retries:
        metrics.traffic_record_persist_retries.inc()
        try:
            raise self.retry(exc=safe_error, args=(safe_record,), kwargs={},
                             countdown=min(2 ** self.request.retries, 8)) from None
        except Retry as retry:
            raise retry from None
        except Exception:
            metrics.traffic_record_persist_terminal_failures.inc()
            raise TrafficRecordingError("流量录制重试投递失败") from None
    metrics.traffic_record_persist_terminal_failures.inc()
    raise safe_error from None
