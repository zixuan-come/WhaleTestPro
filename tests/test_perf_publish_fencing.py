"""Broker publication compensation belongs to one execution, never a task ID alone."""
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routers import perf as router
from tests.test_perf_lifecycle import perf_control


def test_route_passes_original_execution_to_publish_failure_compensation(monkeypatch):
    calls = []
    monkeypatch.setattr(router, "uuid4", lambda: "original-message")
    monkeypatch.setattr(router.perf_service, "s_mark_queued", lambda *args: SimpleNamespace(id=7))
    def unavailable(**kwargs):
        raise ConnectionError("synthetic broker failure")
    monkeypatch.setattr(router.run_perf_task, "apply_async", unavailable)
    monkeypatch.setattr(router.perf_service, "s_mark_failed", lambda *args: calls.append(args))
    db = object()
    with pytest.raises(HTTPException) as caught:
        router.run_task(7, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 503
    assert calls == [(db, 7, 1, "original-message")]


def test_late_publish_failure_does_not_fail_or_stop_replacement(perf_control, monkeypatch):
    perf, db, (task, _), cache, response = perf_control
    monkeypatch.setattr(router, "uuid4", lambda: "original-message")
    stops = []
    monkeypatch.setattr(perf.requests, "get", lambda url, **kw: stops.append(url) or response)
    def delayed_failure(**kwargs):
        perf.s_cancel(db, task.id, 1, "original-message")
        perf.s_mark_queued(db, task.id, 1, "replacement-message")
        perf.perf_repo.db_update_if_status(db, task.id, 1, "queued", status="running")
        cache.set(perf.ACTIVE_RUN_KEY, f"1:{task.id}")
        raise ConnectionError("synthetic old acknowledgement failure")
    monkeypatch.setattr(router.run_perf_task, "apply_async", delayed_failure)
    with pytest.raises(HTTPException) as caught:
        router.run_task(task.id, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 503
    db.refresh(task)
    assert task.status == "running" and task.celery_task_id == "replacement-message"
    assert task.failure_reason is None
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task.id}:replacement-message"
    assert cache.get(perf.ACTIVE_RUN_KEY) == f"1:{task.id}" and stops == []


@pytest.mark.parametrize("status", ["queued", "running"])
def test_matching_publish_failure_finishes_only_its_execution(perf_control, status):
    perf, db, (task, _), cache, _ = perf_control
    perf.s_mark_queued(db, task.id, 1, "current-message")
    if status == "running":
        perf.perf_repo.db_update_if_status(db, task.id, 1, "queued", status="running")
    assert perf.s_mark_failed(db, task.id, 1, "current-message").status == "failed"
    assert cache.get(perf.RUN_LOCK_KEY) is None


def test_cleanup_keeps_original_generation_if_commit_returns_new_row(perf_control, monkeypatch):
    perf, db, (task, _), cache, response = perf_control
    perf.s_mark_queued(db, task.id, 1, "original-message")
    original = perf.perf_repo.db_update_if_status_in
    stops = []
    monkeypatch.setattr(perf.requests, "get", lambda url, **kw: stops.append(url) or response)
    def commit_then_replace(*args, **kwargs):
        assert kwargs["execution_id"] == "original-message"
        result = original(*args, **kwargs)
        # A reconciler can clean the failed lease after commit, before the
        # caller receives/reloads its ORM object. Then a new run may start.
        perf.s_reconcile_stale(db)
        perf.s_mark_queued(db, task.id, 1, "replacement-message")
        perf.perf_repo.db_update_if_status(db, task.id, 1, "queued", status="running")
        cache.set(perf.ACTIVE_RUN_KEY, f"1:{task.id}")
        return result
    monkeypatch.setattr(perf.perf_repo, "db_update_if_status_in", commit_then_replace)
    perf.s_mark_failed(db, task.id, 1, "original-message")
    db.refresh(task)
    assert task.status == "running" and task.celery_task_id == "replacement-message"
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task.id}:replacement-message"
    assert stops == []  # Failed queued generation had never occupied the master.


@pytest.mark.parametrize("execution", [None, ""])
def test_publish_failure_cannot_fall_back_to_task_only(perf_control, execution):
    perf, db, (task, _), cache, _ = perf_control
    perf.s_mark_queued(db, task.id, 1, "current-message")
    with pytest.raises(ValueError, match="原执行 ID"):
        perf.s_mark_failed(db, task.id, 1, execution)
    assert task.status == "queued" and cache.get(perf.RUN_LOCK_KEY)
