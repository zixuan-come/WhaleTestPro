"""Offline lifecycle regressions: actual repositories, synthetic master/Redis."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import redis
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.dialects import mysql

from app.models.perf import PerfTask
from app.models.project import Project
from app.repositories import project as project_repo
from app.routers import project as project_router
from app.services import perf, project
from tests.test_suite_service import db
from tests.test_perf_lifecycle import _ControlRedis


@pytest.fixture
def control(monkeypatch):
    cache = _ControlRedis()
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    monkeypatch.setattr(perf.settings, "LOCUST_CONTROL_TOKEN", "synthetic-control")
    monkeypatch.setattr(perf.time, "sleep", lambda _: None)
    return cache


def task(db, status="pending", plan=None):
    row = PerfTask(name="review", project_id=1, target_host="http://unused.invalid",
                   target_path="/health", users=1, spawn_rate=1, duration=4,
                   status=status, load_config=plan)
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize("status", ["queued", "running"])
def test_project_delete_rejects_active_task_without_mutation(db, control, status):
    row = task(db, status)
    lease = f"1:{row.id}:message"
    control.values[perf.RUN_LOCK_KEY] = lease
    with pytest.raises(Exception) as error:
        project_router.delete_project(db, SimpleNamespace(project_id=1))
    assert error.value.status_code == 409
    assert db.get(Project, 1) and db.get(PerfTask, row.id).status == status
    assert control.get(perf.RUN_LOCK_KEY) == lease


@pytest.mark.parametrize("status", ["pending", "done", "failed", "cancelled"])
@pytest.mark.parametrize("key", [perf.RUN_LOCK_KEY, perf.ACTIVE_RUN_KEY])
def test_project_delete_preserves_any_owned_uncleared_lease(db, control, status, key):
    row = task(db, status)
    control.values[key] = f"1:{row.id}" + (":message" if key == perf.RUN_LOCK_KEY else "")
    before = dict(control.values)
    with pytest.raises(Exception) as error:
        project_router.delete_project(db, SimpleNamespace(project_id=1))
    assert error.value.status_code == 409
    assert db.get(Project, 1) and db.get(PerfTask, row.id)
    assert control.values == before


def test_project_without_task_still_rejects_legacy_orphan_lease(db, control):
    control.values[perf.RUN_LOCK_KEY] = "1:999:old-message"
    with pytest.raises(Exception) as error:
        project_router.delete_project(db, SimpleNamespace(project_id=1))
    assert error.value.status_code == 409 and db.get(Project, 1)


def test_project_delete_redis_outage_is_503_and_preserves_database(db, control, monkeypatch):
    row = task(db)
    def unavailable(_key):
        raise redis.ConnectionError("synthetic-private-location")
    monkeypatch.setattr(control, "get", unavailable)
    with pytest.raises(Exception) as error:
        project_router.delete_project(db, SimpleNamespace(project_id=1))
    assert error.value.status_code == 503
    assert "synthetic-private" not in error.value.detail
    assert db.get(Project, 1) and db.get(PerfTask, row.id)


def test_project_delete_does_not_touch_other_project_lease(db, control):
    task(db)
    control.values.update({perf.RUN_LOCK_KEY: "2:9:message", perf.ACTIVE_RUN_KEY: "2:9"})
    before = dict(control.values)
    assert project.s_delete(db, 1).id == 1
    assert not db.query(Project).count() and not db.query(PerfTask).count()
    assert control.values == before


def test_delete_before_admission_cannot_reserve_orphan_lease(db, control):
    row = task(db)
    task_id = row.id
    project.s_delete(db, 1)
    assert perf.s_mark_queued(db, task_id, 1, "delayed") is None
    assert not control.values


def test_delayed_worker_with_stale_queued_snapshot_cannot_recreate_cancelled_lease(db, control):
    row = task(db)
    perf.s_mark_queued(db, row.id, 1, "old-message")
    competing = Session(db.get_bind())
    try:
        stale = perf.perf_repo.db_get(competing, row.id, 1)
        assert stale.status == "queued"
        assert perf.s_cancel(db, row.id, 1).status == "cancelled"
        assert stale.status == "queued" and not control.values
        assert perf.s_run(competing, row.id, 1, "old-message").status == "cancelled"
        assert not control.values
        assert project.s_delete(db, 1).id == 1
    finally:
        competing.close()


def test_admission_and_cascade_use_current_locked_parent_then_task(db, control):
    row = task(db)
    locked = []
    def observe(_connection, _cursor, _sql, _params, context, _many):
        statement = context.compiled.statement if context.compiled else None
        if statement is not None and getattr(statement, "_for_update_arg", None) is not None:
            locked.append(str(statement.compile(dialect=mysql.dialect())))
    event.listen(db.get_bind(), "before_cursor_execute", observe)
    try:
        perf.s_mark_queued(db, row.id, 1, "message")
        assert "FROM project " in locked[0] and "perf_tasks" in locked[1]
        assert all("FOR UPDATE" in statement for statement in locked)
        locked.clear()
        with pytest.raises(Exception):
            project.s_delete(db, 1)
        assert "FROM project " in locked[0] and "perf_tasks" in locked[1]
        assert db.get(Project, 1) and db.get(PerfTask, row.id).status == "queued"
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", observe)


def test_reconciler_recovers_preexisting_orphan_only_after_stop_ack(db, control, monkeypatch):
    control.values.update({perf.RUN_LOCK_KEY: "1:999:old", perf.ACTIVE_RUN_KEY: "1:999",
                           perf._target_path_key("1:999"): "/old"})
    before = dict(control.values)
    def unavailable(*_args, **_kwargs):
        raise OSError("offline-control-outage")
    monkeypatch.setattr(perf.requests, "get", unavailable)
    perf.s_reconcile_stale(db)
    assert control.values == before
    stops = []
    monkeypatch.setattr(perf.requests, "get", lambda url, **kw:
                        stops.append(url) or SimpleNamespace(raise_for_status=lambda: None))
    perf.s_reconcile_stale(db)
    assert stops == [perf.settings.LOCUST_MASTER_URL + "/stop"] and not control.values
