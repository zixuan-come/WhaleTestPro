"""Scenario occurrences own their saved configuration, never the source case."""
import json
from copy import deepcopy

import pytest
import requests
from sqlalchemy import create_engine, text

from tests.test_execution_reports import reports, data
from app.models.case import Case
from app.models.interface import Interface
from app.models.scenario import Scenario
from app.services import execution
from app.core.migrations import ensure_scenario_steps_schema


def create(client, ids=(1, 1)):
    response = client.post('/scenarios', json={'name': '订单存在与不存在', 'case_ids': list(ids)})
    assert response.status_code == 201, response.text
    return response.json()['data']


def update(client, scenario, steps):
    return client.put(f"/scenarios/{scenario['id']}", json={'name': scenario['name'], 'steps': steps})


def test_repeated_template_steps_are_independent_persist_and_run_after_source_deletion(reports, monkeypatch):
    client, db, _ = reports
    interface = db.get(Interface, 1)
    interface.url = '/orders/{id}'
    interface.path_params = {'id': '42'}
    db.commit()
    scenario = create(client)
    steps = scenario['steps']
    assert steps[0]['step_id'] != steps[1]['step_id']
    steps[0]['name'] = '订单存在'
    steps[1].update(name='订单不存在', expected_status=404, path_params={'id': '999'})
    saved = data(update(client, scenario, steps))
    assert saved['case_ids'] == [1, 1]
    assert saved['steps'][0]['path_params'] == {'id': '42'}
    assert db.get(Case, 1).expected_status == 200
    assert db.get(Interface, 1).path_params == {'id': '42'}
    db.delete(db.get(Case, 1))
    interface.url = '/changed-library-interface'
    db.commit()
    assert data(client.get(f"/scenarios/{scenario['id']}"))['steps'] == saved['steps']
    calls = []
    def downstream(method, url, **kwargs):
        calls.append(url)
        response = requests.Response()
        response.status_code = 404 if url.endswith('/999') else 200
        response._content = b'{"id":42}'
        response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    results = data(client.post(f"/scenarios/{scenario['id']}/run?env_id=1"))
    assert [row['case_name'] for row in results] == ['订单存在', '订单不存在']
    assert all(row['passed'] for row in results)
    assert calls == ['http://runner.invalid/orders/42', 'http://runner.invalid/orders/999']
    assert [row['step_id'] for row in results] == [row['step_id'] for row in saved['steps']]
    for number in (2, 3):
        db.delete(db.get(Case, number))
    db.delete(interface)
    db.commit()
    # The authorized snapshot owns its request, even if its source definition
    # has since been removed or migrated to another definition.
    assert all(row['passed'] for row in data(client.post(f"/scenarios/{scenario['id']}/run?env_id=1")))
    # Reordering or editing an existing snapshot does not need the old source.
    assert update(client, scenario, list(reversed(saved['steps']))).status_code == 200


def test_step_extraction_is_shared_and_records_the_edited_names_and_expectations(reports, monkeypatch):
    client, db, _ = reports
    db.get(Interface, 1).url = '/orders/{id}'
    db.get(Interface, 1).path_params = {'id': '${order_id}'}
    db.add(Interface(id=2, project_id=1, name='创建订单', method='POST', url='/orders', body={'item': 'book'}))
    db.get(Case, 2).interface_id = 2
    db.get(Case, 2).extract_rules = {'order_id': '$.id'}
    db.commit()
    scenario = create(client, (2, 1, 1))
    scenario['steps'][2].update(name='再次查询不存在', expected_status=404)
    assert update(client, scenario, scenario['steps']).status_code == 200
    calls = []
    def downstream(method, url, **kwargs):
        calls.append((method, url))
        response = requests.Response()
        response.status_code = 201 if method == 'POST' else 404 if len(calls) == 3 else 200
        response._content = b'{"id":42}'
        response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    results = data(client.post(f"/scenarios/{scenario['id']}/run?env_id=1"))
    assert all(row['passed'] for row in results)
    assert calls == [('POST', 'http://runner.invalid/orders'), ('GET', 'http://runner.invalid/orders/42'), ('GET', 'http://runner.invalid/orders/42')]
    page = data(client.get('/reports/executions?kind=scenario'))
    report = data(client.get('/reports/executions/' + page['items'][0]['id']))
    assert report['detail']['steps'][2]['case_name'] == '再次查询不存在'
    assert report['detail']['steps'][2]['assertions'][0]['expected'] == 404


def test_snapshot_does_not_follow_case_changes_and_legacy_reordering_preserves_edits(reports):
    client, db, _ = reports
    scenario = create(client, (1, 2, 1))
    scenario['steps'][0]['name'] = '自定义步骤'
    assert update(client, scenario, scenario['steps']).status_code == 200
    db.get(Case, 1).name = '后来修改模板'
    db.commit()
    reordered = data(client.put(f"/scenarios/{scenario['id']}", json={'name': scenario['name'], 'case_ids': [2, 1, 1]}))
    assert reordered['steps'][1]['name'] == '自定义步骤'
    assert reordered['steps'][1]['step_id'] == scenario['steps'][0]['step_id']
    assert reordered['steps'][2]['name'] == scenario['steps'][2]['name']


