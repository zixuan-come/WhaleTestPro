"""Path binding, execution and API persistence regressions without external I/O."""
import json
from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.migrations import ensure_interface_path_parameters_schema
from app.core.path_parameters import render_request_path
from app.database import get_db
from app.models.interface import Interface
from app.routers import interface as interface_router
from app.schemas.interface import InterfaceCreate
from app.services import execution


@pytest.mark.parametrize("template,values,context,expected", [
    ("/orders/{id}", {"id": 1}, {}, "/orders/1"),
    ("/orders/{id}", {"id": "abc"}, {}, "/orders/abc"),
    ("/teams/{team-id}/orders/{id}/{id}", {"team-id": 7, "id": 0}, {}, "/teams/7/orders/0/0"),
    ("/orders/{id}", {"id": "${created_id}"}, {"created_id": 2}, "/orders/2"),
    ("/orders/{id}", None, {"id": 3}, "/orders/3"),
    ("/orders/${id}", None, {"id": 4}, "/orders/4"),
    ("/users/${uid}/orders/{id}", {"id": 5}, {"uid": 7}, "/users/7/orders/5"),
    ("/orders/{id}?q=${q}", {"id": 1}, {"q": "all"}, "/orders/1?q=all"),
    ("/orders/{id}?q={literal}", {"id": 1}, {}, "/orders/1?q={literal}"),
    ("/orders/{id}", {"id": "a/b?c#d %中文"}, {}, "/orders/a%2Fb%3Fc%23d%20%25%E4%B8%AD%E6%96%87"),
    ("/orders/1", None, {}, "/orders/1"),
])
def test_path_binding(template, values, context, expected):
    assert render_request_path(template, context, values) == expected


@pytest.mark.parametrize("value", [None, "", "  ", ".", "..", {}, []])
def test_invalid_or_missing_path_values_are_rejected(value):
    with pytest.raises(ValueError, match="路径参数"):
        render_request_path("/orders/{id}", {}, {"id": value})


def test_unfilled_and_missing_variable_are_explained():
    with pytest.raises(ValueError, match="请填写路径参数：id"):
        render_request_path("/orders/{id}", {})
    with pytest.raises(KeyError, match="变量未找到: order_id"):
        render_request_path("/orders/{id}", {}, {"id": "${order_id}"})


@pytest.mark.parametrize("value", [{"nested": 1}, [1]])
def test_schema_does_not_accept_structured_path_values(value):
    with pytest.raises(ValidationError):
        InterfaceCreate(name="order", method="GET", url="/orders/{id}", path_params={"id": value})


@pytest.fixture
def runner(monkeypatch):
    item = SimpleNamespace(id=7, name="order", method="GET", url="/orders/{id}",
                           headers=None, params={"page": "${page}"}, body=None,
                           path_params={"id": "${order_id}"})
    case = SimpleNamespace(id=11, name="order case", interface_id=7, expected_status=200,
                           extract_rules=None, assertions=None, setup_sql=None, teardown_sql=None,
                           retries=0, datasets=[{"order_id": 2}, {"order_id": 3}])
    calls, reports = [], []
    monkeypatch.setattr(execution.interface_repo, "db_get", lambda *args: item)
    monkeypatch.setattr(execution.case_repo, "db_get", lambda *args: case)
    monkeypatch.setattr(execution, "_env_context", lambda *args: {"base_url": "http://orders.invalid", "order_id": 1, "page": 9})
    monkeypatch.setattr(execution.report_repo, "db_create", lambda *args, **kw: reports.append(kw))
    monkeypatch.setattr(execution, "run_sql", lambda *args: None)
    monkeypatch.setattr(execution, "run_assertions", lambda *args: [])

    def request(interface, **kw):
        calls.append(kw)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"id": 1}).encode()
        return response

    monkeypatch.setattr(execution, "_request", request)
    return item, case, calls, reports


def test_direct_run_override_is_temporary_and_query_params_stay_query_params(runner):
    item, _, calls, reports = runner
    result = execution.run_interface(None, 7, 1, 23, path_params={"id": 8})
    assert result["passed"] is True
    assert result["request"]["url"] == "http://orders.invalid/orders/8"
    assert calls[0]["params"] == {"page": "9"}
    assert item.path_params == {"id": "${order_id}"}
    assert reports == []


