import importlib.util
import json
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from app.core.perf_plan import execute_iteration
from app.schemas.perf_plan import PerfLoadConfig
from app.schemas.perf import PerfTaskCreate


class Response:
    def __init__(self, data=None, status=200):
        self.data, self.status_code = data, status
        self.headers = {"X-Result": "ok"}
        self.elapsed = timedelta(milliseconds=10)
        self.verdict = None
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def json(self): return self.data
    def success(self): self.verdict = True
    def failure(self, message): self.verdict = message


class Client:
    def __init__(self, responses):
        self.responses, self.calls, self.failures = list(responses), [], []
        self.cookies = {"old": "previous-cycle-cookie"}
        self.request_event = SimpleNamespace(fire=lambda **row: self.failures.append(row))
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_methods_are_sent_without_becoming_get(method):
    plan = PerfLoadConfig(steps=[{"method": method, "path": "/item"}])
    client = Client([Response({})])
    assert execute_iteration(client, "http://fixture", plan, "vu", 1)["passed"]
    assert client.calls[0][0] == method


@pytest.mark.parametrize("kind,body,key", [("json", {"n": "${count}"}, "json"),
    ("form", {"x": "${name}"}, "data"), ("raw", "<id>${count}</id>", "data")])
def test_body_formats_and_type_preserving_render(kind, body, key):
    plan = PerfLoadConfig(variables={"count": 3, "name": "test"}, steps=[{
        "method": "POST", "path": "/item", "body_type": kind, "body": body,
        "headers": {"Authorization": "Bearer ${name}"}, "params": {"n": "${count}"}}])
    client = Client([Response({})])
    assert execute_iteration(client, "http://fixture", plan, "vu", 1)["passed"]
    sent = client.calls[0][2]
    assert sent[key] == ({"n": 3} if kind == "json" else {"x": "test"} if kind == "form" else b"<id>3</id>")
    assert sent["params"] == {"n": 3}
    assert sent["headers"]["Authorization"] == "Bearer test"


def test_chain_order_extraction_independent_users_and_cycles():
    plan = PerfLoadConfig(mode="chain", variables={"items": []}, datasets=[{"sku": 1}, {"sku": 2}], steps=[
        {"method": "POST", "path": "/login", "extract_rules": {"token": "$.token"}},
        {"method": "POST", "path": "/orders", "headers": {"Authorization": "Bearer ${token}"},
         "body_type": "json", "body": {"sku": "${sku}", "key": "${_vu_id}-${_iteration}"}, "extract_rules": {"order": "$.id"}},
        {"path": "/orders/${order}"}])
    before = deepcopy(plan.model_dump())
    a = Client([Response({"token": "A"}), Response({"id": 11}), Response({})])
    b = Client([Response({"token": "B"}), Response({"id": 22}), Response({})])
    for client, vu, iteration in [(a, "user-a", 1), (b, "user-b", 2)]:
        assert execute_iteration(client, "http://fixture", plan, vu, iteration)["passed"]
        assert client.cookies == {}
    assert [row[1] for row in a.calls] == ["http://fixture/login", "http://fixture/orders", "http://fixture/orders/11"]
    assert a.calls[1][2]["headers"] == {"Authorization": "Bearer A"}
    assert b.calls[1][2]["headers"] == {"Authorization": "Bearer B"}
    assert a.calls[1][2]["json"] == {"sku": 1, "key": "user-a-1"}
    assert b.calls[1][2]["json"] == {"sku": 2, "key": "user-b-2"}
    assert plan.model_dump() == before
    again = Client([Response({}, 500)])
    assert not execute_iteration(again, "http://fixture", plan, "user-a", 3)["passed"]
    assert len(again.calls) == 1  # No reuse of the previous token/order.


def test_json_null_and_unicode_raw_are_real_request_bodies():
    client = Client([Response({}), Response({})])
    plan = PerfLoadConfig(mode="chain", steps=[
        {"method": "POST", "path": "/null", "body_type": "json", "body": None},
        {"method": "PUT", "path": "/text", "body_type": "raw", "body": "中文"}])
    assert execute_iteration(client, "http://fixture", plan, "vu", 1)["passed"]
    assert client.calls[0][2]["data"] == b"null"
    assert client.calls[0][2]["headers"]["Content-Type"] == "application/json"
    assert client.calls[1][2]["data"] == "中文".encode("utf-8")


