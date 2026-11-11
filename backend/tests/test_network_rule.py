"""Phase 88 plan 05: the per-tenant allowed networks (LIC-05).

Value: protects=network entries are parsed and compared with the standard library on the address the
server observed; the first machine teaches the network atomically, a range can only be widened to a /24
(/48) that contains the observed address, and a network is never added twice or past 100 entries;
fails_when=an IPv4-mapped address is not compared as IPv4, the first or last address of a range falls
outside it, a wider or foreign range is accepted, two concurrent first enrollments both teach a network,
or an allow adds a duplicate; no_claim=the enrollment route and the approval (later tests in this file),
the proxy trust (test_proxy_headers.py).
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import network_rules as nr
import pending_agents
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield


# -- pure parsing and comparison ------------------------------------------------------------------

def test_normalize_ip_unwraps_ipv4_mapped_and_refuses_garbage():
    assert str(nr.normalize_ip("203.0.113.7")) == "203.0.113.7"
    assert str(nr.normalize_ip("::ffff:203.0.113.7")) == "203.0.113.7"
    assert str(nr.normalize_ip(" 2001:db8::1 ")) == "2001:db8::1"
    for bad in ("bad", None, "", "   ", 5, "203.0.113.999"):
        assert nr.normalize_ip(bad) is None


def test_network_of_gives_slash_32_and_128_for_an_address_and_normalizes_a_range():
    assert nr.network_of("203.0.113.7") == "203.0.113.7/32"
    assert nr.network_of("::ffff:203.0.113.7") == "203.0.113.7/32"
    assert nr.network_of("2001:db8::1") == "2001:db8::1/128"
    assert nr.network_of("203.0.113.9/29") == "203.0.113.8/29"
    with pytest.raises(nr.EntryError) as err:
        nr.network_of("x" * 200)
    assert len(str(err.value)) < 120


def test_a_range_contains_its_first_and_last_address_and_not_the_next():
    entries = [{"cidr": "203.0.113.8/29"}]
    assert nr.contains(entries, nr.normalize_ip("203.0.113.8"))
    assert nr.contains(entries, nr.normalize_ip("203.0.113.15"))
    assert not nr.contains(entries, nr.normalize_ip("203.0.113.16"))
    assert not nr.contains(entries, nr.normalize_ip("203.0.113.7"))


def test_contains_skips_an_unparsable_entry_and_never_mixes_versions():
    entries = [{"cidr": "garbage"}, {"cidr": None}, {}, {"cidr": "2001:db8::/48"}]
    assert not nr.contains(entries, nr.normalize_ip("203.0.113.7"))
    assert nr.contains(entries, nr.normalize_ip("2001:db8::5"))
    assert nr.contains([{"cidr": "203.0.113.0/24"}], nr.normalize_ip("::ffff:203.0.113.7"))
    assert not nr.contains(entries, None)


def test_validate_widen_accepts_a_24_or_48_around_the_address():
    assert nr.validate_widen("203.0.113.7", "203.0.113.0/24") == "203.0.113.0/24"
    assert nr.validate_widen("203.0.113.7", "203.0.113.4/30") == "203.0.113.4/30"
    assert nr.validate_widen("10.0.0.4", "10.0.0.0/24") == "10.0.0.0/24"  # the address itself is private
    assert nr.validate_widen("2001:db8:1::5", "2001:db8:1::/48") == "2001:db8:1::/48"


@pytest.mark.parametrize("observed,widen", [
    ("203.0.113.7", "203.0.113.0/23"),   # wider than a /24
    ("203.0.113.7", "198.51.100.0/24"),  # does not contain the address
    ("203.0.113.7", "2001:db8::/48"),    # other IP version
    ("203.0.113.7", "10.0.0.0/24"),      # private range for a global address
    ("2001:db8:1::5", "2001:db8::/47"),  # wider than a /48
    ("203.0.113.7", "not-a-range"),
    ("203.0.113.7", ""),
])
def test_validate_widen_refuses_wide_foreign_or_malformed_ranges(observed, widen):
    with pytest.raises(nr.EntryError):
        nr.validate_widen(observed, widen)


# -- stored on the tenant (real MongoDB) ------------------------------------------------------------

async def _networks(db, tenant_id="t1"):
    return (await db.tenants.find_one({"id": tenant_id}, {"allowedNetworks": 1})).get("allowedNetworks") or []


async def test_learn_first_stores_one_slash_32_and_never_a_second(mongo_db):
    await mongo_db.tenants.insert_one({"id": "t1"})
    assert await nr.learn_first(mongo_db, "t1", nr.normalize_ip("203.0.113.7"), "M1") is True
    stored = await _networks(mongo_db)
    assert [(e["cidr"], e["source"], e["hostname"]) for e in stored] == [("203.0.113.7/32", "learned", "M1")]
    assert await nr.learn_first(mongo_db, "t1", nr.normalize_ip("198.51.100.9"), "M2") is False
    assert len(await _networks(mongo_db)) == 1


async def test_two_concurrent_first_enrollments_leave_exactly_one_learned_network(mongo_db):
    await mongo_db.tenants.insert_one({"id": "t1"})
    won = await asyncio.gather(nr.learn_first(mongo_db, "t1", nr.normalize_ip("203.0.113.7"), "A"),
                               nr.learn_first(mongo_db, "t1", nr.normalize_ip("198.51.100.9"), "B"))
    assert sorted(won) == [False, True]
    assert len(await _networks(mongo_db)) == 1


async def test_allow_twice_stores_once_keeps_order_and_stops_at_100(mongo_db):
    await mongo_db.tenants.insert_one({"id": "t1"})
    assert await nr.allow(mongo_db, "t1", "203.0.113.0/24", source="approved", actor="root") is True
    assert await nr.allow(mongo_db, "t1", "198.51.100.9/32", source="approved", actor="root") is True
    assert await nr.allow(mongo_db, "t1", "203.0.113.0/24", source="approved", actor="root") is False
    assert [e["cidr"] for e in await _networks(mongo_db)] == ["203.0.113.0/24", "198.51.100.9/32"]
    assert (await _networks(mongo_db))[0]["addedBy"] == "root"
    await mongo_db.tenants.update_one({"id": "t1"}, {"$set": {"allowedNetworks": [
        {"cidr": f"10.{i // 250}.{i % 250}.0/24", "source": "approved"} for i in range(nr.MAX_NETWORKS)]}})
    assert await nr.allow(mongo_db, "t1", "203.0.113.99/32", source="approved", actor="root") is False
    assert len(await _networks(mongo_db)) == nr.MAX_NETWORKS


# -- enrollment: the first machine teaches the network, a new machine elsewhere waits ------------------

HOME, OTHER = "203.0.113.7", "198.51.100.9"


async def _agent(db, hostname):
    return await db.agents.find_one({"hostname": hostname}, {"_id": 0})


async def test_the_first_machine_teaches_the_network_and_later_machines_from_it_enroll(mongo_db):
    await harness.tenant(mongo_db, "t1")
    code, _ = await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=HOME)
    assert code == 200
    stored = await _networks(mongo_db)
    assert [(e["cidr"], e["source"], e["hostname"]) for e in stored] == [(f"{HOME}/32", "learned", "M1")]
    assert (await _agent(mongo_db, "M1"))["sourceIp"] == HOME
    code, _ = await harness.register(mongo_db, "M3", hardware=harness.hw("S3"), client_ip=HOME)
    assert code == 200


async def test_a_new_machine_from_another_network_waits_and_the_tenant_is_told_why(mongo_db):
    await harness.tenant(mongo_db, "t1")
    assert (await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=HOME))[0] == 200
    code, body = await harness.register(mongo_db, "M2", hardware=harness.hw("S2"), client_ip=OTHER)
    assert code == 202 and body["pendingReason"] == "new_network"
    held = await _agent(mongo_db, "M2")
    assert held["status"] == "Pending" and held["pendingReason"] == "new_network" and held["sourceIp"] == OTHER
    notice = await mongo_db.notifications.find_one({"tenantId": "t1"})
    assert f"new network {OTHER}, waiting for platform approval" in notice["message"]
    assert len(await _networks(mongo_db)) == 1  # a held machine teaches nothing


async def test_an_enrolled_agent_is_never_checked_against_the_networks(mongo_db):
    await harness.tenant(mongo_db, "t1")
    assert (await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=HOME))[0] == 200
    code, _ = await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=OTHER)
    assert code == 200
    assert (await _agent(mongo_db, "M1"))["status"] == "Online"


async def test_an_old_agent_build_sees_the_new_network_text(mongo_db):
    await harness.tenant(mongo_db, "t1")
    await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=HOME)
    code, detail = await harness.register(mongo_db, "M2", hardware=harness.hw("S2"), client_ip=OTHER,
                                          supportsPending=False)
    assert code == 403 and detail.startswith("new_network:")


async def test_the_platform_organization_is_never_held_and_learns_nothing(mongo_db):
    await harness.tenant(mongo_db, "platform-admin")
    for i, ip in enumerate((HOME, OTHER, "192.0.2.1")):
        code, _ = await harness.register(mongo_db, f"P{i}", hardware=harness.hw(f"SP{i}"), client_ip=ip)
        assert code == 200
    assert await _networks(mongo_db, "platform-admin") == []


async def test_a_missing_observed_address_is_held_and_never_learned(mongo_db):
    await harness.tenant(mongo_db, "t1")
    await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=HOME)
    code, body = await harness.register(mongo_db, "M2", hardware=harness.hw("S2"), client_ip=None)
    assert code == 202 and body["pendingReason"] == "new_network"
    await harness.tenant(mongo_db, "t3", key="reg_third0123456789abcdef0")
    code, body = await harness.register(mongo_db, "M9", key="reg_third0123456789abcdef0",
                                        hardware=harness.hw("S9"), client_ip=None)
    assert code == 202 and body["pendingReason"] == "new_network"
    assert await _networks(mongo_db, "t3") == []


async def test_an_ipv4_mapped_observed_address_matches_its_ipv4_network(mongo_db):
    await harness.tenant(mongo_db, "t1")
    await harness.register(mongo_db, "M1", hardware=harness.hw("S1"), client_ip=f"::ffff:{HOME}")
    assert [e["cidr"] for e in await _networks(mongo_db)] == [f"{HOME}/32"]
    assert (await harness.register(mongo_db, "M2", hardware=harness.hw("S2"), client_ip=HOME))[0] == 200


async def test_two_concurrent_first_enrollments_from_different_networks_teach_one(mongo_db):
    await harness.tenant(mongo_db, "t1")
    first, second = await asyncio.gather(
        harness.register(mongo_db, "A", hardware=harness.hw("SA"), client_ip=HOME),
        harness.register(mongo_db, "B", hardware=harness.hw("SB"), client_ip=OTHER))
    assert sorted((first[0], second[0])) == [200, 202]
    assert len(await _networks(mongo_db)) == 1
    held = [first, second][0 if first[0] == 202 else 1][1]
    assert held["pendingReason"] == "new_network"


async def test_two_concurrent_first_enrollments_from_one_network_both_enroll(mongo_db):
    await harness.tenant(mongo_db, "t1")
    results = await asyncio.gather(
        harness.register(mongo_db, "A", hardware=harness.hw("SA"), client_ip=HOME),
        harness.register(mongo_db, "B", hardware=harness.hw("SB"), client_ip=HOME))
    assert [r[0] for r in results] == [200, 200]
    assert len(await _networks(mongo_db)) == 1


def test_the_reason_texts_live_in_one_module_and_name_the_address():
    import hold_reasons
    agent = {"sourceIp": OTHER}
    assert hold_reasons.reason_text("new_network", agent) == (
        f"it enrolled from a new network {OTHER}, waiting for platform approval")
    assert "unknown address" in hold_reasons.reason_text("new_network", {})
    assert hold_reasons.refusal_text("new_network", 5).startswith("new_network:")
    assert hold_reasons.refusal_text("seat_limit", 5).startswith("Agent limit reached (5)")
    assert pending_agents.reason_text("seat_limit") == hold_reasons.reason_text("seat_limit")
