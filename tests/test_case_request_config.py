"""Independent case requests and scoped API persistence; SQLite and mocked HTTP."""
from copy import deepcopy
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

from app.core.migrations import ensure_case_request_overrides_schema
from app.core.request_config import with_request_overrides
from app.database import get_db
from app.models.case import Case
from app.models.interface import Interface
from app.routers import case as case_router, interface as interface_router
from app.schemas.case import CaseCreate, CaseOut
from app.services import execution
from tests.test_path_parameters import runner  # shared mocked execution fixture


def test_schema_preserves_omitted_fields_and_explicit_clears():
    payload = CaseCreate(name="clear body", interface_id=1, expected_status=200,
                         request_overrides={"body": None, "params": {}})
    assert payload.model_dump()["request_overrides"] == {"body": None, "params": {}}
    row = Case(id=1, project_id=10, **payload.model_dump())
    assert CaseOut.model_validate(row).model_dump()["request_overrides"] == {"body": None, "params": {}}
    assert CaseCreate(name="legacy", interface_id=1, expected_status=200).model_dump()["request_overrides"] is None
    with pytest.raises(ValidationError):
        CaseCreate(name="invalid", interface_id=1, expected_status=200, request_overrides={"url": "/other"})


def test_execution_copy_inherits_omitted_fields_and_isolates_nested_values():
    interface = SimpleNamespace(id=1, name="order", method="GET", url="/orders/{id}",
                                path_params={"id": "1"}, params={"page": 1}, headers={"X-Base": "base"}, body={"nested": {"count": 1}})
    overrides = {"path_params": {"id": "abc"}, "headers": {}, "body": None}
    before = deepcopy(vars(interface))
    copied = with_request_overrides(interface, overrides)
    assert copied.path_params == {"id": "abc"} and copied.headers == {} and copied.body is None
    assert copied.params == {"page": 1}
    copied.params["page"] = 5
    copied.path_params["id"] = 9
    assert vars(interface) == before
    assert overrides["path_params"]["id"] == "abc"
    assert with_request_overrides(interface, None) is interface


def test_data_driven_case_renders_its_own_request_without_changing_interface(runner):
    interface, case, calls, reports = runner
    original = deepcopy(vars(interface))
    case.request_overrides = {"path_params": {"id": "${order_id}"}, "headers": {"X-Row": "${order_id}"},
                              "params": {}, "body": {"quantity": "${order_id}"}}
    outputs = execution.run_case(None, 11, 1, 23)
    assert all(row["passed"] for row in outputs)
    assert [row["url"] for row in calls] == ["http://orders.invalid/orders/2", "http://orders.invalid/orders/3"]
    assert calls[0]["params"] == {} and calls[1]["headers"] == {"X-Row": "3"}
    assert calls[1]["json"] == {"quantity": "3"}
    assert vars(interface) == original and len(reports) == 1


def test_legacy_cases_still_follow_interface_defaults(runner):
    interface, case, calls, _ = runner
    case.datasets = None
    interface.path_params = {"id": 6}
    assert execution.run_case(None, 11, 1, 23)["passed"] is True
    assert calls[0]["url"].endswith("/orders/6")


def test_scenario_uses_each_cases_overrides_and_shares_extracted_variables(runner, monkeypatch):
    interface, base, calls, _ = runner
    first = SimpleNamespace(**vars(base), request_overrides={"path_params": {"id": "2"}, "headers": {"X-Step": "first"}})
    first.extract_rules = {"created_id": "$.id"}
    second = SimpleNamespace(**vars(base), request_overrides={"path_params": {"id": "${created_id}"}, "headers": {"X-Step": "second"}, "body": None})
    monkeypatch.setattr(execution.case_repo, "db_get", lambda db, key, pid: {11:first, 12:second}[key])
    outputs = execution.run_chain(None, [11,12], 1, 23)
    assert all(row["passed"] for row in outputs)
    assert [row["url"] for row in calls] == ["http://orders.invalid/orders/2", "http://orders.invalid/orders/1"]
    assert [row["headers"]["X-Step"] for row in calls] == ["first", "second"]
    assert interface.headers is None


def test_debug_can_override_all_request_fields_but_does_not_save_them(runner):
    interface, _, calls, reports = runner
    before = deepcopy(vars(interface))
    result = execution.run_interface(None, 7, 1, 23, request_overrides={"path_params": {"id": 8},
                                     "params": {"q": "${order_id}"}, "headers": {}, "body": None})
    assert result["passed"] and calls[0]["url"].endswith("/orders/8")
    assert calls[0]["params"] == {"q": "1"} and calls[0]["headers"] == {} and calls[0]["json"] is None
    assert vars(interface) == before and reports == []


