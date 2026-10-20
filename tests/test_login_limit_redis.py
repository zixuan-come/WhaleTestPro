"""Opt-in only: UUID keys on an explicitly disposable Redis server, never FLUSH."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import redis

from app.core import ratelimit


pytestmark = pytest.mark.skipif(
    os.environ.get('WHALE_REVIEW_DISPOSABLE_REDIS') != '1'
    or not os.environ.get('WHALE_REVIEW_REDIS_URL'),
    reason='Requires an explicitly enabled disposable Redis server',
)


@pytest.fixture
def cache(monkeypatch):
    connection = redis.Redis.from_url(os.environ['WHALE_REVIEW_REDIS_URL'],
                                     socket_timeout=2, socket_connect_timeout=2)
    key = 'review-login-' + uuid4().hex
    monkeypatch.setattr(ratelimit, 'redis_client', connection)
    try:
        assert connection.ping()
        yield connection, key
    finally:
        connection.delete('ratelimit:' + key)
        connection.close()


def test_atomic_counter_keeps_one_window_and_one_shared_limit(cache):
    connection, key = cache
    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(lambda _: ratelimit.check_rate_limit(key, 5, 10), range(20)))
    assert sum(allowed) == 5
    assert int(connection.get('ratelimit:' + key)) == 20
    assert 0 < connection.ttl('ratelimit:' + key) <= 10
    connection.pexpire('ratelimit:' + key, 5000)
    assert ratelimit.check_rate_limit(key, 5, 10) is False
    assert 0 < connection.pttl('ratelimit:' + key) <= 5000


def test_legacy_counter_without_ttl_recovers_after_one_window(cache):
    connection, key = cache
    connection.set('ratelimit:' + key, 7)
    assert connection.ttl('ratelimit:' + key) == -1
    assert ratelimit.check_rate_limit(key, 5, 1) is False
    assert 0 <= connection.ttl('ratelimit:' + key) <= 1
    time.sleep(1.1)
    assert ratelimit.check_rate_limit(key, 5, 1) is True
    assert int(connection.get('ratelimit:' + key)) == 1
