"""Regression tests for the 2026-10-07 P1 review. No live services or user data."""
import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.celery_app import celery_app  # Registers all models.
from app.database import Base
from app.models.user import User
from app.models.team import Team
from app.models.project import Project
from app.models.environment import Environment
from app.models.perf import PerfTask
from app.models.schedule import Schedule
from app.models.suite import TestSuite as Suite
from app.models.case import Case
from app.models.interface import Interface
from app.models.report import TestReport as Report
from app.schemas.schedule import ScheduleCreate
from app.services import execution, perf, schedule, suite, traffic_replay


class Redis:
    def __init__(self, values=None):
        self.values = dict(values or {})
    def get(self, key):
        return self.values.get(key)
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True
    def expire(self, key, seconds):
        return key in self.values
    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
    def eval(self, script, count, *args):
        if count == 1:
            key, owner = args
            if self.get(key) != owner:
                return 0
            self.delete(key)
            return 1
        lock, active, target, lease, *extra = args
        run_id = extra[0] if extra else None
        if self.get(lock) != lease:
            return 0
        if self.get(active) == (run_id or lease):
            self.delete(active)
        self.delete(target, lock)
        return 1


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="p1-owner", hashed_password="fake-secret")
        session.add(user)
        session.flush()
        team = Team(name="p1-team", owner_id=user.id)
        session.add(team)
        session.flush()
        project = Project(name="p1-project", team_id=team.id)
        session.add(project)
        session.flush()
        session.add(Environment(id=1, name="local", base_url="http://tested.invalid", project_id=project.id))
        session.commit()
        yield session
    engine.dispose()


def _perf(db, status="pending", **extra):
    task = PerfTask(name="load", target_host="http://tested.invalid", target_path="/health", users=1,
                    spawn_rate=1, duration=1, project_id=1, status=status, **extra)
    db.add(task)
    db.commit()
    return task


def test_recovery_cannot_stop_newer_locust_owner(monkeypatch):
    cache = Redis({perf.RUN_LOCK_KEY: "1:8:new", perf.ACTIVE_RUN_KEY: "1:8"})
    calls = []
    monkeypatch.setattr(perf.requests, "get", lambda *args, **kwargs: calls.append(args))
    assert not perf._cleanup_run(cache, "1:7", "1:7:old", True)
    assert calls == []
    assert cache.get(perf.RUN_LOCK_KEY) == "1:8:new"


def test_normal_completion_cannot_stop_newer_owner(monkeypatch):
    cache = Redis({perf.RUN_LOCK_KEY: "1:8:new"})
    calls = []
    monkeypatch.setattr(perf.requests, "get", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="禁止停止其他任务"):
        perf._stop_owned_run(cache, "1:7:old")
    assert calls == []


def test_teardown_failure_persists_failed_report(db, monkeypatch):
    interface = Interface(name="api", method="GET", url="/health", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="cleanup fails", interface_id=interface.id, project_id=1, expected_status=200,
                teardown_sql=["INSERT INTO missing VALUES (1)"])
    db.add(case)
    db.commit()
    def sql(_db, statements):
        if statements:
            raise RuntimeError("cleanup failed")
    monkeypatch.setattr(execution, "run_sql", sql)
    monkeypatch.setattr(execution, "_request", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    result = execution.run_case(db, case.id, 1, 1)
    assert result["passed"] is False
    assert result["teardown_error"] == "cleanup failed"
    report = db.query(Report).one()
    assert not report.passed
    assert report.detail["teardown_error"] == "cleanup failed"


def test_empty_regression_and_scenario_suite_never_pass(db):
    from app.models.scenario import Scenario
    from app.models.scenario_report import ScenarioReport
    result = execution.run_regression(db, project_id=1)
    assert result["passed"] is False
    assert result["execution_status"] == "no_tests"
    scenario = Scenario(name="empty", case_ids=[], project_id=1)
    db.add(scenario)
    db.flush()
    test_suite = Suite(name="empty suite", type="scenario", scenario_ids=[scenario.id], project_id=1)
    db.add(test_suite)
    db.commit()
    result = suite.run_suite(db, test_suite.id, 1, 1)
    assert result["failed"] == 1
    assert not db.query(ScenarioReport).one().passed
    assert not db.query(Report).one().passed


@pytest.mark.parametrize("retry_id", ["winner", "loser"])
def test_duplicate_http_start_cannot_delete_winners_lease(db, monkeypatch, retry_id):
    task = _perf(db)
    second = Session(db.get_bind())
    stale = perf.perf_repo.db_get(second, task.id, 1)
    cache = Redis()
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    assert perf.s_mark_queued(db, task.id, 1, "winner").status == "queued"
    assert stale.status == "pending"
    with pytest.raises(perf.PerfRunBusyError):
        perf.s_mark_queued(second, task.id, 1, retry_id)
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task.id}:winner"
    second.close()


