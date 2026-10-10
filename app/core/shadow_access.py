"""Short-lived internal replay credentials; never user authentication tokens."""
from datetime import datetime, timedelta, timezone
import hashlib
from urllib.parse import urlsplit

import jwt

from app.core.config import settings

SHADOW_TOKEN_HEADER = "X-Shadow-Authorization"
SHADOW_AUDIENCE = "whale-internal-shadow-replay"


def _signing_key():
    # Separate purpose/key from user JWTs, even though both derive from SECRET_KEY.
    return hashlib.sha256(("shadow-replay:" + settings.SECRET_KEY).encode()).hexdigest()


def shadow_path_allowed(path: str) -> bool:
    # Only the standalone demo business table may use shadow routing. Platform
    # users/teams/projects/schedules must never change identity/database scope.
    return path.rstrip("/") == "/demo/orders"


def is_internal_replay_url(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
            and parsed.port == 8000 and not parsed.username and not parsed.password
            and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment)


def create_shadow_credential(method: str, path: str) -> str:
    if not shadow_path_allowed(path):
        raise ValueError("平台管理接口不允许影子回放")
    now = datetime.now(timezone.utc)
    return jwt.encode({"aud": SHADOW_AUDIENCE, "purpose": "shadow-replay",
                       "method": method.upper(), "path": path,
                       "iat": now, "exp": now + timedelta(seconds=30)},
                      _signing_key(), algorithm="HS256")


def shadow_request_allowed(method: str, path: str, credential: str | None) -> bool:
    if not credential or not shadow_path_allowed(path):
        return False
    try:
        payload = jwt.decode(credential, _signing_key(), algorithms=["HS256"],
                             audience=SHADOW_AUDIENCE,
                             options={"require": ["aud", "exp", "iat", "purpose", "method", "path"]})
    except jwt.PyJWTError:
        return False
    return (payload["purpose"] == "shadow-replay" and payload["method"] == method.upper()
            and payload["path"] == path)
