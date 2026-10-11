"""Consumer persistence failures with synthetic payloads and no live broker."""
import json
import traceback
from copy import deepcopy
from unittest.mock import Mock

import pymysql
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core import metrics
from app.tasks import traffic
from app.models.traffic_record import TrafficRecord
from tests.test_suite_service import db


SECRET = "synthetic-private-request-and-database-secret"


def payload():
    return {"method": "POST", "path": "/demo/orders", "project_id": 1,
            "request_headers": {"Authorization": SECRET},
            "request_body": {"password": SECRET}, "response_status": 200,
            "response_body": {"access_token": SECRET}}


def db_error(code):
    return OperationalError("synthetic INSERT", {"private": SECRET},
                            pymysql.err.OperationalError(code, SECRET))


@pytest.fixture
def consumer(monkeypatch):
    sessions, calls = [], []
    class Session:
        def __init__(self):
            self.rollback = Mock()
            self.close = Mock()
            sessions.append(self)
    monkeypatch.setattr(traffic, "SessionLocal", Session)
    def save(database, record, **kwargs):
        calls.append((database, record.model_dump(), kwargs))
    monkeypatch.setattr(traffic.traffic_record_service, "s_create", save)
    return sessions, calls


def counters():
    return tuple(getattr(metrics, name)._value.get() if hasattr(metrics, name) else 0
                 for name in ("traffic_record_persist_failures", "traffic_record_persist_retries",
                              "traffic_record_persist_terminal_failures"))


def delta(before):
    return tuple(after - old for after, old in zip(counters(), before))


@pytest.mark.parametrize("code", [1205, 1213])
def test_rolled_back_lock_errors_retry_then_save_once(consumer, monkeypatch, code):
    sessions, calls = consumer
    save = traffic.traffic_record_service.s_create
    failures = []
    def retry_once(database, record, **kwargs):
        if not failures:
            failures.append(True)
            raise db_error(code)
        return save(database, record, **kwargs)
    monkeypatch.setattr(traffic.traffic_record_service, "s_create", retry_once)
    original = payload()
    before_payload = deepcopy(original)
    before = counters()
    result = traffic.record_traffic.apply(args=(original,), throw=False)
    assert result.state == "SUCCESS"
    assert delta(before) == (1, 1, 0)
    assert len(sessions) == 2 and len(calls) == 1
    sessions[0].rollback.assert_called_once()
    sessions[1].rollback.assert_not_called()
    assert all(session.close.call_count == 1 for session in sessions)
    assert calls[0][2] == {"refresh": False}
    assert SECRET not in json.dumps(calls[0][1])
    assert original == before_payload


def test_lock_retry_is_bounded_and_terminal_error_is_safe(consumer, monkeypatch, caplog):
    sessions, _ = consumer
    monkeypatch.setattr(traffic.traffic_record_service, "s_create",
                        lambda *a, **k: (_ for _ in ()).throw(db_error(1213)))
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE"
    assert traffic.record_traffic.max_retries == 3
    assert len(sessions) == 4 and delta(before) == (4, 3, 1)
    assert all(session.rollback.call_count == session.close.call_count == 1 for session in sessions)
    rendered = "".join(traceback.format_exception(type(result.result), result.result,
                                                 result.result.__traceback__))
    assert SECRET not in str(result.result) and SECRET not in rendered
    assert SECRET not in caplog.text


@pytest.mark.parametrize("code", [2006, 2013])
def test_unknown_commit_outcome_does_not_retry(consumer, monkeypatch, code):
    sessions, _ = consumer
    monkeypatch.setattr(traffic.traffic_record_service, "s_create",
                        lambda *a, **k: (_ for _ in ()).throw(db_error(code)))
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE" and len(sessions) == 1
    assert delta(before) == (1, 0, 1)
    assert SECRET not in str(result.result)


def test_integrity_error_does_not_retry_or_leak_sql_parameters(consumer, monkeypatch):
    sessions, _ = consumer
    error = IntegrityError("synthetic INSERT", {"private": SECRET},
                           pymysql.err.IntegrityError(1452, SECRET))
    monkeypatch.setattr(traffic.traffic_record_service, "s_create",
                        lambda *a, **k: (_ for _ in ()).throw(error))
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE" and len(sessions) == 1
    assert delta(before) == (1, 0, 1)
    assert SECRET not in str(result.result)


def test_rollback_failure_disables_retries(consumer, monkeypatch):
    sessions, _ = consumer
    def fail(database, record, **kwargs):
        database.rollback.side_effect = RuntimeError(SECRET)
        raise db_error(1213)
    monkeypatch.setattr(traffic.traffic_record_service, "s_create", fail)
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE" and len(sessions) == 1
    assert delta(before) == (1, 0, 1)
    assert SECRET not in str(result.result)
    sessions[0].close.assert_called_once()


def test_invalid_message_is_counted_without_opening_database(consumer, caplog):
    sessions, _ = consumer
    invalid = payload()
    invalid["response_status"] = SECRET
    before = counters()
    result = traffic.record_traffic.apply(args=(invalid,), throw=False)
    assert result.state == "FAILURE" and sessions == []
    assert delta(before) == (1, 0, 1)
    assert SECRET not in str(result.result)
    assert SECRET not in caplog.text


def test_close_failure_after_save_never_retries(consumer, monkeypatch, caplog):
    sessions, calls = consumer
    save = traffic.traffic_record_service.s_create
    def close_failure(database, record, **kwargs):
        save(database, record, **kwargs)
        database.close.side_effect = db_error(1213)
    monkeypatch.setattr(traffic.traffic_record_service, "s_create", close_failure)
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE" and len(sessions) == len(calls) == 1
    assert delta(before) == (1, 0, 1) and SECRET not in caplog.text


def test_retry_publish_failure_is_sanitized_and_final(consumer, monkeypatch, caplog):
    sessions, _ = consumer
    monkeypatch.setattr(traffic.traffic_record_service, "s_create",
                        lambda *a, **k: (_ for _ in ()).throw(db_error(1213)))
    def publish_failure(**kwargs):
        assert SECRET not in json.dumps(kwargs["args"])
        raise RuntimeError(SECRET)
    monkeypatch.setattr(traffic.record_traffic, "retry", publish_failure)
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "FAILURE" and len(sessions) == 1
    assert delta(before) == (1, 1, 1) and SECRET not in caplog.text


def test_excluded_auth_record_is_not_saved_or_retried(consumer):
    sessions, calls = consumer
    item = payload()
    item["path"] = "/auth/login"
    before = counters()
    result = traffic.record_traffic.apply(args=(item,), throw=False)
    assert result.state == "SUCCESS" and sessions == calls == []
    assert delta(before) == (0, 0, 0)


def test_success_commits_one_row_without_post_commit_refresh(db, monkeypatch):
    # The worker must not retry a deadlock in a SELECT refresh after commit.
    # Use the real repository/service, not a mocked persistence function.
    monkeypatch.setattr(traffic, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "refresh", lambda *a: (_ for _ in ()).throw(db_error(1213)))
    before = counters()
    result = traffic.record_traffic.apply(args=(payload(),), throw=False)
    assert result.state == "SUCCESS" and delta(before) == (0, 0, 0)
    assert db.query(TrafficRecord).count() == 1
    row = db.query(TrafficRecord).one()
    assert row.project_id == 1 and row.response_status == 200
    assert SECRET not in json.dumps([row.request_headers, row.request_body, row.response_body])
