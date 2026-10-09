"""Regression tests for the 2026-10-07 P1 review. No live services or user data."""
import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.celery_app import celery_app  # Registers all models.
from app.database import Base
from app.models.user import User
from app.models.team import Team
from app.models.project import Project
from app.models.environment import Environment
from app.models.perf import PerfTask
from app.models.schedule import Schedule
from app.models.suite import TestSuite as Suite
from app.models.case import Case
from app.models.interface import Interface
from app.models.report import TestReport as Report
from app.schemas.schedule import ScheduleCreate
from app.services import execution, perf, schedule, suite, traffic_replay


class Redis:
    def __init__(self, values=None):
        self.values = dict(values or {})
    def get(self, key):
        return self.values.get(key)
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
    def eval(self, script, count, lock, active, target, lease, run_id=None):
        if self.get(lock) != lease:
            return 0
        if self.get(active) == (run_id or lease):
            self.delete(active)
        self.delete(target, lock)
        return 1


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="p1-owner", hashed_password="fake-secret")
        session.add(user)
        session.flush()
        team = Team(name="p1-team", owner_id=user.id)
        session.add(team)
        session.flush()
        project = Project(name="p1-project", team_id=team.id)
        session.add(project)
        session.flush()
        session.add(Environment(id=1, name="local", base_url="http://tested.invalid", project_id=project.id))
        session.commit()
        yield session
    engine.dispose()


def _perf(db, status="pending", **extra):
    task = PerfTask(name="load", target_host="http://tested.invalid", target_path="/health", users=1,
                    spawn_rate=1, duration=1, project_id=1, status=status, **extra)
    db.add(task)
    db.commit()
    return task


def test_teardown_failure_persists_failed_report(db, monkeypatch):
    interface = Interface(name="api", method="GET", url="/health", project_id=1)
    db.add(interface)
    db.flush()
    case = Case(name="cleanup fails", interface_id=interface.id, project_id=1, expected_status=200,
                teardown_sql=["INSERT INTO missing VALUES (1)"])
    db.add(case)
    db.commit()
    def sql(_db, statements):
        if statements:
            raise RuntimeError("cleanup failed")
    monkeypatch.setattr(execution, "run_sql", sql)
    monkeypatch.setattr(execution, "_request", lambda *args, **kwargs: SimpleNamespace(status_code=200))
    result = execution.run_case(db, case.id, 1, 1)
    assert result["passed"] is False
    assert result["teardown_error"] == "cleanup failed"
    report = db.query(Report).one()
    assert not report.passed
    assert report.detail["teardown_error"] == "cleanup failed"


def test_empty_regression_and_scenario_suite_never_pass(db):
    from app.models.scenario import Scenario
    from app.models.scenario_report import ScenarioReport
    result = execution.run_regression(db, project_id=1)
    assert result["passed"] is False
    assert result["execution_status"] == "no_tests"
    scenario = Scenario(name="empty", case_ids=[], project_id=1)
    db.add(scenario)
    db.flush()
    test_suite = Suite(name="empty suite", type="scenario", scenario_ids=[scenario.id], project_id=1)
    db.add(test_suite)
    db.commit()
    result = suite.run_suite(db, test_suite.id, 1, 1)
    assert result["failed"] == 1
    assert not db.query(ScenarioReport).one().passed
    assert not db.query(Report).one().passed
