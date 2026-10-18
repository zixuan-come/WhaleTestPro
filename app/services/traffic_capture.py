"""Capture only the current user's explicit interface debug executions."""
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from app.models.traffic_capture import TrafficCapture
from app.models.traffic_record import TrafficRecord
from app.schemas.traffic_record import TrafficRecordCreate
from app.repositories.traffic_record import db_create
from app.core.redaction import mask_sensitive, sensitive_strings

MAX_RECORDS = 1000
MAX_BYTES = 64 * 1024


def _row(db, project_id, user_id):
    return db.get(TrafficCapture, (project_id, user_id))


def active(db, project_id, user_id):
    row = _row(db, project_id, user_id)
    return row if row and not row.stopped_at and row.expires_at > datetime.utcnow() else None


def state(db, project_id, user_id):
    row = _row(db, project_id, user_id)
    count = db.query(TrafficRecord).filter(TrafficRecord.project_id == project_id,
        TrafficRecord.capture_id == row.capture_id).count() if row else 0
    return {"active": bool(row and not row.stopped_at and row.expires_at > datetime.utcnow()),
            "capture_id": row.capture_id if row else None, "count": count,
            "started_at": row.started_at if row else None,
            "expires_at": row.expires_at if row else None, "limit": MAX_RECORDS}


def start(db, project_id, user_id):
    row = _row(db, project_id, user_id)
    if row and not row.stopped_at and row.expires_at > datetime.utcnow():
        return state(db, project_id, user_id)
    now = datetime.utcnow()
    if row is None:
        row = TrafficCapture(project_id=project_id, user_id=user_id)
        db.add(row)
    row.capture_id, row.started_at = str(uuid4()), now
    row.expires_at, row.stopped_at = now + timedelta(hours=1), None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # Concurrent first start: keep the already created session.
    return state(db, project_id, user_id)


def stop(db, project_id, user_id):
    db.query(TrafficCapture).filter(TrafficCapture.project_id == project_id,
        TrafficCapture.user_id == user_id).update({"stopped_at": datetime.utcnow()})
    db.commit()
    return state(db, project_id, user_id)


def save_debug(db, *, project_id, user_id, capture_id, interface, request, response, duration_ms, base_url="", known_secrets=()):
    # Recheck at completion so stop, expiry and restart cannot attach a late response.
    row = db.query(TrafficCapture).filter(TrafficCapture.project_id == project_id,
        TrafficCapture.user_id == user_id).populate_existing().with_for_update().first()
    if not row or row.stopped_at or row.expires_at <= datetime.utcnow() or row.capture_id != capture_id:
        return "录制已停止，本次请求未加入记录"
    count = len(db.query(TrafficRecord.id).filter(TrafficRecord.project_id == project_id,
        TrafficRecord.capture_id == capture_id).with_for_update().all())
    if count >= MAX_RECORDS:
        return "本次录制已达到 1000 条上限，请停止后重新开始"
    parsed = urlsplit(request["url"])
    base = urlsplit(base_url)
    path = parsed.path or "/"
    if base.path.rstrip("/") and path.startswith(base.path.rstrip("/") + "/"):
        path = path[len(base.path.rstrip("/")):]
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in (request.get("params") or {}).items():
        if value is None:
            continue
        if key in params:
            params[key] += [item for item in (value if isinstance(value, list) else [value]) if item is not None]
        else:
            params[key] = value
    fields = {"request_headers": request.get("headers"), "request_params": params,
              "request_body": request.get("body"), "response_body": response.get("body")}
    if response.get("body_truncated") or len(json.dumps(fields, ensure_ascii=False).encode()) > MAX_BYTES:
        return "请求或响应超过 64 KB，本次未录制"
    secrets = set(known_secrets) | {secret for value in fields.values() for secret in sensitive_strings(value)}
    safe = mask_sensitive(fields, secrets=secrets)
    payload = TrafficRecordCreate(method=request["method"], path=mask_sensitive(path, secrets=secrets),
        project_id=project_id, source="debug", capture_id=capture_id,
        interface_name=mask_sensitive(interface.name, secrets=secrets)[:200],
        target_host=f"{parsed.scheme}://{parsed.netloc.rsplit('@', 1)[-1]}"[:500],
        response_status=response["status_code"], duration_ms=duration_ms, **safe)
    db_create(db, payload)
    return None
