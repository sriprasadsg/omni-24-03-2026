"""Autonomous Ops never-touch list (Phase 81, plan 81-11, GATE-08 / D-19). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the platform server, its own addresses, its interface subnets (the management
network), the hosts named by PLATFORM_URL / BACKEND_HOST / BACKEND_WS_HOST and every
platform-tenant agent can never be a target of an automatic decision; built-in entries cannot
be removed; a stored entry applies from the very next check; IP matching is strict stdlib
ipaddress parsing (never string comparison);
fails_when=a built-in address, subnet edge or IPv4-mapped form is not protected, the first
address past a subnet is protected, a leading-zero or non-string IP is matched instead of
refused invalid_target, a builtin id can be removed, or a 501st entry is accepted;
no_claim=DNS resolution of host names (none is made), how gate.decide uses the answer
(test_autonomous_ops_gate.py).
"""
import os
import socket
import sys
from collections import namedtuple

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
from autonomous_ops import protected
from pymongo.errors import DuplicateKeyError
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent

_Addr = namedtuple("_Addr", "family address netmask broadcast ptp")
OWN = "192.0.2.17"          # a documentation address standing in for the backend's interface


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in ("PLATFORM_URL", "BACKEND_HOST", "BACKEND_WS_HOST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(psutil, "net_if_addrs", lambda: {
        "eth9": [_Addr(socket.AF_INET, OWN, "255.255.255.240", None, None),
                 _Addr(socket.AF_INET6, "fe80::1%eth9", "ffff:ffff:ffff:ffff::", None, None)]})
    protected.cache_clear()
    yield
    protected.cache_clear()


@pytest_asyncio.fixture
async def db(mongo_db):  # noqa: F811
    await protected.ensure_indexes(mongo_db)
    return mongo_db


async def test_builtins_cover_loopback_link_local_unspecified_multicast_and_own_interfaces(db):
    for ip in ("127.0.0.1", "127.255.255.254", "::1", "169.254.10.10", "fe80::5", "0.0.0.0", "::",
               "224.0.0.251", "ff02::1", OWN):
        assert await protected.check(db, "t1", ip=ip) == "protected_target", ip
    assert await protected.check(db, "t1", ip="203.0.113.7") is None
    ids = {e.id for e in await protected.builtin_entries(db)}
    assert f"builtin:ip:{OWN}" in ids and "builtin:cidr:192.0.2.16/28" in ids


async def test_subnet_boundary_first_and_last_protected_first_outside_is_not(db):
    """Edge GATE-08 boundary: 192.0.2.16/28 spans .16 to .31."""
    assert await protected.check(db, "t1", ip="192.0.2.16") == "protected_target"
    assert await protected.check(db, "t1", ip="192.0.2.31") == "protected_target"
    assert await protected.check(db, "t1", ip="192.0.2.32") is None
    assert await protected.check(db, "t1", ip="192.0.2.15") is None


async def test_ipv4_mapped_form_of_a_protected_address_is_protected(db):
    for ip in ("::ffff:192.0.2.20", "::ffff:127.0.0.1"):
        assert await protected.check(db, "t1", ip=ip) == "protected_target", ip
    assert await protected.check(db, "t1", ip="::ffff:203.0.113.7") is None


@pytest.mark.parametrize("bad", ["010.0.0.1", "1.2.3", "not-an-ip", "", " 192.0.2.1", "192.0.2.1 ",
                                 "0x7f.0.0.1", "192.0.2.0/24", 3232235777, None.__class__, ["1.1.1.1"]])
async def test_unparsable_or_leading_zero_ip_is_invalid_not_string_matched(db, bad):
    """Edge GATE-08 precision: refused invalid_target, even when a string compare would match."""
    assert await protected.check(db, "t1", ip=bad) == "invalid_target"


async def test_env_hosts_are_protected_without_dns(db, monkeypatch):
    monkeypatch.setenv("PLATFORM_URL", "https://203.0.113.50:8443/app")
    monkeypatch.setenv("BACKEND_HOST", "backend.example.test")
    monkeypatch.setenv("BACKEND_WS_HOST", "ws://203.0.113.51:5000")
    protected.cache_clear()
    assert await protected.check(db, "t1", ip="203.0.113.50") == "protected_target"
    assert await protected.check(db, "t1", ip="203.0.113.51") == "protected_target"
    await seed_agent(db, "t1", "n1", hostname="Backend.Example.Test", ip="198.51.100.9")
    agent = await db.agents.find_one({"id": "n1"})
    assert await protected.check(db, "t1", agent=agent) == "protected_target"


