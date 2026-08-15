from app.core.redis_client import redis_client
from app.core.security import get_token_jti

def add_to_blacklist(token: str, expire_seconds: int):
    if expire_seconds > 0:
        jti = get_token_jti(token)
        key = jti if jti is not None else token
        redis_client.set(f"blacklist:{key}", "1", ex=expire_seconds)


def is_blacklisted(token: str) -> bool:
    jti = get_token_jti(token)
    key = jti if jti is not None else token
    return redis_client.exists(f"blacklist:{key}") == 1






