"""Spec C1 AC1/AC2: what Platform Support and Platform Billing may do on the real routes.

Value: protects=support reads every tenant and changes nothing; billing reads tenants
and changes only seat licenses and Pending agents; fails_when=support's PATCH/DELETE of a
tenant, or any mutating route of the real app, gets past the read-only guard, or billing
can delete a tenant or create a user; no_claim=handlers are called directly with a
TokenData (JWT parsing and the HTTP stack are covered in test_platform_roles); the
route walk checks the guard's decision per route, it does not execute the handlers.
"""
import os
import re
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tenant_endpoints as te
import tenant_middleware
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._route_walk import run_real_app_walk

SUPPORT = TokenData(username="support@platform", role="Platform Support", tenant_id="platform-admin", mfa_verified=True)
BILLING = TokenData(username="billing@platform", role="Platform Billing", tenant_id="platform-admin", mfa_verified=True)
ADMIN_A = TokenData(username="admin@a", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)


async def _seed(db):
    await db.tenants.insert_many([
        {"id": "tenant-a", "name": "A", "license": {"maxAgents": 5, "seatsUsed": 2, "inactiveReclaimDays": 30}},
        {"id": "tenant-b", "name": "B", "maxAgents": 3},
    ])


@pytest.mark.parametrize("user", [SUPPORT, BILLING], ids=["support", "billing"])
async def test_platform_staff_list_every_tenant(mongo_db, user):
    await _seed(mongo_db)
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)):
        tenants = await te.get_tenants(current_user=user)
        assert {t["id"] for t in tenants} == {"tenant-a", "tenant-b"}
        lic = await te.get_tenant_license("tenant-b", current_user=user)
        assert lic["maxAgents"] == 3


async def test_a_tenant_admin_cannot_list_tenants(mongo_db):
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), pytest.raises(HTTPException) as exc:
        await te.get_tenants(current_user=ADMIN_A)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("user", [SUPPORT, BILLING], ids=["support", "billing"])
async def test_platform_staff_cannot_change_or_delete_a_tenant(mongo_db, user):
    await _seed(mongo_db)
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)):
        with pytest.raises(HTTPException) as exc:
            await te.update_tenant("tenant-a", te.TenantUpdate(subscriptionTier="Free"), current_user=user)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await te.delete_tenant("tenant-a", current_user=user)
        assert exc.value.status_code == 403
    assert await mongo_db.tenants.count_documents({}) == 2


async def test_billing_changes_a_seat_license_and_support_cannot(mongo_db):
    await _seed(mongo_db)
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit):
        with pytest.raises(HTTPException) as exc:
            await te.update_tenant_license("tenant-a", te.LicenseUpdate(maxAgents=50), current_user=SUPPORT)
        assert exc.value.status_code == 403
        out = await te.update_tenant_license("tenant-a", te.LicenseUpdate(maxAgents=50), current_user=BILLING)
    assert out["maxAgents"] == 50
    assert audit.log_action_async.call_args.kwargs["user_name"] == "billing@platform"


async def test_billing_cannot_create_users():
    """POST /api/users is gated by manage:assets, which billing does not hold."""
    from itam_asset_endpoints import _require_itam_admin_session_only
    with pytest.raises(HTTPException) as exc:
        await _require_itam_admin_session_only(BILLING)
    assert exc.value.status_code == 403
    assert tenant_middleware.platform_write_refusal(BILLING.role, "POST", "/api/users")


# ── Every mutating route of the real app ──────────────────────────────────────

_SELF_SERVICE = re.compile(r"^/api/(auth|mfa|passkey)/|^/api/users/me/")
_BILLING_OWN = re.compile(r"^/api/tenants/x/(license|allowlist|enrollment-keys)(/|$)|^/api/agents/pending(/|$)")


@pytest.fixture(scope="module")
def mutating_routes():
    routes = []
    for record in run_real_app_walk()["routes"]:
        for method in record["methods"]:
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                routes.append((method, re.sub(r"\{[^}]+\}", "x", record["path"])))
    assert len(routes) > 500
    return routes


def test_support_is_refused_every_mutating_route_but_its_own_sign_in(mutating_routes):
    allowed = [(m, p) for m, p in mutating_routes if not tenant_middleware.platform_write_refusal("Platform Support", m, p)]
    unexpected = [(m, p) for m, p in allowed if not _SELF_SERVICE.search(p)]
    assert unexpected == [], unexpected
    assert ("POST", "/api/auth/logout") in allowed


def test_billing_reaches_only_licenses_pending_agents_and_its_own_sign_in(mutating_routes):
    allowed = [(m, p) for m, p in mutating_routes if not tenant_middleware.platform_write_refusal("Platform Billing", m, p)]
    unexpected = [(m, p) for m, p in allowed if not (_SELF_SERVICE.search(p) or _BILLING_OWN.search(p))]
    assert unexpected == [], unexpected
    assert ("PATCH", "/api/tenants/x/license") in allowed
    assert ("POST", "/api/agents/pending/x/approve") in allowed
