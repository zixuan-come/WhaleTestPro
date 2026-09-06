from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.assertions import run_assertions
from app.core.sql_runner import run_sql
from app.services import user as user_service


class _Response:
    elapsed = SimpleNamespace(total_seconds=lambda: 0)


def _db_with_items():
    engine = create_engine("sqlite:///:memory:")
    db = sessionmaker(bind=engine)()
    db.execute(sql_text("create table items (value integer)"))
    db.execute(sql_text("insert into items values (1)"))
    db.commit()
    return db


def test_db_eq_allows_single_select():
    db = _db_with_items()

    result = run_assertions(
        _Response(),
        [{"type": "db_eq", "sql": "SELECT value FROM items", "expected": 1}],
        db,
    )[0]

    assert result["passed"] is True
    assert result["actual"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM items",
        "UPDATE items SET value = 2",
        "INSERT INTO items VALUES (2)",
        "DROP TABLE items",
        "SELECT value FROM items; DELETE FROM items",
    ],
)
def test_db_eq_rejects_write_or_multi_statement_sql(sql):
    db = _db_with_items()

    result = run_assertions(
        _Response(),
        [{"type": "db_eq", "sql": sql, "expected": 1}],
        db,
    )[0]

    assert result["passed"] is False
    assert db.execute(sql_text("SELECT count(*) FROM items")).scalar() == 1


def test_register_maps_race_integrity_error_to_conflict(monkeypatch):
    class _DB:
        rolled_back = False

        def rollback(self):
            self.rolled_back = True

    def raise_integrity_error(_db, _user):
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(user_service.user_repo, "db_get_by_username", lambda _db, _name: None)
    monkeypatch.setattr(user_service.user_repo, "db_create", raise_integrity_error)

    db = _DB()
    with pytest.raises(HTTPException) as exc:
        user_service.s_register(db, SimpleNamespace(username="abcd", password="p" * 8))

    assert exc.value.status_code == 400
    assert db.rolled_back is True
@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE items",
        "ALTER TABLE items ADD COLUMN secret integer",
        "SELECT value FROM items",
        "DELETE FROM items; DROP TABLE items",
    ],
)
def test_setup_sql_rejects_non_dml_or_multi_statement_sql(sql):
    db = _db_with_items()

    with pytest.raises(ValueError):
        run_sql(db, [sql])

    assert db.execute(sql_text("SELECT count(*) FROM items")).scalar() == 1


def test_setup_sql_allows_single_dml_statement():
    db = _db_with_items()

    run_sql(db, ["UPDATE items SET value = 2"])

    assert db.execute(sql_text("SELECT value FROM items")).scalar() == 2
@pytest.mark.parametrize("sql", [
    "DELETE FROM users WHERE id = 1",
    "UPDATE project SET name = 'x' WHERE id = 1",
    "INSERT INTO test_case (name) VALUES ('x')",
])
def test_setup_sql_rejects_platform_table(sql):
    db = _db_with_items()

    with pytest.raises(ValueError, match="平台业务表"):
        run_sql(db, [sql])

def test_case_retries_rejects_negative():
    from pydantic import ValidationError
    from app.schemas.case import CaseCreate

    with pytest.raises(ValidationError):
        CaseCreate(name="retry", interface_id=1, expected_status=200, retries=-1)


def test_case_retries_defaults_to_zero():
    from app.schemas.case import CaseCreate

    case = CaseCreate(name="retry", interface_id=1, expected_status=200)
    assert case.retries == 0

