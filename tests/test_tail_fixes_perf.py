"""Deletion error semantics; memory DB and fake Locust control only."""
from types import SimpleNamespace

import pytest
import requests
from fastapi import HTTPException

from app.repositories import perf as perf_repo
from app.routers import perf as perf_router
from tests.test_perf_lifecycle import perf_control


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_delete_is_conflict_not_missing(perf_control, status):
    perf, db, (task, _), cache, _ = perf_control
    task.status = status
    db.commit()
    cache.values[perf.RUN_LOCK_KEY] = f"1:{task.id}:message"
    before = dict(cache.values)
    with pytest.raises(HTTPException) as caught:
        perf_router.delete_task(task.id, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 409
    assert perf_repo.db_get(db, task.id, 1).status == status
    assert cache.values == before


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
def test_cleanup_failure_is_unavailable_and_keeps_lease(perf_control, monkeypatch, status):
    perf, db, (task, _), cache, response = perf_control
    task_id = task.id
    task.status = status
    db.commit()
    run_id = f"1:{task_id}"
    cache.values.update({perf.RUN_LOCK_KEY: run_id + ":message", perf.ACTIVE_RUN_KEY: run_id})
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("synthetic-private-control-address")
    monkeypatch.setattr(perf.requests, "get", unavailable)
    with pytest.raises(HTTPException) as caught:
        perf_router.delete_task(task_id, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 503
    assert "synthetic-private" not in caught.value.detail
    assert perf_repo.db_get(db, task_id, 1) is not None
    assert cache.get(perf.RUN_LOCK_KEY) == run_id + ":message"
    assert cache.get(perf.ACTIVE_RUN_KEY) == run_id
    monkeypatch.setattr(perf.requests, "get", lambda *a, **k: response)
    assert perf_router.delete_task(task_id, db, SimpleNamespace(project_id=1))["code"] == 0
    assert perf_repo.db_get(db, task_id, 1) is None
    assert cache.get(perf.RUN_LOCK_KEY) is None


@pytest.mark.parametrize("foreign", [False, True])
def test_missing_or_foreign_task_stays_404(perf_control, foreign):
    _, db, (task, _), cache, _ = perf_control
    with pytest.raises(HTTPException) as caught:
        perf_router.delete_task(task.id if foreign else 999999, db,
                                SimpleNamespace(project_id=2 if foreign else 1))
    assert caught.value.status_code == 404
    assert perf_repo.db_get(db, task.id, 1) is not None
    assert cache.values == {}
