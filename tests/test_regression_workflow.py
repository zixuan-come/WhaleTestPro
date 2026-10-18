import pytest
import requests

from tests.test_execution_reports import reports, data, listing, Case, Suite, Scenario, Interface, ExecutionReport
from app.models.environment import Environment


def preview(client, mode='suite', ids=None, **kwargs):
    return data(client.post('/regression/preview', json={'mode': mode, 'ids': ids or [1], 'env_id': 1, **kwargs}))


def run(client, plan, mode='suite', ids=None, **kwargs):
    return client.post('/regression/run', json={'mode': mode, 'ids': ids or [1], 'env_id': 1, 'preview_key': plan['preview_key'], **kwargs})


def test_preview_matches_suite_deduplication_and_never_executes(reports):
    client, db, calls = reports
    plan = preview(client)
    assert plan['ready'] and plan['suite_count'] == 1
    assert (plan['scenario_count'], plan['case_count'], plan['step_count']) == (1, 1, 2)
    assert [item['name'] for item in plan['groups'][0]['items']] == ['下单场景', '用例3']
    assert not calls and db.query(ExecutionReport).count() == 0
    assert 'private-fixture-token' not in str(plan)


def test_suite_regression_preserves_chain_variables_and_nests_reports(reports, monkeypatch):
    client, db, calls = reports
    db.get(Case, 1).extract_rules = {'created_id': '$.data.id'}
    db.get(Case, 2).request_overrides = {'params': {'id': '${created_id}'}}
    db.commit()
    plan = preview(client)
    result = data(run(client, plan))
    assert result['total'] == 2 and result['failed_count'] == 1
    assert calls[1]['params'] == {'id': '1'}
    root = data(client.get('/reports/executions/' + result['report_id']))
    assert root['kind'] == 'regression' and [child['kind'] for child in root['children']] == ['suite']
    child = data(client.get('/reports/executions/' + root['children'][0]['id']))
    assert [item['kind'] for item in child['children']] == ['scenario', 'case']
    assert listing(client, 'suite')['total'] == listing(client, 'case')['total'] == listing(client, 'scenario')['total'] == 0


def test_manual_selection_uses_only_checked_ids_in_selection_order(reports):
    client, _, calls = reports
    plan = preview(client, 'case', [3, 1, 3])
    result = data(run(client, plan, 'case', [3, 1, 3]))
    assert [item['id'] for item in result['results']] == [3, 1]
    assert len(calls) == 2 and result['passed_count'] == 2


@pytest.mark.parametrize('change', ['case', 'interface', 'environment', 'suite'])
def test_changed_configuration_requires_review_before_any_execution(reports, change):
    client, db, calls = reports
    plan = preview(client)
    if change == 'case': db.get(Case, 1).expected_status = 201
    if change == 'interface': db.get(Interface, 1).url = '/changed'
    if change == 'environment': db.get(Environment, 1).variables = {'api_token': 'changed'}
    if change == 'suite': db.get(Suite, 1).case_ids = [1]
    db.commit()
    assert run(client, plan).status_code == 409
    assert not calls and db.query(ExecutionReport).count() == 0


def test_missing_references_and_relative_url_without_environment_are_blocked(reports):
    client, db, calls = reports
    db.get(Suite, 1).scenario_ids = [999]
    db.commit()
    plan = preview(client)
    assert not plan['ready'] and '已删除' in str(plan['warnings'])
    assert run(client, plan).status_code == 400
    no_env = preview(client, 'case', [1], env_id=None)
    assert not no_env['ready'] and '请选择测试环境' in str(no_env['warnings'])
    assert not calls


def test_cross_project_and_empty_selections_are_rejected(reports):
    client, db, calls = reports
    db.add(Suite(id=9, name='private-suite', type='mixed', project_id=2))
    db.commit()
    assert 'private-suite' not in str(data(client.get('/regression/options')))
    for payload in ({'mode':'suite','ids':[9]}, {'mode':'case','ids':[999]}, {'mode':'suite','ids':[]}):
        response = client.post('/regression/preview', json=payload)
        assert response.status_code in {404, 422}
    assert not calls


def test_old_regression_api_is_removed_without_execution(reports):
    client, _, calls = reports
    assert client.post('/regression?env_id=1', json=[1]).status_code == 404
    assert not calls


def test_notification_failure_preserves_regression_result_and_report(reports, monkeypatch):
    from app.services import project_notification
    from app.schemas.project_notification import NotificationUpdate
    from app.core.notifier import NotificationDeliveryError
    client, db, _ = reports
    url = 'https://open.feishu.cn/open-apis/bot/v2/hook/11111111-2222-3333-4444-555555555555'
    project_notification.save(db, 1, NotificationUpdate(enabled=True, webhook_url=url))
    def failed(*args):raise NotificationDeliveryError('飞书未接受消息')
    monkeypatch.setattr(project_notification, 'send_feishu', failed)
    result = data(run(client, preview(client), notify=True))
    assert result['failed_count'] == 1 and result['passed_count'] == 1
    assert '飞书未接受消息' in result['notification_warning'] and url not in str(result)
    root = data(client.get('/reports/executions/' + result['report_id']))
    assert root['kind'] == 'regression'


def test_missing_project_notification_returns_warning_without_sending_globally(reports):
    client, _, _ = reports
    result = data(run(client, preview(client, 'case', [1]), 'case', [1], notify=True))
    assert result['passed'] and '尚未配置' in result['notification_warning']
