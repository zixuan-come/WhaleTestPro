"""Review regressions: synthetic credentials and memory databases only."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import assertions, security
from app.models.report import TestReport as Report
from app.models.schedule import Schedule
from app.models.interface import Interface
from app.models.case import Case
from app.repositories import perf as perf_repo
from app.routers import suite as suite_router
from app.schemas.suite import SuiteCreate, SuiteUpdate
from app.schemas.user import UserCreate, UserLogin
from app.services import execution, suite
from app.tasks.traffic import _mask
from tests.test_suite_service import db as suite_db
from tests.test_perf_lifecycle import perf_control


@pytest.fixture
def foreign_key_db(suite_db):
    suite_db.execute(text("PRAGMA foreign_keys=ON"))
    assert suite_db.execute(text("PRAGMA foreign_keys")).scalar() == 1
    return suite_db


def test_delete_executed_suite_retains_report_snapshot(foreign_key_db):
    db = foreign_key_db
    item = suite.s_create(db, SuiteCreate(name="report-snapshot", type="case"), 1)
    suite.run_suite(db, item.id, 1)
    report = db.query(Report).filter_by(suite_id=item.id).one()
    report_id = report.id
    suite.s_delete(db, item.id, 1)
    db.expire_all()
    report = db.get(Report, report_id)
    assert report.suite_id is None
    assert report.suite_name == "report-snapshot"
    assert db.query(Report).count() == 1


def test_delete_scheduled_suite_returns_conflict_without_detaching_report(foreign_key_db):
    db = foreign_key_db
    item = suite.s_create(db, SuiteCreate(name="scheduled", type="case"), 1)
    suite.run_suite(db, item.id, 1)
    db.add(Schedule(name="schedule", cron="* * * * *", suite_id=item.id, project_id=1))
    db.commit()
    with pytest.raises(HTTPException) as caught:
        suite.s_delete(db, item.id, 1)
    assert caught.value.status_code == 409
    assert db.query(Report).filter_by(suite_id=item.id).count() == 1


@pytest.mark.parametrize("deletion_phase", ["during_request", "before_summary"])
def test_suite_deleted_during_execution_still_keeps_summary_snapshot(foreign_key_db, monkeypatch, deletion_phase):
    from app.repositories import report as report_repo
    db = foreign_key_db
    interface = Interface(name="isolated", method="GET", url="/safe", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="isolated", interface_id=interface.id, expected_status=200, project_id=1)
    db.add(case)
    db.commit()
    item = suite.s_create(db, SuiteCreate(name="immutable-snapshot", type="case", case_ids=[case.id]), 1)
    item_id = item.id
    def delete_suite():
        with Session(db.get_bind()) as competing:
            suite.s_delete(competing, item_id, 1)
    def request(*args, **kwargs):
        if deletion_phase == "during_request":
            delete_suite()
        return response({"ok": True})
    monkeypatch.setattr(execution, "_request", request)
    create_summary = report_repo.db_create_suite_report
    def summary(*args, **kwargs):
        if deletion_phase == "before_summary":
            delete_suite()
        return create_summary(*args, **kwargs)
    monkeypatch.setattr(report_repo, "db_create_suite_report", summary)
    result = suite.run_suite(db, item_id, 1)
    assert result["suite_name"] == "immutable-snapshot" and result["passed"] == 1
    report = db.query(Report).filter_by(execution_type="suite").one()
    assert report.suite_id is None and report.suite_name == "immutable-snapshot"
    assert db.query(Report).count() == 2




@pytest.mark.parametrize("field", ["name", "type"])
def test_suite_update_rejects_explicit_null_but_accepts_omission(field):
    assert SuiteUpdate().model_dump(exclude_unset=True) == {}
    with pytest.raises(ValidationError):
        SuiteUpdate(**{field: None})


def test_suite_route_maps_foreign_environment_to_not_found(foreign_key_db):
    db = foreign_key_db
    interface = Interface(name="isolated", method="GET", url="/safe", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="isolated", interface_id=interface.id, expected_status=200, project_id=1)
    db.add(case)
    db.commit()
    item = suite.s_create(db, SuiteCreate(name="foreign-env", type="case", case_ids=[case.id]), 1)
    with pytest.raises(HTTPException) as caught:
        suite_router.run_suite(item.id, 999999, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 404
    assert db.query(Report).count() == 0








def response(body):
    result = requests.Response()
    result.status_code = 200
    result.encoding = "utf-8"
    result._content = json.dumps(body).encode()
    return result








@pytest.mark.parametrize("case_ids", [[], [999999]])
def test_suite_rejects_invalid_environment_before_resolving_members(foreign_key_db, case_ids):
    db = foreign_key_db
    item = suite.s_create(db, SuiteCreate(name="validate-first", type="case", case_ids=case_ids), 1)
    with pytest.raises(HTTPException) as caught:
        suite_router.run_suite(item.id, 999999, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 404
    assert db.query(Report).count() == 0






def test_delete_cannot_remove_task_queued_after_old_snapshot(perf_control, monkeypatch):
    perf, db, (old, _), cache, _response = perf_control
    delete = perf_repo.db_delete
    task_id = old.id
    def queue_before_delete(database, task_id, project_id):
        # A second session commits between the delete request's read and DELETE.
        with Session(database.get_bind()) as competing:
            assert perf.s_mark_queued(competing, task_id, project_id, "queued-message") is not None
        return delete(database, task_id, project_id)
    monkeypatch.setattr(perf_repo, "db_delete", queue_before_delete)
    assert perf.s_delete(db, task_id, 1) is None
    db.expire_all()
    assert perf_repo.db_get(db, task_id, 1).status == "queued"
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task_id}:queued-message"


def test_queue_losing_race_to_delete_releases_its_reserved_lease(perf_control, monkeypatch):
    perf, db, (old, _), cache, _response = perf_control
    task_id = old.id
    update = perf_repo.db_update_if_status
    def delete_before_queue(database, task_id, project_id, expected_status, **fields):
        with Session(database.get_bind()) as competing:
            assert perf_repo.db_delete(competing, task_id, project_id) is not None
        return update(database, task_id, project_id, expected_status, **fields)
    monkeypatch.setattr(perf_repo, "db_update_if_status", delete_before_queue)
    assert perf.s_mark_queued(db, task_id, 1, "losing-message") is None
    assert cache.get(perf.RUN_LOCK_KEY) is None
    assert perf_repo.db_get(db, task_id, 1) is None


def test_old_pending_snapshot_cannot_delete_newly_cancelled_worker_lease(perf_control, monkeypatch):
    perf, db, (old, _), cache, response = perf_control
    delete = perf_repo.db_delete
    task_id = old.id
    def cancel_before_delete(database, task_id, project_id):
        with Session(database.get_bind()) as competing:
            perf.s_mark_queued(competing, task_id, project_id, "worker-message")
            perf_repo.db_update_if_status(competing, task_id, project_id, "queued", status="running")
            assert perf.s_cancel(competing, task_id, project_id).status == "cancelled"
        return delete(database, task_id, project_id)
    monkeypatch.setattr(perf_repo, "db_delete", cancel_before_delete)
    assert perf.s_delete(db, task_id, 1) is None
    db.expire_all()
    assert perf_repo.db_get(db, task_id, 1).status == "cancelled"
    assert cache.get(perf.RUN_LOCK_KEY) == f"1:{task_id}:worker-message"
    monkeypatch.setattr(perf_repo, "db_delete", delete)
    assert perf.s_delete(db, task_id, 1) is not None
    assert cache.get(perf.RUN_LOCK_KEY) is None


def test_missing_control_token_returns_503_before_reserving_or_publishing(perf_control, monkeypatch):
    from app.routers import perf as perf_router
    perf, db, (old, _), cache, _response = perf_control
    monkeypatch.setattr(perf.settings, "LOCUST_CONTROL_TOKEN", "")
    published = []
    monkeypatch.setattr(perf_router.run_perf_task, "apply_async", lambda **kwargs: published.append(kwargs))
    with pytest.raises(HTTPException) as caught:
        perf_router.run_task(old.id, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 503
    assert old.status == "pending" and cache.values == {} and published == []


def test_terminal_delete_waits_for_master_cleanup_before_removing_row(perf_control, monkeypatch):
    perf, db, (old, _), cache, response = perf_control
    task_id = old.id
    run_id = f"1:{task_id}"
    old.status = "cancelled"
    db.commit()
    cache.values.update({perf.RUN_LOCK_KEY: run_id + ":message", perf.ACTIVE_RUN_KEY: run_id})
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("isolated unavailable master")
    monkeypatch.setattr(perf.requests, "get", unavailable)
    assert perf.s_delete(db, task_id, 1) is None
    assert perf_repo.db_get(db, task_id, 1) is not None
    assert cache.get(perf.RUN_LOCK_KEY) == run_id + ":message"
    monkeypatch.setattr(perf.requests, "get", lambda *args, **kwargs: response)
    assert perf.s_delete(db, task_id, 1) is not None
    assert perf_repo.db_get(db, task_id, 1) is None
    assert cache.get(perf.RUN_LOCK_KEY) is None


def test_terminal_delete_with_unavailable_redis_returns_503_and_keeps_row(perf_control, monkeypatch):
    from app.routers import perf as perf_router
    perf, db, (old, _), cache, _response = perf_control
    old.status = "failed"
    db.commit()
    def unavailable(_key):
        raise perf.redis.ConnectionError("isolated unavailable cache")
    monkeypatch.setattr(cache, "get", unavailable)
    with pytest.raises(HTTPException) as caught:
        perf_router.delete_task(old.id, db, SimpleNamespace(project_id=1))
    assert caught.value.status_code == 503
    assert perf_repo.db_get(db, old.id, 1) is not None


def test_all_master_requests_include_the_control_header(perf_control, monkeypatch):
    perf, db, (old, _), cache, response = perf_control
    calls = []
    def reply(url, **kwargs):
        calls.append((url, kwargs.get("headers")))
        return response
    monkeypatch.setattr(perf.requests, "get", reply)
    monkeypatch.setattr(perf.requests, "post", reply)
    perf.s_mark_queued(db, old.id, 1, "message")
    assert perf.s_run(db, old.id, 1, "message").status == "done"
    assert {url.rsplit("/", 1)[-1] for url, _ in calls} == {"swarm", "stop", "requests"}
    assert all(headers == {"X-Locust-Control-Token": "isolated-control-token"} for _, headers in calls)


@pytest.mark.parametrize("endpoint", ["/safe", "/safe?a=1&b=2", "/literal&amp;path"])
def test_real_locust_error_occurrences_are_preserved(perf_control, monkeypatch, endpoint):
    import html
    from locust.stats import StatsError
    perf, db, (old, _), cache, _response = perf_control
    error = StatsError("GET", endpoint, "HTTP 500", occurrences=7).serialize()
    error["name"] = html.escape(error["name"])
    statistics = {"errors": [error], "stats": [{"method": "GET", "name": endpoint, "num_requests": 10, "num_failures": 7}]}
    reply = SimpleNamespace(raise_for_status=lambda: None, json=lambda: statistics)
    monkeypatch.setattr(perf.requests, "get", lambda *a, **k: reply)
    monkeypatch.setattr(perf.requests, "post", lambda *a, **k: reply)
    perf.s_mark_queued(db, old.id, 1, "message")
    result = perf.s_run(db, old.id, 1, "message")
    assert result.error_summary[0]["error_count"] == 7
    assert result.error_summary[0]["error_rate"] == pytest.approx(0.7)
    assert result.error_summary[0]["name"] == endpoint


def test_compose_keeps_master_private_and_configures_app_recovery():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    app_section = compose.split("  app:", 1)[1].split("  worker:", 1)[0]
    assert "LOCUST_MASTER_URL: http://locust-master:8089" in app_section
    assert '"8089:8089"' not in compose
    assert "nodePort: 30089" not in (root / "k8s/40-frontend-locust.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize("token,blocked_status", [("isolated-control-token", 403), ("", 503)])
def test_master_rejects_unauthenticated_control_and_accepts_internal_token(monkeypatch, token, blocked_status):
    from locust.env import Environment
    monkeypatch.setenv("LOCUST_CONTROL_TOKEN", token)
    monkeypatch.setattr("sys.argv", ["locust"])
    path = Path(__file__).resolve().parents[1] / "locustfile.py"
    spec = importlib.util.spec_from_file_location("review_locustfile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    environment = Environment()
    runner = environment.create_local_runner()
    web = environment.create_web_ui("127.0.0.1", 0, delayed_start=True)
    stops = []
    monkeypatch.setattr(runner, "stop", lambda: stops.append(True))
    module._on_init(environment)
    try:
        client = web.app.test_client()
        assert client.get("/stop").status_code == blocked_status
        assert client.get("/stats/requests").status_code == blocked_status
        assert client.post("/swarm", data={"user_count": "1", "spawn_rate": "1"}).status_code == blocked_status
        assert stops == []
        assert client.get("/stop", headers={"X-Locust-Control-Token": "wrong"}).status_code == blocked_status
        accepted = client.get("/stop", headers={"X-Locust-Control-Token": "isolated-control-token"})
        assert accepted.status_code == (200 if token else 503)
        assert stops == ([True] if token else [])
    finally:
        runner.quit()
