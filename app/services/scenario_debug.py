"""Transient, owned single-step HTTP debugging; never mutate assets or reports."""
from contextlib import contextmanager
from copy import deepcopy
import json
import re
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.shadow_ctx import is_shadow
from app.core.redaction import MASK, is_sensitive_source, mask_sensitive, sensitive_strings
from app.core.variables import extract_match, render_deep
from app.schemas.scenario import ScenarioCreate
from app.services import execution, scenario

TTL = 600
MAX_JSON = 256 * 1024
MAX_STATE = 1024 * 1024
MAX_VARIABLES = 128 * 1024


def _key(project_id, user_id, scenario_id, env_id, session_id):
    return f'scenario-debug:{int(is_shadow())}:{project_id}:{user_id}:{scenario_id}:{env_id}:{session_id}'


@contextmanager
def _session(project_id, user_id, scenario_id, env_id, session_id):
    token = session_id or uuid4().hex
    key = _key(project_id, user_id, scenario_id, env_id, token)
    lock = redis_client.lock(key + ':busy', timeout=max(45, settings.REQUEST_TIMEOUT_SECONDS + 15), blocking_timeout=0)
    acquired = False
    try:
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise HTTPException(409, '当前调试尚未完成，请等待后再操作')
        raw = redis_client.get(key)
        if session_id and raw is None:
            raise HTTPException(409, '调试会话已过期，请清空调试变量后重试')
        state = json.loads(raw) if raw else {'variables': {}, 'owners': {}, 'responses': {}, 'secrets': []}
        yield token, key, state
    except RedisError:
        raise HTTPException(503, '调试缓存暂不可用，请稍后重试') from None
    finally:
        if acquired:
            try:
                lock.release()
            except RedisError:
                pass


def _save(key, state):
    while len(state['responses']) > 8 or len(json.dumps(state, ensure_ascii=False).encode()) > MAX_STATE:
        if not state['responses']:
            raise HTTPException(400, '临时变量过大，请清空后重试')
        del state['responses'][next(iter(state['responses']))]
    redis_client.set(key, json.dumps(state, ensure_ascii=False), ex=TTL)


def _clear_step(state, step_id):
    for name in list(state['owners']):
        if state['owners'][name] == step_id:
            state['variables'].pop(name, None)
            del state['owners'][name]
    for token, item in list(state['responses'].items()):
        if item['step_id'] == step_id:
            del state['responses'][token]


