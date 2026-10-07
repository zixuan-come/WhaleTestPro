"""Exercise the real health handlers without main.py's database bootstrap."""
import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.schemas.response import success_response


COMPONENTS = ("main_database", "shadow_database", "redis", "rabbitmq")


def _health_application(unavailable=()):
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handlers = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"health_live", "health_ready"}
    ]
    assert len(handlers) == 2
    application = FastAPI()
    checked = []

    def check(component):
        checked.append(component)
        return component not in unavailable

    namespace = {
        "app": application,
        "JSONResponse": JSONResponse,
        "success_response": success_response,
        "database_is_ready": check,
        "redis_is_ready": check,
        "celery_broker_is_ready": check,
        "engine": "main_database",
        "engine_shadow": "shadow_database",
        "redis_client": "redis",
        "celery_app": "rabbitmq",
    }
    module = ast.Module(body=handlers, type_ignores=[])
    exec(compile(module, str(source), "exec"), namespace)
    return application, checked


def test_ready_returns_success_when_all_dependencies_are_available():
    application, checked = _health_application()
    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {
        "status": "ready", **{component: "ok" for component in COMPONENTS},
    }
    assert checked == list(COMPONENTS)


@pytest.mark.parametrize("unavailable", [
    (component,) for component in COMPONENTS
] + [COMPONENTS])
def test_ready_returns_503_and_identifies_unavailable_dependencies(unavailable):
    application, checked = _health_application(unavailable)
    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == 503
    assert response.json()["data"] == {
        component: "unavailable" if component in unavailable else "ok"
        for component in COMPONENTS
    }
    assert checked == list(COMPONENTS)


def test_live_does_not_check_external_dependencies():
    application, checked = _health_application(COMPONENTS)
    with TestClient(application) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "alive"}
    assert checked == []
