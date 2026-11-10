"""One agent id per machine for life, against a real MongoDB (skips without one).

Value: protects=a machine that enrolls again (after its agent was deleted, or reinstalled
under a new name) gets the agent id it had, every token issued under that id before is
refused from then on, a live agent on the same hardware is never taken over, machines with
no hardware identity and other tenants keep separate ids, and migration 033 records the
ids of today's agents; fails_when=a re-enrollment mints a new id, or an old install's token
keeps working once its id has passed on; no_claim=the HTTP layer (register_agent and
verify_agent_key are called directly; the slowapi limiter is disabled).
"""
import importlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_auth
import agent_registry_endpoints as reg
import machine_identity
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T, OTHER = "tenant-a", "tenant-b"
LAPTOP = {"serialNumber": "5CD5234T2F", "macAddresses": ["9c:b1:50:f4:58:12"]}


async def _tenants(db):
    await db.assets.create_index([("id", 1)], unique=True)
    await machine_identity.ensure_indexes(db)
    for tid, key in ((T, "ka"), (OTHER, "kb")):
        await db.tenants.insert_one({"id": tid, "name": tid, "registrationKey": key,
                                     "license": {"maxAgents": 10, "seatsUsed": 0, "inactiveReclaimDays": 30}})


def _request(path="/api/agents/register"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("203.0.113.7", 5555)})


async def _register(db, hostname, hardware=LAPTOP, key="ka", **body):
    payload = {"registrationKey": key, "hostname": hostname, "platform": "Windows", "version": "2.1.18",
               "ipAddress": "10.1.2.3", "supportsPending": True, "hardware": hardware, **body}
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    response = Response()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        out = await reg.register_agent(_request(), response, payload, background_tasks=MagicMock())
    return response.status_code, out


async def _accepted(db, token):
    """Whether the agent routes accept this token."""
    try:
        await agent_auth.verify_agent_key(request=_request("/api/agents/x/heartbeat"), x_tenant_key=None,
                                          authorization=f"Bearer {token}", db=db)
        return True
    except HTTPException as exc:
        assert exc.status_code == 403
        return False


async def _age(db, agent_id, days=2):
    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    await db.agents.update_one({"id": agent_id}, {"$set": {"lastSeen": old}})


async def test_a_machine_enrolling_after_its_agent_was_deleted_gets_its_id_back(mongo_db):
    await _tenants(mongo_db)
    _, first = await _register(mongo_db, "EILT0197")
    await mongo_db.agents.delete_one({"id": first["agentId"]})
    time.sleep(0.01)
    code, again = await _register(mongo_db, "EILT0197")
    assert code == 200 and again["agentId"] == first["agentId"]
    assert not await _accepted(mongo_db, first["token"])   # the old install's token stops working
    assert await _accepted(mongo_db, again["token"])


async def test_a_reinstall_under_a_new_name_takes_over_a_silent_record(mongo_db):
    await _tenants(mongo_db)
    _, first = await _register(mongo_db, "EILT0197")
    await _age(mongo_db, first["agentId"])
    seats = (await mongo_db.tenants.find_one({"id": T}))["license"]["seatsUsed"]
    time.sleep(0.01)
    code, again = await _register(mongo_db, "EILT0197-NEW")
    assert code == 200 and again["agentId"] == first["agentId"]
    assert await mongo_db.agents.count_documents({}) == 1
    record = await mongo_db.agents.find_one({"id": first["agentId"]})
    assert record["hostname"] == "EILT0197-NEW" and record["status"] == "Online"
    assert (await mongo_db.tenants.find_one({"id": T}))["license"]["seatsUsed"] == seats  # no second seat
    assert not await _accepted(mongo_db, first["token"])
    assert again["agentSecret"] != first["agentSecret"]


async def test_an_uninstalled_record_is_taken_over_even_when_recent(mongo_db):
    await _tenants(mongo_db)
    _, first = await _register(mongo_db, "EILT0197")
    await mongo_db.agents.update_one({"id": first["agentId"]}, {"$set": {"status": "Uninstalled"}})
    code, again = await _register(mongo_db, "EILT0197-NEW")
    assert code == 200 and again["agentId"] == first["agentId"]


async def test_a_live_agent_on_the_same_hardware_is_left_alone(mongo_db):
    await _tenants(mongo_db)
    _, live = await _register(mongo_db, "EILT0197")
    code, other = await _register(mongo_db, "EILT0197-CLONE")
    assert code == 202 and other["agentId"] != live["agentId"]  # held as a hardware duplicate
    assert (await mongo_db.agents.find_one({"id": live["agentId"]}))["hostname"] == "EILT0197"
    assert await _accepted(mongo_db, live["token"])
    assert await machine_identity.remembered_id(mongo_db, T, "serial:5CD5234T2F") == live["agentId"]


async def test_the_agent_presenting_its_secret_keeps_its_tokens(mongo_db):
    await _tenants(mongo_db)
    _, first = await _register(mongo_db, "EILT0197")
    code, again = await _register(mongo_db, "EILT0197-NEW", agentSecret=first["agentSecret"])
    assert code == 200 and again["agentId"] == first["agentId"]
    assert await _accepted(mongo_db, first["token"])  # nothing was superseded


async def test_machines_without_hardware_identity_and_other_tenants_get_their_own_ids(mongo_db):
    await _tenants(mongo_db)
    _, weak = await _register(mongo_db, "vm-01", hardware={})
    await mongo_db.agents.delete_one({"id": weak["agentId"]})
    _, weak_again = await _register(mongo_db, "vm-01", hardware={})
    assert weak_again["agentId"] != weak["agentId"]
    _, in_a = await _register(mongo_db, "EILT0197")
    _, in_b = await _register(mongo_db, "EILT0197", key="kb")
    assert in_b["agentId"] != in_a["agentId"]
    assert await _accepted(mongo_db, in_a["token"])


async def test_migration_records_the_ids_of_current_agents(mongo_db):
    await mongo_db.agents.insert_many([
        {"id": "agent-live", "tenantId": T, "hostname": "EILT0197", "seatKey": "serial:5CD5234T2F",
         "status": "Online", "lastSeen": "2026-11-10T17:00:00+00:00"},
        {"id": "agent-replaced", "tenantId": T, "hostname": "EILT0197-OLD", "seatKey": "serial:5CD5234T2F",
         "status": "Replaced", "lastSeen": "2026-11-10T18:00:00+00:00"},
        {"id": "agent-weak", "tenantId": T, "hostname": "vm-01", "seatKey": "legacy:abc", "status": "Online"},
    ])
    migration = importlib.import_module("migrations.033_machine_identities")
    await migration.up(mongo_db)
    await migration.up(mongo_db)  # a second run changes nothing
    assert await machine_identity.remembered_id(mongo_db, T, "serial:5CD5234T2F") == "agent-live"
    assert await mongo_db[machine_identity.COLLECTION].count_documents({}) == 1


def test_weak_keys_are_never_remembered():
    assert not machine_identity.is_hardware_key("legacy:unknown")
    assert machine_identity.is_hardware_key("mac:9c:b1:50:f4:58:12")


@pytest.fixture(autouse=True)
def _no_stale_cutoffs():
    import authentication_service
    authentication_service._user_cutoff_cache.clear()
    yield
    authentication_service._user_cutoff_cache.clear()