def _collect_variables(value):
    if isinstance(value, str):
        return set(re.findall(r'\$\{(\w+)\}', value))
    if isinstance(value, dict):
        return set().union(*(_collect_variables(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_collect_variables(item) for item in value), set())
    return set()


def _extract(state, entry, rules, context, secrets):
    values, rows = {}, []
    for name, path in rules.items():
        try:
            if not re.fullmatch(r'\w{1,64}', name) or name == 'base_url':
                raise ValueError('提取变量名无效或覆盖了 base_url')
            match = extract_match(entry['json'], render_deep(path, context))
            value = match.value
            sensitive = is_sensitive_source(str(match.full_path)) or is_sensitive_source(name)
            secrets.update(sensitive_strings(value, sensitive=sensitive))
            values[name] = deepcopy(value)
            rows.append({'name': name, 'path': path, 'passed': True, 'value': MASK if sensitive else value})
        except Exception as exc:
            rows.append({'name': name, 'path': path, 'passed': False, 'error': str(exc)})
    if all(row['passed'] for row in rows):
        merged = {**{name: value for name, value in state['variables'].items()
                     if state['owners'].get(name) != entry['step_id']}, **values}
        if len(merged) > 100 or len(json.dumps(merged, ensure_ascii=False).encode()) > MAX_VARIABLES:
            return [{'passed': False, 'error': '提取结果过大，临时变量最多 100 项、128 KiB'}]
        # Replace this step's previous extraction atomically, including removed rules.
        for name in list(state['owners']):
            if state['owners'][name] == entry['step_id']:
                state['variables'].pop(name, None)
                del state['owners'][name]
        state['variables'].update(values)
        state['owners'].update({name: entry['step_id'] for name in values})
    return rows


def _result(token, state, result, secrets):
    state['secrets'] = list(secrets)
    result = deepcopy(result)
    for key in ('error', 'extraction'):
        if key in result:
            result[key] = mask_sensitive(result[key], secrets=secrets)
    for key in ('request_detail', 'response_detail'):
        if key in result:
            result[key] = execution._evidence_detail(result[key], secrets)
    if 'assertions' in result:
        result['assertions'] = execution._assertion_evidence(result['assertions'], secrets)
    return {**result, 'session_id': token, 'variables': mask_sensitive(state['variables'], secrets=secrets)}


def _owned_scene(db, scenario_id, project_id):
    scene = scenario.s_get(db, scenario_id, project_id)
    if scene is None:
        raise HTTPException(404, '场景不存在或不属于当前项目')
    return scene


def debug_step(db, scenario_id, env_id, project_id, user_id, payload):
    scene = _owned_scene(db, scenario_id, project_id)
    resolved = scenario._with_steps(db, ScenarioCreate(name=scene.name, steps=[payload.step]), project_id, scene)
    step = resolved.steps[0]
    if step.missing_reason:
        raise HTTPException(400, '此步骤配置失效，请重新应用模板')
    base = execution._env_context(db, env_id, project_id)
    if not base.get('base_url'):
        raise HTTPException(400, '请先选择配置了 Base URL 的执行环境')
    with _session(project_id, user_id, scenario_id, env_id, payload.session_id) as (token, key, state):
        _clear_step(state, step.step_id)
        state['variables'].update(deepcopy(payload.variables))
        state['owners'].update({name: 'manual' for name in payload.variables})
        if len(state['variables']) > 100 or len(json.dumps(state['variables'], ensure_ascii=False).encode()) > MAX_VARIABLES:
            raise HTTPException(400, '临时变量最多 100 项、128 KiB')
        context = {**base, **state['variables']}
        secrets = set(state['secrets']) | set(sensitive_strings(context))
        # Ensure Redis is writable before any downstream side effect.
        _save(key, state)
        result = {'step_id': step.step_id, 'expected_status': step.expected_status, 'actual_status': None,
                  'passed': False, 'assertions': [], 'extraction': [], 'request_detail': None,
                  'response_detail': None, 'response_id': None, 'missing_variables': []}
        started = perf_counter()
        try:
            missing = sorted(_collect_variables({field: getattr(step, field) for field in
                ('url', 'path_params', 'headers', 'params', 'body', 'assertions', 'extract_rules')}) - context.keys())
            if missing:
                result['missing_variables'] = missing
                raise ValueError('请填写缺失的临时变量：' + '、'.join(missing))
            interface = SimpleNamespace(id=step.interface_id, **{field: getattr(step, field) for field in ('method', 'url', 'path_params', 'headers', 'params', 'body')})
            secrets.update(sensitive_strings(render_deep(step.path_params, context)))
            url = execution._full_url(step.url, context, step.path_params)
            fields = execution._render_request_fields(interface, context, secrets)
            result['request_detail'] = {'method': step.method, 'url': url, 'headers': fields['headers'], 'params': fields['params'], 'body': fields['json']}
            response = execution._request(interface, url=url, **fields)
            result['actual_status'] = response.status_code
            execution._add_response_secrets(response, secrets)
            result['response_detail'] = execution._response_detail(response, secrets=secrets)
            if len(response.content or b'') <= MAX_JSON:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                    cacheable = False
                else:
                    cacheable = True
                if cacheable:
                    response_id = uuid4().hex
                    entry = {'step_id': step.step_id, 'json': body, 'context': context,
                             'checks_passed': False,
                             'response_detail': result['response_detail'], 'request_detail': result['request_detail']}
                    state['responses'][response_id] = entry
                    result['response_id'] = response_id
                    result['extraction'] = _extract(state, entry, step.extract_rules or {}, context, secrets)
            if step.extract_rules and result['response_id'] is None:
                result['extraction'] = [{'passed': False, 'error': '响应不是 JSON 或超过 256 KiB，无法验证提取'}]
            result['assertions'] = execution.run_assertions(response, render_deep(step.assertions, context), db)
            result['passed'] = response.status_code == step.expected_status and all(row['passed'] for row in result['assertions'])
            if result['response_id']:
                state['responses'][result['response_id']]['checks_passed'] = result['passed']
            if any(not row['passed'] for row in result['extraction']):
                result['passed'] = False
        except Exception as exc:
            result['passed'] = False
            result['error'] = str(exc)
        result['duration_ms'] = round((perf_counter() - started) * 1000)
        safe = _result(token, state, result, secrets)
        _save(key, state)
        return safe


def validate_extraction(db, scenario_id, env_id, project_id, user_id, payload):
    _owned_scene(db, scenario_id, project_id)
    execution._env_context(db, env_id, project_id)
    with _session(project_id, user_id, scenario_id, env_id, payload.session_id) as (token, key, state):
        entry = state['responses'].get(payload.response_id)
        if entry is None:
            raise HTTPException(409, '这次响应已过期，请重新发送当前步骤')
        secrets = set(state['secrets'])
        rows = _extract(state, entry, payload.extract_rules, entry['context'], secrets)
        safe = _result(token, state, {'step_id': entry['step_id'], 'extraction': rows,
            'passed': entry['checks_passed'] and all(row['passed'] for row in rows),
            'request_detail': entry['request_detail'], 'response_detail': entry['response_detail']}, secrets)
        _save(key, state)
        return safe
