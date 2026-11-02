"""Phase 87 plan 10 (D-08): a partner's pool expiry holds new agents of its customers (real MongoDB).

Value: protects=once a partner's pool has expired a new machine of any of its customers waits for
approval as license_expired while agents already enrolled keep their status and seats, and direct
customers and unexpired pools are unaffected; fails_when=a new agent is admitted after the pool
expired, a running agent is touched, or a direct customer is held; no_claim=the enrollment HTTP route
(hold_reason is called directly, as the register route does).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import license_rules
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

PAST = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
FUTURE = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
HW = {"serialNumber": "PF3ABC12", "osFamily": "windows", "deviceType": "workstation"}


async def _partner(db, expires=None, pid="p1"):
    pool = {"poolSize": 100, "allocated": 10, "status": "active", "screenCeiling": ["all"]}
    if expires:
        pool["expiresAt"] = expires
    await db.tenants.insert_one({"id": pid, "name": "Partner", "type": "partner", "license": {"maxAgents": 0},
                                 "partner": pool})


async def _customer(db, partner_id=None, expires=None, cid="c1"):
    lic = {"maxAgents": 10, "seatsUsed": 1, "inactiveReclaimDays": 30}
    if expires:
        lic["expiresAt"] = expires
    doc = {"id": cid, "name": "Customer", "maxAgents": 10, "license": lic}
    if partner_id:
        doc["partnerId"] = partner_id
    await db.tenants.insert_one(doc)
    return doc


async def _hold(db, cid="c1"):
    return await license_rules.hold_reason(db, {"id": cid}, HW, "Windows")


async def test_a_new_agent_of_a_partner_customer_is_held_once_the_pool_expired(mongo_db):
    await _partner(mongo_db, expires=PAST)
    await _customer(mongo_db, "p1")
    assert await _hold(mongo_db) == "license_expired"


async def test_an_unexpired_pool_and_a_pool_without_expiry_admit_the_agent(mongo_db):
    await _partner(mongo_db, expires=FUTURE, pid="p1")
    await _partner(mongo_db, expires=None, pid="p2")
    await _customer(mongo_db, "p1", cid="c1")
    await _customer(mongo_db, "p2", cid="c2")
    assert await _hold(mongo_db, "c1") is None
    assert await _hold(mongo_db, "c2") is None


async def test_a_direct_customer_is_not_held(mongo_db):
    await _partner(mongo_db, expires=PAST)
    await _customer(mongo_db, None)
    assert await _hold(mongo_db) is None


async def test_the_customers_own_earlier_expiry_still_holds_the_agent(mongo_db):
    await _partner(mongo_db, expires=FUTURE)
    await _customer(mongo_db, "p1", expires=PAST)
    assert await _hold(mongo_db) == "license_expired"


async def test_a_customer_whose_partner_is_missing_is_not_held(mongo_db):
    await _customer(mongo_db, "gone")
    assert await _hold(mongo_db) is None


async def test_enrolled_agents_keep_status_and_seats_after_the_pool_expired(mongo_db):
    await _partner(mongo_db, expires=PAST)
    await _customer(mongo_db, "p1")
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": "c1", "hostname": "old", "status": "Online"})
    before_agent = await mongo_db.agents.find_one({"id": "a1"}, {"_id": 0})
    before_tenant = await mongo_db.tenants.find_one({"id": "c1"}, {"_id": 0})
    assert await _hold(mongo_db) == "license_expired"
    assert await mongo_db.agents.find_one({"id": "a1"}, {"_id": 0}) == before_agent
    assert await mongo_db.tenants.find_one({"id": "c1"}, {"_id": 0}) == before_tenant
