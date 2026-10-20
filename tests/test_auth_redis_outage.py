"""Security Redis outages must be unavailable, never authorized or successful."""
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from redis.exceptions import AuthenticationError, ConnectionError, RedisError, TimeoutError

from app.core import authentication, blacklist, ratelimit
from app.core.exception_handlers import http_exception_handler
from app.core.security import create_access_token, get_token_jti
from app.database import get_db
from app.routers.user import router
from app.services import user as user_service


class SecurityCache:
    def __init__(self):
        self.calls = []
        self.failure = {}
        self.keys = set()
        self.count = 0
        self.expiring = False

    def operation(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name in self.failure:
            raise self.failure[name]

    def exists(self, key):
        self.operation("exists", key)
        return int(key in self.keys)

    def set(self, key, value, **kwargs):
        self.operation("set", key, value, **kwargs)
        self.keys.add(key)
        return True

    def incr(self, key):
        self.operation("incr", key)
        self.count += 1
        return self.count

    def expire(self, key, seconds):
        self.operation("expire", key, seconds)
        self.expiring = True
        return True

    def eval(self, script, key_count, key, seconds):
        self.operation("eval", script, key_count, key, seconds)
        count = self.incr(key)
        if not self.expiring:
            self.expire(key, seconds)
        return count


@pytest.fixture
def auth_app(monkeypatch):
    cache = SecurityCache()
    monkeypatch.setattr(blacklist, "redis_client", cache)
    monkeypatch.setattr(ratelimit, "redis_client", cache)
    entered, queries, logins = [], [], []
    owner = SimpleNamespace(id=1)

    def find_user(db, user_id):
        queries.append(user_id)
        return owner if user_id == 1 else None

    def login(db, credentials):
        logins.append(credentials.username)
        return {"access_token": create_access_token(1), "token_type": "bearer"}

    monkeypatch.setattr(authentication.user_repo, "db_get_by_id", find_user)
    monkeypatch.setattr(user_service, "s_login", login)
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.dependency_overrides[get_db] = lambda: None
    app.include_router(router)

    @app.api_route("/protected", methods=["GET", "DELETE"])
    def protected(user=Depends(authentication.get_current_user)):
        entered.append(user.id)
        return {"id": user.id}

    with TestClient(app) as client:
        yield client, cache, entered, queries, logins


def headers(token):
    return {"Authorization": "Bearer " + token}


def assert_unavailable(response, secret):
    assert response.status_code == 503
    assert response.json() == {
        "code": 503, "message": "认证服务暂不可用，请稍后重试", "data": None,
    }
    assert response.headers["Retry-After"] == "5"
    assert secret not in response.text


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("error", [ConnectionError, TimeoutError, AuthenticationError, RedisError])
def test_blacklist_failure_blocks_before_user_lookup_and_business(auth_app, method, error, caplog):
    client, cache, entered, queries, _ = auth_app
    token = create_access_token(1)
    cache.failure["exists"] = error("synthetic-redis-password " + token)
    response = client.request(method, "/protected", headers=headers(token))
    assert_unavailable(response, token)
    assert "synthetic-redis-password" not in response.text + caplog.text
    assert entered == queries == []


@pytest.mark.parametrize("operation", ["incr", "expire"])
def test_login_limit_outage_does_not_issue_token(auth_app, operation):
    client, cache, _, _, logins = auth_app
    cache.failure[operation] = ConnectionError("synthetic-cache-credential")
    response = client.post("/auth/login", json={"username": "synthetic", "password": "valid-password"})
    assert_unavailable(response, "synthetic-cache-credential")
    assert logins == []
    assert "access_token" not in response.text


def test_logout_write_outage_is_not_reported_as_success(auth_app):
    client, cache, _, queries, _ = auth_app
    token = create_access_token(1)
    cache.failure["set"] = TimeoutError("synthetic-cache-credential")
    response = client.post("/auth/logout", headers=headers(token))
    assert_unavailable(response, "synthetic-cache-credential")
    assert queries == [1]  # The blacklist read succeeded before the write failed.
    assert cache.keys == set()
    assert [call[0] for call in cache.calls] == ["exists", "set"]


def test_logout_read_outage_does_not_attempt_write(auth_app):
    client, cache, _, queries, _ = auth_app
    cache.failure["exists"] = ConnectionError("synthetic-cache-credential")
    response = client.post("/auth/logout", headers=headers(create_access_token(1)))
    assert_unavailable(response, "synthetic-cache-credential")
    assert queries == []
    assert [call[0] for call in cache.calls] == ["exists"]


def test_invalid_token_remains_unauthorized_without_redis_access(auth_app):
    client, cache, entered, queries, _ = auth_app
    cache.failure["exists"] = ConnectionError("synthetic-cache-credential")
    response = client.get("/protected", headers=headers("invalid-synthetic-token"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert cache.calls == entered == queries == []


def test_healthy_logout_revokes_only_the_same_jti(auth_app):
    client, cache, _, _, _ = auth_app
    token, another = create_access_token(1), create_access_token(1)
    assert client.get("/protected", headers=headers(token)).status_code == 200
    assert client.post("/auth/logout", headers=headers(token)).status_code == 200
    written = next(call for call in cache.calls if call[0] == "set")
    assert written[1] == ("blacklist:" + get_token_jti(token), "1")
    assert written[2]["ex"] > 0
    assert client.get("/protected", headers=headers(token)).status_code == 401
    assert client.get("/protected", headers=headers(another)).status_code == 200


def test_healthy_limit_keeps_existing_429_semantics(auth_app):
    client, cache, _, _, logins = auth_app
    credentials = {"username": "synthetic", "password": "valid-password"}
    for _ in range(5):
        assert client.post("/auth/login", json=credentials).status_code == 200
    assert client.post("/auth/login", json=credentials).status_code == 429
    assert len(logins) == 5
    assert sum(call[0] == "expire" for call in cache.calls) == 1


def test_existing_counter_without_expiry_is_repaired(auth_app):
    _, cache, _, _, _ = auth_app
    cache.count = 3
    assert ratelimit.check_rate_limit('synthetic-orphan', 5, 60) is True
    assert cache.expiring is True
    assert sum(call[0] == 'eval' for call in cache.calls) == 1


def test_limit_expiry_failure_can_recover_on_next_atomic_attempt(auth_app):
    _, cache, _, _, _ = auth_app
    cache.failure['expire'] = ConnectionError('synthetic-expiry-outage')
    with pytest.raises(HTTPException) as error:
        ratelimit.check_rate_limit('synthetic-recovery', 5, 60)
    assert error.value.status_code == 503 and cache.expiring is False
    cache.failure.clear()
    assert ratelimit.check_rate_limit('synthetic-recovery', 5, 60) is True
    assert cache.expiring is True


def test_missing_user_remains_unauthorized(auth_app):
    client, _, entered, queries, _ = auth_app
    assert client.get("/protected", headers=headers(create_access_token(999))).status_code == 401
    assert entered == [] and queries == [999]


def test_programming_error_is_not_misclassified_as_redis_unavailability(auth_app):
    client, cache, entered, queries, _ = auth_app
    cache.failure["exists"] = ValueError("synthetic-programming-defect")
    with pytest.raises(ValueError, match="synthetic-programming-defect"):
        client.get("/protected", headers=headers(create_access_token(1)))
    assert entered == queries == []
