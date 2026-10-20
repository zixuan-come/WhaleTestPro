"""Forwarded login IPs must come from a known immediate proxy."""
import socket
from collections import Counter

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import authentication, client_ip


def request(peer, forwarded=None):
    headers = [] if forwarded is None else [(b'x-forwarded-for', forwarded.encode())]
    return Request({'type': 'http', 'client': (peer, 50000), 'headers': headers})


@pytest.fixture(autouse=True)
def clear_proxy_cache():
    client_ip._proxy_networks.cache_clear()
    yield
    client_ip._proxy_networks.cache_clear()


def dns(address):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 0))]


def test_login_buckets_are_independent_behind_the_frontend(monkeypatch):
    monkeypatch.setattr(authentication.settings, 'TRUSTED_PROXY_HOSTS', 'frontend')
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', lambda *a, **kw: dns('172.19.0.4'))
    counts = Counter()

    def limit(key, limit, window_seconds):
        counts[key] += 1
        return counts[key] <= limit

    monkeypatch.setattr(authentication, 'check_rate_limit', limit)
    for number in range(1, 7):
        authentication.login_rate_limit(request('172.19.0.4', f'203.0.113.{number}'))
    assert len(counts) == 6 and set(counts.values()) == {1}
    for _ in range(4):
        authentication.login_rate_limit(request('172.19.0.4', '203.0.113.1'))
    with pytest.raises(HTTPException) as error:
        authentication.login_rate_limit(request('172.19.0.4', '203.0.113.1'))
    assert error.value.status_code == 429


def test_direct_public_client_cannot_choose_bucket_with_forwarded_header(monkeypatch):
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', lambda *a, **kw: dns('172.19.0.4'))
    assert client_ip.get_client_ip(request('203.0.113.9', '198.51.100.7'), 'frontend') == '203.0.113.9'


def test_visitors_prepended_forwarded_values_are_not_authoritative():
    assert client_ip.get_client_ip(
        request('172.19.0.4', '198.51.100.200, 203.0.113.9'), '172.19.0.4',
    ) == '203.0.113.9'


@pytest.mark.parametrize('forwarded', ['', 'not-an-address', '203.0.113.1,'])
def test_invalid_forwarding_falls_back_to_peer(forwarded):
    assert client_ip.get_client_ip(request('172.19.0.4', forwarded), '172.19.0.4') == '172.19.0.4'


def test_ipv6_proxy_chain():
    assert client_ip.get_client_ip(
        request('fd00::4', '2001:db8::7, fd00::5'), 'fd00::/64',
    ) == '2001:db8::7'


def test_unconfigured_proxy_does_not_resolve_or_trust_headers(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Unconfigured proxies must not cause DNS lookups')
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', forbidden)
    assert client_ip.get_client_ip(request('172.19.0.4', '203.0.113.9')) == '172.19.0.4'


def test_dns_failure_never_trusts_forwarding_headers(monkeypatch):
    def unavailable(*args, **kwargs):
        raise socket.gaierror('synthetic DNS outage')
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', unavailable)
    assert client_ip.get_client_ip(request('172.19.0.4', '203.0.113.9'), 'frontend') == '172.19.0.4'


def test_replaced_frontend_address_is_refreshed(monkeypatch):
    clock = [100.0]
    address = ['172.19.0.4']
    monkeypatch.setattr(client_ip.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(client_ip.socket, 'getaddrinfo', lambda *a, **kw: dns(address[0]))
    assert client_ip.get_client_ip(request(address[0], '203.0.113.9'), 'frontend') == '203.0.113.9'
    address[0] = '172.19.0.8'
    clock[0] += 6
    assert client_ip.get_client_ip(request(address[0], '203.0.113.9'), 'frontend') == '203.0.113.9'
    assert client_ip.get_client_ip(request('172.19.0.4', '203.0.113.9'), 'frontend') == '172.19.0.4'
