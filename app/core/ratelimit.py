from app.core.redis_client import redis_client

def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    count = redis_client.incr(f"ratelimit:{key}")
    if count == 1:
        redis_client.expire(f"ratelimit:{key}", window_seconds)
    return count <= limit










