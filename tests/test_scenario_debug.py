"""Owned step drafts and cached JSONPath previews without real external IO."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import requests
from redis.exceptions import ConnectionError

from tests.test_execution_reports import reports, data
from app.core.scenario_steps import case_snapshot
from app.models.case import Case
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.report import TestReport as Report
from app.models.execution_report import ExecutionReport
from app.models.scenario import Scenario
from app.routers import scenario as router
from app.services import execution, scenario_debug


class Cache:
    def __init__(self):
        self.values = {}
        self.available = True
        self.busy = False

    def lock(self, *args, **kwargs):
        return self

    def acquire(self, **kwargs):
        if not self.available:
            raise ConnectionError('private-cache-credential')
        return not self.busy

    def release(self):
        pass

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        assert ex == 600
        self.values[key] = value
        return True


@pytest.fixture
def debug(reports, monkeypatch):
    client, db, calls = reports
    cache = Cache()
    monkeypatch.setattr(scenario_debug, 'redis_client', cache)
    owner = SimpleNamespace(project_id=1, user=SimpleNamespace(id=1))
    for route in router.router.routes:
        if '/debug' in route.path:
            for dependency in route.dependant.dependencies:
                if dependency.name == 'context':
                    client.app.dependency_overrides[dependency.call] = lambda: owner
    interface = db.get(Interface, 1)
    step = case_snapshot(db.get(Case, 1), interface)
    step.update(name='创建订单', method='POST', url='/orders', body={'quantity': 2}, expected_status=201)
    db.get(Scenario, 1).steps = [deepcopy(step)]
    db.commit()

    def downstream(method, url, **kwargs):
        calls.append({'method': method, 'url': url, **kwargs})
        response = requests.Response()
        response.status_code = 201 if method == 'POST' else 200
        response._content = b'{"id":42,"token":"private-response-token","enabled":false,"items":[]}'
        response.headers['Content-Type'] = 'application/json'
        return response

    monkeypatch.setattr(execution.requests, 'request', downstream)
    return client, db, calls, step, owner, cache


def send(client, step, **kwargs):
    env = kwargs.pop('env', 1)
    return client.post(f'/scenarios/1/debug?env_id={env}', json={'step': step, **kwargs})


def extract(client, result, rules, env=1):
    return client.post(f'/scenarios/1/debug/extract?env_id={env}', json={
        'session_id': result['session_id'], 'response_id': result['response_id'], 'extract_rules': rules})


def test_draft_debug_response_and_cached_extraction_do_not_save_or_resend(debug):
    client, db, calls, step, _, _ = debug
    before = deepcopy(db.get(Scenario, 1).steps)
    step.update(name='临时创建步骤', expected_status=200)  # Mismatch must still expose the JSON.
    result = data(send(client, step))
    assert not result['passed'] and result['actual_status'] == 201
    assert result['response_detail']['body']['id'] == 42
    assert result['response_detail']['body']['token'] == '***'
    assert len(calls) == 1 and calls[0]['method'] == 'POST'
    assert calls[0]['json'] == {'quantity': 2}
    preview = data(extract(client, result, {'order_id': '$.id', 'enabled': '$.enabled', 'items': '$.items'}))
    assert preview['variables'] == {'order_id': 42, 'enabled': False, 'items': []}
    assert len(calls) == 1
    assert db.get(Scenario, 1).steps == before and db.get(Case, 1).name == '用例1'
    assert db.query(Report).count() == db.query(ExecutionReport).count() == 0
    query = {**step, 'step_id': 'query-copy', 'method': 'GET', 'url': '/orders/{id}',
             'path_params': {'id': '${order_id}'}, 'body': None, 'expected_status': 200}
    queried = data(send(client, query, session_id=result['session_id']))
    assert queried['passed'] and calls[-1]['url'] == 'http://runner.invalid/orders/42'


def test_missing_variables_never_send_and_manual_values_can_complete_the_step(debug):
    client, _, calls, step, _, _ = debug
    step.update(method='GET', url='/orders/${order_id}', body=None, expected_status=200)
    missing = data(send(client, step))
    assert missing['missing_variables'] == ['order_id'] and not calls
    result = data(send(client, step, session_id=missing['session_id'], variables={'order_id': 777}))
    assert result['passed'] and calls[0]['url'].endswith('/orders/777')


def test_extraction_failures_are_atomic_and_changed_rules_replace_previous_values(debug):
    client, _, calls, step, _, _ = debug
    result = data(send(client, step))
    first = data(extract(client, result, {'order_id': '$.id'}))
    failed = data(extract(client, result, {'other_id': '$.id', 'bad': '$.absent'}))
    assert failed['variables'] == first['variables'] == {'order_id': 42}
    assert any(not row['passed'] for row in failed['extraction'])
    cleared = data(extract(client, result, {}))
    assert cleared['variables'] == {} and len(calls) == 1


def test_raw_extracted_credentials_are_reused_but_evidence_and_variables_are_masked(debug):
    client, _, calls, step, _, _ = debug
    result = data(send(client, step))
    result = {**result, **data(extract(client, result, {'login_token': '$.token'}))}
    assert result['variables']['login_token'] == '***'
    assert 'private-response-token' not in json.dumps(result)
    query = {**step, 'step_id': 'authenticated-query', 'method': 'GET', 'url': '/orders',
             'headers': {'Authorization': 'Bearer ${login_token}'}, 'body': None, 'expected_status': 200}
    result = data(send(client, query, session_id=result['session_id']))
    assert result['passed'] and calls[-1]['headers']['Authorization'] == 'Bearer private-response-token'
    assert 'private-response-token' not in json.dumps(result)


def test_context_and_response_tickets_are_isolated_and_expire(debug):
    client, db, calls, step, owner, cache = debug
    result = data(send(client, step))
    owner.user.id = 2
    assert extract(client, result, {'id': '$.id'}).status_code == 409
    owner.user.id = 1
    db.add(Environment(id=2, project_id=1, name='another', base_url='http://other.invalid'))
    db.add(Scenario(id=2, project_id=1, name='another-scene', steps=[step], case_ids=[1]))
    db.commit()
    assert extract(client, result, {'id': '$.id'}, env=2).status_code == 409
    assert client.post('/scenarios/2/debug/extract?env_id=1', json={'session_id': result['session_id'],
        'response_id': result['response_id'], 'extract_rules': {'id': '$.id'}}).status_code == 409
    owner.project_id = 2
    assert send(client, step, session_id=result['session_id']).status_code == 404
    owner.project_id = 1
    cache.values.clear()
    assert extract(client, result, {'id': '$.id'}).status_code == 409
    assert len(calls) == 1


def test_owned_draft_validation_and_cache_outages_fail_before_downstream_call(debug):
    client, db, calls, step, _, cache = debug
    db.add(Interface(id=2, project_id=2, name='foreign', method='GET', url='/private'))
    db.commit()
    assert send(client, {**step, 'interface_id': 2}).status_code == 400
    assert send(client, step, variables={'base_url': 'http://foreign.invalid'}).status_code == 422
    assert send(client, step, env=999).status_code == 404
    assert send(client, {**step, 'url': 'http://foreign.invalid'}).status_code == 422
    cache.available = False
    failure = send(client, step)
    assert failure.status_code == 503 and 'private-cache-credential' not in failure.text
    cache.available = True; cache.busy = True
    assert send(client, step).status_code == 409 and not calls


@pytest.mark.parametrize('raw,path,value', [(b'false', '$', False), (b'0', '$', 0), (b'null', '$', None), (b'[]', '$', [])])
def test_cached_json_preserves_falsy_root_values(debug, monkeypatch, raw, path, value):
    client, _, _, step, _, _ = debug
    def downstream(*args, **kwargs):
        response = requests.Response(); response.status_code = 201; response._content = raw
        response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    result = data(send(client, step))
    assert data(extract(client, result, {'value': path}))['variables']['value'] == value


@pytest.mark.parametrize('raw', [b'plain text', b'{"large":"' + b'x' * (260 * 1024) + b'"}'])
def test_non_json_and_oversized_responses_still_display_without_extract_ticket(debug, monkeypatch, raw):
    client, _, _, step, _, _ = debug
    def downstream(*args, **kwargs):
        response = requests.Response(); response.status_code = 201; response._content = raw
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    result = data(send(client, step))
    assert result['response_detail']['status_code'] == 201 and result['response_id'] is None


def test_timeout_keeps_request_evidence_and_returns_no_fake_response(debug, monkeypatch):
    client, _, _, step, _, _ = debug
    monkeypatch.setattr(execution.requests, 'request', lambda *a, **k: (_ for _ in ()).throw(requests.Timeout('timeout')))
    result = data(send(client, step))
    assert result['error'] == 'timeout' and not result['passed']
    assert result['request_detail']['method'] == 'POST' and result['response_detail'] is None


def test_numeric_secret_does_not_redact_http_status_or_verdict_metadata(debug, monkeypatch):
    client, _, _, step, _, _ = debug
    def downstream(*args, **kwargs):
        response = requests.Response(); response.status_code = 201
        response._content = b'{"token":201,"id":42}'; response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    result = data(send(client, step))
    assert result['passed'] and result['actual_status'] == result['response_detail']['status_code'] == 201
    assert result['response_detail']['body']['token'] == '***'


def test_bad_assertion_still_caches_received_json_for_later_extraction(debug):
    client, _, calls, step, _, _ = debug
    step['assertions'] = [{'malformed': True}]
    result = data(send(client, step))
    assert not result['passed'] and result['response_id']
    assert data(extract(client, result, {'id': '$.id'}))['variables'] == {'id': 42}
    assert len(calls) == 1


def test_correcting_jsonpath_updates_debug_verdict_without_a_second_http_request(debug):
    client, _, calls, step, _, _ = debug
    step['extract_rules'] = {'order_id': '$.missing'}
    result = data(send(client, step))
    assert not result['passed']
    corrected = data(extract(client, result, {'order_id': '$.id'}))
    assert corrected['passed'] and corrected['variables'] == {'order_id': 42}
    assert len(calls) == 1