@pytest.mark.parametrize("failure", ["status", "assertion", "extraction", "network"])
def test_failure_counts_and_stops_dependent_steps_without_secrets(failure):
    step = {"path": "/login?token=synthetic-secret", "expected_status": 200}
    response = Response({"code": 5}, status=500 if failure == "status" else 200)
    if failure == "assertion": step["assertions"] = [{"type": "json_eq", "path": "$.code", "expected": 0}]
    if failure == "extraction": step["extract_rules"] = {"token": "$.missing"}
    if failure == "network": response = RuntimeError("failed URL contains synthetic-secret")
    plan = PerfLoadConfig(mode="chain", steps=[step, {"path": "/next"}])
    client = Client([response])
    assert not execute_iteration(client, "http://fixture", plan, "vu", 1)["passed"]
    assert len(client.calls) == 1
    evidence = repr(client.failures) if failure == "network" else response.verdict
    assert "synthetic-secret" not in evidence
    assert client.calls[0][2]["name"] == "step_01"


def test_missing_variable_is_failure_not_skipped_success():
    client = Client([])
    result = execute_iteration(client, "http://fixture", PerfLoadConfig(steps=[{"path": "/${missing}"}]), "vu", 1)
    assert not result["passed"] and not client.calls
    assert len(client.failures) == 1


def test_continue_failure_does_not_set_partially_extracted_variables():
    plan = PerfLoadConfig(mode="chain", stop_on_failure=False, steps=[
        {"path": "/one", "extract_rules": {"token": "$.token", "other": "$.absent"}},
        {"path": "/${token}"}, {"path": "/independent"}])
    client = Client([Response({"token": "secret"}), Response({})])
    assert not execute_iteration(client, "http://fixture", plan, "vu", 1)["passed"]
    assert [row[1] for row in client.calls] == ["http://fixture/one", "http://fixture/independent"]
    assert len(client.failures) == 1


@pytest.mark.parametrize("step", [{"path": "//foreign/x"}, {"path": "https://foreign"},
    {"path": "/ok", "method": "CONNECT"}, {"path": "/ok", "headers": {"X": "x\r\nInjected: true"}},
    {"path": "/ok", "body_type": "form", "body": "raw"},
    {"path": "/ok", "assertions": [{"type": "db_eq", "expected": 1, "sql": "SELECT 1"}]},
    {"path": "/ok", "extract_rules": {"_vu_id": "$.id"}}])
def test_unsupported_or_unsafe_plans_are_rejected(step):
    with pytest.raises(ValidationError): PerfLoadConfig(steps=[step])


def test_single_count_size_reserved_values_and_old_get_contract():
    with pytest.raises(ValidationError): PerfLoadConfig(steps=[{"path": "/a"}, {"path": "/b"}])
    with pytest.raises(ValidationError): PerfLoadConfig(variables={"_vu_id": "shared"}, steps=[{"path": "/a"}])
    with pytest.raises(ValidationError): PerfLoadConfig(variables={"big": "x" * 262144}, steps=[{"path": "/a"}])
    old = PerfTaskCreate(name="legacy", target_host="http://fixture", target_path="health", users=1, spawn_rate=1, duration=1)
    assert old.load_config is None and old.target_path == "/health"


def test_json_schema_remote_references_are_rejected():
    with pytest.raises(ValidationError):
        PerfLoadConfig(steps=[{"path": "/x", "assertions": [{"type": "json_schema",
            "expected": {"$ref": "https://not-a-target.invalid/private"}}]}])
    plan = PerfLoadConfig(steps=[{"path": "/x", "assertions": [{"type": "json_schema",
        "expected": {"type": "object", "$defs": {"code": {"type": "integer"}},
                     "properties": {"code": {"$ref": "#/$defs/code"}}}}]}])
    assert execute_iteration(Client([Response({"code": 0})]), "http://fixture", plan, "vu", 1)["passed"]


def test_additive_migration_is_repeatable_and_preserves_old_tasks():
    from app.core.migrations import ensure_perf_load_plan_schema
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE perf_tasks(id INTEGER PRIMARY KEY, target_path TEXT)"))
        db.execute(text("INSERT INTO perf_tasks VALUES(1, '/old')"))
    ensure_perf_load_plan_schema(engine)
    ensure_perf_load_plan_schema(engine)
    assert {row["name"] for row in inspect(engine).get_columns("perf_tasks")} == {"id", "target_path", "load_config", "iteration_stats"}
    with engine.connect() as db:
        assert tuple(db.execute(text("SELECT * FROM perf_tasks")).one()) == (1, "/old", None, None)


