"""Real services with isolated SQLite and synthetic HTTP; no TestClient needed."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
import requests
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import register_models
from app.models.user import User
from app.models.team import Team
from app.models.project import Project
from app.models.interface import Interface
from app.models.environment import Environment
from app.models.case import Case
from app.models.scenario import Scenario
from app.models.report import TestReport as Report
from app.models.execution_report import ExecutionReport
from app.models.scenario_report import ScenarioReport
from app.core.scenario_steps import case_snapshot, equivalent_case_ids
from app.schemas.scenario import ScenarioCreate
from app.schemas.suite import SuiteCreate
from app.schemas.regression import RegressionSelection
from app.services import execution, scenario, suite, regression


@pytest.fixture
def assets(monkeypatch):
    register_models()
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=1, username="repair-owner", hashed_password="unused")); db.flush()
        db.add(Team(id=1, name="repair-team", owner_id=1)); db.flush()
        db.add(Project(id=1, name="repair-project", team_id=1)); db.flush()
        db.add(Environment(id=1, project_id=1, name="synthetic", base_url="http://repair.invalid",
                           variables={"quantity": 1}))
        db.add(Interface(id=1, project_id=1, name="synthetic API", method="POST", url="/orders",
                         body={"quantity": "${quantity}"})); db.flush()
        db.add_all([Case(id=i, project_id=1, name=f"case-{i}", interface_id=1, expected_status=200)
                    for i in (1, 2)])
        db.commit()
        calls = []
        def send(method, url, **kwargs):
            quantity = int(kwargs["json"]["quantity"]); calls.append(quantity)
            response = requests.Response(); response.status_code = 200 if quantity else 400
            response._content = b'{"id":42}'; response.elapsed = timedelta(0)
            return response
        monkeypatch.setattr(execution.requests, "request", send)
        monkeypatch.setattr(execution, "get_breaker", lambda _: SimpleNamespace(
            allow_request=lambda: True, record_success=lambda: None, record_failure=lambda: None))
        yield db, calls
    engine.dispose()


@pytest.mark.parametrize("field,value", [
    ("datasets", [{"quantity": 1}, {"quantity": 0}]),
    ("setup_sql", ["INSERT INTO items(value) VALUES (1)"]),
    ("teardown_sql", ["DELETE FROM items WHERE value=1"]),
    ("retries", 1),
])
def test_equivalent_chain_cannot_replace_standalone_execution_options(assets, field, value):
    db, _ = assets
    case, interface = db.get(Case, 1), db.get(Interface, 1)
    setattr(case, field, value)
    snapshot = case_snapshot(case, interface)
    assert equivalent_case_ids([snapshot], {1: case}, {1: interface}) == set()


@pytest.mark.parametrize("legacy", [False, True])
def test_suite_and_regression_preview_keep_dataset_failure_in_explicit_case(assets, legacy):
    db, calls = assets
    db.get(Case, 1).datasets = [{"quantity": 1}, {"quantity": 0}]; db.commit()
    if legacy:
        scene = Scenario(name="legacy scene", project_id=1, case_ids=[1]); db.add(scene); db.commit()
    else:
        scene = scenario.s_create(db, ScenarioCreate(name="scene", case_ids=[1]), 1)
    item = suite.s_create(db, SuiteCreate(name="mixed", type="mixed", scenario_ids=[scene.id], case_ids=[1]), 1)
    plan = regression.preview(db, 1, RegressionSelection(mode="suite", ids=[item.id], env_id=1))
    assert plan["ready"] and plan["case_count"] == 1
    result = suite.run_suite(db, item.id, 1, 1)
    assert calls == [1, 1, 0]
    assert result["total"] == 2 and result["passed"] == 1 and result["failed"] == 1
    assert [row["passed"] for row in result["results"][1]["detail"]] == [True, False]


@pytest.mark.parametrize("source", ["case", "scenario"])
def test_source_deleted_during_child_request_keeps_result_and_runs_later_items(assets, monkeypatch, source):
    db, calls = assets
    scene = scenario.s_create(db, ScenarioCreate(name="source scene", case_ids=[1]), 1)
    source_id = 1 if source == "case" else scene.id
    item = suite.s_create(db, SuiteCreate(name="deletion", type="mixed",
        scenario_ids=[scene.id] if source == "scenario" else [], case_ids=[1, 2] if source == "case" else [2]), 1)
    original_send = execution.requests.request
    def send(*args, **kwargs):
        if not calls:
            with Session(db.get_bind()) as competing:
                model = Case if source == "case" else Scenario
                competing.query(model).filter_by(id=source_id).delete(synchronize_session=False)
                competing.commit()
        return original_send(*args, **kwargs)
    monkeypatch.setattr(execution.requests, "request", send)
    result = suite.run_suite(db, item.id, 1, 1)
    assert len(calls) == 2 and result["total"] == result["passed"] == 2 and result["failed"] == 0
    assert result["results"][0]["name"] == ("case-1" if source == "case" else "source scene")
    summary = db.query(Report).filter_by(execution_type="suite").one()
    assert summary.passed and summary.detail["total"] == 2
    assert db.query(ExecutionReport).filter_by(kind="suite").one().status == "completed"
    if source == "scenario":
        assert db.query(ScenarioReport).one().scenario_name == "source scene"


@pytest.mark.parametrize("source", ["case", "scenario"])
def test_unexpected_child_exception_is_a_failure_and_does_not_abort_suite(assets, monkeypatch, source):
    db, _ = assets
    scene = scenario.s_create(db, ScenarioCreate(name="bad scene", case_ids=[1]), 1)
    item = suite.s_create(db, SuiteCreate(name="exception", type="mixed",
        scenario_ids=[scene.id] if source == "scenario" else [], case_ids=[1, 2] if source == "case" else [2]), 1)
    actual = execution.run_case
    def fail_first(*args, **kwargs):
        if args[1] == 1:
            raise RuntimeError("synthetic-private-error")
        return actual(*args, **kwargs)
    def fail_scene(*args, **kwargs):
        raise RuntimeError("synthetic-private-error")
    monkeypatch.setattr(execution, "run_case" if source == "case" else "run_chain",
                        fail_first if source == "case" else fail_scene)
    result = suite.run_suite(db, item.id, 1, 1)
    assert result["total"] == 2 and result["failed"] == result["passed"] == 1
    assert result["results"][0]["error"] == "执行异常（RuntimeError）"
    assert db.query(Report).filter_by(execution_type="suite").one().passed is False
