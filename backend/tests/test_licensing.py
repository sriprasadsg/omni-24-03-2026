"""Spec C2: agent seat licensing against a real MongoDB (skips without one).

Value: protects=seats are claimed atomically (never above maxAgents, even concurrently),
released without going negative, reclaimed after the tenant's window, repaired by
reconcile, and enrollment honours hardware identity (takeover vs live duplicate, which
since spec C3 is held as Pending rather than refused outright);
fails_when=the claim is a non-atomic check-then-insert, a release underflows, reclaim or
reconcile miss, or a known machine gets a second seat; no_claim=multi-process timing
(one event loop) and the HTTP layer (register_agent is called directly).
"""
import asyncio
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import licensing
import agent_registry_endpoints as reg
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "tenant-a"
NOW = datetime.now(timezone.utc)


def _ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


async def _tenant(db, max_agents=5, legacy=False):
    doc = {"id": T, "name": "A", "registrationKey": "k"}
    if legacy:
        doc["maxAgents"] = max_agents
    else:
        doc["license"] = {"maxAgents": max_agents, "seatsUsed": 0, "inactiveReclaimDays": 30}
    await db.tenants.insert_one(doc)


async def _agent(db, n, status="Online", last_seen=None, **extra):
    await db.agents.insert_one({"id": f"agent-{n}", "tenantId": T, "hostname": f"host-{n}", "status": status,
                                "lastSeen": last_seen or NOW.isoformat(), **extra})


async def _used(db):
    return (await db.tenants.find_one({"id": T}))["license"]["seatsUsed"]


# ── licensing module ────────────────────────────────────────────────────────

async def test_twenty_concurrent_claims_take_exactly_the_free_seats(mongo_db):
    await _tenant(mongo_db, max_agents=5)
    results = await asyncio.gather(*(licensing.try_claim_seat(mongo_db, T) for _ in range(20)))
    assert results.count(True) == 5
    assert await _used(mongo_db) == 5


async def test_legacy_tenant_gets_a_license_counted_from_seat_holders(mongo_db):
    await _tenant(mongo_db, max_agents=3, legacy=True)
    await _agent(mongo_db, 1)
    await _agent(mongo_db, 2, status="Offline")
    await _agent(mongo_db, 3, status="Uninstalled")  # holds no seat
    lic = await licensing.ensure_license(mongo_db, T)
    assert (lic["maxAgents"], lic["seatsUsed"]) == (3, 2)


async def test_release_never_goes_below_zero(mongo_db):
    await _tenant(mongo_db)
    await licensing.release_seats(mongo_db, T, 3)
    assert await _used(mongo_db) == 0


async def test_reclaim_marks_silent_agents_inactive_and_frees_their_seats(mongo_db):
    await _tenant(mongo_db)
    await _agent(mongo_db, 1, status="Offline", last_seen=_ago(days=31))
    await _agent(mongo_db, 2, status="Offline", last_seen=_ago(days=29))
    await mongo_db.tenants.update_one({"id": T}, {"$set": {"license.seatsUsed": 2}})
    with patch.object(licensing, "_audit", AsyncMock()):
        assert await licensing.reclaim_inactive_agents(mongo_db, now=NOW) == 1
    assert (await mongo_db.agents.find_one({"id": "agent-1"}))["status"] == "Inactive"
    assert (await mongo_db.agents.find_one({"id": "agent-2"}))["status"] == "Offline"
    assert await _used(mongo_db) == 1


async def test_reconcile_repairs_drift(mongo_db):
    await _tenant(mongo_db)
    await _agent(mongo_db, 1)
    await mongo_db.tenants.update_one({"id": T}, {"$set": {"license.seatsUsed": 4}})
    with patch.object(licensing, "_audit", AsyncMock()):
        drifts = await licensing.reconcile_all(mongo_db)
    assert drifts == [{"tenantId": T, "before": 4, "after": 1}]
    assert await _used(mongo_db) == 1


async def test_lowering_the_limit_reports_over_by(mongo_db):
    await _tenant(mongo_db)
    for i in range(3):
        await _agent(mongo_db, i)
    await licensing.recount_seats(mongo_db, T)
    summary = await licensing.update_license(mongo_db, T, max_agents=2)
    assert (summary["maxAgents"], summary["seatsUsed"], summary["overBy"]) == (2, 3, 1)
    assert not await licensing.try_claim_seat(mongo_db, T)
    with pytest.raises(ValueError):
        await licensing.update_license(mongo_db, T, reclaim_days=0)


