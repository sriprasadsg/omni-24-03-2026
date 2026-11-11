"""Pins the proxy trust the Phase 88 network rule depends on.

Value: protects=the network rule decides on request.client.host only; uvicorn's ProxyHeadersMiddleware
with trusted hosts 127.0.0.1 and ::1 (nginx on the same machine) turns the appended X-Forwarded-For
address into the client and ignores the header from any other peer, so a caller cannot choose the
address the rule sees; fails_when=uvicorn changes the trusted-hosts semantics, or a rule module starts
reading a request header or the agent's own publicIp; no_claim=the production service flags
(--proxy-headers --forwarded-allow-ips, handed to the user in 88-16) and nginx's own configuration.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

BACKEND = os.path.join(os.path.dirname(__file__), "..")


async def _observed(peer, forwarded=None):
    seen = {}

    async def app(scope, receive, send):
        seen["client"] = scope.get("client")

    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1,::1")
    await wrapped({"type": "http", "client": (peer, 40000), "headers": headers}, None, None)
    return seen["client"][0]


async def test_a_local_proxy_without_a_header_leaves_the_peer():
    assert await _observed("127.0.0.1") == "127.0.0.1"


async def test_a_local_proxy_header_is_resolved_to_the_address_nginx_appended():
    # the caller sent "10.9.9.9"; nginx appended the address it really saw
    assert await _observed("127.0.0.1", "10.9.9.9, 203.0.113.50") == "203.0.113.50"


async def test_the_header_from_any_other_peer_is_ignored():
    assert await _observed("198.51.100.4", "10.9.9.9") == "198.51.100.4"


async def test_an_ipv6_loopback_proxy_is_trusted_too():
    assert await _observed("::1", "10.9.9.9, 203.0.113.51") == "203.0.113.51"


def test_the_rule_modules_hold_no_header_name_and_never_the_agents_own_report():
    for name in ("network_rules.py", "license_rules.py"):
        source = open(os.path.join(BACKEND, name), encoding="utf-8").read()
        assert not re.search(r"forwarded|x-real", source, re.IGNORECASE), name
        assert "publicIp" not in source, name
