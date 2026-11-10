"""Phase 88 plan 02: a plan, an override or a partner allotment decides every tenant's seats (real MongoDB).

Value: protects=a plan's seat number reaches every direct tenant on it at once, a hand-set number
survives plan edits, a partner customer's allotment and the platform organization are never touched by
a plan edit, running agents keep their seats when a plan is lowered, and the platform has no seat limit;
fails_when=a plan edit overwrites an override or a partner customer, an override is dropped by a later
edit or stored as a float/bool/out-of-range number, an over-limit tenant loses a running agent, or the
platform organization is held for seats; no_claim=the HTTP layer (functions are called directly) and the
plan-edit route that calls apply_plan_seats (a later plan); audit writers are mocked.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import licensing
import partner_pool
import pending_agents
from tests import _enrollment_harness as harness
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield


async def _tenant(db, tid, plan="Free", seats=5, used=0, **extra):
    doc = {"id": tid, "name": f"Org {tid}", "maxAgents": seats,
           "license": {"maxAgents": seats, "seatsUsed": used, "inactiveReclaimDays": 30}}
    if plan is not None:
        doc["subscriptionTier"] = plan
    doc.update(extra)
    await db.tenants.insert_one(dict(doc))
    return tid


async def _seats(db, tid):
    return (await db.tenants.find_one({"id": tid}, {"_id": 0}))["license"]["maxAgents"]


async def _doc(db, tid):
    return await db.tenants.find_one({"id": tid}, {"_id": 0})


async def _partner(db, pool=100, allocated=0, pid="p1"):
    await db.tenants.insert_one({"id": pid, "name": f"Partner {pid}", "type": "partner", "license": {"maxAgents": 0},
                                 "partner": {"poolSize": pool, "allocated": allocated, "status": "active",
                                             "screenCeiling": ["all"]}})
    return pid


# -- derivation: the plan decides direct tenants only --------------------------------------------

async def test_a_plan_edit_reaches_direct_tenants_and_nothing_else(mongo_db):
    await _tenant(mongo_db, "free-direct")
    await _tenant(mongo_db, "free-noplan", plan=None)
    await _tenant(mongo_db, "free-override", seats=12, **{"license": {"maxAgents": 12, "seatsUsed": 0, "seatOverride": 12}})
    await _partner(mongo_db, allocated=30)
    await _tenant(mongo_db, "free-partner", seats=30, partnerId="p1")
    await _tenant(mongo_db, "platform-admin")
    await _tenant(mongo_db, "pro-direct", plan="Pro", seats=50)
    changed = await licensing.apply_plan_seats(mongo_db, "Free", 8)
    assert sorted(changed) == ["free-direct", "free-noplan"]
    assert [await _seats(mongo_db, t) for t in ("free-direct", "free-noplan")] == [8, 8]
    assert (await _doc(mongo_db, "free-direct"))["maxAgents"] == 8  # legacy readers follow
    assert [await _seats(mongo_db, t) for t in ("free-override", "free-partner", "platform-admin", "pro-direct")] \
        == [12, 30, 5, 50]
    assert (await _doc(mongo_db, "p1"))["partner"]["allocated"] == 30  # the pool is never touched (PROH-88-06)


async def test_a_tenant_already_on_the_number_is_not_reported_changed(mongo_db):
    await _tenant(mongo_db, "t1", seats=8)
    assert await licensing.apply_plan_seats(mongo_db, "Free", 8) == []


async def test_lowering_a_plan_keeps_every_running_agent_and_holds_only_new_machines(mongo_db):
    await _tenant(mongo_db, "t1", plan="Pro", seats=50, used=45)
    await mongo_db.agents.insert_many([{"id": f"a{i}", "tenantId": "t1", "hostname": f"h{i}", "status": "Online"}
                                       for i in range(45)])
    assert await licensing.apply_plan_seats(mongo_db, "Pro", 40) == ["t1"]
    assert await _seats(mongo_db, "t1") == 40
    assert await licensing.try_claim_seat(mongo_db, "t1") is False  # D-12: only new machines are held
    assert await mongo_db.agents.count_documents({"tenantId": "t1", "status": "Online"}) == 45
    assert (await _doc(mongo_db, "t1"))["license"]["seatsUsed"] == 45


# -- override: a hand-set number survives plan edits ----------------------------------------------

async def test_an_override_survives_plan_edits_until_it_is_cleared(mongo_db):
    await _tenant(mongo_db, "t1")
    out = await licensing.set_seat_override(mongo_db, "t1", 5)  # equal to the plan's number: still an override
    assert out["maxAgents"] == 5 and (await _doc(mongo_db, "t1"))["license"]["seatOverride"] == 5
    assert await licensing.apply_plan_seats(mongo_db, "Free", 8) == []
    assert await _seats(mongo_db, "t1") == 5
    out = await licensing.clear_seat_override(mongo_db, "t1", 8)
    stored = await _doc(mongo_db, "t1")
    assert out["maxAgents"] == 8 and "seatOverride" not in stored["license"]
    assert (stored["license"]["maxAgents"], stored["maxAgents"]) == (8, 8)
    assert await licensing.apply_plan_seats(mongo_db, "Free", 9) == ["t1"]


async def test_the_licence_patch_number_is_stored_as_an_override(mongo_db):
    await _tenant(mongo_db, "t1")
    out = await licensing.update_license(mongo_db, "t1", max_agents=9)
    stored = await _doc(mongo_db, "t1")
    assert out["maxAgents"] == 9 and stored["license"]["seatOverride"] == 9
    await licensing.apply_plan_seats(mongo_db, "Free", 7)
    assert await _seats(mongo_db, "t1") == 9
    await licensing.update_license(mongo_db, "t1", reclaim_days=10)  # no seat number: the override stays as it is
    assert (await _doc(mongo_db, "t1"))["license"]["seatOverride"] == 9


@pytest.mark.parametrize("bad", [True, 2.5, "7", -1, 1_000_001, None])
async def test_seat_numbers_must_be_whole_numbers_in_range_and_change_nothing(mongo_db, bad):
    await _tenant(mongo_db, "t1")
    for call in (licensing.set_seat_override(mongo_db, "t1", bad), licensing.clear_seat_override(mongo_db, "t1", bad),
                 licensing.apply_plan_seats(mongo_db, "Free", bad), licensing.set_plan_seats(mongo_db, "t1", bad)):
        with pytest.raises(ValueError):
            await call
    stored = await _doc(mongo_db, "t1")
    assert stored["license"]["maxAgents"] == 5 and "seatOverride" not in stored["license"]


@pytest.mark.parametrize("seats", [0, 1_000_000])
async def test_the_range_ends_are_accepted(mongo_db, seats):
    await _tenant(mongo_db, "t1")
    assert (await licensing.set_seat_override(mongo_db, "t1", seats))["maxAgents"] == seats


async def test_an_override_is_refused_for_partner_customers_the_platform_and_partners(mongo_db):
    await _partner(mongo_db)
    await _tenant(mongo_db, "c1", seats=30, partnerId="p1")
    await _tenant(mongo_db, "platform-admin")
    for tid in ("c1", "platform-admin", "p1"):
        with pytest.raises(ValueError):
            await licensing.set_seat_override(mongo_db, tid, 9)
        with pytest.raises(ValueError):
            await licensing.clear_seat_override(mongo_db, tid, 9)
    assert await _seats(mongo_db, "c1") == 30 and "seatOverride" not in (await _doc(mongo_db, "c1"))["license"]
    with pytest.raises(LookupError):
        await licensing.set_seat_override(mongo_db, "nope", 9)


async def test_set_plan_seats_skips_overrides_partner_customers_and_the_platform(mongo_db):
    await _tenant(mongo_db, "t1")
    await _tenant(mongo_db, "t2", **{"license": {"maxAgents": 12, "seatsUsed": 0, "seatOverride": 12}})
    await _partner(mongo_db)
    await _tenant(mongo_db, "c1", seats=30, partnerId="p1")
    await _tenant(mongo_db, "platform-admin")
    assert [await licensing.set_plan_seats(mongo_db, t, 50) for t in ("t1", "t2", "c1", "platform-admin")] \
        == [True, False, False, False]
    assert [await _seats(mongo_db, t) for t in ("t1", "t2", "c1", "platform-admin")] == [50, 12, 30, 5]


@pytest.mark.parametrize("override_first", [True, False])
async def test_a_concurrent_override_and_plan_edit_end_on_the_override(mongo_db, override_first):
    await _tenant(mongo_db, "t1")
    calls = [licensing.set_seat_override(mongo_db, "t1", 12), licensing.apply_plan_seats(mongo_db, "Free", 8)]
    await asyncio.gather(*(calls if override_first else calls[::-1]))
    stored = await _doc(mongo_db, "t1")
    assert (stored["license"]["maxAgents"], stored["maxAgents"], stored["license"]["seatOverride"]) == (12, 12, 12)


async def test_raise_direct_seats_adds_and_keeps_the_override_in_one_update(mongo_db):
    await _tenant(mongo_db, "t1", seats=10)
    assert await licensing.raise_direct_seats(mongo_db, "t1", 3) == 13
    stored = await _doc(mongo_db, "t1")
    assert (stored["license"]["maxAgents"], stored["license"]["seatOverride"], stored["maxAgents"]) == (13, 13, 13)
    await licensing.apply_plan_seats(mongo_db, "Free", 8)
    assert await _seats(mongo_db, "t1") == 13
    for bad in (0, -1, True, 1.5, 1_000_001):
        with pytest.raises(ValueError):
            await licensing.raise_direct_seats(mongo_db, "t1", bad)
    await _partner(mongo_db)
    await _tenant(mongo_db, "c1", seats=30, partnerId="p1")
    with pytest.raises(LookupError):  # a partner customer is raised through its pool, never here
        await licensing.raise_direct_seats(mongo_db, "c1", 1)


# -- the platform organization has no seat limit ---------------------------------------------------

async def test_platform_admin_never_runs_out_of_seats(mongo_db):
    await _tenant(mongo_db, "platform-admin", seats=5, used=5)
    assert await licensing.try_claim_seat(mongo_db, "platform-admin") is True
    assert (await _doc(mongo_db, "platform-admin"))["license"]["seatsUsed"] == 6
    assert await licensing.seats_available(mongo_db, await _doc(mongo_db, "platform-admin")) == licensing.MAX_AGENTS_CEILING
    await _tenant(mongo_db, "t1", seats=5, used=5)
    assert await licensing.try_claim_seat(mongo_db, "t1") is False


# -- the seat boundary at enrollment ---------------------------------------------------------------

async def test_the_next_machine_is_held_at_the_limit_and_enrolls_one_below_it(mongo_db):
    await harness.tenant(mongo_db, "t1", plan="Pro", max_agents=5)  # a Pro tenant has no trial to end
    await mongo_db.tenants.update_one({"id": "t1"}, {"$set": {"license.seatsUsed": 4}})
    code, _ = await harness.register(mongo_db, "m1", hardware=harness.hw("S1"))
    assert code == 200
    assert (await _doc(mongo_db, "t1"))["license"]["seatsUsed"] == 5
    code, body = await harness.register(mongo_db, "m2", hardware=harness.hw("S2"))
    assert code == 202 and body["pendingReason"] == "seat_limit"