def test_missing_path_value_prevents_an_http_request(runner):
    item, _, calls, _ = runner
    item.path_params = None
    result = execution.run_interface(None, 7, 1, 23)
    assert result["passed"] is False
    assert "请填写路径参数：id" in result["error"]
    assert calls == []


def test_sensitive_path_values_are_used_live_but_redacted_from_evidence(runner):
    item, case, calls, _ = runner
    item.url = "/orders/{api_key}"
    item.path_params = {"api_key": "synthetic/secret?value"}
    result = execution.run_interface(None, 7, 1, 23)
    assert calls[0]["url"].endswith("/synthetic%2Fsecret%3Fvalue")
    assert "synthetic" not in json.dumps(result)
    case.datasets = None
    assert execution.run_case(None, 11, 1, 23)["passed"] is True


def test_case_datasets_bind_saved_path_variable_and_persist_one_report(runner):
    _, _, calls, reports = runner
    result = execution.run_case(None, 11, 1, 23)
    assert all(row["passed"] for row in result)
    assert [row["url"] for row in calls] == ["http://orders.invalid/orders/2", "http://orders.invalid/orders/3"]
    assert len(reports) == 1


def test_chain_extracts_created_id_for_the_next_path_parameter(runner, monkeypatch):
    item, case, calls, _ = runner
    case.extract_rules = {"created_id": "$.id"}
    step = 0

    def get_case(*args):
        nonlocal step
        step += 1
        if step == 2:
            item.path_params = {"id": "${created_id}"}
        return case

    monkeypatch.setattr(execution.case_repo, "db_get", get_case)
    result = execution.run_chain(None, [11, 12], 1, 23)
    assert all(row["passed"] for row in result)
    assert [row["url"] for row in calls] == ["http://orders.invalid/orders/1"] * 2


def test_additive_migration_is_repeatable_and_preserves_existing_interface():
    bind = create_engine("sqlite://")
    with bind.begin() as conn:
        conn.execute(text("CREATE TABLE interface (id INTEGER PRIMARY KEY, url TEXT)"))
        conn.execute(text("INSERT INTO interface VALUES (1, '/orders/1')"))
    ensure_interface_path_parameters_schema(bind)
    ensure_interface_path_parameters_schema(bind)
    assert next(c for c in inspect(bind).get_columns("interface") if c["name"] == "path_params")["nullable"]
    with bind.connect() as conn:
        assert tuple(conn.execute(text("SELECT url, path_params FROM interface")).one()) == ("/orders/1", None)
    bind.dispose()


def test_interface_api_saves_defaults_runs_overrides_and_accepts_legacy_null_body(monkeypatch):
    bind = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Interface.__table__.create(bind)
    application = FastAPI()
    application.include_router(interface_router.router)

    def database():
        with Session(bind) as db:
            yield db

    application.dependency_overrides[get_db] = database
    for route in interface_router.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "context":
                application.dependency_overrides[dependency.call] = lambda: SimpleNamespace(project_id=23)
    calls = []
    monkeypatch.setattr(execution, "_env_context", lambda *args: {"base_url": "http://orders.invalid"})

    def request(interface, **kw):
        calls.append(kw["url"])
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"id":1}'
        return response

    monkeypatch.setattr(execution, "_request", request)
    payload = {"name": "order", "method": "GET", "url": "/orders/{id}", "path_params": {"id": "1"}}
    with TestClient(application) as client:
        response = client.post("/interfaces", json=payload)
        assert response.status_code == 201
        saved = response.json()["data"]
        key = saved["id"]
        assert saved["path_params"] == {"id": "1"}
        assert client.post(f"/interfaces/{key}/run", json={"path_params": {"id": 2}}).json()["data"]["passed"] is True
        assert client.get(f"/interfaces/{key}").json()["data"]["path_params"] == {"id": "1"}
        assert client.post(f"/interfaces/{key}/run").json()["data"]["passed"] is True
        assert calls == ["http://orders.invalid/orders/2", "http://orders.invalid/orders/1"]
        assert client.post(f"/interfaces/{key}/run", json={"url": "http://other.invalid"}).status_code == 422
        assert client.post(f"/interfaces/{key}/run", json={"path_params": {"id": {"nested": 1}}}).status_code == 422
        changed = client.put(f"/interfaces/{key}", json={**payload, "path_params": {"id": "3"}})
        assert changed.json()["data"]["path_params"] == {"id": "3"}
    bind.dispose()
