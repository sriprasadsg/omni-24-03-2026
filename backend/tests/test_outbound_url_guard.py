"""
outbound_url_guard — the SSRF guard for user-configured integration URLs.

Covers the pre-request URL check (literal IPs, schemes, DNS answers), the
private-range allowlist (which must never re-open loopback or metadata), and
the connect-time GuardedResolver that defeats DNS rebinding. Hermetic: DNS is
monkeypatched, no network.
"""
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import outbound_url_guard as guard
from outbound_url_guard import GuardedResolver, UnsafeOutboundURL, check_ip, validate_outbound_url


@pytest.fixture(autouse=True)
def _no_allowlist(monkeypatch):
    monkeypatch.delenv("OUTBOUND_PRIVATE_ALLOWLIST", raising=False)


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "::1", "169.254.169.254", "0.0.0.0", "224.0.0.1",
    "::ffff:127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.4", "100.64.0.1", "fd00::1",
])
def test_internal_addresses_blocked(ip):
    with pytest.raises(UnsafeOutboundURL):
        check_ip(ip)


def test_public_address_allowed():
    check_ip("8.8.8.8")
    check_ip("2606:4700:4700::1111")


def test_allowlist_opens_private_range_only(monkeypatch):
    monkeypatch.setenv("OUTBOUND_PRIVATE_ALLOWLIST", "10.20.0.0/16, 169.254.0.0/16, garbage")
    check_ip("10.20.3.4")
    with pytest.raises(UnsafeOutboundURL):
        check_ip("10.21.0.1")
    # Link-local (cloud metadata) and loopback stay blocked even if listed.
    with pytest.raises(UnsafeOutboundURL):
        check_ip("169.254.169.254")
    with pytest.raises(UnsafeOutboundURL):
        check_ip("127.0.0.1")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/api/tags?",
    "http://[::1]:5000/",
    "http://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "http://",
    "",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(UnsafeOutboundURL):
        validate_outbound_url(url)


def _fake_dns(address):
    def getaddrinfo(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]
    return getaddrinfo


def test_hostname_resolving_to_loopback_rejected(monkeypatch):
    monkeypatch.setattr(guard.socket, "getaddrinfo", _fake_dns("127.0.0.1"))
    with pytest.raises(UnsafeOutboundURL):
        validate_outbound_url("https://splunk.attacker.example/")


def test_hostname_resolving_to_public_address_allowed(monkeypatch):
    monkeypatch.setattr(guard.socket, "getaddrinfo", _fake_dns("93.184.216.34"))
    assert validate_outbound_url("https://hec.splunk.example:8088") == "https://hec.splunk.example:8088"


async def test_guarded_resolver_blocks_rebinding_at_connect_time():
    resolver = GuardedResolver()

    async def rebinding(host, port=0, family=socket.AF_INET):
        return [{"hostname": host, "host": "10.0.0.7", "port": port, "family": family, "proto": 0, "flags": 0}]

    resolver._inner.resolve = rebinding
    with pytest.raises(UnsafeOutboundURL):
        await resolver.resolve("hec.splunk.example", 443)
    await resolver.close()


async def test_guarded_resolver_passes_public_answers():
    resolver = GuardedResolver()

    async def public(host, port=0, family=socket.AF_INET):
        return [{"hostname": host, "host": "93.184.216.34", "port": port, "family": family, "proto": 0, "flags": 0}]

    resolver._inner.resolve = public
    results = await resolver.resolve("hec.splunk.example", 443)
    assert results[0]["host"] == "93.184.216.34"
    await resolver.close()