def test_case_override_secrets_are_redacted_but_sent_unchanged(runner):
    _, case, calls, reports = runner
    case.datasets = None
    case.request_overrides = {"headers": {"Authorization": "Bearer synthetic-override-token"}, "body": {"password": "synthetic-case-password"}}
    result = execution.run_case(None, 11, 1, 23)
    assert result["passed"] and calls[0]["headers"]["Authorization"] == "Bearer synthetic-override-token"
    assert calls[0]["json"]["password"] == "synthetic-case-password"
    assert "synthetic-override-token" not in json.dumps(reports)


def test_case_request_migration_is_additive_and_repeatable():
    bind = create_engine("sqlite://")
    with bind.begin() as conn:
        conn.execute(text("CREATE TABLE test_case (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO test_case VALUES (1,'old')"))
    ensure_case_request_overrides_schema(bind)
    ensure_case_request_overrides_schema(bind)
    assert next(c for c in inspect(bind).get_columns("test_case") if c["name"] == "request_overrides")["nullable"]
    with bind.connect() as conn:
        assert tuple(conn.execute(text("SELECT name,request_overrides FROM test_case")).one()) == ("old",None)
    bind.dispose()


def test_case_api_roundtrips_independent_values_and_filters_within_project(monkeypatch):
    bind=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Interface.__table__.create(bind)
    Case.__table__.create(bind)
    with Session(bind) as db:
        db.add_all([Interface(id=key,project_id=pid,name="order",method="GET",url="/orders/{id}",
                             path_params={"id":"1"},headers={"X-Base":"default"},body={"a":1}) for key,pid in [(1,10),(2,10),(3,99)]])
        db.add(Case(id=99,project_id=99,name="foreign",interface_id=3,expected_status=200))
        db.commit()
    app=FastAPI()
    app.include_router(case_router.router)
    app.include_router(interface_router.router)
    def database():
        with Session(bind) as db: yield db
    app.dependency_overrides[get_db]=database
    for router in [case_router.router,interface_router.router]:
        for route in router.routes:
            for dep in route.dependant.dependencies:
                if dep.name=='context':app.dependency_overrides[dep.call]=lambda:SimpleNamespace(project_id=10)
    calls=[]
    monkeypatch.setattr(execution,'_env_context',lambda *args:{'base_url':'http://orders.invalid'})
    monkeypatch.setattr(execution.report_repo,'db_create',lambda *args,**kw:None)
    def send(interface,**kw):
        calls.append(kw)
        response=requests.Response()
        response.status_code=400 if kw['url'].endswith('/abc') else 200
        response._content=b'{"id":1}'
        return response
    monkeypatch.setattr(execution,'_request',send)
    with TestClient(app) as client:
        payload={'name':'valid','interface_id':1,'expected_status':200,'request_overrides':{'path_params':{'id':'1'},'body':None}}
        first=client.post('/cases',json=payload)
        assert first.status_code==201
        first=first.json()['data']
        second=client.post('/cases',json={**payload,'name':'invalid id','expected_status':400,'request_overrides':{'path_params':{'id':'abc'}}}).json()['data']
        client.post('/cases',json={**payload,'interface_id':2,'name':'other interface'})
        listed=client.get('/cases?interface_id=1').json()['data']
        assert {row['id'] for row in listed}=={first['id'],second['id']}
        assert len(client.get('/cases').json()['data'])==3
        assert client.get('/cases?interface_id=3').json()['data']==[]
        assert client.post('/cases',json={**payload,'interface_id':3}).status_code==400
        for saved in [first,second]:
            assert client.post(f"/cases/{saved['id']}/run").json()['data']['passed'] is True
        assert calls[0]['url'].endswith('/1') and calls[0]['json'] is None
        assert calls[1]['url'].endswith('/abc') and calls[1]['json']=={'a':1}
        assert client.get('/interfaces/1').json()['data']['path_params']=={'id':'1'}
        update=client.put(f"/cases/{first['id']}",json={**payload,'request_overrides':{'body':None}})
        assert update.json()['data']['request_overrides']=={'body':None}
        assert client.post('/cases',json={**payload,'request_overrides':{'url':'/evil'}}).status_code==422
        assert client.get('/cases?interface_id=0').status_code==400
        debug=client.post('/interfaces/1/run',json={'request_overrides':{'path_params':{'id':'2'},'params':{'q':'one'},'body':None}})
        assert debug.json()['data']['passed'] is True and calls[-1]['params']=={'q':'one'}
    bind.dispose()
