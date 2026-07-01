import requests
from app.repositories import traffic_record as traffic_record_repo
from app.repositories import environment as env_repo
from app.core.response_diff import diff_response

DEFAULT_BASE_URL = "http://127.0.0.1:8000"  # 不指定环境就打回本机（录的就是本机接口）


def _base_url(db, env_id):
    if env_id is None:
        return DEFAULT_BASE_URL
    env = env_repo.db_get(db, env_id)
    return env.base_url if env else DEFAULT_BASE_URL


def _safe_json(response):
    # 响应不一定是 JSON，不是就存 None，别让回放崩
    try:
        return response.json()
    except Exception:
        return None


def s_replay(db, record_id, env_id=None, field_rules=None):
    record = traffic_record_repo.db_get(db, record_id)
    if record is None:
        return None

    url = _base_url(db, env_id).rstrip("/") + record.path
    # 重放只带 X-Shadow:1（写操作落影子库零污染，复用 #17）；body 用 json= 让 requests
    # 自动设 Content-Type/content-length。不原样带录制的 headers：host 是录制时的会错、
    # content-length 跟新 body 不一定符、鉴权头已脱敏成 *** 带过去也没用
    response = requests.request(
        method=record.method,
        url=url,
        json=record.request_body,
        headers={"X-Shadow": "1"},
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
