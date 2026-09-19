import json
from types import SimpleNamespace

import pytest

from app.routers import suite as suite_router
from app.schemas.response import ApiResponse
from app.schemas.suite import SuiteCreate, SuiteOut, SuiteUpdate


DB = object()
CONTEXT = SimpleNamespace(project_id=23)
SUITE_DATA = {
    "id": 7,
    "name": "冒烟套件",
    "description": None,
    "project_id": 23,
    "type": "case",
    "scenario_ids": None,
    "case_ids": [1],
    "tags": None,
    "created_at": "2026-09-18T10:00:00",
    "updated_at": "2026-09-18T10:00:00",
}


def _body(response):
    return json.loads(response.body)


def _assert_success(response, *, data, message, status_code=200):
    assert response.status_code == status_code
    assert _body(response) == {"code": 0, "message": message, "data": data}


@pytest.mark.parametrize(
    ("path", "method", "response_model"),
    [
        ("/suites", "POST", ApiResponse[SuiteOut]),
        ("/suites", "GET", ApiResponse[list[SuiteOut]]),
        ("/suites/{suite_id}", "GET", ApiResponse[SuiteOut]),
        ("/suites/{suite_id}", "PUT", ApiResponse[SuiteOut]),
        ("/suites/{suite_id}", "DELETE", ApiResponse[None]),
        ("/suites/{suite_id}/run", "POST", ApiResponse[dict]),
    ],
)
def test_suite_routes_declare_common_response_model(path, method, response_model):
    route = next(
        item
        for item in suite_router.router.routes
        if item.path == path and method in item.methods
    )

    assert route.response_model == response_model


def test_create_suite_uses_common_response(monkeypatch):
    monkeypatch.setattr(suite_router.suite_service, "s_create", lambda *_: SUITE_DATA)

    response = suite_router.create_suite(
        SuiteCreate(name="冒烟套件", type="case", case_ids=[1]), DB, CONTEXT
    )

    _assert_success(
        response,
        data=SUITE_DATA,
        message="测试套件创建成功",
        status_code=201,
    )


def test_list_suites_uses_common_response(monkeypatch):
    monkeypatch.setattr(
        suite_router.suite_service,
        "s_list",
        lambda db, project_id, skip, limit: [SUITE_DATA],
    )

    response = suite_router.list_suites(0, 100, DB, CONTEXT)

    _assert_success(response, data=[SUITE_DATA], message="查询成功")


def test_get_suite_uses_common_response(monkeypatch):
    monkeypatch.setattr(suite_router.suite_service, "s_get", lambda *_: SUITE_DATA)

    response = suite_router.get_suite(7, DB, CONTEXT)

    _assert_success(response, data=SUITE_DATA, message="查询成功")


def test_update_suite_uses_common_response(monkeypatch):
    monkeypatch.setattr(suite_router.suite_service, "s_update", lambda *_: SUITE_DATA)

    response = suite_router.update_suite(
        7, SuiteUpdate(name="冒烟套件"), DB, CONTEXT
    )

    _assert_success(response, data=SUITE_DATA, message="测试套件更新成功")


def test_delete_suite_uses_common_response(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        suite_router.suite_service,
        "s_delete",
        lambda *args: deleted.append(args) or {"message": "删除成功"},
    )

    response = suite_router.delete_suite(7, DB, CONTEXT)

    assert deleted == [(DB, 7, 23)]
    _assert_success(response, data=None, message="测试套件删除成功")


def test_run_suite_uses_common_response(monkeypatch):
    result = {"suite_id": 7, "total": 1, "passed": 1, "failed": 0}
    monkeypatch.setattr(suite_router.suite_service, "run_suite", lambda *_: result)

    response = suite_router.run_suite(7, 3, DB, CONTEXT)

    _assert_success(response, data=result, message="测试套件执行完成")
