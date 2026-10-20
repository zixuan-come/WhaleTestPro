import json
import requests
from app.repositories import traffic_record as traffic_record_repo
from app.repositories import environment as env_repo
from app.core.response_diff import diff_response, validate_field_rules
from app.core.config import settings
from app.core.redaction import mask_sensitive, sensitive_strings
from app.core.variables import render_deep
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


def s_replay(db, record_id, project_id, env_id=None, field_rules=None, *, overrides=None):
    validate_field_rules(field_rules)
    record = traffic_record_repo.db_get(db, record_id, project_id)
    if record is None:
        return None

    env = env_repo.db_get(db, env_id, project_id) if env_id is not None else None
    if env_id is not None and env is None:
        raise ValueError("所选环境不存在或不属于当前项目")
    if getattr(record, "source", None) == "debug" and env is None:
        raise ValueError("请选择回放环境")
    base_url = _base_url(db, env_id, project_id)
    context = (env.variables or {}) if env else {}
    overrides = overrides or {}
    excluded = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding",
                "x-shadow", "x-shadow-authorization"}
    headers = {key.lower(): value for key, value in (getattr(record, "request_headers", None) or {}).items()}
    headers.update({key.lower(): value for key, value in (overrides.get("headers") or {}).items()})
    headers = {key: value for key, value in headers.items() if key not in excluded}
    params = overrides.get("params", getattr(record, "request_params", None))
    body = overrides.get("body", record.request_body)
    try:
        headers, params, body = (render_deep(value, context) for value in (headers, params, body))
    except KeyError:
        raise ValueError("环境变量未找到，请检查回放配置") from None
    if "***" in record.path:
        raise ValueError("录制路径包含脱敏内容，请在接口调试中重新配置请求")
    if "***" in json.dumps([headers, params, body], ensure_ascii=False):
        raise ValueError("请求包含已脱敏字段，请在回放配置中补充 Headers、Query 或 Body")
    if len(json.dumps([headers, params, body]).encode()) > 64 * 1024:
        raise ValueError("回放请求配置不能超过 64 KB")
    if not record.path.startswith("/") or record.path.startswith("//") or any(c in record.path for c in "?#"):
        raise ValueError("录制路径无效，未发送请求")
    url = base_url.rstrip("/") + record.path
    headers["X-Shadow"] = "1"
    internal = is_internal_replay_url(base_url)
    if internal:
        headers[SHADOW_TOKEN_HEADER] = create_shadow_credential(record.method, record.path)
    # Internal demo replay requires a method/path-bound credential. External
    # targets receive only the shadow hint, never our internal credential.
    # Do not forward recorded Host, Content-Length or masked authentication.
    secrets = set(secret for value in (headers, params, body) for secret in sensitive_strings(value))
    try:
        response = requests.request(method=record.method, headers=headers, url=url, params=params,
            timeout=settings.REQUEST_TIMEOUT_SECONDS, json=body, allow_redirects=False)
    except requests.RequestException:
        raise ValueError("回放请求失败，请检查目标环境、网络和超时配置") from None
    truncated = len(getattr(response, "content", b"") or b"") > 64 * 1024
    if truncated:
        replayed_body = None
    else:
        try:
            replayed_body = response.json()
        except (ValueError, AttributeError):
            replayed_body = getattr(response, "text", None)
    secrets.update(sensitive_strings(replayed_body))
    recorded_body = mask_sensitive(record.response_body, secrets=secrets)
    replayed_body = mask_sensitive(replayed_body, secrets=secrets)
    # 第⑤步：录制老响应 vs 回放新响应逐字段 diff（智能模糊比对，忽略/类型/正则/容差）
    diff = diff_response(recorded_body, replayed_body, field_rules)
    if record.response_status != response.status_code:
        diff["diffs"].insert(0, {"path": "(HTTP 状态码)", "recorded": record.response_status,
            "replayed": response.status_code, "reason": "状态码不同"})
    if truncated:
        diff["diffs"].append({"path": "(响应体)", "recorded": None, "replayed": None,
            "reason": "响应超过 64 KB，未进行完整比较"})
    diff["same"] = not diff["diffs"]

    return {
        "record_id": record.id,
        "method": record.method,
        "path": record.path,
        "recorded_status": record.response_status,
        "recorded_body": recorded_body,
        "replayed_status": response.status_code,
        "replayed_body": replayed_body,
        "diff": diff,
        "target_url": mask_sensitive(url, secrets=secrets),
        "body_truncated": truncated,
    }
