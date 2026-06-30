import time
from app.core.circuit_breaker import CircuitBreaker, State


def test_trip_open_after_threshold_failures():
    """连续失败到阈值就跳闸：状态变 OPEN 且不再放行"""
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.allow_request() is True
    assert cb.state == State.CLOSED
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow_request() is False

def test_success_resets_failure_count():
    """未到阈值时一次成功会清零失败计数"""
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == State.CLOSED


def test_open_to_half_open_after_cooldown():
    """冷却时间到了，下一次请求放行并进入半开"""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=5)
    cb.record_failure()
    assert cb.state == State.OPEN
    assert cb.allow_request() is False          # 冷却中，快速失败
    cb.opened_at = time.time() - 6              # 模拟冷却已过，不真 sleep
    assert cb.allow_request() is True
    assert cb.state == State.HALF_OPEN


def test_half_open_recovers_after_enough_successes():
    """半开态成功够数 → 恢复 CLOSED"""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=5, success_threshold=2)
    cb.record_failure()
    cb.opened_at = time.time() - 6
    cb.allow_request()                          # 进 HALF_OPEN
    assert cb.state == State.HALF_OPEN
    cb.record_success()                         # 第 1 次（还不够）
    assert cb.state == State.HALF_OPEN
    cb.record_success()                         # 第 2 次，够了
    assert cb.state == State.CLOSED
    assert cb.failure_count == 0


def test_half_open_failure_trips_open_again():
    """半开态再失败 → 立刻退回 OPEN"""
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=5)
    cb.record_failure()
    cb.opened_at = time.time() - 6
    cb.allow_request()                          # 进 HALF_OPEN
    assert cb.state == State.HALF_OPEN
    cb.record_failure()
    assert cb.state == State.OPEN





















