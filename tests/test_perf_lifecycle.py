import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.user
import app.models.team_member
import app.models.team_invitation
import app.models.team
import app.models.project  # 注册 perf_tasks.project_id 指向的表元数据
from app.models.perf import PerfTask
from app.repositories import perf as perf_repo


def test_stale_perf_tasks_are_failed_without_touching_fresh_heartbeat():
    engine = create_engine("sqlite:///:memory:")
    PerfTask.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    now = datetime(2026, 10, 6, 12, 0, 0)
    try:
        db.add_all(
            [
                PerfTask(
                    name="queued",
                    target_host="http://app",
                    target_path="/health",
                    users=1,
                    spawn_rate=1,
                    duration=30,
                    status="queued",
                    queued_at=now - timedelta(minutes=10),
                    project_id=1,
                ),
                PerfTask(
                    name="lost-worker",
                    target_host="http://app",
                    target_path="/health",
                    users=1,
                    spawn_rate=1,
                    duration=30,
                    status="running",
                    started_at=now - timedelta(minutes=5),
                    heartbeat_at=now - timedelta(minutes=2),
                    project_id=1,
                ),
                PerfTask(
                    name="healthy-worker",
                    target_host="http://app",
                    target_path="/health",
                    users=1,
                    spawn_rate=1,
                    duration=30,
                    status="running",
                    started_at=now - timedelta(minutes=1),
                    heartbeat_at=now - timedelta(seconds=5),
                    project_id=1,
                ),
                PerfTask(
                    name="other-project",
                    target_host="http://app",
                    target_path="/health",
                    users=1,
                    spawn_rate=1,
                    duration=30,
                    status="queued",
                    queued_at=now - timedelta(minutes=10),
                    project_id=2,
                ),
            ]
        )
        db.commit()

        failed = perf_repo.db_fail_stale(
            db,
            queued_before=now - timedelta(minutes=5),
            running_before=now - timedelta(minutes=1),
            finished_at=now,
            project_id=1,
        )

        tasks = {task.name: task for task in db.query(PerfTask).all()}
        assert {(project_id, status) for _, project_id, status in failed} == {
            (1, "queued"),
            (1, "running"),
        }
        assert tasks["queued"].status == "failed"
        assert "排队超时" in tasks["queued"].failure_reason
        assert tasks["lost-worker"].status == "failed"
        assert "心跳超时" in tasks["lost-worker"].failure_reason
        assert tasks["healthy-worker"].status == "running"
        assert tasks["other-project"].status == "queued"
    finally:
        db.close()


def test_run_route_uses_same_celery_id_for_database_and_message(monkeypatch):
    from app.routers import perf as perf_router

    task = SimpleNamespace(id=7, status="queued", celery_task_id="fixed-task-id")
    queued_calls = []
    publish_calls = []

    monkeypatch.setattr(perf_router, "uuid4", lambda: "fixed-task-id")
    monkeypatch.setattr(
        perf_router.perf_service,
        "s_mark_queued",
        lambda db, task_id, project_id, celery_task_id: (
            queued_calls.append((task_id, project_id, celery_task_id)) or task
        ),
    )
    monkeypatch.setattr(
        perf_router.run_perf_task,
        "apply_async",
        lambda args, task_id: publish_calls.append((args, task_id)),
    )

    response = perf_router.run_task(
        7,
        object(),
        SimpleNamespace(project_id=11),
    )

    assert queued_calls == [(7, 11, "fixed-task-id")]
    assert publish_calls == [((7, 11), "fixed-task-id")]
    assert response["data"].status == "queued"


def test_reconcile_stale_perf_tasks_counts_metric(monkeypatch):
    from app.services import perf as perf_service

    released = []
    labels = []

    class Counter:
        def labels(self, **values):
            labels.append(values)
            return self

        def inc(self):
            return None

    monkeypatch.setattr(
        perf_service.perf_repo,
        "db_fail_stale",
        lambda *args, **kwargs: [(5, 9, "running")],
    )
    monkeypatch.setattr(perf_service.redis, "from_url", lambda url: object())
    monkeypatch.setattr(
        perf_service,
        "_release_run_lock",
        lambda redis_client, run_id: released.append(run_id),
    )
    monkeypatch.setattr(perf_service.metrics, "perf_stale_tasks_recovered", Counter())

    assert perf_service.s_reconcile_stale(object()) == {"failed": 1}
    assert released == []  # No ownership proof: must not free an arbitrary lock.
    assert labels == [{"previous_status": "running"}]


def test_celery_perf_task_returns_json_serializable_summary(monkeypatch):
    from app.tasks import perf as perf_tasks

    class Db:
        def close(self):
            return None

    monkeypatch.setattr(perf_tasks, "SessionLocal", Db)
    monkeypatch.setattr(
        perf_tasks.perf_service,
        "s_run",
        lambda db, task_id, project_id, celery_task_id=None: SimpleNamespace(
            status="done"
        ),
    )

    assert perf_tasks.run_perf_task.run(7, 11) == {
        "task_id": 7,
        "project_id": 11,
        "status": "done",
    }


class _ControlRedis:
    def __init__(self):
        self.values = {}
        self.on_get = None

    def get(self, key):
        value = self.values.get(key)
        if self.on_get:
            self.on_get(key)
        return value

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

    def eval(self, script, numkeys, *args):
        if numkeys == 1:
            key, owner = args
            if self.values.get(key) != owner:
                return 0
            self.delete(key)
            return 1
        lock, active, target, owner, run_id = args
        if self.values.get(lock) != owner:
            return 0
        if self.values.get(active) == run_id:
            self.delete(active)
        self.delete(target, lock)
        return 1


