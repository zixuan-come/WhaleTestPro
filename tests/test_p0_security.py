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


class _FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
                del self.values[key]
        return deleted

    def expire(self, key, seconds):
        return key in self.values

    def eval(self, script, numkeys, lock_key, active_key, target_key, owner):
        if self.values.get(lock_key) != owner:
            return 0
        if self.values.get(active_key) == owner:
            self.values.pop(active_key, None)
        self.values.pop(target_key, None)
        self.values.pop(lock_key, None)
        return 1


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

    run_sql(db, ["UPDATE items SET value = 2 WHERE value = 1"])

    assert db.execute(sql_text("SELECT value FROM items")).scalar() == 2


@pytest.mark.parametrize("sql", [
    "UPDATE items SET value = 2",
    "DELETE FROM items",
])
def test_setup_sql_rejects_update_delete_without_where(sql):
    db = _db_with_items()

    with pytest.raises(ValueError, match="WHERE"):
        run_sql(db, [sql])

    assert db.execute(sql_text("SELECT count(*) FROM items")).scalar() == 1
    assert db.execute(sql_text("SELECT value FROM items")).scalar() == 1


@pytest.mark.parametrize("sql", [
    "UPDATE us/**/ers SET value = 2 WHERE value = 1",
    "DELETE FROM items WHERE value = 1 -- drop everything",
    "INSERT INTO items VALUES (2) # comment",
    "DELETE FROM items WHERE value = 1;#",
])
def test_setup_sql_rejects_comments(sql):
    db = _db_with_items()

    with pytest.raises(ValueError, match="注释"):
        run_sql(db, [sql])

    assert db.execute(sql_text("SELECT count(*) FROM items")).scalar() == 1


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
    monkeypatch.setattr(perf_service.redis, "from_url", lambda url: _FakeRedis())
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
    import app.models.suite
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
    fake_redis = _FakeRedis()
    monkeypatch.setattr(perf_service.perf_repo, 'db_get', lambda db, task_id, project_id: task)
    monkeypatch.setattr(perf_service.perf_repo, 'db_update', lambda db, task_id, project_id, **fields: updates.append(fields) or SimpleNamespace(id=8, status=fields.get('status', task.status)))
    monkeypatch.setattr(perf_service.perf_repo, 'db_update_if_status', lambda db, task_id, project_id, expected_status, **fields: updates.append(fields) or SimpleNamespace(id=8, status=fields.get('status', task.status)))
    monkeypatch.setattr(perf_service.redis, 'from_url', lambda url: fake_redis)
    monkeypatch.setattr(perf_service.requests, 'get', lambda *args, **kwargs: SimpleNamespace())

    result = perf_service.s_cancel(object(), 8, 11)

    assert result.status == 'cancelled'
    assert updates[-1] == {'status': 'cancelled'}
    assert fake_redis.values['locust:cancel:11:8'] == '1'


def test_perf_mark_running_rejects_second_run(monkeypatch):
    from app.services import perf as perf_service

    tasks = {
        1: SimpleNamespace(id=1, status="pending", duration=60),
        2: SimpleNamespace(id=2, status="pending", duration=60),
    }
    fake_redis = _FakeRedis()
    monkeypatch.setattr(perf_service.redis, "from_url", lambda url: fake_redis)
    monkeypatch.setattr(
        perf_service.perf_repo,
        "db_get",
        lambda db, task_id, project_id: tasks[task_id],
    )

    def update(db, task_id, project_id, **fields):
        tasks[task_id].status = fields["status"]
        return tasks[task_id]

    monkeypatch.setattr(perf_service.perf_repo, "db_update", update)

    assert perf_service.s_mark_running(object(), 1, 10).status == "running"
    with pytest.raises(perf_service.PerfRunBusyError):
        perf_service.s_mark_running(object(), 2, 20)

    assert tasks[2].status == "pending"
    assert fake_redis.values[perf_service.RUN_LOCK_KEY] == "10:1"


