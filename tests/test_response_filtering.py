"""Exercise real response models, including nested user information."""
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.models.user import User


def test_real_routes_filter_nested_password_hashes(monkeypatch):
    from app.routers import user, team

    application = FastAPI()
    application.include_router(user.router)
    application.include_router(team.router)
    application.dependency_overrides[get_db] = lambda: None
    application.dependency_overrides[team.get_current_team_member] = lambda: SimpleNamespace(team_id=1)
    application.dependency_overrides[team.get_current_team_admin_or_owner] = lambda: SimpleNamespace(team_id=1)
    account = User(id=1, username="owner", hashed_password="NEVER-RETURN-THIS")
    monkeypatch.setattr(user.user_service, "s_register", lambda *_: account)
    membership = SimpleNamespace(id=1, team_id=1, user_id=1, role="member", created_at=datetime.now(), user=account)
    monkeypatch.setattr(team.team_service, "s_list_members", lambda *_: [membership])
    monkeypatch.setattr(team.team_service, "s_candidates", lambda *_: [account])
    with TestClient(application) as client:
        registered = client.post("/auth/register", json={"username": "owner", "password": "abcd"})
        assert registered.status_code == 201
        members = client.get("/teams/1/members")
        candidates = client.get("/teams/1/member-candidates?keyword=ow")
        assert members.status_code == candidates.status_code == 200
        for response in (registered, members, candidates):
            assert "hashed_password" not in response.text
            assert "NEVER-RETURN-THIS" not in response.text