async def test_every_platform_tenant_agent_is_protected_by_id_hostname_and_address(db):
    await seed_agent(db, "platform-admin", "pa1", hostname="Omni-Host", ip="198.51.100.20")
    await seed_agent(db, "t1", "x1", hostname="other", ip="198.51.100.21")
    protected.cache_clear()
    assert await protected.check(db, "t1", ip="198.51.100.20") == "protected_target"
    assert await protected.check(db, "t1", agent={"id": "pa1"}) == "protected_target"
    assert await protected.check(db, "t1", agent={"id": "zz", "hostname": "OMNI-host"}) == "protected_target"
    assert await protected.check(db, "t1", agent={"id": "zz", "ipAddress": "198.51.100.20"}) == "protected_target"
    assert await protected.check(db, "t1", agent=await db.agents.find_one({"id": "x1"})) is None


async def test_agent_address_in_the_management_subnet_is_protected(db):
    assert await protected.check(db, "t1", agent={"id": "q", "ipAddress": "192.0.2.30"}) == "protected_target"
    assert await protected.check(db, "t1", agent={"id": "q", "ipAddress": "not recorded"}) is None


async def test_remove_entry_is_false_for_every_builtin_id(db):
    await seed_agent(db, "platform-admin", "pa1", hostname="omni-host", ip="198.51.100.20")
    protected.cache_clear()
    builtin = await protected.builtin_entries(db)
    assert len(builtin) > 10 and all(e.builtin and e.id.startswith("builtin:") for e in builtin)
    for entry in builtin:
        for scope in ("platform", "tenant"):
            assert await protected.remove_entry(db, entry.id, scope=scope, tenant_id="t1") is False
    assert await protected.check(db, "t1", ip="127.0.0.1") == "protected_target"


async def test_a_stored_entry_applies_to_the_next_check_and_stays_in_its_scope(db):
    """Edge GATE-08 concurrency: stored entries are read on every decision."""
    assert await protected.check(db, "t1", ip="203.0.113.7") is None
    tenant_entry = await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="ip",
                                             value="203.0.113.7", note="vendor", actor="admin")
    assert await protected.check(db, "t1", ip="203.0.113.7") == "protected_target"
    assert await protected.check(db, "t2", ip="203.0.113.7") is None
    await protected.add_entry(db, scope="platform", tenant_id=None, kind="cidr", value="198.51.100.0/24")
    assert await protected.check(db, "t2", ip="198.51.100.99") == "protected_target"
    stored = [e.id for e in await protected.list_entries(db, "t1") if not e.builtin]
    assert tenant_entry.id in stored
    assert await protected.remove_entry(db, tenant_entry.id, scope="platform", tenant_id=None) is False
    assert await protected.remove_entry(db, tenant_entry.id, scope="tenant", tenant_id="t1") is True
    assert await protected.check(db, "t1", ip="203.0.113.7") is None
    assert await protected.check(db, "t1", ip="198.51.100.99") == "protected_target"


async def test_stored_agent_and_host_entries_match_agents(db):
    await seed_agent(db, "t1", "a9", hostname="crown-jewel", ip="198.51.100.30")
    agent = await db.agents.find_one({"id": "a9"})
    assert await protected.check(db, "t1", agent=agent) is None
    await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="agent", value="a9")
    assert await protected.check(db, "t1", agent=agent) == "protected_target"
    await protected.add_entry(db, scope="tenant", tenant_id="t2", kind="host", value="Crown-Jewel")
    assert await protected.check(db, "t2", agent=agent) == "protected_target"


async def test_add_entry_validates_dedupes_and_caps_each_scope_at_500(db):
    for kwargs in ({"kind": "ip", "value": "010.1.1.1"}, {"kind": "cidr", "value": "10.0.0.0"},
                   {"kind": "host", "value": "two words"}, {"kind": "agent", "value": ""},
                   {"kind": "mac", "value": "x"}):
        with pytest.raises(ValueError):
            await protected.add_entry(db, scope="platform", tenant_id=None, **kwargs)
    for scope in ("builtin", "other"):
        with pytest.raises(ValueError):
            await protected.add_entry(db, scope=scope, tenant_id="t1", kind="ip", value="203.0.113.1")
    with pytest.raises(ValueError):
        await protected.add_entry(db, scope="tenant", tenant_id=None, kind="ip", value="203.0.113.1")
    first = await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="ip", value="203.0.113.1")
    again = await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="ip", value="203.0.113.1")
    assert first.id == again.id
    await db.autonomy_never_touch.insert_many(
        [{"id": f"NT-{n}", "scope": "tenant", "tenantId": "t1", "kind": "ip", "value": f"10.200.{n // 250}.{n % 250}"}
         for n in range(499)])
    with pytest.raises(ValueError):
        await protected.add_entry(db, scope="tenant", tenant_id="t1", kind="ip", value="203.0.113.250")
    ok = await protected.add_entry(db, scope="tenant", tenant_id="t2", kind="ip", value="203.0.113.250")
    assert ok.tenant_id == "t2"
    with pytest.raises(DuplicateKeyError):
        await db.autonomy_never_touch.insert_one({"id": "NT-dup", "scope": "tenant", "tenantId": "t2",
                                                  "kind": "ip", "value": "203.0.113.250"})