@pytest.fixture
def plugin(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["locust"])
    spec = importlib.util.spec_from_file_location("perf_plan_locustfile", Path(__file__).resolve().parents[1] / "locustfile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owned_worker_plan_rejects_missing_changed_and_stale_config(plugin):
    lease, run = "1:2:message", "1:2"
    values = {plugin.RUN_LOCK_KEY: lease, plugin.ACTIVE_RUN_KEY: run,
              f"locust:target_path:{run}": json.dumps({"lease": lease, "target_host": "http://fixture", "deadline": 9999999999,
                                                    "load_config": {"steps": [{"method": "POST", "path": "/x"}]}})}
    cache = SimpleNamespace(get=lambda key: values.get(key))
    owned = plugin._owned_plan(cache, "http://wrong")
    assert owned[1] == "http://fixture" and owned[2].steps[0].method == "POST"
    values[plugin.RUN_LOCK_KEY] = "1:2:new-generation"
    with pytest.raises(ValueError): plugin._owned_plan(cache, "http://wrong")
    values.pop(f"locust:target_path:{run}")
    with pytest.raises(ValueError): plugin._owned_plan(cache, "http://wrong")


def test_worker_metrics_replace_cumulative_reports_and_ignore_old_run(plugin, monkeypatch):
    plugin._iteration_stats["lease"] = "new"
    plugin._iteration_started = 10
    monkeypatch.setattr(plugin.time, "monotonic", lambda: 12)
    first = {"lease": "new", "iterations": 3, "failures": 1, "total_duration_ms": 30}
    plugin._worker_report("worker-a", {"whale_iterations": first})
    plugin._worker_report("worker-a", {"whale_iterations": {**first, "iterations": 5}})
    plugin._worker_report("worker-b", {"whale_iterations": first})
    plugin._worker_report("worker-old", {"whale_iterations": {**first, "lease": "old"}})
    class Master: pass
    monkeypatch.setattr(plugin, "MasterRunner", Master)
    summary = plugin._iteration_summary(SimpleNamespace(runner=Master()))
    assert summary["iterations"] == 8 and summary["failures"] == 2
    assert summary["iteration_rps"] == 4 and summary["avg_duration_ms"] == 7.5


@pytest.mark.parametrize("configuration_failures", [0, 1])
def test_backend_publishes_owned_snapshot_and_saves_iteration_metrics(monkeypatch, configuration_failures):
    import app.models.project
    from app.models.perf import PerfTask, PerfRun
    from app.services import perf
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    PerfTask.__table__.create(engine)
    PerfRun.__table__.create(engine)
    app.models.project.Project.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    db.add(app.models.project.Project(id=1, name="isolated-snapshot-project", team_id=1))
    db.commit()
    plan = PerfTaskCreate(name="snapshot", target_host="http://fixture", target_path="/login", users=2,
        spawn_rate=2, duration=2, load_config={"steps": [{"method": "POST", "path": "/login"}]})
    saved = perf.s_create(db, plan, 1)
    saved.status, saved.celery_task_id = "queued", "message"
    db.commit()
    lease = f"1:{saved.id}:message"
    class Cache:
        def __init__(self): self.values = {}
        def get(self, key): return self.values.get(key)
        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.values: return False
            self.values[key] = value
            return True
        def expire(self, key, seconds): return key in self.values
        def eval(self, script, numkeys, *args):
            keys, values = args[:numkeys], args[numkeys:]
            if self.get(keys[0]) != values[0]: return 0
            if numkeys == 3:
                if self.get(keys[1]) == values[1]: self.values.pop(keys[1], None)
                self.values.pop(keys[2], None)
            self.values.pop(keys[0], None)
            return 1
    cache = Cache()
    monkeypatch.setattr(perf.redis, "from_url", lambda *_: cache)
    monkeypatch.setattr(perf.settings, "LOCUST_CONTROL_TOKEN", "synthetic-control")
    monkeypatch.setattr(perf.time, "sleep", lambda *_: None)
    started = []
    def launch(url, **kwargs):
        payload = json.loads(cache.get(perf._target_path_key(f"1:{saved.id}")))
        assert payload["lease"] == lease and payload["target_host"] == "http://fixture"
        assert payload["load_config"]["steps"][0]["method"] == "POST"
        started.append(kwargs)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"success": True})
    monkeypatch.setattr(perf.requests, "post", launch)
    summary = {"lease": lease, "iterations": 5, "failures": 0, "configuration_failures": configuration_failures}
    monkeypatch.setattr(perf.requests, "get", lambda url, **kwargs: SimpleNamespace(raise_for_status=lambda: None,
        json=lambda: summary if url.endswith("/whale/iterations") else {
            "stats": [{"name": "Aggregated", "num_requests": 5}], "total_rps": 0, "fail_ratio": 0}))
    try:
        if configuration_failures:
            with pytest.raises(perf.PerfControlUnavailableError): perf.s_run(db, saved.id, 1, "message")
            assert db.get(PerfTask, saved.id).status == "failed"
        else:
            result = perf.s_run(db, saved.id, 1, "message")
            assert result.status == "done" and result.iteration_stats["iterations"] == 5
        assert len(started) == 1
        assert not cache.values  # Same owned cleanup removes credential snapshot.
        assert db.get(PerfTask, saved.id).load_config == plan.load_config.model_dump()
    finally:
        db.close()