def test_perf_run_marks_failed_on_worker_error(monkeypatch):
    from types import SimpleNamespace
    from app.services import perf as perf_service

    task = SimpleNamespace(id=7, target_host="http://app", target_path="/health", users=1, spawn_rate=1, duration=1)
    updates = []

    monkeypatch.setattr(perf_service.perf_repo, "db_get", lambda db, task_id, project_id: task)
    monkeypatch.setattr(perf_service.perf_repo, "db_update", lambda db, task_id, project_id, **fields: updates.append(fields) or task)
    monkeypatch.setattr(perf_service.redis, "from_url", lambda url: SimpleNamespace(set=lambda *args: None))
    monkeypatch.setattr(perf_service.requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("locust unavailable")))
    for name in ("perf_rps", "perf_fail_ratio", "perf_user_count", "perf_avg_response_ms"):
        monkeypatch.setattr(getattr(perf_service.metrics, name), "set", lambda value: None)

    with pytest.raises(RuntimeError, match="locust unavailable"):
        perf_service.s_run(object(), 7, 11)

    assert updates[0] == {"status": "running"}
    assert {"status": "failed"} in updates

def test_interface_references_batch_indexes_reports_and_scenarios():
    from datetime import datetime, timedelta
    from app.models.case import Case
    from app.models.interface import Interface
    from app.models.project import Project
    from app.models.report import TestReport
    from app.models.scenario import Scenario
    from app.repositories.interface import db_references

    engine = create_engine("sqlite:///:memory:")
    from app.database import Base
    import app.models.team
    import app.models.case
    import app.models.environment
    import app.models.interface
    import app.models.mock
    import app.models.perf
    import app.models.project_member
    import app.models.report
    import app.models.scenario_report
    import app.models.schedule
    import app.models.traffic_record
    import app.models.user
    import app.models.team_member
    import app.models.team_invitation
    import app.models.team_permission
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    project = Project(name="reference-project")
    db.add(project)
    db.flush()
    interface = Interface(name="health", method="GET", url="/health", project_id=project.id)
    db.add(interface)
    db.flush()
    case = Case(name="health case", interface_id=interface.id, expected_status=200, project_id=project.id)
    db.add(case)
    db.flush()
    now = datetime.now()
    db.add_all([
        TestReport(case_id=case.id, passed=False, project_id=project.id, created_at=now - timedelta(minutes=1)),
        TestReport(case_id=case.id, passed=True, project_id=project.id, created_at=now),
        Scenario(name="health scenario", case_ids=[case.id], project_id=project.id),
    ])
    db.commit()

    result = db_references(db, interface.id, project.id)

    assert result["case_count"] == 1
    assert result["cases"] == [{"id": case.id, "name": "health case", "scenario_ids": [1], "last_passed": True}]


def test_regression_coverage_uses_selected_cases_and_ignores_ghost_interfaces(monkeypatch):
    from app.services import execution

    interfaces = [SimpleNamespace(id=10), SimpleNamespace(id=11)]
    cases = [
        SimpleNamespace(id=1, interface_id=10, tags=['smoke']),
        SimpleNamespace(id=2, interface_id=999, tags=['smoke']),
    ]

    monkeypatch.setattr(execution.interface_repo, 'db_list', lambda db, project_id: interfaces)
    monkeypatch.setattr(execution.case_repo, 'db_list', lambda db, project_id: cases)
    monkeypatch.setattr(execution, 'run_case', lambda db, case_id, env_id, project_id: {'passed': True})

    summary = execution.run_regression(object(), case_ids=[1], project_id=7)
    assert summary['interface_total'] == 2
    assert summary['interface_covered'] == 1
    assert summary['interface_coverage'] == 0.5

    summary = execution.run_regression(object(), tag='smoke', project_id=7)
    assert summary['interface_covered'] == 1
    assert summary['interface_coverage'] == 0.5
def test_mock_schema_normalizes_match_fields_and_rejects_invalid_ranges():
    from pydantic import ValidationError
    from app.schemas.mock import MockCreate

    mock = MockCreate(name='health', path='health', method=' get ', status=201, delay_ms=120)
    assert mock.path == '/health'
    assert mock.method == 'GET'

    with pytest.raises(ValidationError):
        MockCreate(name='bad', path='/x', method='GET', status=99)
    with pytest.raises(ValidationError):
        MockCreate(name='bad', path='/x', method='GET', delay_ms=-1)


