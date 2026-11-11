"""Phase 88 plan 07: one computer must not hold a licence in two organizations (LIC-06).

Value: protects=a machine live (seen in the last 24 h, holding a seat) in another tenant is found on the raw
collections by normalized serial or SMBIOS UUID and nothing else, a silent or seat-less copy is never a
duplicate, a retired copy loses its seat and its tokens, and no name or id of one organization reaches the
other's ledger, feed or Pending record; fails_when=a MAC alone or an OEM placeholder serial matches across
tenants, a copy seen 30 h ago still blocks, an Inactive copy blocks, a copy in the same tenant blocks, a
retirement writes replacedBy or names the other organization in the old tenant's ledger, or a second
retirement changes anything; no_claim=the approve/reject/heartbeat/restore flow (88-09) and the enrollment
route wiring (later tests in this file).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cross_tenant
import licensing
import pending_agents
import seat_identity
from authentication_service import agent_token_revoked
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NON_SEAT = sorted(licensing.NON_SEAT_STATUSES)
KEY_A, KEY_B = "reg_aaaaaaaaaaaaaaaaaaaa", "reg_bbbbbbbbbbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield


def _ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def _two_tenants(db, seats_used_a=3):
    await harness.tenant(db, "tenant-a", key=KEY_A, name="Alpha Org",
                         license={"maxAgents": 50, "seatsUsed": seats_used_a, "inactiveReclaimDays": 30})
    await harness.tenant(db, "tenant-b", key=KEY_B, name="Beta Org")


async def _agent(db, tenant_id, agent_id, serial=None, uuid=None, status="Online", seen_hours=2.0, hostname=None):
    hardware = {"macAddresses": []}
    if serial:
        hardware["serialNumber"] = serial
    if uuid:
        hardware["smbiosUuid"] = uuid
    doc = {"id": agent_id, "tenantId": tenant_id, "hostname": hostname or f"host-{agent_id}", "status": status,
           "lastSeen": _ago(seen_hours), "hardware": hardware}
    await db.agents.insert_one(dict(doc))
    return doc


def _hw(**raw):
    return seat_identity.normalize_hardware(raw)


# -- the unscoped filter and the pure helpers ------------------------------------------------------

def test_the_other_tenants_filter_takes_serial_and_uuid_and_never_a_mac():
    only_serial = seat_identity.hardware_match_other_tenants_filter({"serialNumber": "ABC123"}, "B", NON_SEAT)
    assert only_serial == {"tenantId": {"$ne": "B"}, "status": {"$nin": NON_SEAT},
                           "$or": [{"hardware.serialNumber": "ABC123"}]}
    both = seat_identity.hardware_match_other_tenants_filter(
        {"serialNumber": "ABC123", "smbiosUuid": "u-1"}, "B", NON_SEAT)
    assert both["$or"] == [{"hardware.serialNumber": "ABC123"}, {"hardware.smbiosUuid": "u-1"}]
    assert seat_identity.hardware_match_other_tenants_filter(
        {"macAddresses": ["aa:bb:cc:dd:ee:ff"]}, "B", NON_SEAT) is None
    assert seat_identity.hardware_match_other_tenants_filter({}, "B", NON_SEAT) is None


def test_seen_within_parses_the_stored_time_and_fails_closed():
    now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    window = timedelta(hours=24)
    assert seat_identity.seen_within({"lastSeen": "2026-11-11T10:00:00+00:00"}, window, now)
    assert seat_identity.seen_within({"lastSeen": "2026-11-11T10:00:00Z"}, window, now)
    assert seat_identity.seen_within({"lastSeen": "2026-11-11T10:00:00"}, window, now)  # naive means UTC
    assert not seat_identity.seen_within({"lastSeen": "2026-11-10T11:59:59+00:00"}, window, now)
    for bad in ({}, {"lastSeen": None}, {"lastSeen": "yesterday"}):
        assert not seat_identity.seen_within(bad, window, now)


# -- finding a machine's copies in other tenants ---------------------------------------------------

async def test_a_live_seat_holder_elsewhere_is_found_after_normalizing_the_serial(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=2)
    owner = await cross_tenant.live_owner(mongo_db, "tenant-b", _hw(serialNumber=" abc123 "))
    assert owner and owner["id"] == "agent-a" and owner["tenantId"] == "tenant-a"


async def test_the_uuid_finds_a_copy_whose_serial_differs(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="OTHER1", uuid="4c4c4544-0042-3510-8051-b8c04f4d4a32")
    owner = await cross_tenant.live_owner(
        mongo_db, "tenant-b", _hw(serialNumber="ABC123", smbiosUuid="4C4C4544-0042-3510-8051-B8C04F4D4A32"))
    assert owner and owner["id"] == "agent-a"


@pytest.mark.parametrize("status,seen_hours,tenant_id", [
    ("Online", 30, "tenant-a"),            # silent for more than 24 h
    ("Inactive", 2, "tenant-a"),           # holds no seat
    ("Uninstalled", 2, "tenant-a"),
    ("Replaced", 2, "tenant-a"),
    ("Pending", 2, "tenant-a"),
    ("Rejected", 2, "tenant-a"),
    ("Online", 2, "tenant-b"),             # the same tenant is not another organization
])
async def test_no_live_owner_for_a_silent_seatless_or_same_tenant_copy(mongo_db, status, seen_hours, tenant_id):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, tenant_id, "agent-x", serial="ABC123", status=status, seen_hours=seen_hours)
    assert await cross_tenant.live_owner(mongo_db, "tenant-b", _hw(serialNumber="ABC123")) is None


async def test_the_most_recently_seen_live_copy_is_the_owner(mongo_db):
    await _two_tenants(mongo_db)
    await harness.tenant(mongo_db, "tenant-c", key="reg_cccccccccccccccccccc")
    await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=10)
    await _agent(mongo_db, "tenant-c", "agent-c", serial="ABC123", seen_hours=1)
    owner = await cross_tenant.live_owner(mongo_db, "tenant-b", _hw(serialNumber="ABC123"))
    assert owner["id"] == "agent-c"


async def test_hardware_without_a_serial_or_uuid_never_matches(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=1)
    mac_only = _hw(macAddresses=["a4:bb:6d:11:22:33"])
    assert await cross_tenant.live_owner(mongo_db, "tenant-b", mac_only) is None
    assert await cross_tenant.live_owner(mongo_db, "tenant-b", _hw()) is None
    assert await cross_tenant.silent_copies(mongo_db, "tenant-b", mac_only) == []
    assert await cross_tenant.hold_detail(mongo_db, "tenant-b", mac_only) is None


async def test_an_oem_placeholder_serial_never_matches_across_tenants(mongo_db):
    await _two_tenants(mongo_db)
    # what a build that skipped normalization would have stored under the placeholder
    await _agent(mongo_db, "tenant-a", "agent-a", serial="TO BE FILLED BY O.E.M.", seen_hours=1)
    placeholder = _hw(serialNumber="To be filled by O.E.M.")
    assert placeholder["serialNumber"] is None
    assert await cross_tenant.live_owner(mongo_db, "tenant-b", placeholder) is None


async def test_silent_copies_are_the_seat_holders_unseen_for_a_day(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-quiet", serial="ABC123", seen_hours=30)
    await _agent(mongo_db, "tenant-a", "agent-gone", serial="ABC123", status="Inactive", seen_hours=90)
    quiet = await cross_tenant.silent_copies(mongo_db, "tenant-b", _hw(serialNumber="ABC123"))
    assert [a["id"] for a in quiet] == ["agent-quiet"]
    await _agent(mongo_db, "tenant-a", "agent-live", serial="LIVE9", seen_hours=2)
    assert await cross_tenant.silent_copies(mongo_db, "tenant-b", _hw(serialNumber="LIVE9")) == []


async def test_hold_detail_names_the_owner_for_the_platform_only(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=1, hostname="alpha-pc")
    detail = await cross_tenant.hold_detail(mongo_db, "tenant-b", _hw(serialNumber="ABC123"))
    assert detail == {"agentId": "agent-a", "tenantId": "tenant-a", "tenantName": "Alpha Org",
                      "hostname": "alpha-pc"}


async def test_the_two_sparse_indexes_serve_the_lookup(mongo_db):
    await _two_tenants(mongo_db)
    await cross_tenant.ensure_indexes(mongo_db)
    await cross_tenant.ensure_indexes(mongo_db)  # idempotent
    info = await mongo_db.agents.index_information()
    assert info["agents_hw_serial_sparse"]["sparse"] is True
    assert info["agents_hw_uuid_sparse"]["sparse"] is True
    flt = seat_identity.hardware_match_other_tenants_filter(
        {"serialNumber": "ABC123", "smbiosUuid": "u-1"}, "tenant-b", NON_SEAT)
    plan = await mongo_db.agents.find(flt).explain()
    assert '"IXSCAN"' in json.dumps(plan, default=str)
    assert '"COLLSCAN"' not in json.dumps(plan, default=str)


# -- retiring a copy -------------------------------------------------------------------------------

def _calls(mock, action):
    return [c for c in mock.await_args_list if c.args[0] == action]


async def test_retiring_a_copy_frees_its_seat_ends_its_tokens_and_keeps_the_names_apart(mongo_db):
    await _two_tenants(mongo_db, seats_used_a=3)
    owner = await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=30, hostname="alpha-pc")
    started = time.time() - 100
    with patch("audit_ledger.event", new=AsyncMock()) as ledger:
        done = await cross_tenant.retire_copy(
            mongo_db, owner, reason="moved_silent", actor="enrollment",
            to_tenant={"id": "tenant-b", "name": "Beta Org"}, to_agent_id="agent-b")
        again = await cross_tenant.retire_copy(
            mongo_db, owner, reason="moved_silent", actor="enrollment",
            to_tenant={"id": "tenant-b", "name": "Beta Org"}, to_agent_id="agent-b")
    assert done is True and again is False
    stored = await mongo_db.agents.find_one({"id": "agent-a"})
    assert stored["status"] == "Replaced" and stored["replacedReason"] == "moved_silent"
    assert stored["movedAt"] and stored["replacedAt"]
    assert "replacedBy" not in stored  # a cross-tenant link would be visible to the old tenant's users
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["seatsUsed"] == 2
    assert await agent_token_revoked(mongo_db, "agent-a", started)

    assert len(_calls(ledger, "agent.moved_out")) == 1 and len(_calls(ledger, "agent.moved")) == 1
    moved_out = _calls(ledger, "agent.moved_out")[0]
    assert moved_out.args[1] == "tenant-a"
    text = repr(moved_out)
    for other in ("Beta", "tenant-b", "agent-b"):
        assert other not in text
    assert moved_out.kwargs["agentId"] == "agent-a" and moved_out.kwargs["reason"] == "moved_silent"
    moved = _calls(ledger, "agent.moved")[0]
    assert moved.args[1] == "platform-admin"
    assert (moved.kwargs["fromTenantName"], moved.kwargs["toTenantName"]) == ("Alpha Org", "Beta Org")
    assert (moved.kwargs["fromTenantId"], moved.kwargs["toTenantId"]) == ("tenant-a", "tenant-b")
    assert moved.kwargs["toAgentId"] == "agent-b"

    notices = await mongo_db.notifications.find({}).to_list(10)
    assert len(notices) == 1 and notices[0]["tenantId"] == "platform-admin"
    assert "audience" not in notices[0]["metadata"]
    assert "Alpha Org" in notices[0]["message"] and "Beta Org" in notices[0]["message"]


async def test_a_copy_that_lost_its_seat_meanwhile_is_not_retired_twice(mongo_db):
    await _two_tenants(mongo_db, seats_used_a=3)
    owner = await _agent(mongo_db, "tenant-a", "agent-a", serial="ABC123", seen_hours=30)
    await mongo_db.agents.update_one({"id": "agent-a"}, {"$set": {"status": "Inactive"}})
    with patch("audit_ledger.event", new=AsyncMock()) as ledger:
        assert await cross_tenant.retire_copy(
            mongo_db, owner, reason="moved_silent", actor="enrollment",
            to_tenant={"id": "tenant-b", "name": "Beta Org"}, to_agent_id="agent-b") is False
    ledger.assert_not_awaited()
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["seatsUsed"] == 3
    assert (await mongo_db.agents.find_one({"id": "agent-a"}))["status"] == "Inactive"


async def test_retire_silent_copies_retires_each_silent_copy_and_no_live_one(mongo_db):
    await _two_tenants(mongo_db, seats_used_a=3)
    await _agent(mongo_db, "tenant-a", "agent-quiet", serial="ABC123", seen_hours=30)
    await harness.tenant(mongo_db, "tenant-c", key="reg_cccccccccccccccccccc",
                         license={"maxAgents": 50, "seatsUsed": 1, "inactiveReclaimDays": 30})
    await _agent(mongo_db, "tenant-c", "agent-quiet-c", uuid="4c4c4544-0042-3510-8051-b8c04f4d4a32", seen_hours=40)
    hardware = _hw(serialNumber="ABC123", smbiosUuid="4c4c4544-0042-3510-8051-b8c04f4d4a32")
    tenant_b = await mongo_db.tenants.find_one({"id": "tenant-b"})
    with patch("audit_ledger.event", new=AsyncMock()):
        assert await cross_tenant.retire_silent_copies(mongo_db, tenant_b, hardware, "agent-b", "enrollment") == 2
        assert await cross_tenant.retire_silent_copies(mongo_db, tenant_b, hardware, "agent-b", "enrollment") == 0
    statuses = {a["id"]: a["status"] for a in await mongo_db.agents.find({}).to_list(10)}
    assert statuses == {"agent-quiet": "Replaced", "agent-quiet-c": "Replaced"}
    assert cross_tenant.MOVED_REASONS == ("moved", "moved_silent")


# -- enrollment through the real register route ----------------------------------------------------

HOME, OTHER = "203.0.113.7", "198.51.100.9"
WAITING = "this computer is enrolled in another organization; waiting for platform approval"


async def _register(db, hostname, key=KEY_B, **kwargs):
    with patch("audit_ledger.event", new=AsyncMock()) as ledger:
        code, body = await harness.register(db, hostname, key=key, **kwargs)
    return code, body, ledger


async def _feed(db, tenant_id):
    return await db.notifications.find({"tenantId": tenant_id}, {"_id": 0}).to_list(50)


async def test_a_machine_live_in_another_organization_is_held_and_neither_name_leaks(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "owner-copy-1", serial="S1", seen_hours=1, hostname="alpha-pc")
    before = await mongo_db.agents.find_one({"id": "owner-copy-1"}, {"_id": 0})
    code, body, _ = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"))
    assert code == 202 and body["pendingReason"] == "cross_tenant_duplicate"
    held = await mongo_db.agents.find_one({"id": body["agentId"]})
    assert held["status"] == "Pending" and held["tenantId"] == "tenant-b"
    assert held["crossTenant"] == {"agentId": "owner-copy-1", "tenantId": "tenant-a", "tenantName": "Alpha Org",
                                   "hostname": "alpha-pc"}
    assert await mongo_db.agents.find_one({"id": "owner-copy-1"}, {"_id": 0}) == before
    assert await _feed(mongo_db, "tenant-a") == []
    b_feed = await _feed(mongo_db, "tenant-b")
    assert len(b_feed) == 1 and WAITING in b_feed[0]["message"]
    leaked = json.dumps(b_feed, default=str)
    for secret in ("Alpha", "tenant-a", "owner-copy-1", "alpha-pc"):
        assert secret not in leaked
    platform = [n for n in await _feed(mongo_db, "platform-admin")
                if n["metadata"].get("event") == "agent.cross_tenant_duplicate"]
    assert len(platform) == 1 and "audience" not in platform[0]["metadata"]
    assert "Alpha Org" in platform[0]["message"] and "Beta Org" in platform[0]["message"]
    assert not (await mongo_db.tenants.find_one({"id": "tenant-b"})).get("allowedNetworks")  # nothing learned


async def test_an_old_agent_build_is_refused_without_a_name(mongo_db):
    await _two_tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1, hostname="alpha-pc")
    code, detail, _ = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"), supportsPending=False)
    assert code == 403 and detail.startswith("cross_tenant_duplicate:")
    for secret in ("Alpha", "tenant-a", "alpha-pc"):
        assert secret not in detail


async def test_a_silent_copy_elsewhere_is_retired_by_the_new_enrollment(mongo_db):
    await _two_tenants(mongo_db, seats_used_a=3)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=30, hostname="alpha-pc")
    code, body, ledger = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"))
    assert code == 200 and body.get("agentId")
    old = await mongo_db.agents.find_one({"id": "agent-a"})
    assert old["status"] == "Replaced" and old["replacedReason"] == "moved_silent" and "replacedBy" not in old
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["seatsUsed"] == 2
    assert (await mongo_db.agents.find_one({"id": body["agentId"]}))["status"] == "Online"
    assert [c.args[1] for c in ledger.await_args_list if c.args[0] == "agent.moved_out"] == ["tenant-a"]
    assert [c.args[1] for c in ledger.await_args_list if c.args[0] == "agent.moved"] == ["platform-admin"]
    for secret in ("Beta", "tenant-b"):
        assert secret not in repr([c for c in ledger.await_args_list if c.args[0] == "agent.moved_out"])
    assert await _feed(mongo_db, "tenant-a") == []


async def test_a_copy_that_holds_no_seat_does_not_hold_the_new_enrollment(mongo_db):
    await _two_tenants(mongo_db, seats_used_a=3)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", status="Inactive", seen_hours=1)
    code, body, _ = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"))
    assert code == 200
    assert (await mongo_db.agents.find_one({"id": "agent-a"}))["status"] == "Inactive"
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["seatsUsed"] == 3


async def test_a_mac_alone_is_never_a_cross_tenant_duplicate(mongo_db):
    await _two_tenants(mongo_db)
    mac = "a4:bb:6d:11:22:33"
    await mongo_db.agents.insert_one({"id": "agent-a", "tenantId": "tenant-a", "hostname": "alpha-pc",
                                      "status": "Online", "lastSeen": _ago(1),
                                      "hardware": {"macAddresses": [mac]}})
    code, body, _ = await _register(mongo_db, "beta-pc", hardware={"macAddresses": [mac], "osFamily": "windows"})
    assert code == 200
    assert (await mongo_db.agents.find_one({"id": "agent-a"}))["status"] == "Online"


async def test_a_returning_agent_that_needs_a_seat_is_held_while_the_machine_is_live_elsewhere(mongo_db):
    await _two_tenants(mongo_db)
    code, body, _ = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"))
    assert code == 200
    await mongo_db.agents.update_one({"id": body["agentId"]}, {"$set": {"status": "Inactive"}})
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1, hostname="alpha-pc")
    code, again, _ = await _register(mongo_db, "beta-pc", hardware=harness.hw("S1"), agentSecret=body["agentSecret"])
    assert code == 202 and again["pendingReason"] == "cross_tenant_duplicate"
    held = await mongo_db.agents.find_one({"id": body["agentId"]})
    assert held["status"] == "Pending" and held["crossTenant"]["tenantId"] == "tenant-a"
    assert len([n for n in await _feed(mongo_db, "platform-admin")
                if n["metadata"].get("event") == "agent.cross_tenant_duplicate"]) == 1


async def test_the_duplicate_rule_runs_before_the_network_rule_and_teaches_nothing(mongo_db):
    await _two_tenants(mongo_db)
    assert (await _register(mongo_db, "beta-1", hardware=harness.hw("S0"), client_ip=HOME))[0] == 200
    learned = (await mongo_db.tenants.find_one({"id": "tenant-b"}))["allowedNetworks"]
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1)
    code, body, _ = await _register(mongo_db, "beta-2", hardware=harness.hw("S1"), client_ip=OTHER)
    assert code == 202 and body["pendingReason"] == "cross_tenant_duplicate"
    assert (await mongo_db.tenants.find_one({"id": "tenant-b"}))["allowedNetworks"] == learned


async def test_the_platform_organization_is_held_too(mongo_db):
    await _two_tenants(mongo_db)
    await harness.tenant(mongo_db, "platform-admin", key="reg_pppppppppppppppppppp", plan=None, name="Platform")
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1)
    code, body, _ = await _register(mongo_db, "ops-pc", key="reg_pppppppppppppppppppp", hardware=harness.hw("S1"))
    assert code == 202 and body["pendingReason"] == "cross_tenant_duplicate"
