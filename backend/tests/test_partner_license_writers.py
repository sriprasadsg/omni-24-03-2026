"""Phase 87 plan 10: every other writer of a customer's seats respects the partner pool (real MongoDB).

Value: protects=a partner's pool total holds for the licence PATCH, approve-and-raise, customer
deletion and the direct create path, and no new module can write license.maxAgents behind the
pool's back; fails_when=a PATCH or approval lifts a partner customer past the pool, a refusal still
changes a document, deleting a customer leaks its seats, a partner with customers can be deleted, or
a new seat writer appears outside the allowlist; no_claim=the HTTP layer (route functions are called
directly with a TokenData, the audit writers are mocked).
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tenant_endpoints as te
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)

PRE_CHANGE_KEYS = {"id", "name", "subscriptionTier", "registrationKey", "enabledFeatures", "agentCapabilities",
                   "notificationPreferences", "emailConfig", "maxAgents", "license", "createdAt", "updatedAt"}


@pytest.fixture
def wired(mongo_db):
    """The tenant routes run against the private database; auditing and session revocation are mocked."""
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit), \
            patch.object(te, "get_database", return_value=mongo_db), \
            patch.object(te, "revoke_user_sessions", new=AsyncMock()):
        yield mongo_db


async def _partner(db, pool=100, allocated=0, status="active", pid="p1", expires=None):
    doc = {"id": pid, "name": f"Partner {pid}", "type": "partner", "license": {"maxAgents": 0},
           "partner": {"poolSize": pool, "allocated": allocated, "status": status, "screenCeiling": ["all"]}}
    if expires:
        doc["partner"]["expiresAt"] = expires
    await db.tenants.insert_one(doc)
    return pid


async def _customer(db, partner_id, seats, used=0, cid="c1"):
    doc = {"id": cid, "name": f"Customer {cid}", "maxAgents": seats,
           "license": {"maxAgents": seats, "seatsUsed": used, "inactiveReclaimDays": 30}}
    if partner_id:
        doc["partnerId"] = partner_id
    await db.tenants.insert_one(doc)
    return cid


async def _allocated(db, pid="p1"):
    return (await db.tenants.find_one({"id": pid}))["partner"]["allocated"]


async def _seats(db, cid="c1"):
    return (await db.tenants.find_one({"id": cid}))["license"]["maxAgents"]


def _body(resp):
    return json.loads(resp.body)


async def test_create_tenant_uses_the_shared_builder_and_stores_the_same_fields(wired):
    import tenant_docs
    with patch.object(tenant_docs, "build_tenant_doc", wraps=tenant_docs.build_tenant_doc) as builder:
        out = await te.create_tenant(te.TenantCreate(name="Direct Co", maxAgents=7), current_user=SUPER)
    assert builder.call_count == 1
    stored = await wired.tenants.find_one({"id": out["id"]}, {"_id": 0})
    assert set(stored) == PRE_CHANGE_KEYS and "partnerId" not in stored
    assert stored["license"]["maxAgents"] == 7 and stored["registrationKey"].startswith("reg_")


async def test_patch_seats_on_a_partner_customer_claims_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=50), current_user=SUPER)
    assert out["maxAgents"] == 50
    assert (await _seats(wired), await _allocated(wired)) == (50, 95)


async def test_patch_past_the_pool_answers_pool_full_and_changes_nothing(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    resp = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=80), current_user=SUPER)
    assert resp.status_code == 409
    body = _body(resp)
    assert body["code"] == "pool_full" and body["free"] == 25
    assert (await _seats(wired), await _allocated(wired)) == (30, 75)


async def test_patch_below_the_seats_used_succeeds_and_returns_the_seats(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30, used=30)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=10), current_user=SUPER)
    assert (out["maxAgents"], out["seatsUsed"]) == (10, 30)
    assert (await _seats(wired), await _allocated(wired)) == (10, 55)


async def test_a_raise_ignores_the_partners_suspension_and_expiry_but_not_the_pool_total(wired):
    await _partner(wired, pool=100, allocated=75, status="suspended", expires="2020-01-01T00:00:00+00:00")
    await _customer(wired, "p1", 30)
    await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=40), current_user=SUPER)
    assert (await _seats(wired), await _allocated(wired)) == (40, 85)
    resp = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=200), current_user=SUPER)
    assert resp.status_code == 409 and _body(resp)["code"] == "pool_full"


async def test_patching_only_the_reclaim_window_never_touches_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    with patch("partner_pool.change_allotment", new=AsyncMock()) as change:
        out = await te.update_tenant_license("c1", te.LicenseUpdate(inactiveReclaimDays=14), current_user=SUPER)
    assert out["inactiveReclaimDays"] == 14 and change.await_count == 0
    assert (await _seats(wired), await _allocated(wired)) == (30, 75)


async def test_a_direct_customer_is_patched_as_before(wired):
    await _customer(wired, None, 5)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=500), current_user=SUPER)
    assert out["maxAgents"] == 500 and await _seats(wired) == 500


async def test_deleting_a_partner_customer_returns_its_seats_to_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    await te.delete_tenant("c1", current_user=SUPER)
    assert await wired.tenants.find_one({"id": "c1"}) is None
    assert await _allocated(wired) == 45


async def test_deleting_a_partner_with_customers_is_refused_and_deletes_nothing(wired):
    await _partner(wired, pool=100, allocated=30)
    await _customer(wired, "p1", 30)
    with pytest.raises(HTTPException) as exc:
        await te.delete_tenant("p1", current_user=SUPER)
    assert exc.value.status_code == 409 and exc.value.detail == "Move this partner's customers first."
    assert await wired.tenants.find_one({"id": "p1"}) is not None
    assert await _seats(wired) == 30


async def test_deleting_a_partner_without_customers_works(wired):
    await _partner(wired, pool=100, allocated=0)
    await te.delete_tenant("p1", current_user=SUPER)
    assert await wired.tenants.find_one({"id": "p1"}) is None
