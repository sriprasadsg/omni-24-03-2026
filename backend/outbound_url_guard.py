"""Outbound URL guard — blocks SSRF through user-configured integration URLs.

Integration configs (SIEM endpoints, chat webhooks, SOAR connector base URLs)
are attacker-influenced input: before this guard, POST /api/integrations/test
let any logged-in user make the backend POST to loopback services, the cloud
metadata endpoint or the internal network and read back the response.

Two layers, because either alone has a gap:
  1. ``validate_outbound_url`` checks the URL before the request. It is the
     only check that covers literal-IP URLs (aiohttp never calls the resolver
     for those).
  2. ``guarded_session`` installs a resolver that re-checks every address at
     connect time, so a hostname that re-resolves to an internal address
     after validation (DNS rebinding) is still refused.
Callers must also pass ``allow_redirects=False`` so a public endpoint cannot
302 the request onto a literal internal IP.

Loopback, link-local (incl. 169.254.169.254 metadata), multicast, reserved and
unspecified addresses are always blocked. Private ranges (RFC 1918, ULA,
CGNAT) are blocked unless listed in OUTBOUND_PRIVATE_ALLOWLIST — a comma-
separated list of CIDRs for on-prem SIEMs, e.g. "10.20.0.0/16,192.168.5.10/32".
"""

import asyncio
import ipaddress
import os
import socket
from typing import Iterable, List, Union
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


class UnsafeOutboundURL(ValueError):
    """Raised when an outbound URL or its resolved address is not permitted."""


def _private_allowlist() -> List[ipaddress._BaseNetwork]:
    raw = os.getenv("OUTBOUND_PRIVATE_ALLOWLIST", "")
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue  # a malformed entry must never widen the allowlist
    return networks


def check_ip(address: Union[str, _IPAddress]) -> None:
    """Raise UnsafeOutboundURL unless ``address`` is a permitted destination."""
    try:
        ip = ipaddress.ip_address(address) if isinstance(address, str) else address
    except ValueError:
        raise UnsafeOutboundURL("Destination address is not a valid IP")
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 must be judged as 127.0.0.1
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        raise UnsafeOutboundURL("Destination address is not permitted")
    if ip.is_private or not ip.is_global:
        if any(ip in net for net in _private_allowlist()):
            return
        raise UnsafeOutboundURL(
            "Destination is a private address; add it to OUTBOUND_PRIVATE_ALLOWLIST to permit it"
        )


def _check_all(addresses: Iterable[str]) -> None:
    found = False
    for addr in addresses:
        found = True
        check_ip(addr)
    if not found:
        raise UnsafeOutboundURL("Destination host did not resolve")


def _split_host(url: str) -> tuple[str, int]:
    if not isinstance(url, str) or not url.strip():
        raise UnsafeOutboundURL("URL is required")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise UnsafeOutboundURL("Only http and https URLs are permitted")
    host = parts.hostname
    if not host:
        raise UnsafeOutboundURL("URL has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise UnsafeOutboundURL("URL has an invalid port")
    return host, port


def _literal_ip(host: str):
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def validate_outbound_url(url: str) -> str:
    """Synchronously validate ``url`` (resolving DNS); return it unchanged."""
    host, port = _split_host(url)
    literal = _literal_ip(host)
    if literal is not None:
        check_ip(literal)
        return url
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeOutboundURL("Destination host did not resolve")
    _check_all(info[4][0] for info in infos)
    return url


async def avalidate_outbound_url(url: str) -> str:
    """Async variant of validate_outbound_url (DNS lookup off the event loop)."""
    host, port = _split_host(url)
    literal = _literal_ip(host)
    if literal is not None:
        check_ip(literal)
        return url
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeOutboundURL("Destination host did not resolve")
    _check_all(info[4][0] for info in infos)
    return url


class GuardedResolver(AbstractResolver):
    """aiohttp resolver that refuses connections to non-permitted addresses."""

    def __init__(self) -> None:
        self._inner = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> List[ResolveResult]:
        results = await self._inner.resolve(host, port, family)
        _check_all(r["host"] for r in results)
        return results

    async def close(self) -> None:
        await self._inner.close()


def guarded_session(**kwargs) -> aiohttp.ClientSession:
    """ClientSession whose every connection passes through GuardedResolver."""
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=GuardedResolver()), **kwargs)
