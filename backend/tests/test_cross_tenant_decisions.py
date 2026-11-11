"""Phase 88 plan 09: the decisions around a machine held because it is live in another organization (LIC-06).

Value: protects=approving a cross_tenant_duplicate hold moves the machine (one licence, the old copy retired
with its seat released), no other approval can admit a duplicate or leave a silent copy behind, a rejection
denylists nothing, and a tenant user never learns who else holds the machine; a retired agent cannot heartbeat
its way back, the Super Admin can restore it, and the hourly report names a machine live in two organizations;
fails_when=an approval admits B while A keeps its seat, a seat_limit hold is admitted with a live copy
elsewhere, a reject of the hold denylists the shared serial, the tenant's Pending list carries crossTenant, the
other organization's name or id, a moved agent claims a seat at its heartbeat, a tenant admin lists or restores
moved agents, or a pair seen in two tenants is reported twice a day or not at all; no_claim=the UI, the
enrollment route (88-07 tests) and the agent's own token handling.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cross_tenant
import pending_agent_endpoints as pae
import pending_agents
from auth_types import TokenData
from authentication_service import agent_token_revoked
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

KEY_A, KEY_B = "reg_aaaaaaaaaaaaaaaaaaaa", "reg_bbbbbbbbbbbbbbbbbbbb"
SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
ADMIN_B = TokenData(username="admin@b.example", role="Tenant Admin", tenant_id="tenant-b", mfa_verified=True)


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield
    pending_agents._status_cache.clear()


def _ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def _tenants(db, seats_used_a=3, b_max=50, b_used=0):
    await harness.tenant(db, "tenant-a", key=KEY_A, name="Alpha Org",
                         license={"maxAgents": 50, "seatsUsed": seats_used_a, "inactiveReclaimDays": 30})
    await harness.tenant(db, "tenant-b", key=KEY_B, name="Beta Org",
                         license={"maxAgents": b_max, "seatsUsed": b_used, "inactiveReclaimDays": 30})


async def _agent(db, tenant_id, agent_id, serial=None, uuid=None, status="Online", seen_hours=2.0, hostname=None,
                 **extra):
    hardware = {"macAddresses": []}
    if serial:
        hardware["serialNumber"] = serial
    if uuid:
        hardware["smbiosUuid"] = uuid
    doc = {"id": agent_id, "tenantId": tenant_id, "hostname": hostname or f"host-{agent_id}", "status": status,
           "lastSeen": _ago(seen_hours), "hardware": hardware, **extra}
    await db.agents.insert_one(dict(doc))
    return doc


async def _register_b(db, hostname="beta-pc", serial="S1", **kwargs):
    with patch("audit_ledger.event", new=AsyncMock()):
        return await harness.register(db, hostname, key=KEY_B, hardware=harness.hw(serial), **kwargs)


async def _approve(db, agent_id, user=SUPER, **body):
    with patch.object(pae, "get_database", return_value=db), patch.object(pae, "invalidate_cache"), \
            patch("audit_ledger.event", new=AsyncMock()) as ledger:
        out = await pae.approve_pending_agent(agent_id, pae.ApproveBody(**body), user)
    return out, ledger


def _error(response):
    return response.status_code, json.loads(response.body)["error"]


async def _seats(db, tenant_id):
    return (await db.tenants.find_one({"id": tenant_id}))["license"]["seatsUsed"]


# -- approving a cross_tenant_duplicate hold moves the machine (D-37) -------------------------------

async def test_approving_a_held_duplicate_admits_it_and_moves_the_machine_off_the_old_tenant(mongo_db):
    await _tenants(mongo_db, seats_used_a=3)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1, hostname="alpha-pc")
    code, held = await _register_b(mongo_db)
    assert code == 202 and held["pendingReason"] == "cross_tenant_duplicate"
    started = time.time() - 100
    out, ledger = await _approve(mongo_db, held["agentId"])
    assert out["status"] == "Offline"
    b = await mongo_db.agents.find_one({"id": held["agentId"]})
    assert b["status"] == "Offline" and "crossTenant" not in b and "pendingReason" not in b
    assert await _seats(mongo_db, "tenant-b") == 1
    a = await mongo_db.agents.find_one({"id": "agent-a"})
    assert a["status"] == "Replaced" and a["replacedReason"] == "moved" and "replacedBy" not in a
    assert await _seats(mongo_db, "tenant-a") == 2
    assert await agent_token_revoked(mongo_db, "agent-a", started)
    remembered = await mongo_db.machine_identities.find_one({"tenantId": "tenant-b", "hardwareKey": "serial:S1"})
    assert remembered["agentId"] == held["agentId"]
    moved = [c for c in ledger.await_args_list if c.args[0] == "agent.moved"]
    assert len(moved) == 1 and moved[0].args[1] == "platform-admin" and moved[0].kwargs["reason"] == "moved"
    moved_out = [c for c in ledger.await_args_list if c.args[0] == "agent.moved_out"]
    assert len(moved_out) == 1 and moved_out[0].args[1] == "tenant-a"
    for other in ("Beta", "tenant-b", held["agentId"]):
        assert other not in repr(moved_out[0])


async def test_with_no_free_seat_in_the_new_tenant_the_old_copy_is_untouched(mongo_db):
    await _tenants(mongo_db, seats_used_a=3, b_max=1, b_used=1)
    await _agent(mongo_db, "tenant-b", "b-existing", serial="OTHER", seen_hours=1)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1)
    code, held = await _register_b(mongo_db)
    assert code == 202 and held["pendingReason"] == "cross_tenant_duplicate"
    response, _ = await _approve(mongo_db, held["agentId"])
    status, error = _error(response)
    assert status == 409 and error.startswith("no_free_seat")
    assert (await mongo_db.agents.find_one({"id": "agent-a"}))["status"] == "Online"
    assert await _seats(mongo_db, "tenant-a") == 3
    b = await mongo_db.agents.find_one({"id": held["agentId"]})
    assert b["status"] == "Pending" and b["pendingReason"] == "cross_tenant_duplicate"


async def test_every_seat_holding_copy_elsewhere_is_retired_in_one_approval(mongo_db):
    await _tenants(mongo_db, seats_used_a=3)
    await harness.tenant(mongo_db, "tenant-c", key="reg_cccccccccccccccccccc", name="Gamma Org",
                         license={"maxAgents": 50, "seatsUsed": 2, "inactiveReclaimDays": 30})
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1)
    await _agent(mongo_db, "tenant-c", "agent-c", uuid="4c4c4544-0042-3510-8051-b8c04f4d4a32", seen_hours=40)
    code, held = await _register_b(mongo_db)
    assert code == 202
    await mongo_db.agents.update_one({"id": held["agentId"]}, {"$set": {
        "hardware.smbiosUuid": "4c4c4544-0042-3510-8051-b8c04f4d4a32"}})
    await _approve(mongo_db, held["agentId"])
    statuses = {a["id"]: (a["status"], a.get("replacedReason"))
                for a in await mongo_db.agents.find({"id": {"$in": ["agent-a", "agent-c"]}}).to_list(5)}
    assert statuses == {"agent-a": ("Replaced", "moved"), "agent-c": ("Replaced", "moved")}
    assert await _seats(mongo_db, "tenant-a") == 2 and await _seats(mongo_db, "tenant-c") == 1


# -- approving for another reason cannot admit a duplicate (Pitfall 6) ------------------------------

async def test_a_seat_limit_hold_whose_machine_is_now_live_elsewhere_turns_into_a_duplicate_hold(mongo_db):
    await _tenants(mongo_db, b_max=1, b_used=1)
    await _agent(mongo_db, "tenant-b", "b-existing", serial="OTHER", seen_hours=1)
    code, held = await _register_b(mongo_db, serial="S2")
    assert code == 202 and held["pendingReason"] == "seat_limit"
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S2", seen_hours=1, hostname="alpha-pc")
    response, _ = await _approve(mongo_db, held["agentId"], raiseLimitBy=2)
    status, error = _error(response)
    assert status == 409 and error.startswith("reason_changed:")
    b = await mongo_db.agents.find_one({"id": held["agentId"]})
    assert b["status"] == "Pending" and b["pendingReason"] == "cross_tenant_duplicate"
    assert b["crossTenant"]["tenantId"] == "tenant-a" and b["crossTenant"]["tenantName"] == "Alpha Org"
    assert await _seats(mongo_db, "tenant-b") == 1  # nothing admitted, and the limit was not raised first
    assert (await mongo_db.tenants.find_one({"id": "tenant-b"}))["license"]["maxAgents"] == 1
    assert (await mongo_db.agents.find_one({"id": "agent-a"}))["status"] == "Online"
    platform = [n for n in await mongo_db.notifications.find({"tenantId": "platform-admin"}).to_list(20)
                if n["metadata"].get("event") == "agent.cross_tenant_duplicate"]
    assert len(platform) == 1 and "Alpha Org" in platform[0]["message"]


async def test_any_approval_retires_a_silent_copy_in_another_organization(mongo_db):
    await _tenants(mongo_db, seats_used_a=3)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=30)
    await _agent(mongo_db, "tenant-b", "b-held", serial="S1", status="Pending", seen_hours=1,
                 pendingReason="trial_ended", seatKey="serial:S1")
    out, ledger = await _approve(mongo_db, "b-held")
    assert out["status"] == "Offline"
    a = await mongo_db.agents.find_one({"id": "agent-a"})
    assert a["status"] == "Replaced" and a["replacedReason"] == "moved_silent"
    assert await _seats(mongo_db, "tenant-a") == 2
    assert [c.args[1] for c in ledger.await_args_list if c.args[0] == "agent.moved"] == ["platform-admin"]
    remembered = await mongo_db.machine_identities.find_one({"tenantId": "tenant-b", "hardwareKey": "serial:S1"})
    assert remembered["agentId"] == "b-held"


async def test_an_approval_with_no_copy_elsewhere_changes_nothing_else(mongo_db):
    await _tenants(mongo_db)
    await _agent(mongo_db, "tenant-b", "b-held", serial="S9", status="Pending", seen_hours=1,
                 pendingReason="trial_ended", seatKey="serial:S9")
    out, ledger = await _approve(mongo_db, "b-held")
    assert out["status"] == "Offline"
    assert not [c for c in ledger.await_args_list if c.args[0].startswith("agent.moved")]


# -- rejecting -------------------------------------------------------------------------------------

async def test_rejecting_a_cross_tenant_hold_denylists_nothing(mongo_db):
    await _tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1)
    code, held = await _register_b(mongo_db)
    assert code == 202
    await pending_agents.reject(mongo_db, held["agentId"], "root")
    assert (await mongo_db.agents.find_one({"id": held["agentId"]}))["status"] == "Rejected"
    assert await mongo_db.agent_denylist.count_documents({}) == 0


# -- who sees the other organization (D-36) ---------------------------------------------------------

async def test_the_tenant_list_never_carries_the_other_organization_but_the_platform_list_does(mongo_db):
    await _tenants(mongo_db)
    await _agent(mongo_db, "tenant-a", "agent-a", serial="S1", seen_hours=1, hostname="alpha-pc")
    code, held = await _register_b(mongo_db)
    assert code == 202
    with patch.object(pae, "get_database", return_value=mongo_db):
        tenant_view = await pae.list_pending_agents(tenant_id=None, status=None, reason=None, current_user=ADMIN_B)
        platform_view = await pae.list_pending_agents(tenant_id=None, status=None, reason=None, current_user=SUPER)
    assert [a["id"] for a in tenant_view["agents"]] == [held["agentId"]]
    assert tenant_view["agents"][0]["pendingReason"] == "cross_tenant_duplicate"
    assert "crossTenant" not in tenant_view["agents"][0]
    text = json.dumps(tenant_view, default=str)
    for other in ("Alpha", "tenant-a", "agent-a", "alpha-pc"):
        assert other not in text
    platform_agent = [a for a in platform_view["agents"] if a["id"] == held["agentId"]][0]
    assert platform_agent["crossTenant"]["tenantName"] == "Alpha Org"
