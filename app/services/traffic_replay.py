import requests
from app.repositories import traffic_record as traffic_record_repo
from app.repositories import environment as env_repo
from app.core.response_diff import diff_response
from app.core.config import settings
from app.core.shadow_access import SHADOW_TOKEN_HEADER, create_shadow_credential, is_internal_replay_url

DEFAULT_BASE_URL = "http://127.0.0.1:8000"  # 不指定环境就打回本机（录的就是本机接口）


def _safe_json(response):
    # 响应不一定是 JSON，不是就存 None，别让回放崩
    try:
        return response.json()
    except Exception:
        return None


def _base_url(db, env_id, project_id):
    if env_id is None:
        return DEFAULT_BASE_URL
    env = env_repo.db_get(db, env_id, project_id)
    if env is None:
        raise ValueError(f"环境 id={env_id} 不存在或不属于当前项目")
    return env.base_url


def s_replay(db, record_id, project_id, env_id=None, field_rules=None):
    record = traffic_record_repo.db_get(db, record_id, project_id)
    if record is None:
        return None

    base_url = _base_url(db, env_id, project_id)
    url = base_url.rstrip("/") + record.path
    headers = {"X-Shadow": "1"}
    internal = is_internal_replay_url(base_url)
    if internal:
        headers[SHADOW_TOKEN_HEADER] = create_shadow_credential(record.method, record.path)
    # Internal demo replay requires a method/path-bound credential. External
    # targets receive only the shadow hint, never our internal credential.
    # Do not forward recorded Host, Content-Length or masked authentication.
    response = requests.request(
        method=record.method,
        headers=headers,
        url=url,
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
        json=record.request_body,
        allow_redirects=not internal,
    )

    replayed_body = _safe_json(response)
    # 第⑤步：录制老响应 vs 回放新响应逐字段 diff（智能模糊比对，忽略/类型/正则/容差）
    diff = diff_response(record.response_body, replayed_body, field_rules)

    return {
        "record_id": record.id,
        "method": record.method,
        "path": record.path,
        "recorded_status": record.response_status,
        "recorded_body": record.response_body,
        "replayed_status": response.status_code,
        "replayed_body": replayed_body,
        "diff": diff,
    }
