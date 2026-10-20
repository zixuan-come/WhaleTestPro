import time
from collections.abc import Hashable
from enum import Enum
from urllib.parse import urlsplit


class State(str, Enum):
    CLOSED = "closed"        # 正常，放行
    OPEN = "open"            # 跳闸，快速失败
    HALF_OPEN = "half_open"  # 半开，放试探


class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=10, success_threshold=1):
        self.failure_threshold = failure_threshold  # 连续失败几次→跳闸
        self.recovery_timeout = recovery_timeout    # Open 后冷却几秒→进半开
        self.success_threshold = success_threshold  # 半开时成功几次→恢复
        self.state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = 0.0  # 跳闸的时间戳

    def allow_request(self) -> bool:
        if self.state == State.CLOSED:
            return True
        if self.state == State.OPEN:
            if time.time() - self.opened_at >= self.recovery_timeout:
                self.state = State.HALF_OPEN
                self.success_count = 0
                return True
            return False
        # HALF_OPEN：放试探
        return True

    def record_success(self) -> None:
        if self.state == State.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = State.CLOSED
                self.failure_count = 0
        elif self.state == State.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        if self.state == State.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = State.OPEN
                self.opened_at = time.time()
        elif self.state == State.HALF_OPEN:
            self.state = State.OPEN
            self.opened_at = time.time()


class CircuitBreakerOpen(Exception):
    """熔断器打开，快速失败，不打下游"""
    pass


_breakers: dict[Hashable, CircuitBreaker] = {}


def target_breaker_key(interface_id: int, url: str):
    """Partition by the downstream origin, never credentials or request data."""
    if not isinstance(url, str):
        return None
    try:
        target = urlsplit(url)
        scheme, host = target.scheme.lower(), target.hostname
        port = target.port
    except ValueError:
        return None
    if scheme not in {"http", "https"} or not host:
        return None
    return (interface_id, scheme, host.lower(), port if port is not None else (443 if scheme == "https" else 80))


def get_breaker(interface_id: Hashable) -> CircuitBreaker:
    if interface_id not in _breakers:
        _breakers[interface_id] = CircuitBreaker()
    return _breakers[interface_id]


