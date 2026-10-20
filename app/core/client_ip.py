"""Resolve forwarded login addresses only for explicitly trusted proxy peers."""
from functools import lru_cache
from ipaddress import ip_address, ip_network
import socket
import time


@lru_cache(maxsize=32)
def _proxy_networks(hosts: str, refresh_bucket: int):
    # Docker may replace the frontend container without restarting the API.
    # Resolve its service name again after a short cache window; DNS failure
    # must ignore forwarding headers rather than broaden the trust boundary.
    networks = []
    for host in hosts.split(','):
        host = host.strip()
        if not host:
            continue
        try:
            networks.append(ip_network(host, strict=False))
            continue
        except ValueError:
            pass
        try:
            addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            continue
        for _, _, _, _, address in addresses:
            try:
                networks.append(ip_network(address[0], strict=False))
            except ValueError:
                continue
    return tuple(networks)


def get_client_ip(request, trusted_proxy_hosts: str = '') -> str:
    peer = request.client.host if request.client else 'unknown'
    if not trusted_proxy_hosts:
        return peer
    try:
        peer_address = ip_address(peer)
    except ValueError:
        return peer
    networks = _proxy_networks(trusted_proxy_hosts, int(time.monotonic() // 5))

    def trusted(address):
        return any(address in network for network in networks)

    if not trusted(peer_address):
        return peer
    forwarded = request.headers.get('x-forwarded-for', '')
    if not forwarded:
        return peer
    try:
        addresses = [ip_address(value.strip()) for value in forwarded.split(',')]
    except ValueError:
        return peer
    # The rightmost untrusted hop is authoritative. A visitor cannot choose
    # their bucket by prepending arbitrary X-Forwarded-For values.
    for address in reversed(addresses):
        if not trusted(address):
            return str(address)
    return str(addresses[0])