@pytest.fixture
def perf_control(monkeypatch):
    from app.services import perf

    engine = create_engine("sqlite:///:memory:")
    PerfTask.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    tasks = [
        PerfTask(name=name, target_host=f"http://{name}.invalid", target_path=f"/{name}",
                 users=1, spawn_rate=1, duration=1, project_id=1, status="pending")
        for name in ("old", "new")
    ]
    db.add_all(tasks)
    db.commit()
    cache = _ControlRedis()
    monkeypatch.setattr(perf.redis, "from_url", lambda _: cache)
    monkeypatch.setattr(perf.time, "sleep", lambda _: None)
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"stats": []})
    monkeypatch.setattr(perf.requests, "get", lambda *a, **k: response)
    try:
        yield perf, db, tasks, cache, response
    finally:
        db.close()
        engine.dispose()


def test_cancel_before_active_publication_cannot_admit_new_swarm(perf_control, monkeypatch):
    perf, db, (old, new), cache, response = perf_control
    perf.s_mark_queued(db, old.id, 1, "old-message")
    admissions = []
    posts = []

    def cancel_between_check_and_publish(key):
        if key != perf.RUN_LOCK_KEY or old.status != "running":
            return
        cache.on_get = None
        assert perf.s_cancel(db, old.id, 1).status == "cancelled"
        try:
            perf.s_mark_queued(db, new.id, 1, "new-message")
            admissions.append("admitted")
        except perf.PerfRunBusyError:
            admissions.append("busy")

    cache.on_get = cancel_between_check_and_publish
    monkeypatch.setattr(perf.requests, "post", lambda *a, **k: posts.append(k) or response)
    assert perf.s_run(db, old.id, 1, "old-message").status == "cancelled"
    assert admissions == ["busy"]
    assert posts == []
    assert perf.s_mark_queued(db, new.id, 1, "new-message").status == "queued"


def test_recovery_cannot_release_lease_during_swarm_request(perf_control, monkeypatch):
    perf, db, (old, new), cache, response = perf_control
    perf.s_mark_queued(db, old.id, 1, "old-message")
    observations = []

    def in_flight(*args, **kwargs):
        perf.s_cancel(db, old.id, 1)
        perf.s_reconcile_stale(db)
        observations.append(cache.get(perf.RUN_LOCK_KEY))
        try:
            perf.s_mark_queued(db, new.id, 1, "new-message")
            observations.append("admitted")
        except perf.PerfRunBusyError:
            observations.append("busy")
        return response

    monkeypatch.setattr(perf.requests, "post", in_flight)
    assert perf.s_run(db, old.id, 1, "old-message").status == "cancelled"
    assert observations == [f"1:{old.id}:old-message", "busy"]
    assert cache.get(perf.RUN_LOCK_KEY) is None
    assert perf.s_mark_queued(db, new.id, 1, "new-message").status == "queued"


def test_queued_cancel_racing_worker_claim_keeps_running_lease(perf_control, monkeypatch):
    perf, db, (old, new), cache, response = perf_control
    perf.s_mark_queued(db, old.id, 1, "old-message")
    update = perf.perf_repo.db_update_if_status

    def claim_before_cancel(db, task_id, project_id, expected_status, **fields):
        if expected_status == "queued" and fields.get("status") == "cancelled":
            update(db, task_id, project_id, "queued", status="running", started_at=perf._utcnow())
        return update(db, task_id, project_id, expected_status, **fields)

    monkeypatch.setattr(perf.perf_repo, "db_update_if_status", claim_before_cancel)
    assert perf.s_cancel(db, old.id, 1).status == "cancelled"
    assert old.started_at is not None
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{old.id}:old-message"
    with pytest.raises(perf.PerfRunBusyError):
        perf.s_mark_queued(db, new.id, 1, "new-message")


def test_cancel_queued_task_releases_lease_without_http(perf_control, monkeypatch):
    perf, db, (old, new), cache, response = perf_control
    posts = []
    monkeypatch.setattr(perf.requests, "post", lambda *a, **k: posts.append(k) or response)
    perf.s_mark_queued(db, old.id, 1, "old-message")
    assert perf.s_cancel(db, old.id, 1).status == "cancelled"
    assert perf.s_run(db, old.id, 1, "old-message").status == "cancelled"
    assert posts == []
    assert perf.s_mark_queued(db, new.id, 1, "new-message").status == "queued"


def test_control_cleanup_cannot_delete_replacement_owner(perf_control):
    perf, db, tasks, cache, response = perf_control
    with perf._locust_control(cache):
        cache.set(perf.CONTROL_LOCK_KEY, "replacement-control")
    assert cache.get(perf.CONTROL_LOCK_KEY) == "replacement-control"


def test_launch_timeout_keeps_lease_until_master_can_be_stopped(perf_control, monkeypatch):
    perf, db, (old, new), cache, response = perf_control
    perf.s_mark_queued(db, old.id, 1, "old-message")

    def unavailable(*args, **kwargs):
        raise OSError("master control request timed out")

    monkeypatch.setattr(perf.requests, "post", unavailable)
    monkeypatch.setattr(perf.requests, "get", unavailable)
    with pytest.raises(OSError, match="timed out"):
        perf.s_run(db, old.id, 1, "old-message")
    assert old.status == "failed"
    assert cache.get(perf.CONTROL_LOCK_KEY) is None
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{old.id}:old-message"
    with pytest.raises(perf.PerfRunBusyError):
        perf.s_mark_queued(db, new.id, 1, "new-message")
    monkeypatch.setattr(perf.requests, "get", lambda *a, **k: response)
    perf.s_reconcile_stale(db)
    assert cache.get(perf.RUN_LOCK_KEY) is None
    assert perf.s_mark_queued(db, new.id, 1, "new-message").status == "queued"
