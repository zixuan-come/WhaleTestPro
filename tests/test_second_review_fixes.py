"""Second-review regressions, using isolated databases and no live broker."""
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database
from app.core import authentication
from app.core.security import create_access_token
from app.core.shadow_ctx import set_shadow
from app.models.project import Project
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.user import User


@pytest.fixture
def platform(monkeypatch):
    engines = [create_engine("sqlite://", connect_args={"check_same_thread": False},
                             poolclass=StaticPool) for _ in range(2)]
    monkeypatch.setattr(database, "engine", engines[0])
    monkeypatch.setattr(database, "engine_shadow", engines[1])
    set_shadow(False)
    source = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("isolated_review_main", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(authentication, "is_blacklisted", lambda _: False)
    captured = []
    async def publish(_task, payload):
        captured.append(payload)
    monkeypatch.setattr(module, "publish_recording", publish)
    for index, engine in enumerate(engines):
        with Session(engine) as db:
            db.add(User(id=1, username=f"owner-{index}", hashed_password="fake"))
            db.flush()
            db.add(Team(id=1, name=f"team-{index}", owner_id=1))
            db.flush()
            db.add(TeamMember(team_id=1, user_id=1, role="owner"))
            db.add(Project(id=1, name=f"project-{index}", team_id=1))
            if index == 0:
                db.add(User(id=2, username="private-owner", hashed_password="fake"))
                db.flush()
                db.add(Team(id=2, name="private-team", owner_id=2))
                db.flush()
                db.add(TeamMember(team_id=2, user_id=2, role="owner"))
            db.commit()
    with TestClient(module.app) as client:
        yield client, engines, captured
    set_shadow(False)
    for engine in engines:
        engine.dispose()


def headers(user_id=1, **extra):
    return {"Authorization": f"Bearer {create_access_token(user_id)}", **extra}


def test_untrusted_shadow_header_cannot_change_identity(platform):
    client, _, _ = platform
    ordinary = client.get("/teams", headers=headers())
    assert ordinary.json()["data"][0]["name"] == "team-0"
    forged = client.get("/teams", headers=headers(**{"X-Shadow": "1"}))
    assert forged.status_code == 403
    assert "team-1" not in forged.text


def test_untrusted_shadow_registration_is_rejected(platform):
    client, engines, _ = platform
    response = client.post("/auth/register", headers={"X-Shadow": "1"},
                           json={"username": "new-user", "password": "abcd"})
    assert response.status_code == 403
    with Session(engines[1]) as db:
        assert db.query(User).count() == 1


def test_private_team_response_never_enters_other_projects_recording(platform):
    client, _, captured = platform
    response = client.get("/teams", headers=headers(2, **{"X-Project-Id": "1"}))
    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "private-team"
    assert captured == []


def test_project_recording_uses_authorized_context(platform):
    client, _, captured = platform
    response = client.get("/interfaces", headers=headers(**{"X-Project-Id": "1"}))
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["project_id"] == 1
    assert captured[0]["request_headers"]["authorization"] == "***"
    captured.clear()
    denied = client.get("/interfaces", headers=headers(2, **{"X-Project-Id": "1"}))
    assert denied.status_code == 404
    assert captured == []


def test_demo_without_project_context_is_not_assigned_to_project_one(platform):
    client, _, captured = platform
    assert client.get("/demo/orders").status_code == 200
    assert captured == []


def test_recording_masks_nested_arrays_and_response_secrets():
    from app.tasks.traffic import _mask
    data = [{"hashed_password": "hash", "rows": [{"access_token": "secret", "id": 1}]}]
    assert _mask(data) == [{"hashed_password": "***", "rows": [{"access_token": "***", "id": 1}]}]
    assert data[0]["hashed_password"] == "hash"


def test_internal_shadow_replay_writes_only_demo_shadow_table(platform):
    from app.core.shadow_access import SHADOW_TOKEN_HEADER, create_shadow_credential
    from app.models.demo_order import DemoOrder
    client, engines, captured = platform
    path = "/demo/orders"
    credential = create_shadow_credential("POST", path)
    response = client.post(path, json={"item": "shadow-only"}, headers={
        "X-Shadow": "1", SHADOW_TOKEN_HEADER: credential,
    })
    assert response.status_code == 201
    with Session(engines[0]) as db:
        assert db.query(DemoOrder).count() == 0
    with Session(engines[1]) as db:
        assert db.query(DemoOrder).one().item == "shadow-only"
    assert captured == []
    assert client.get("/teams", headers=headers()).json()["data"][0]["name"] == "team-0"


def test_shadow_credentials_cannot_be_reused_for_platform_or_other_methods(platform):
    from app.core.shadow_access import SHADOW_TOKEN_HEADER, create_shadow_credential
    client, _, _ = platform
    credential = create_shadow_credential("GET", "/demo/orders")
    forged_headers = {"X-Shadow": "1", SHADOW_TOKEN_HEADER: credential}
    assert client.get("/teams", headers={**headers(), **forged_headers}).status_code == 403
    assert client.post("/demo/orders", headers=forged_headers, json={"item": "bad"}).status_code == 403
    assert client.get("/demo/orders", headers={"X-Shadow": "1", SHADOW_TOKEN_HEADER: create_access_token(1)}).status_code == 403


def test_expired_shadow_credentials_are_rejected(platform, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core import shadow_access
    client, _, _ = platform
    old = datetime.now(timezone.utc) - timedelta(minutes=1)
    credential = jwt.encode({"aud": shadow_access.SHADOW_AUDIENCE, "purpose": "shadow-replay",
                             "method": "GET", "path": "/demo/orders", "iat": old,
                             "exp": old + timedelta(seconds=30)}, shadow_access._signing_key(), algorithm="HS256")
    assert client.get("/demo/orders", headers={"X-Shadow": "1", shadow_access.SHADOW_TOKEN_HEADER: credential}).status_code == 403


def test_external_replay_never_receives_internal_credential(monkeypatch):
    from types import SimpleNamespace
    from app.core.shadow_access import SHADOW_TOKEN_HEADER
    from app.services import traffic_replay
    record = SimpleNamespace(id=1, method="GET", path="/items", request_body=None,
                             response_status=200, response_body={})
    monkeypatch.setattr(traffic_replay.traffic_record_repo, "db_get", lambda *_: record)
    monkeypatch.setattr(traffic_replay, "_base_url", lambda *_: "https://external.invalid")
    calls = []
    monkeypatch.setattr(traffic_replay.requests, "request", lambda **kw: calls.append(kw) or
                        SimpleNamespace(status_code=200, json=lambda: {}))
    traffic_replay.s_replay(None, 1, 1)
    assert SHADOW_TOKEN_HEADER not in calls[0]["headers"]


def test_recording_masks_response_before_publication(platform):
    from app.models.mock import Mock
    client, engines, captured = platform
    with Session(engines[0]) as db:
        db.add(Mock(name="private response", method="GET", path="/secrets", status=200,
                    project_id=1, body={"rows": [{"access_token": "never-enqueue"}]}))
        db.commit()
    response = client.get("/mock/1/secrets", headers={"X-Project-Id": "2"})
    assert response.status_code == 200
    assert captured[0]["project_id"] == 1
    assert captured[0]["response_body"] == {"rows": [{"access_token": "***"}]}


def test_historical_misassigned_team_record_is_hidden_without_deleting_data(platform):
    from app.models.traffic_record import TrafficRecord
    client, engines, _ = platform
    with Session(engines[0]) as db:
        record = TrafficRecord(method="GET", path="/teams", project_id=1,
                               response_body={"private": "other team's information"})
        db.add(record)
        db.commit()
        record_id = record.id
    scoped = headers(**{"X-Project-Id": "1"})
    assert client.get("/traffic/records", headers=scoped).json()["data"] == []
    assert client.get(f"/traffic/records/{record_id}", headers=scoped).status_code == 404
    assert client.post(f"/traffic/replay/{record_id}", headers=scoped, json={}).status_code == 404
    with Session(engines[0]) as db:
        assert db.get(TrafficRecord, record_id) is not None


def test_queued_unsafe_team_record_is_discarded_before_database_access(monkeypatch):
    from app.tasks import traffic
    def forbidden():
        raise AssertionError("unsafe queued record must not open a database")
    monkeypatch.setattr(traffic, "SessionLocal", forbidden)
    traffic.record_traffic.run({"path": "/teams", "project_id": 1})