def test_duplicate_worker_cas_loser_preserves_lock(monkeypatch):
    task = SimpleNamespace(status="queued", duration=1, celery_task_id="winner")
    cache = Redis({perf.RUN_LOCK_KEY: "1:7:winner"})
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    monkeypatch.setattr(perf.perf_repo, "db_get", lambda *_: task)
    monkeypatch.setattr(perf.perf_repo, "db_update_if_status", lambda *args, **kwargs: None)
    assert perf.s_run(None, 7, 1, "winner") is task
    assert cache.get(perf.RUN_LOCK_KEY) == "1:7:winner"


def test_stale_cleanup_stops_master_and_keeps_lock_if_stop_fails(db, monkeypatch):
    now = datetime.utcnow()
    task = _perf(db, "running", celery_task_id="lost", started_at=now-timedelta(minutes=10), heartbeat_at=now-timedelta(minutes=5))
    run_id = f"1:{task.id}"
    cache = Redis({perf.RUN_LOCK_KEY: run_id + ":lost", perf.ACTIVE_RUN_KEY: run_id})
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[0])
        raise OSError("master unreachable")
    monkeypatch.setattr(perf.requests, "get", fail)
    assert perf.s_reconcile_stale(db)["failed"] == 1
    assert db.get(PerfTask, task.id).status == "failed"
    assert cache.get(perf.RUN_LOCK_KEY) is not None
    assert calls[0].endswith("/stop")
    monkeypatch.setattr(perf.requests, "get", lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None))
    perf.s_reconcile_stale(db)
    assert cache.get(perf.RUN_LOCK_KEY) is None


