"""Phase 87 tracer: appoint a partner, create a customer from its pool, read the overview (real MongoDB).

Value: protects=the partner channel's stored shape, the atomic pool claim, the token-only
partner scoping and the D-01 customer row allowlist; fails_when=a customer is created past the
pool, a Super Admin or a non-partner reaches /api/partner, the overview carries a field outside
D-01, or a partner route is mounted without its catalogue guard; no_claim=JWT handling and the
frontend (route functions are called with a TokenData, the audit writer is mocked).
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import partner_platform_endpoints as ppe
import partner_pool
import partner_store
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)


def _partner_user(partner_id, role="partner_admin"):
    return TokenData(username=f"{role}@retailer.example", role=role, tenant_id=partner_id, mfa_verified=True)


@pytest.fixture
def wired(mongo_db):
    """Both endpoint modules read the test database; the audit ledger never reaches a real one."""
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(pe, "mongodb", handle), patch.object(ppe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db, audit=audit)


async def _appoint(pool_size=100, name="Retailer A"):
    email = f"boss@{name.lower().replace(' ', '')}.example"
    out = await ppe.create_partner(ppe.PartnerCreate(name=name, poolSize=pool_size, screenCeiling=["all"],
                                                     adminName="Boss", adminEmail=email), current_user=SUPER)
    return out["partner"]["id"]


async def _admin_ctx(partner_id, role="partner_admin"):
    return await pe.current_partner(current_user=_partner_user(partner_id, role))


async def test_appoint_stores_the_partner_shape(wired):
    partner_id = await _appoint()
    doc = await wired.db.tenants.find_one({"id": partner_id})
    assert doc["type"] == "partner"
    assert doc["partner"]["poolSize"] == 100 and doc["partner"]["allocated"] == 0
    assert doc["partner"]["status"] == "active" and doc["partner"]["screenCeiling"] == ["all"]
    assert doc["license"]["maxAgents"] == 0 and doc["enabledFeatures"] == []
    assert "registrationKey" not in doc and "agentCapabilities" not in doc
    listed = await ppe.list_partners(current_user=SUPER)
    assert [p["id"] for p in listed["partners"]] == [partner_id]
    assert listed["partners"][0]["free"] == 100 and listed["partners"][0]["unrestricted"] is True


async def test_a_partner_admin_cannot_appoint(wired):
    with pytest.raises(HTTPException) as exc:
        await ppe.create_partner(ppe.PartnerCreate(name="X", poolSize=5, screenCeiling=[], adminName="B",
                                                   adminEmail="b@x.example"),
                                 current_user=_partner_user("partner_x"))
    assert exc.value.status_code == 403


async def test_customer_creation_draws_from_the_pool(wired):
    partner_id = await _appoint()
    ctx = await _admin_ctx(partner_id)
    out = await pe.post_customer(pe.CustomerCreate(name="Cafe One", seats=30), ctx=ctx)
    customer = await wired.db.tenants.find_one({"id": out["customer"]["id"]})
    assert customer["partnerId"] == partner_id
    assert customer["license"]["maxAgents"] == 30 and customer["maxAgents"] == 30
    assert customer["registrationKey"].startswith("reg_") and customer["agentCapabilities"]
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["allocated"] == 30
    created = [c for c in wired.audit.await_args_list if c.args[0] == "partner.customer_created"]
    assert len(created) == 1 and created[0].args[1] == partner_id


async def test_a_full_pool_refuses_with_the_free_count(wired):
    partner_id = await _appoint()
    ctx = await _admin_ctx(partner_id)
    await pe.post_customer(pe.CustomerCreate(name="Cafe One", seats=30), ctx=ctx)
    refused = await pe.post_customer(pe.CustomerCreate(name="Cafe Two", seats=80), ctx=ctx)
    assert refused.status_code == 409
    body = json.loads(refused.body)
    assert body["code"] == "pool_full" and body["free"] == 70 and body["status_code"] == 409
    assert "70" in body["error"]
    assert await wired.db.tenants.count_documents({"partnerId": partner_id}) == 1
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["allocated"] == 30


async def test_concurrent_creations_never_exceed_the_pool(wired):
    partner_id = await _appoint(pool_size=50)
    ctx = await _admin_ctx(partner_id)
    results = await asyncio.gather(*(
        pe.post_customer(pe.CustomerCreate(name=f"Shop {i}", seats=10), ctx=ctx) for i in range(12)))
    made = [r for r in results if isinstance(r, dict)]
    assert len(made) == 5
    doc = await wired.db.tenants.find_one({"id": partner_id})
    assert doc["partner"]["allocated"] == 50
    assert await wired.db.tenants.count_documents({"partnerId": partner_id}) == 5


async def test_a_taken_name_is_refused_without_a_claim(wired):
    partner_id = await _appoint()
    ctx = await _admin_ctx(partner_id)
    await pe.post_customer(pe.CustomerCreate(name="Cafe One", seats=5), ctx=ctx)
    refused = await pe.post_customer(pe.CustomerCreate(name="  cafe one ", seats=5), ctx=ctx)
    assert refused.status_code == 409 and json.loads(refused.body)["code"] == "name_unavailable"
    assert (await wired.db.tenants.find_one({"id": partner_id}))["partner"]["allocated"] == 5


async def test_overview_carries_only_the_d01_fields(wired):
    partner_id = await _appoint()
    ctx = await _admin_ctx(partner_id)
    made = await pe.post_customer(pe.CustomerCreate(name="Cafe One", seats=30), ctx=ctx)
    await wired.db.agents.insert_many([
        {"id": "a1", "hostname": "h1", "tenantId": made["customer"]["id"], "status": "Online"},
        {"id": "a2", "hostname": "h2", "tenantId": made["customer"]["id"], "status": "Offline"},
        {"id": "a3", "hostname": "h3", "tenantId": made["customer"]["id"], "status": "Pending"},
    ])
    # A direct customer and another partner's customer must never show up.
    await wired.db.tenants.insert_one({"id": "tenant_direct", "name": "Direct", "license": {"maxAgents": 9}})
    other = await _appoint(name="Retailer B")
    await pe.post_customer(pe.CustomerCreate(name="Other Shop", seats=5), ctx=await _admin_ctx(other))
    out = await pe.get_overview(ctx=await _admin_ctx(partner_id))  # each request loads the partner afresh
    assert out["pool"] == {"size": 100, "handedOut": 30, "free": 70, "expiresAt": None, "expired": False}
    assert len(out["customers"]) == 1
    row = out["customers"][0]
    assert tuple(row) == partner_store.CUSTOMER_FIELDS
    assert (row["name"], row["seatsAssigned"], row["agentsOnline"], row["agentsTotal"]) == ("Cafe One", 30, 1, 2)
    assert out["role"] == "admin" and out["partner"] == {"name": "Retailer A"}


async def test_current_partner_refuses_everyone_else(wired):
    partner_id = await _appoint()
    await wired.db.tenants.insert_one({"id": "tenant_plain", "name": "Plain Co"})
    for user in (SUPER, _partner_user("tenant_plain"), _partner_user("missing_org"),
                 TokenData(username="a@x", role="Tenant Admin", tenant_id=partner_id, mfa_verified=True)):
        with pytest.raises(HTTPException) as exc:
            await pe.current_partner(current_user=user)
        assert exc.value.status_code == 403
    await wired.db.tenants.update_one({"id": partner_id}, {"$set": {"partner.status": "suspended"}})
    with pytest.raises(HTTPException) as exc:
        await _admin_ctx(partner_id)
    assert exc.value.status_code == 403 and "suspended" in exc.value.detail


async def test_a_partner_viewer_reads_but_cannot_create(wired):
    partner_id = await _appoint()
    ctx = await _admin_ctx(partner_id, role="partner_viewer")
    assert (await pe.get_overview(ctx=ctx))["role"] == "viewer"
    with pytest.raises(HTTPException) as exc:
        await pe.post_customer(pe.CustomerCreate(name="Nope", seats=1), ctx=ctx)
    assert exc.value.status_code == 403


async def test_claim_and_release_are_bounded(wired):
    partner_id = await _appoint(pool_size=10)
    # A release the counter cannot cover is repaired to the true sum (87-03), so the customers hold 6.
    await wired.db.tenants.insert_one({"id": "held", "name": "Held", "partnerId": partner_id,
                                       "license": {"maxAgents": 6}})
    assert await partner_pool.claim(wired.db, partner_id, 10) is True
    assert await partner_pool.claim(wired.db, partner_id, 1) is False
    await partner_pool.release(wired.db, partner_id, 4)
    assert await partner_pool.free_seats(wired.db, partner_id) == 4
    await partner_pool.release(wired.db, partner_id, 99)  # never below zero
    assert await partner_pool.free_seats(wired.db, partner_id) == 4


def test_the_mounted_routes_carry_their_catalogue_guards():
    from tests._route_walk import run_real_app_walk
    seen = {}
    for rec in run_real_app_walk()["routes"]:
        if rec["path"].startswith(("/api/platform/partners", "/api/partner")):
            for method in rec["methods"]:
                seen[(method, rec["path"])] = [t["catalogue"] for t in rec["tags"]]
    assert seen[("GET", "/api/platform/partners")] == ["partners"]
    assert seen[("POST", "/api/platform/partners")] == ["partners"]
    assert seen[("GET", "/api/partner/overview")] == ["partnerPortal"]
    assert seen[("POST", "/api/partner/customers")] == ["partnerPortal"]
    assert all(len(v) == 1 for v in seen.values())