def test_perf_schema_rejects_invalid_ranges_and_normalizes_target():
    from pydantic import ValidationError
    from app.schemas.perf import PerfTaskCreate

    task = PerfTaskCreate(name='load', target_host='https://api.example.com/', target_path='health', users=1, spawn_rate=1, duration=30)
    assert task.target_host == 'https://api.example.com'
    assert task.target_path == '/health'

    with pytest.raises(ValidationError):
        PerfTaskCreate(name='load', target_host='api.example.com', target_path='/health', users=1, spawn_rate=1, duration=30)
    with pytest.raises(ValidationError):
        PerfTaskCreate(name='load', target_host='https://api.example.com', target_path='/health', users=0, spawn_rate=1, duration=30)


def test_traffic_record_schema_accepts_array_bodies():
    from app.schemas.traffic_record import TrafficRecordCreate

    record = TrafficRecordCreate(
        method='GET',
        path='/items',
        request_body=[{'id': 1}],
        response_body=[{'id': 1}],
        project_id=1,
    )

    assert record.request_body == [{'id': 1}]
    assert record.response_body == [{'id': 1}]


def test_perf_cancel_marks_task_cancelled(monkeypatch):
    from types import SimpleNamespace
    from app.services import perf as perf_service

    task = SimpleNamespace(id=8, status='running')
    updates = []
    redis_values = {}
    monkeypatch.setattr(perf_service.perf_repo, 'db_get', lambda db, task_id, project_id: task)
    monkeypatch.setattr(perf_service.perf_repo, 'db_update', lambda db, task_id, project_id, **fields: updates.append(fields) or SimpleNamespace(id=8, status=fields.get('status', task.status)))
    monkeypatch.setattr(perf_service.redis, 'from_url', lambda url: SimpleNamespace(set=lambda key, value, **kwargs: redis_values.update({key: value})))
    monkeypatch.setattr(perf_service.requests, 'get', lambda *args, **kwargs: SimpleNamespace())

    result = perf_service.s_cancel(object(), 8, 11)

    assert result.status == 'cancelled'
    assert updates[-1] == {'status': 'cancelled'}
    assert redis_values['locust:cancel:11:8'] == '1'


def test_direct_chain_writes_test_reports(monkeypatch):
    from app.services import execution

    monkeypatch.setattr(execution.case_repo, 'db_get', lambda db, case_id, project_id: None)
    reports = []
    monkeypatch.setattr(execution.report_repo, 'db_create', lambda db, **kwargs: reports.append(kwargs))

    result = execution.run_chain(object(), [42], None, 7)

    assert result[0]['passed'] is False
    assert reports[0]['case_id'] == 42
    assert reports[0]['passed'] is False
    assert reports[0]['project_id'] == 7
    assert reports[0]['detail']['chain'] is True


def test_environment_schema_validates_base_url():
    from pydantic import ValidationError
    from app.schemas.environment import EnvironmentCreate

    env = EnvironmentCreate(name='local', base_url='https://api.example.com/')
    assert env.base_url == 'https://api.example.com'

    with pytest.raises(ValidationError):
        EnvironmentCreate(name='bad', base_url='api.example.com')
    with pytest.raises(ValidationError):
        EnvironmentCreate(name='bad', base_url='   ')


def test_schedule_create_removes_orphan_on_sync_failure(monkeypatch):
    from types import SimpleNamespace
    from app.services import schedule as schedule_service

    deleted = []
    obj = SimpleNamespace(id=3)
    monkeypatch.setattr(schedule_service.schedule_repo, 'db_create', lambda db, schedule, project_id: obj)
    monkeypatch.setattr(schedule_service.scheduler, 'sync_schedule', lambda schedule: (_ for _ in ()).throw(ValueError('cron invalid')))
    class Db:
        def delete(self, value): deleted.append(value)
        def commit(self): pass
        def rollback(self): pass

    with pytest.raises(ValueError, match='cron invalid'):
        schedule_service.s_create(Db(), object(), 7)
    assert deleted == [obj]

