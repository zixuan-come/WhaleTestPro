from app.core.redis_client import redis_client

def add_to_blacklist(token: str, expire_seconds: int):
    if expire_seconds > 0:
        redis_client.set(f"blacklist:{token}", "1", ex=expire_seconds)


def is_blacklisted(token: str) -> bool:
    return redis_client.exists(f"blacklist:{token}") == 1






