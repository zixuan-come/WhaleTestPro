"""Real report routes and execution services, isolated SQLite and HTTP target."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.user import User
from app.models.team import Team
import app.models.team_invitation
import app.models.team_permission
from app.models.project import Project
from app.models.environment import Environment
from app.models.interface import Interface
from app.models.case import Case
from app.models.scenario import Scenario
from app.models.suite import TestSuite as Suite
from app.models.report import TestReport as Report
from app.models.scenario_report import ScenarioReport
from app.models.execution_report import ExecutionReport
from app.routers import report, case, scenario, suite, regression, schedule
from app.services import execution
from app.core.execution_context import current_execution, triggered_by
from app.core.migrations import ensure_execution_report_schema


@pytest.fixture
def reports(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.execute(text("PRAGMA foreign_keys=ON"))
    db.add(User(id=1, username="report-owner", hashed_password="unused"))
    db.flush()
    db.add(Team(id=1, name="report-team", owner_id=1))
    db.flush()
    db.add_all([Project(id=i, name=f"project{i}", team_id=1) for i in (1, 2)])
    db.flush()
    db.add(Environment(id=1, project_id=1, name="测试环境", base_url="http://runner.invalid",
                       variables={"api_token": "private-fixture-token"}))
    db.add(Interface(id=1, project_id=1, name="接口", method="GET", url="/health/live",
                     headers={"Authorization": "Bearer ${api_token}"}))
    db.flush()
    db.add_all([Case(id=i, project_id=1, interface_id=1, name=f"用例{i}",
                     expected_status=201 if i == 2 else 200, retries=0) for i in (1, 2, 3)])
    db.add(Scenario(id=1, project_id=1, name="下单场景", case_ids=[1, 2]))
    db.add(Suite(id=1, project_id=1, name="每日冒烟", type="mixed", scenario_ids=[1], case_ids=[1, 3]))
    db.commit()
    app = FastAPI()
    for module in (report, case, scenario, suite, regression, schedule):
        app.include_router(module.router)
        for route in module.router.routes:
            for dependency in route.dependant.dependencies:
                if dependency.name == "context":
                    app.dependency_overrides[dependency.call] = lambda: SimpleNamespace(project_id=1)
    app.dependency_overrides[get_db] = lambda: db
    calls = []

    def downstream(method, url, **kwargs):
        assert url == "http://runner.invalid/health/live"
        calls.append(kwargs)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"data":{"id":1},"token":"private-response-token"}'
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(execution.requests, "request", downstream)
    monkeypatch.setattr(execution, "get_breaker", lambda _: SimpleNamespace(
        allow_request=lambda: True, record_success=lambda: None, record_failure=lambda: None))
    try:
        with TestClient(app) as client:
            yield client, db, calls
    finally:
        db.close()
        engine.dispose()


def data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def listing(client, kind, **params):
    return data(client.get("/reports/executions", params={"kind": kind, **params}))


def test_case_snapshot_evidence_and_deleted_source(reports):
    client, db, calls = reports
    result = data(client.post("/cases/1/run?env_id=1"))
    assert result["passed"] is True
    assert result["response_detail"]["body"]["data"] == {"id": 1}
    assert result["response_detail"]["headers"]["Content-Type"] == "application/json"
    assert result["request_detail"]["url"] == "http://runner.invalid/health/live"
    assert result["duration_ms"] >= 0
    assert "private-fixture-token" not in str(result)
    assert "private-response-token" not in str(result)
    page = listing(client, "case")
    assert page["total"] == page["passed_count"] == 1
    item = page["items"][0]
    assert item["name"] == "用例1" and item["environment_name"] == "测试环境"
    detail = data(client.get(f"/reports/executions/{item['id']}"))
    attempt = detail["detail"]["attempts"][0]
    assert calls[0]["headers"]["Authorization"] == "Bearer private-fixture-token"
    assert "private-fixture-token" not in str(detail)
    assert "private-response-token" not in str(detail)
    assert attempt["response_detail"]["status_code"] == 200
    assert db.query(Report).one().execution_report_id == int(item["id"].split("-")[1])
    db.delete(db.get(Case, 1))
    db.commit()
    assert listing(client, "case")["items"][0]["name"] == "用例1"
    assert current_execution.get() is None


@pytest.mark.parametrize("content,content_type,body", [
    (b'{"id":42,"quantity":1}', "application/json", {"id": 42, "quantity": 1}),
    (b'[]', "application/json", []),
    (b'false', "application/json", False),
    (b'0', "application/json", 0),
    (b'null', "application/json", None),
    (b'created', "text/plain", "created"),
    (b'', "text/plain", None),
])
def test_case_immediate_response_keeps_body_even_when_status_assertion_fails(reports, monkeypatch, content, content_type, body):
    client, _, calls = reports
    def downstream(*args, **kwargs):
        calls.append(kwargs)
        response = requests.Response()
        response.status_code = 201
        response._content = content
        response.headers['Content-Type'] = content_type
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    result = data(client.post('/cases/1/run?env_id=1'))
    assert not result['passed']  # Expected 200; still inspect the actual creation response.
    assert result['response_detail']['body'] == body
    assert result['response_detail']['status_code'] == result['actual_status'] == 201
    assert len(calls) == 1


def test_case_data_groups_keep_their_own_last_retry_response(reports, monkeypatch):
    client, db, calls = reports
    test_case = db.get(Case, 1)
    test_case.datasets = [{'group': 'first'}, {'group': 'second'}]
    test_case.retries = 1
    db.commit()
    def downstream(*args, **kwargs):
        calls.append(kwargs)
        response = requests.Response()
        response.status_code = 500 if len(calls) == 1 else 200
        response._content = ('{"request":%d}' % len(calls)).encode()
        response.headers['Content-Type'] = 'application/json'
        return response
    monkeypatch.setattr(execution.requests, 'request', downstream)
    results = data(client.post('/cases/1/run?env_id=1'))
    assert [row['response_detail']['body'] for row in results] == [{'request': 2}, {'request': 3}]
    assert [row['attempts'] for row in results] == [2, 1]


def test_case_without_an_http_response_does_not_fabricate_a_body(reports, monkeypatch):
    client, _, _ = reports
    def timeout(*args, **kwargs):
        raise requests.Timeout('synthetic timeout')
    monkeypatch.setattr(execution.requests, 'request', timeout)
    result = data(client.post('/cases/1/run?env_id=1'))
    assert not result['passed'] and 'timeout' in result['error']
    assert result['response_detail'] is None
    assert result['request_detail']['url'].endswith('/health/live')


def test_suite_has_one_root_and_explicit_child_reports(reports):
    client, db, calls = reports
    result = data(client.post("/suites/1/run?env_id=1"))
    assert result["failed"] == 1 and len(calls) == 3
    page = listing(client, "suite")
    assert page["total"] == page["failed_count"] == 1
    assert listing(client, "case")["total"] == listing(client, "scenario")["total"] == 0
    detail = data(client.get(f"/reports/executions/{page['items'][0]['id']}"))
    assert detail["name"] == "每日冒烟" and detail["passed"] is False
    assert [child["kind"] for child in detail["children"]] == ["scenario", "case"]
    child = data(client.get(f"/reports/executions/{detail['children'][0]['id']}"))
    assert [step["case_name"] for step in child["detail"]["steps"]] == ["用例1", "用例2"]
    assert db.query(ScenarioReport).one().execution_report_id is not None
    # Legacy read contracts are retained for existing clients.
    assert data(client.get("/reports"))["total"] == 2
    assert data(client.get("/reports/scenarios"))["total"] == 1


def test_regression_summary_and_scheduled_trigger_are_persisted(reports):
    client, db, _ = reports
    with triggered_by("scheduled"):
        result = execution.run_regression(db, [1, 2], 1, project_id=1)
    assert result["failed_count"] == 1
    root = listing(client, "regression")["items"][0]
    assert root["trigger_source"] == "scheduled" and root["passed"] is False
    detail = data(client.get(f"/reports/executions/{root['id']}"))
    assert len(detail["children"]) == 2 and detail["detail"]["result"]["total"] == 2
    assert listing(client, "case")["total"] == 0
    data(client.post("/cases/3/run?env_id=1"))
    assert listing(client, "case")["items"][0]["trigger_source"] == "manual"
    assert current_execution.get() is None


def test_standalone_scenario_and_chain_are_grouped(reports):
    client, _, _ = reports
    data(client.post("/scenarios/1/run?env_id=1"))
    data(client.post("/cases/chain?env_id=1", json=[1, 3]))
    page = listing(client, "scenario")
    assert page["total"] == 2 and {row["name"] for row in page["items"]} == {"下单场景", "临时接口链路"}
    assert listing(client, "case")["total"] == 0


def test_missing_selection_is_visible_without_inventing_child_executions(reports):
    client, db, _ = reports
    suite = db.get(Suite, 1)
    suite.scenario_ids, suite.case_ids, suite.tags = [999], [1], []
    db.commit()
    data(client.post("/suites/1/run?env_id=1"))
    root = listing(client, "suite")["items"][0]
    detail = data(client.get(f"/reports/executions/{root['id']}"))
    assert root["passed"] is False
    assert len(detail["children"]) == 1
    assert detail["detail"]["unexecuted_items"] == [
        {"type": "scenario", "id": 999, "name": "场景 #999", "passed": False, "error": "场景不存在"},
    ]


def test_execution_exception_records_failure_and_restores_context(reports, monkeypatch):
    client, db, _ = reports
    monkeypatch.setattr(execution, "_env_context", lambda *_: (_ for _ in ()).throw(ValueError("private-fixture-token")))
    with pytest.raises(ValueError):
        execution.run_case(db, 1, 1, 1)
    root = listing(client, "case")["items"][0]
    detail = data(client.get(f"/reports/executions/{root['id']}"))
    assert root["status"] == "error" and root["passed"] is False
    assert detail["detail"]["error"] == "执行异常（ValueError）"
    assert "private-fixture-token" not in str(detail)
    assert current_execution.get() is None


def test_filters_apply_before_pagination_and_use_shanghai_dates(reports):
    client, db, _ = reports
    for index in range(31):
        db.add(ExecutionReport(project_id=1, kind="case", name="needle" if index < 2 else "other",
                               passed=index % 2 == 0, status="completed", trigger_source="manual",
                               created_at=datetime(2026, 10, 17, 12) + timedelta(minutes=index)))
    for project_id, date in ((1, datetime(2026, 10, 17, 15, 59, 59)), (1, datetime(2026, 10, 17, 16)),
                             (1, datetime(2026, 10, 18, 16)), (2, datetime(2026, 10, 17, 16))):
        db.add(ExecutionReport(project_id=project_id, kind="case", name="edge", passed=False,
                               status="completed", trigger_source="manual", created_at=date))
    db.commit()
    page = listing(client, "case", page_size=10)
    assert len(page["items"]) == 10 and page["total"] == 34
    assert listing(client, "case", q="needle")["total"] == 2
    filtered = listing(client, "case", q="needle", status="failed")
    assert filtered["total"] == filtered["failed_count"] == 1 and filtered["pass_rate"] == 0
    dated = listing(client, "case", q="edge", date_from="2026-10-18", date_to="2026-10-18")
    assert dated["total"] == 1
    assert listing(client, "case", q="%")["total"] == 0
    assert listing(client, "case", page=8)["items"] == []


def test_legacy_reports_keep_names_without_inventing_parentage(reports):
    client, db, _ = reports
    db.add_all([Report(case_id=0, project_id=1, passed=True, suite_name="老套件", execution_type="suite", detail={}),
                Report(case_id=999, project_id=1, passed=False, detail={})])
    db.commit()
    suite = listing(client, "suite")["items"][0]
    assert suite["name"] == "老套件" and suite["historical"] is True
    assert suite["trigger_source"] is None and suite["environment_name"] is None
    assert "名称未记录" in listing(client, "case")["items"][0]["name"]
    assert data(client.get(f"/reports/executions/{suite['id']}"))["children"] == []


@pytest.mark.parametrize("params", [{"kind": "invalid"}, {"status": "invalid"}, {"page": 0},
                                       {"q": "x" * 101}, {"date_from": "invalid"}])
def test_invalid_filters_are_rejected(reports, params):
    client, _, _ = reports
    assert client.get("/reports/executions", params=params).status_code == 422


def test_details_are_project_scoped_and_date_range_is_validated(reports):
    client, db, _ = reports
    record = ExecutionReport(project_id=2, kind="case", name="foreign", passed=True,
                             status="completed", trigger_source="manual", created_at=datetime.utcnow())
    db.add(record)
    db.commit()
    for report_id in (f"run-{record.id}", "run-0", "legacy-999", "invalid"):
        assert client.get(f"/reports/executions/{report_id}").status_code == 404
    assert client.get("/reports/executions?date_from=2026-10-19&date_to=2026-10-18").status_code == 400


def test_additive_migration_is_idempotent_and_does_not_backfill():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE project (id INTEGER PRIMARY KEY)"))
        for name in ("test_report", "scenario_report"):
            connection.execute(text(f"CREATE TABLE {name} (id INTEGER PRIMARY KEY)"))
            connection.execute(text(f"INSERT INTO {name} (id) VALUES (7)"))
    ensure_execution_report_schema(engine)
    ensure_execution_report_schema(engine)
    with engine.connect() as connection:
        for name in ("test_report", "scenario_report"):
            assert connection.execute(text(f"SELECT id, execution_report_id FROM {name}")).all() == [(7, None)]
        assert connection.execute(text("SELECT COUNT(*) FROM execution_report")).scalar_one() == 0
    assert "execution_report" in inspect(engine).get_table_names()
    engine.dispose()
