"""Spec C2: GET/PATCH /api/tenants/{id}/license authorization and audit (real MongoDB).

Value: protects=only a super admin changes a tenant's seat limit, the change is audited,
and a tenant user reads only its own license; fails_when=a tenant admin can PATCH, the
audit write is skipped, or another tenant's license is readable; no_claim=JWT handling
and the router (endpoint functions are called with a TokenData; the audit writer is
mocked).
"""
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
ADMIN_A = TokenData(username="admin@a.example", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)


async def _seed(db):
    await db.tenants.insert_many([
        {"id": "tenant-a", "name": "A", "license": {"maxAgents": 5, "seatsUsed": 2, "inactiveReclaimDays": 30}},
        {"id": "tenant-b", "name": "B", "maxAgents": 3},
    ])


async def test_tenant_admin_cannot_change_its_seat_limit(mongo_db):
    await _seed(mongo_db)
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)):
        with pytest.raises(HTTPException) as exc:
            await te.update_tenant_license("tenant-a", te.LicenseUpdate(maxAgents=500), current_user=ADMIN_A)
    assert exc.value.status_code == 403
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["maxAgents"] == 5


async def test_super_admin_changes_the_limit_and_it_is_audited(mongo_db):
    await _seed(mongo_db)
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit):
        out = await te.update_tenant_license("tenant-a", te.LicenseUpdate(maxAgents=50, inactiveReclaimDays=14),
                                             current_user=SUPER)
    assert (out["maxAgents"], out["seatsUsed"], out["inactiveReclaimDays"]) == (50, 2, 14)
    kwargs = audit.log_action_async.call_args.kwargs
    assert kwargs["action"] == "license.changed" and kwargs["tenant_id"] == "tenant-a"
    assert "5 -> 50" in kwargs["details"]


async def test_tenant_user_reads_only_its_own_license(mongo_db):
    await _seed(mongo_db)
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)):
        own = await te.get_tenant_license("tenant-a", current_user=ADMIN_A)
        assert (own["maxAgents"], own["seatsAvailable"]) == (5, 3)
        with pytest.raises(HTTPException) as exc:
            await te.get_tenant_license("tenant-b", current_user=ADMIN_A)
    assert exc.value.status_code == 403


def test_out_of_range_values_are_rejected():
    with pytest.raises(ValueError):
        te.LicenseUpdate(maxAgents=-1)
    with pytest.raises(ValueError):
        te.LicenseUpdate(inactiveReclaimDays=0)