def test_snapshot_validation_and_project_isolation(reports):
    client, db, _ = reports
    scenario = create(client, (1,))
    step = scenario['steps'][0]
    for field, value, status in [('expected_status', 99, 422), ('name', ' ', 422), ('interface_id', 999, 400), ('source_case_id', 999, 400)]:
        changed = {**step, field: value}
        # A new occurrence cannot claim a deleted/foreign source as provenance.
        if field == 'source_case_id':
            changed['step_id'] = 'new-occurrence'
        assert update(client, scenario, [changed]).status_code == status
    assert update(client, scenario, [step, step]).status_code == 422
    assert update(client, scenario, [{**step, 'missing_reason': 'forged'}]).status_code == 400
    assert client.put(f"/scenarios/{scenario['id']}", json={'name': scenario['name'], 'case_ids': [2], 'steps': [step]}).status_code == 400
    db.add(Interface(id=99, project_id=2, name='foreign', method='GET', url='/secret'))
    db.commit()
    assert update(client, scenario, [{**step, 'interface_id': 99}]).status_code == 400
    assert data(client.get(f"/scenarios/{scenario['id']}"))['steps'] == [step]


def test_legacy_invalid_references_remain_visible_and_never_send_a_request(reports):
    client, _, calls = reports
    scenario = create(client, (0, 999))
    assert len(scenario['steps']) == 2 and all(step['missing_reason'] for step in scenario['steps'])
    results = data(client.post(f"/scenarios/{scenario['id']}/run?env_id=1"))
    assert len(results) == 2 and not any(row['passed'] for row in results)
    assert not calls


@pytest.mark.parametrize('modified', [False, True])
def test_suite_preview_and_execution_deduplicate_only_equivalent_template_config(reports, modified):
    client, db, calls = reports
    scenario = create(client, (1,))
    if modified:
        scenario['steps'][0]['params'] = {'purpose': 'different occurrence'}
        assert update(client, scenario, scenario['steps']).status_code == 200
    suite = client.post('/suites', json={'name': '独立步骤套件', 'type': 'mixed', 'scenario_ids': [scenario['id']], 'case_ids': [1]}).json()['data']
    selection = {'mode': 'suite', 'ids': [suite['id']], 'env_id': 1}
    preview = data(client.post('/regression/preview', json=selection))
    assert preview['ready']
    assert preview['case_count'] == int(modified)
    result = data(client.post('/regression/run', json={**selection, 'preview_key': preview['preview_key']}))
    assert result['passed']
    assert len(calls) == (2 if modified else 1)


def test_migration_preserves_order_duplicates_missing_and_project_boundaries_and_is_idempotent():
    engine = create_engine('sqlite://')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE scenario(id INTEGER PRIMARY KEY, project_id INTEGER, case_ids JSON)'))
        db.execute(text('CREATE TABLE test_case(id INTEGER PRIMARY KEY, project_id INTEGER, interface_id INTEGER, name TEXT, expected_status INTEGER, request_overrides JSON)'))
        db.execute(text('CREATE TABLE interface(id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, method TEXT, url TEXT, path_params JSON, body JSON)'))
        db.execute(text("INSERT INTO interface VALUES(1,1,'查询','GET','/orders/{id}','{\"id\":\"base\"}',NULL)"))
        db.execute(text("INSERT INTO test_case VALUES(1,1,1,'模板',200,'{\"path_params\":{\"id\":\"42\"}}'),(2,2,1,'foreign-secret',200,NULL)"))
        db.execute(text("INSERT INTO scenario VALUES(1,1,'[1,1,2,999]'),(2,1,'[]')"))
    ensure_scenario_steps_schema(engine)
    with engine.connect() as db:
        saved = json.loads(db.execute(text('SELECT steps FROM scenario WHERE id=1')).scalar_one())
        assert [step['source_case_id'] for step in saved] == [1, 1, 2, 999]
        assert saved[0]['path_params'] == {'id': '42'}
        assert len({step['step_id'] for step in saved}) == 4
        assert saved[2]['missing_reason'] and 'foreign-secret' not in str(saved)
        assert json.loads(db.execute(text('SELECT steps FROM scenario WHERE id=2')).scalar_one()) == []
    with engine.begin() as db:
        db.execute(text("UPDATE test_case SET name='later-change' WHERE id=1"))
    ensure_scenario_steps_schema(engine)
    with engine.connect() as db:
        assert json.loads(db.execute(text('SELECT steps FROM scenario WHERE id=1')).scalar_one()) == saved
        assert db.execute(text('SELECT COUNT(*) FROM test_case')).scalar_one() == 2
    engine.dispose()