def test_perf_run_uses_scoped_target_key_and_releases_lock(monkeypatch):
    from app.services import perf as perf_service

    task = SimpleNamespace(
        id=12,
        status="running",
        target_host="http://app",
        target_path="/health",
        users=1,
        spawn_rate=1,
        duration=0,
    )
    run_id = "3:12"
    fake_redis = _FakeRedis({perf_service.RUN_LOCK_KEY: run_id})
    swarm_state = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"stats": [], "errors": []}

    def post(url, data, timeout):
        swarm_state.update(fake_redis.values)
        return Response()

    monkeypatch.setattr(perf_service.redis, "from_url", lambda url: fake_redis)
    monkeypatch.setattr(perf_service.perf_repo, "db_get", lambda db, task_id, project_id: task)
    monkeypatch.setattr(
        perf_service.perf_repo,
        "db_update_if_status",
        lambda db, task_id, project_id, expected_status, **fields: task,
    )
    monkeypatch.setattr(perf_service.requests, "post", post)
    monkeypatch.setattr(perf_service.requests, "get", lambda *args, **kwargs: Response())

    assert perf_service.s_run(object(), 12, 3) is task

    assert "locust:target_path" not in swarm_state
    assert swarm_state[perf_service.ACTIVE_RUN_KEY] == run_id
    assert swarm_state[f"locust:target_path:{run_id}"] == "/health"
    assert perf_service.RUN_LOCK_KEY not in fake_redis.values
    assert perf_service.ACTIVE_RUN_KEY not in fake_redis.values
    assert f"locust:target_path:{run_id}" not in fake_redis.values


def test_perf_lock_cleanup_does_not_delete_another_run():
    from app.services import perf as perf_service

    fake_redis = _FakeRedis(
        {
            perf_service.RUN_LOCK_KEY: "20:2",
            perf_service.ACTIVE_RUN_KEY: "20:2",
            "locust:target_path:20:2": "/orders",
        }
    )

    assert perf_service._release_run_lock(fake_redis, "10:1") == 0
    assert fake_redis.values[perf_service.RUN_LOCK_KEY] == "20:2"
    assert fake_redis.values[perf_service.ACTIVE_RUN_KEY] == "20:2"
    assert fake_redis.values["locust:target_path:20:2"] == "/orders"


def test_locust_master_reads_task_scoped_target_path(monkeypatch):
    import importlib
    import sys
    from types import ModuleType

    class EventHook:
        def add_listener(self, function):
            return function

    fake_locust = ModuleType("locust")
    fake_locust.HttpUser = type("HttpUser", (), {})
    fake_locust.task = lambda function: function
    fake_locust.between = lambda start, end: (start, end)
    fake_locust.events = SimpleNamespace(init=EventHook(), test_start=EventHook())
    fake_runners = ModuleType("locust.runners")
    fake_runners.MasterRunner = type("MasterRunner", (), {})
    fake_runners.WorkerRunner = type("WorkerRunner", (), {})
    monkeypatch.setitem(sys.modules, "locust", fake_locust)
    monkeypatch.setitem(sys.modules, "locust.runners", fake_runners)
    sys.modules.pop("locustfile", None)
    locustfile = importlib.import_module("locustfile")

    run_id = "3:12"
    fake_redis = _FakeRedis(
        {
            locustfile.ACTIVE_RUN_KEY: run_id,
            f"locust:target_path:{run_id}": "/orders",
        }
    )

    class FakeMasterRunner:
        def __init__(self):
            self.messages = []

        def send_message(self, name, data):
            self.messages.append((name, data))

    runner = FakeMasterRunner()
    monkeypatch.setattr(locustfile, "MasterRunner", FakeMasterRunner)
    monkeypatch.setattr(locustfile.redis, "from_url", lambda url: fake_redis)

    locustfile._on_test_start(SimpleNamespace(runner=runner))

    assert runner.messages == [("set_path", "/orders")]