def test_worker_supplies_locust_native_stop_deadline(db, monkeypatch):
    task = _perf(db)
    cache = Redis()
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    perf.s_mark_queued(db, task.id, 1, "run")
    requests = []
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"stats": []})
    monkeypatch.setattr(perf.requests, "post", lambda *args, **kwargs: requests.append(kwargs) or response)
    monkeypatch.setattr(perf.requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(perf.time, "sleep", lambda _: None)
    perf.s_run(db, task.id, 1, "run")
    assert requests[0]["data"]["run_time"] == "1s"
    assert cache.get(perf.RUN_LOCK_KEY) is None


def test_schedule_keeps_suite_on_toggle_and_restores_lost_redis(db, monkeypatch):
    test_suite = Suite(name="suite", type="case", case_ids=[], project_id=1)
    db.add(test_suite)
    db.commit()
    synced = []
    monkeypatch.setattr(schedule.scheduler, "sync_schedule", lambda obj: synced.append(obj))
    task = schedule.s_create(db, ScheduleCreate(name="daily", cron="0 0 * * *", env_id=1, suite_id=test_suite.id), 1)
    schedule.s_update(db, task.id, ScheduleCreate(name="daily", cron="0 0 * * *", env_id=1, enabled=False), 1)
    assert db.get(Schedule, task.id).suite_id == test_suite.id
    assert synced[-1].env_id == 1
    monkeypatch.setattr(schedule.scheduler, "schedule_is_synced", lambda obj: False)
    assert schedule.reconcile_desired(db) == {"repaired": 1, "failed": 0}
    monkeypatch.setattr(schedule.scheduler, "schedule_is_synced", lambda obj: True)
    assert schedule.reconcile_desired(db) == {"repaired": 0, "failed": 0}


def test_scheduled_execution_receives_environment(db, monkeypatch):
    from app.tasks import schedule as tasks
    calls = []
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(tasks.execution_service, "run_regression", lambda *args, **kwargs: calls.append(kwargs) or {"passed": True})
    assert tasks.scheduled_regression.run(1, "smoke", None, 1)["passed"]
    assert calls[0]["env_id"] == 1


def test_schedule_environment_migration_is_repeatable():
    from app.core.migrations import ensure_schedule_environment_schema
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE schedule (id INTEGER PRIMARY KEY)"))
    for _ in range(2):
        ensure_schedule_environment_schema(engine)
    assert [c["name"] for c in inspect(engine).get_columns("schedule")] == ["id", "env_id"]


@pytest.mark.parametrize("resource, missing", [("environment", True), ("environment", False), ("suite", True), ("suite", False)])
def test_schedule_rejects_missing_or_foreign_bindings(db, monkeypatch, resource, missing):
    from app.models.schedule_sync_outbox import ScheduleSyncOutbox
    foreign_project = Project(name="foreign-job-project", team_id=1)
    db.add(foreign_project)
    db.flush()
    foreign_env = Environment(name="foreign-env", base_url="http://foreign.invalid", project_id=foreign_project.id)
    foreign_suite = Suite(name="foreign-suite", type="case", case_ids=[], project_id=foreign_project.id)
    db.add_all([foreign_env, foreign_suite])
    db.commit()
    data = ScheduleCreate(name="bad-binding", cron="0 0 * * *", env_id=1)
    if resource == "environment":
        data.env_id = 99999 if missing else foreign_env.id
    else:
        data.suite_id = 99999 if missing else foreign_suite.id
    calls = []
    monkeypatch.setattr(schedule.scheduler, "sync_schedule", lambda *args: calls.append(args))
    with pytest.raises(HTTPException) as exc:
        schedule.s_create(db, data, 1)
    assert exc.value.status_code == 404
    assert db.query(Schedule).count() == 0
    assert db.query(ScheduleSyncOutbox).count() == 0
    assert calls == []


def test_schedule_reference_prevents_environment_deletion(db):
    from app.services import environment
    db.add(Schedule(name="bound-env", cron="0 0 * * *", enabled=False, env_id=1, project_id=1))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        environment.s_delete(db, 1, 1)
    assert exc.value.status_code == 409
    assert db.get(Environment, 1) is not None
    assert db.query(Schedule).count() == 1


@pytest.mark.parametrize("drift", ["arguments", "index", "missing-environment", "correct"])
def test_redbeat_definition_and_index_are_checked(drift, monkeypatch):
    import redbeat.schedulers
    from app.core import scheduler
    job = SimpleNamespace(id=1, project_id=1, tag=None, suite_id=None, env_id=1,
                          enabled=True, cron="0 0 * * *")
    deleted = []
    entry = SimpleNamespace(task=scheduler.TASK, args=[1, None, None, 1],
                            schedule=scheduler._parse_cron(job.cron), key="redbeat:schedule-1",
                            app=SimpleNamespace(redbeat_conf=SimpleNamespace(schedule_key="redbeat:zset")),
                            delete=lambda: deleted.append(True))
    if drift == "arguments":
        entry.args[-1] = 999
    elif drift == "missing-environment":
        job.env_id = None
    monkeypatch.setattr(scheduler.RedBeatSchedulerEntry, "from_key", lambda *a, **k: entry)
    monkeypatch.setattr(redbeat.schedulers, "get_redis", lambda _: SimpleNamespace(
        zscore=lambda *a: None if drift == "index" else 123.0))
    assert scheduler.schedule_is_synced(job) is (drift == "correct")
    if drift == "missing-environment":
        with pytest.raises(ValueError, match="选择执行环境"):
            scheduler.sync_schedule(job)
        assert deleted == [True]


def test_wrong_celery_message_cannot_run_existing_task(db, monkeypatch):
    task = _perf(db, "queued", celery_task_id="right-message")
    cache = Redis({perf.RUN_LOCK_KEY: f"1:{task.id}:right-message"})
    calls = []
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    monkeypatch.setattr(perf.requests, "post", lambda *a, **k: calls.append(k))
    assert perf.s_run(db, task.id, 1, "wrong-message") is task
    assert task.status == "queued"
    assert task.started_at is None
    assert calls == []
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task.id}:right-message"


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_perf_task_cannot_be_deleted(db, status):
    task = _perf(db, status)
    assert perf.s_delete(db, task.id, 1) is None
    assert db.get(PerfTask, task.id).status == status


def test_perf_enqueue_failure_returns_503_and_releases_lease(db, monkeypatch):
    from app.routers import perf as router
    task = _perf(db)
    cache = Redis()
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    monkeypatch.setattr(perf.requests, "get", lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None))
    def unavailable(*args, **kwargs):
        raise OSError("synthetic broker unavailable")
    monkeypatch.setattr(router.run_perf_task, "apply_async", unavailable)
    with pytest.raises(HTTPException) as exc:
        router.run_task(task.id, db, SimpleNamespace(project_id=1))
    assert exc.value.status_code == 503
    assert task.status == "failed"
    assert task.celery_task_id is not None
    assert task.finished_at is not None
    assert cache.get(perf.RUN_LOCK_KEY) is None
    assert cache.get(perf.CONTROL_LOCK_KEY) is None
