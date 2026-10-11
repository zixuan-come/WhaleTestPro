"""Response-boundary regressions; no production app startup or database I/O."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exception_handlers import http_exception_handler
from app.database import get_db
from app.models.interface import Interface
# Register ORM relationship targets without importing the production entry point.
from app.models.team import Team  # noqa: F401
from app.models.team_member import TeamMember  # noqa: F401
from app.models.team_invitation import TeamInvitation  # noqa: F401
from app.routers import interface as interface_router


@pytest.fixture
def reference_api(monkeypatch):
    result = {
        "interface": Interface(
            id=7, project_id=23, name="引用查询回归", method="GET", url="/health/live",
            headers={"Accept": "application/json"}, params=None, body=None, category="core",
        ),
        "case_count": 2,
        "cases": [
            {"id": 11, "name": "已执行用例", "scenario_ids": [31], "last_passed": True},
            {"id": 12, "name": "未执行用例", "scenario_ids": [], "last_passed": None},
        ],
    }
    calls = []

    def references(db, interface_id, project_id):
        calls.append((interface_id, project_id))
        return result if interface_id == 7 else None

    monkeypatch.setattr(interface_router.api_service, "s_references", references)
    route = next(item for item in interface_router.router.routes
                 if item.path == "/interfaces/{interface_id}/references")
    context_dependency = next(item.call for item in route.dependant.dependencies
                              if item.name == "context")
    application = FastAPI()
    application.include_router(interface_router.router)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[context_dependency] = lambda: SimpleNamespace(project_id=23)
    with TestClient(application) as client:
        yield client, result, calls


def test_references_serializes_orm_and_filters_internal_fields(reference_api):
    client, _, calls = reference_api
    response = client.get("/interfaces/7/references")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "查询接口引用成功",
        "data": {
            "interface": {
                "id": 7, "name": "引用查询回归",
                "method": "GET", "url": "/health/live",
                "headers": {"Accept": "application/json"},
                "params": None, "body": None, "category": "core",
            },
            "case_count": 2,
            "cases": [
                {"id": 11, "name": "已执行用例", "scenario_ids": [31], "last_passed": True},
                {"id": 12, "name": "未执行用例", "scenario_ids": [], "last_passed": None},
            ],
        },
    }
    assert calls == [(7, 23)]


def test_references_with_no_cases_still_serializes_interface(reference_api):
    client, result, _ = reference_api
    result.update(case_count=0, cases=[])
    response = client.get("/interfaces/7/references")

    assert response.status_code == 200
    assert response.json()["data"]["case_count"] == 0
    assert response.json()["data"]["cases"] == []
    assert response.json()["data"]["interface"]["id"] == 7


def test_references_missing_interface_keeps_404_envelope(reference_api):
    client, _, calls = reference_api
    response = client.get("/interfaces/999/references")

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "接口 id=999 不存在", "data": None}
    assert calls == [(999, 23)]
