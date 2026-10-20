"""Bounded comparison and owned load-run regressions; no actual HTTP traffic."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import time

import pytest

from app.core import response_diff
from app.services import traffic_replay
from tests.test_perf_lifecycle import perf_control


@pytest.mark.parametrize('field,rules', [
    ('amount', None), ('id', None), ('value', {'value': 'type:float'}),
    ('value', {'value': 'range:0.1'}),
])
def test_replay_detects_bool_as_a_numeric_contract_change(field, rules):
    assert not response_diff.diff_response({field: 1}, {field: True}, rules)['same']
    if rules is None and field == 'amount':
        assert not response_diff.diff_response({field: True}, {field: 1}, rules)['same']
    assert response_diff.diff_response({'amount': 1}, {'amount': 1})['same']
    assert response_diff.diff_response({'id': 1}, {'id': 42})['same']


def test_expensive_regex_is_interrupted_and_becomes_a_failed_comparison(monkeypatch):
    monkeypatch.setattr(response_diff, 'REGEX_BUDGET_SECONDS', 0.02)
    started = time.monotonic()
    result = response_diff.diff_response({'sample': ''}, {'sample': 'a' * 20000 + '!'},
                                         {'sample': 'regex:(a+)+$'})
    assert time.monotonic() - started < 2
    assert not result['same']
    assert '超过上限' in result['diffs'][0]['reason']


def test_all_regex_fields_share_one_comparison_budget(monkeypatch):
    clock, budgets = [0.0], []
    monkeypatch.setattr(response_diff, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(response_diff, 'REGEX_BUDGET_SECONDS', 0.1)
    class Pattern:
        def match(self, value, timeout, concurrent):
            assert concurrent
            budgets.append(timeout)
            clock[0] += min(0.03, timeout)
            if timeout < 0.03:
                raise TimeoutError
            return None
    monkeypatch.setattr(response_diff, '_compile_regex', lambda _: Pattern())
    fields = {str(index): 'x' for index in range(10)}
    result = response_diff.diff_response(fields, fields, {key: 'regex:x' for key in fields})
    assert not result['same'] and len(budgets) < len(fields)
    assert budgets[0] == pytest.approx(0.1) and budgets[-1] < budgets[0]
    assert clock[0] <= 0.100001


@pytest.mark.parametrize('rule', ['regex:[', 'range:-1', 'range:nan', 'type:unknown'])
def test_invalid_diff_rule_is_rejected_before_replay_reads_or_sends(monkeypatch, rule):
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid rule must be rejected before a mutating replay')
    monkeypatch.setattr(traffic_replay.traffic_record_repo, 'db_get', forbidden)
    monkeypatch.setattr(traffic_replay.requests, 'request', forbidden)
    with pytest.raises(ValueError):
        traffic_replay.s_replay(None, 1, 1, field_rules={'amount': rule})


def test_old_stop_is_fenced_even_if_a_new_run_is_injected_between_updates(perf_control, monkeypatch):
    perf, db, (task, _), cache, _ = perf_control
    perf.s_mark_queued(db, task.id, 1, 'old')
    task.status = 'running'; db.commit()
    original = perf.perf_repo.db_update_if_status
    def interleave(session, task_id, project_id, expected, **fields):
        if expected == 'queued':
            assert fields.pop('rollback_on_miss') is False
            # Simulate the lost-lock interleaving defensively. The fixed code
            # retains locks in MySQL and also fences the second CAS by old ID.
            task.celery_task_id = 'new'; task.status = 'running'; db.commit()
            return None
        return original(session, task_id, project_id, expected, **fields)
    monkeypatch.setattr(perf.perf_repo, 'db_update_if_status', interleave)
    with pytest.raises(perf.PerfRunBusyError, match='执行记录已变化'):
        perf.s_cancel(db, task.id, 1, execution_id='old')
    db.refresh(task)
    assert task.celery_task_id == 'new' and task.status == 'running'
    assert cache.get(perf._cancel_key(1, task.id, 'old')) == '1'
    assert cache.get(perf._cancel_key(1, task.id, 'new')) is None
    assert 'perf_execution' not in db.info


def test_running_cancel_keeps_admission_locks_and_uses_private_flag(perf_control):
    from sqlalchemy import event
    perf, db, (task, _), cache, _ = perf_control
    perf.s_mark_queued(db, task.id, 1, 'current')
    task.status = 'running'; db.commit()
    rollbacks = []
    def rolled_back(session):
        rollbacks.append(True)
    event.listen(db, 'after_rollback', rolled_back)
    try:
        assert perf.s_cancel(db, task.id, 1, execution_id='current').status == 'cancelled'
        assert not rollbacks
        assert cache.get(perf._cancel_key(1, task.id, 'current')) == '1'
        assert cache.get(f'locust:cancel:1:{task.id}') is None
    finally:
        event.remove(db, 'after_rollback', rolled_back)


def test_slow_control_requests_use_wall_elapsed_and_never_publish_stopped_rps(perf_control, monkeypatch):
    perf, db, (task, _), cache, response = perf_control
    task.duration = 6; db.commit(); perf.s_mark_queued(db, task.id, 1, 'clock')
    clock = cache.clock
    base = datetime(2026, 10, 21)
    monkeypatch.setattr(perf, '_utcnow', lambda: base + timedelta(seconds=clock.seconds))
    monkeypatch.setattr(perf.requests, 'post', lambda *a, **kw: response)
    def get(base_url, path):
        clock.advance(1)
        if path == '/whale/iterations':
            return {'lease': cache.get(perf.RUN_LOCK_KEY), 'configuration_failures': 0,
                    'iterations': 60, 'failures': 0, 'elapsed_seconds': min(clock.seconds, 6)}
        running = clock.seconds <= 6
        return {'state': 'running' if running else 'stopped', 'total_rps': 10 if running else 0,
                'stats': [{'name': 'Aggregated', 'num_requests': 60},
                          {'name': '/orders', 'method': 'GET', 'num_requests': 60,
                           'current_rps': 10 if running else 0}]}
    monkeypatch.setattr(perf, '_control_get_json', get)
    result = perf.s_run(db, task.id, 1, 'clock')
    assert result.status == 'done' and clock.seconds < 12
    assert result.rps == result.request_stats[0]['rps'] == 10
    assert len(result.history_samples) == 1
    sample = result.history_samples[0]
    sampled_time = datetime.fromisoformat(sample['sampled_at'].rstrip('Z'))
    assert sample['elapsed_s'] == pytest.approx((sampled_time - base).total_seconds())
    assert sample['elapsed_s'] == 3 and sample['rps'] == 10
