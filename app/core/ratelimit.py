from app.core.redis_client import redis_client, security_redis_operation


# One atomic operation keeps a transient client/network failure from leaving a
# counter without an expiry. Also repair counters left by older versions.
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def check_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    with security_redis_operation():
        count = redis_client.eval(RATE_LIMIT_SCRIPT, 1, f"ratelimit:{key}", window_seconds)
    return count <= limit










