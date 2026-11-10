"""An asset belongs to the machine's hardware, not its hostname, against a real MongoDB
(skips without one).

Value: protects=a computer keeps its asset across a rename or a re-enrollment, a different
computer given the same name gets its own asset instead of taking over another machine's
record, a same-named computer in another tenant gets an asset at all, and heartbeats write
into the asset enrollment chose; fails_when=the asset is found by hostname alone;
no_claim=the HTTP layer and JWT handling (register_agent/report_heartbeat are called
directly; the slowapi limiters are disabled).
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_heartbeat_endpoints as hb
import agent_registry_endpoints as reg
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T, OTHER = "tenant-a", "tenant-b"
LAPTOP = {"serialNumber": "5CD5234T2F", "macAddresses": ["9c:b1:50:f4:58:12"]}
OTHER_LAPTOP = {"serialNumber": "PF3ABC12", "macAddresses": ["3c:52:82:aa:bb:cc"]}


async def _tenants(db):
    await db.assets.create_index([("id", 1)], unique=True)  # as on the platform
    for tid, key in ((T, "ka"), (OTHER, "kb")):
        await db.tenants.insert_one({"id": tid, "name": tid, "registrationKey": key,
                                     "license": {"maxAgents": 10, "seatsUsed": 0, "inactiveReclaimDays": 30}})


def _request(path="/api/agents/register"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("203.0.113.7", 5555)})


async def _register(db, hostname, hardware, key="ka"):
    payload = {"registrationKey": key, "hostname": hostname, "platform": "Windows", "version": "2.1.18",
               "ipAddress": "10.1.2.3", "supportsPending": True, "hardware": hardware}
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        out = await reg.register_agent(_request(), Response(), payload, background_tasks=MagicMock())
    return await db.agents.find_one({"id": out["agentId"]})


async def test_first_enrollment_keeps_the_familiar_id_and_binds_the_hardware(mongo_db):
    await _tenants(mongo_db)
    agent = await _register(mongo_db, "EILT0197", LAPTOP)
    asset = await mongo_db.assets.find_one({"id": agent["assetId"]})
    assert asset["id"] == "asset-EILT0197"
    assert asset["hardwareKey"] == "serial:5CD5234T2F"


async def test_a_reenrolled_or_renamed_machine_keeps_its_asset(mongo_db):
    await _tenants(mongo_db)
    first = await _register(mongo_db, "EILT0197", LAPTOP)
    await mongo_db.agents.delete_one({"id": first["id"]})  # an admin deleted it to re-enroll
    renamed = await _register(mongo_db, "EILT0197-NEW", LAPTOP)
    assert renamed["id"] == first["id"]  # one agent id per machine (machine_identity)
    assert renamed["assetId"] == "asset-EILT0197"
    assert await mongo_db.assets.count_documents({}) == 1


async def test_another_machine_with_the_same_name_gets_its_own_asset(mongo_db):
    await _tenants(mongo_db)
    first = await _register(mongo_db, "EILT0197", LAPTOP)
    await mongo_db.agents.delete_one({"id": first["id"]})
    other = await _register(mongo_db, "EILT0197", OTHER_LAPTOP)
    assert other["assetId"] != "asset-EILT0197"
    original = await mongo_db.assets.find_one({"id": "asset-EILT0197"})
    assert original["serialNumber"] == "5CD5234T2F"  # the first laptop's record is untouched
    assert (await mongo_db.assets.find_one({"id": other["assetId"]}))["hardwareKey"] == "serial:PF3ABC12"


async def test_a_same_named_machine_in_another_tenant_gets_an_asset(mongo_db):
    # Asset ids are unique platform-wide: the second tenant's computer used to get none.
    await _tenants(mongo_db)
    await _register(mongo_db, "EILT0197", LAPTOP)
    other = await _register(mongo_db, "EILT0197", OTHER_LAPTOP, key="kb")
    asset = await mongo_db.assets.find_one({"id": other["assetId"]})
    assert asset and asset["tenantId"] == OTHER and asset["id"] != "asset-EILT0197"


async def test_an_asset_from_before_binding_is_adopted_only_by_its_own_serial(mongo_db):
    await _tenants(mongo_db)
    await mongo_db.assets.insert_one({"id": "asset-EILT0197", "tenantId": T, "hostname": "EILT0197",
                                      "serialNumber": "5CD5234T2F"})
    agent = await _register(mongo_db, "EILT0197", LAPTOP)
    assert agent["assetId"] == "asset-EILT0197"
    assert (await mongo_db.assets.find_one({"id": "asset-EILT0197"}))["hardwareKey"] == "serial:5CD5234T2F"


async def test_a_machine_bound_by_its_network_interface_keeps_the_asset_once_it_reports_a_serial(mongo_db):
    await _tenants(mongo_db)
    first = await _register(mongo_db, "vm-01", {"macAddresses": LAPTOP["macAddresses"]})
    assert (await mongo_db.assets.find_one({"id": first["assetId"]}))["hardwareKey"] == "mac:9c:b1:50:f4:58:12"
    await mongo_db.agents.delete_one({"id": first["id"]})
    again = await _register(mongo_db, "vm-01-renamed", LAPTOP)
    assert again["assetId"] == first["assetId"]


async def test_heartbeats_write_into_the_enrolled_asset_not_asset_hostname(mongo_db):
    await _tenants(mongo_db)
    first = await _register(mongo_db, "EILT0197", LAPTOP)
    await mongo_db.agents.delete_one({"id": first["id"]})
    other = await _register(mongo_db, "EILT0197", OTHER_LAPTOP)
    tenant = await mongo_db.tenants.find_one({"id": T})
    with patch.object(hb, "get_database", return_value=mongo_db), patch.object(hb.agent_limiter, "enabled", False):
        await hb.report_heartbeat(_request(f"/api/agents/{other['id']}/heartbeat"), Response(), other["id"],
                                  MagicMock(), {"hostname": "EILT0197", "platform": "Windows"}, tenant)
    assert (await mongo_db.assets.find_one({"id": other["assetId"]}))["agentId"] == other["id"]
    assert (await mongo_db.assets.find_one({"id": "asset-EILT0197"})).get("agentId") != other["id"]