async def test_migration_011_backfills_and_is_idempotent(mongo_db):
    await _tenant(mongo_db, max_agents=7, legacy=True)
    await _agent(mongo_db, 1)
    mig = importlib.import_module("migrations.011_tenant_license")
    await mig.up(mongo_db)
    await mongo_db.tenants.update_one({"id": T}, {"$set": {"license.seatsUsed": 9}})
    await mig.up(mongo_db)  # must not overwrite an existing license
    lic = (await mongo_db.tenants.find_one({"id": T}))["license"]
    assert (lic["maxAgents"], lic["seatsUsed"], lic["inactiveReclaimDays"]) == (7, 9, 30)


# ── enrollment (register_agent) ────────────────────────────────────────────

def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": []})


async def _register(db, hostname, **body):
    payload = {"registrationKey": "k", "hostname": hostname, "platform": "Linux", **body}
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        return await reg.register_agent(_request(), MagicMock(), payload, background_tasks=MagicMock())


async def test_third_enrollment_on_two_seats_is_refused(mongo_db):
    await _tenant(mongo_db, max_agents=2)
    await _register(mongo_db, "a")
    await _register(mongo_db, "b")
    with pytest.raises(HTTPException) as exc:
        await _register(mongo_db, "c")  # an older build: refused with 403, kept as Pending (spec C3)
    assert exc.value.status_code == 403
    assert await _used(mongo_db) == 2
    assert await mongo_db.agents.count_documents({"tenantId": T, "status": "Online"}) == 2
    third = await mongo_db.agents.find_one({"hostname": "c"})
    assert third["status"] == "Pending" and third["pendingReason"] == "seat_limit"


async def test_reinstall_on_silent_hardware_inherits_the_seat(mongo_db):
    await _tenant(mongo_db, max_agents=1)
    await _agent(mongo_db, 1, status="Offline", last_seen=_ago(hours=25), hardware={"serialNumber": "PF3ABC12"})
    await licensing.recount_seats(mongo_db, T)
    out = await _register(mongo_db, "renamed-host", hardware={"serialNumber": "pf3abc12"})
    assert (await mongo_db.agents.find_one({"id": "agent-1"}))["status"] == "Replaced"
    new = await mongo_db.agents.find_one({"id": out["agentId"]})
    assert new["seatKey"] == "serial:PF3ABC12" and new["replaces"] == "agent-1"
    assert await _used(mongo_db) == 1


async def test_same_hardware_seen_recently_is_refused(mongo_db):
    await _tenant(mongo_db, max_agents=5)
    await _agent(mongo_db, 1, last_seen=_ago(hours=1), hardware={"serialNumber": "PF3ABC12"})
    await licensing.recount_seats(mongo_db, T)
    with pytest.raises(HTTPException) as exc:
        await _register(mongo_db, "clone", hardware={"serialNumber": "PF3ABC12"})
    # Spec C3: held as Pending with reason duplicate_hardware_id (older builds see a 403).
    assert exc.value.status_code == 403 and "duplicate_hardware_id" in str(exc.value.detail)
    clone = await mongo_db.agents.find_one({"hostname": "clone"})
    assert clone["status"] == "Pending" and clone["pendingReason"] == "duplicate_hardware_id"
    assert await _used(mongo_db) == 1
    assert (await mongo_db.agents.find_one({"id": "agent-1"}))["status"] == "Online"


async def test_junk_serial_falls_back_to_uuid(mongo_db):
    await _tenant(mongo_db)
    out = await _register(mongo_db, "h", hardware={"serialNumber": "To Be Filled By O.E.M.",
                                                  "smbiosUuid": "4c4c4544-0042-3010-8051-b4c04f4d3132"})
    agent = await mongo_db.agents.find_one({"id": out["agentId"]})
    assert agent["seatKey"] == "uuid:4c4c4544-0042-3010-8051-b4c04f4d3132"
    assert agent["identityStrength"] == "strong"


async def test_agent_without_hardware_gets_a_weak_legacy_seat(mongo_db):
    await _tenant(mongo_db)
    out = await _register(mongo_db, "old-build", device_id="b33294631e77afd6")
    agent = await mongo_db.agents.find_one({"id": out["agentId"]})
    assert (agent["seatKey"], agent["identityStrength"]) == ("legacy:b33294631e77afd6", "weak")
    assert await _used(mongo_db) == 1