def test_perf_run_route_returns_conflict_when_master_is_busy(monkeypatch):
    from app.routers import perf as perf_router
    from app.services import perf as perf_service

    def busy(*args, **kwargs):
        raise perf_service.PerfRunBusyError("已有压测任务正在运行")

    monkeypatch.setattr(perf_router.perf_service, "s_mark_running", busy)

    with pytest.raises(HTTPException) as exc:
        perf_router.run_task(2, object(), SimpleNamespace(project_id=20))

    assert exc.value.status_code == 409
    assert exc.value.detail == "已有压测任务正在运行"


def test_perf_run_does_not_restart_cancelled_task(monkeypatch):
    from app.services import perf as perf_service

    task = SimpleNamespace(id=9, status='cancelled')
    updates = []
    monkeypatch.setattr(perf_service.perf_repo, 'db_get', lambda db, task_id, project_id: task)
    monkeypatch.setattr(perf_service.perf_repo, 'db_update', lambda *args, **kwargs: updates.append(kwargs))
    monkeypatch.setattr(perf_service.redis, 'from_url', lambda url: _FakeRedis())

    result = perf_service.s_run(object(), 9, 11)

    assert result is task
    assert updates == []

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


def test_mock_match_supports_path_parameters(monkeypatch):
    from app.repositories import mock as mock_repo

    exact = SimpleNamespace(path='/orders/123', method='GET')
    wildcard = SimpleNamespace(path='/orders/{id}', method='GET')
    class Query:
        def __init__(self, rows): self.rows = rows
        def filter(self, *args): return self
        def first(self): return self.rows[0] if self.rows else None
        def all(self): return self.rows
    class Db:
        def __init__(self): self.calls = 0
        def query(self, model):
            self.calls += 1
            return Query([exact] if self.calls == 1 else [wildcard])

    assert mock_repo.db_match(Db(), 1, '/orders/123', 'get') is exact

    class WildDb:
        def query(self, model): return Query([wildcard])
    assert mock_repo.db_match(WildDb(), 1, '/orders/456', 'GET') is wildcard


def test_schedule_schema_validates_field_lengths():
    from pydantic import ValidationError
    from app.schemas.schedule import ScheduleCreate

    schedule = ScheduleCreate(name='daily', cron='0 0 * * *', tag=' smoke ')
    assert schedule.tag == 'smoke'

    with pytest.raises(ValidationError):
        ScheduleCreate(name='daily', cron='0 0 * * *', tag='x' * 51)
    with pytest.raises(ValidationError):
        ScheduleCreate(name='daily', cron='   ')



def test_scenario_schema_validates_description_length():
    import pytest
    from pydantic import ValidationError
    from app.schemas.scenario import ScenarioCreate

    ScenarioCreate(name='场景', description='a' * 500)
    with pytest.raises(ValidationError):
        ScenarioCreate(name='场景', description='a' * 501)


def test_interface_schema_validates_request_fields():
    import pytest
    from pydantic import ValidationError
    from app.schemas.interface import InterfaceCreate

    normalized = InterfaceCreate(name='查询', method=' get ', url=' /health ', category='  系统  ')
    assert normalized.method == 'GET'
    assert normalized.url == '/health'
    assert normalized.category == '系统'
    with pytest.raises(ValidationError):
        InterfaceCreate(name='查询', method='TRACE', url='/health')
    with pytest.raises(ValidationError):
        InterfaceCreate(name='查询', method='GET', url='health')
    with pytest.raises(ValidationError):
        InterfaceCreate(name='查询', method='GET', url='/' + 'a' * 500)


def test_execution_rejects_missing_or_foreign_environment(monkeypatch):
    from app.services import execution

    monkeypatch.setattr(execution.env_repo, "db_get", lambda db, env_id, project_id: None)

    with pytest.raises(ValueError, match="不存在或不属于当前项目"):
        execution._env_context(object(), 999, 7)


def test_traffic_replay_safe_json_handles_non_json_response():
    from app.services import traffic_replay

    class Response:
        def json(self):
            raise ValueError("not json")

    assert traffic_replay._safe_json(Response()) is None
