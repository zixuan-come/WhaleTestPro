from contextlib import contextmanager

import redis
from fastapi import HTTPException
from app.core.config import settings

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    socket_timeout=1,
)


@contextmanager
def security_redis_operation():
    """Fail closed when a security check/write cannot reach Redis."""
    try:
        yield
    except redis.RedisError:
        # Never expose driver errors (which may contain connection credentials),
        # skip revocation checks, or claim a failed blacklist write succeeded.
        raise HTTPException(
            status_code=503,
            detail="认证服务暂不可用，请稍后重试",
            headers={"Retry-After": "5"},
        ) from None





