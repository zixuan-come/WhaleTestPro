"""Circuit health belongs to one interface and target, not every environment."""
from types import SimpleNamespace

import pytest
import requests

from app.core import circuit_breaker
from app.core.circuit_breaker import CircuitBreakerOpen, target_breaker_key
from app.services import execution


@pytest.fixture(autouse=True)
def isolated_breakers(monkeypatch):
    monkeypatch.setattr(circuit_breaker, "_breakers", {})


def result(status):
    return SimpleNamespace(status_code=status)


def test_target_key_normalizes_default_port_and_excludes_request_secrets():
    assert target_breaker_key(1, "HTTP://Example.COM/orders") == target_breaker_key(1, "http://example.com:80/other")
    assert target_breaker_key(1, "https://example.com") == target_breaker_key(1, "https://example.com:443/")
    key = target_breaker_key(1, "https://synthetic-user:synthetic-password@example.com:8443/orders/secret-id?token=secret-query")
    assert key == (1, "https", "example.com", 8443)
    assert "synthetic" not in repr(key) and "secret" not in repr(key)


@pytest.mark.parametrize("target", ["http://healthy.invalid/orders", "http://broken.invalid:8080/orders",
                                    "https://broken.invalid/orders"])
def test_failed_environment_does_not_block_a_different_target(monkeypatch, target):
    calls = []
    def send(method, url, **kwargs):
        calls.append(url)
        return result(200 if url == target else 503)
    monkeypatch.setattr(execution.requests, "request", send)
    interface = SimpleNamespace(id=101, method="GET")
    for _ in range(5):
        execution._request(interface, url="http://broken.invalid/orders")
    assert execution._request(interface, url=target).status_code == 200
    assert calls[-1] == target


def test_same_target_still_trips_without_query_or_path_changing_its_health(monkeypatch):
    calls = []
    monkeypatch.setattr(execution.requests, "request", lambda **kw: calls.append(kw) or result(503))
    interface = SimpleNamespace(id=101, method="GET")
    for _ in range(5):
        execution._request(interface, url="http://broken.invalid/orders")
    with pytest.raises(CircuitBreakerOpen):
        execution._request(interface, url="http://BROKEN.invalid:80/other?token=synthetic")
    assert len(calls) == 5
    assert execution._request(SimpleNamespace(id=102, method="GET"), url="http://broken.invalid/orders").status_code == 503


@pytest.mark.parametrize("error", [requests.ConnectionError, requests.Timeout,
                                   requests.exceptions.ChunkedEncodingError])
def test_network_failures_still_open_the_matching_target_breaker(monkeypatch, error):
    calls = []
    def send(**kwargs):
        calls.append(kwargs)
        raise error("synthetic transport failure")
    monkeypatch.setattr(execution.requests, "request", send)
    interface = SimpleNamespace(id=101, method="GET")
    for _ in range(5):
        with pytest.raises(error):
            execution._request(interface, url="http://broken.invalid/orders")
    with pytest.raises(CircuitBreakerOpen):
        execution._request(interface, url="http://broken.invalid/orders")
    assert len(calls) == 5


@pytest.mark.parametrize("error", [requests.exceptions.InvalidURL, requests.exceptions.InvalidHeader,
                                   requests.exceptions.InvalidSchema, requests.exceptions.MissingSchema,
                                   ValueError, TypeError])
def test_request_configuration_errors_do_not_trip_downstream_health(monkeypatch, error):
    def invalid(**kwargs):
        raise error("synthetic configuration error")
    monkeypatch.setattr(execution.requests, "request", invalid)
    interface = SimpleNamespace(id=101, method="GET")
    for _ in range(5):
        with pytest.raises(error):
            execution._request(interface, url="http://healthy.invalid/orders")
    monkeypatch.setattr(execution.requests, "request", lambda **kw: result(200))
    assert execution._request(interface, url="http://healthy.invalid/orders").status_code == 200


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_http_status_does_not_open_the_target_breaker(monkeypatch, status):
    monkeypatch.setattr(execution.requests, "request", lambda **kw: result(status))
    interface = SimpleNamespace(id=101, method="GET")
    for _ in range(6):
        assert execution._request(interface, url="http://healthy.invalid/orders").status_code == status


@pytest.mark.parametrize("url", [None, "/orders", "ftp://example.com/orders", "http://example.com:invalid/orders"])
def test_invalid_target_has_no_shared_fallback_breaker(url):
    assert target_breaker_key(101, url) is None
