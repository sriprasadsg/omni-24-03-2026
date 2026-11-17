"""GET /api/assets/reports/overdue-audit covers one organization, like the other ITAM reports.

Value: protects=the overdue-audit report never mixes tenants: the Platform Owner gets the tenant
the switcher names (X-Tenant-ID), an Owner who names none is asked to pick one (400), and a tenant
user gets their own tenant whatever header they send; fails_when=the Owner's report lists every
tenant's overdue assets, or a tenant user's header moves their report to another tenant;
no_claim=the permission and catalogue checks (overridden here; their own suites own them) and the
overdue rule itself (test_itam_lifecycle_audit owns it).

Real MongoDB through the real tenant-isolating wrapper (skipped without one, and a skip is a failed
gate), and the real route and tenant resolver.
"""
import os
import sys
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest

import database
import itam_asset_endpoints
import itam_lifecycle_endpoints
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from catalogue_mounts_assets import ITAM_API_KEY_GUARD

REPORT = "/api/assets/reports/overdue-audit"
TENANTS = ("tenant-a", "tenant-b")


def _ids(tenant):
    return {f"{tenant}-asset-{n}" for n in (1, 2)}


@pytest_asyncio.fixture
async def never_audited(mongo_db):
    await mongo_db.tenants.insert_many([{"id": tenant, "name": tenant} for tenant in TENANTS])
    for tenant in TENANTS:
        # Never audited and created long ago, so every one of them is overdue.
        await mongo_db.assets.insert_many([
            {"tenantId": tenant, "id": asset_id, "name": asset_id, "createdAt": "2020-01-01T00:00:00+00:00"}
            for asset_id in sorted(_ids(tenant))
        ])
    return mongo_db


@pytest.fixture
def as_user(monkeypatch, never_audited):
    monkeypatch.setattr(itam_lifecycle_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(never_audited))
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    def build(role, tenant):
        user = TokenData(username=f"{role}@{tenant}", role=role, tenant_id=tenant, mfa_verified=True)
        app = FastAPI()
        app.include_router(itam_lifecycle_endpoints.router)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: user
        app.dependency_overrides[ITAM_API_KEY_GUARD] = lambda: user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    return build


async def report(client, header=None):
    async with client:
        return await client.get(REPORT, headers={"X-Tenant-ID": header} if header is not None else {})


def _rows(response):
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["rows"]}


class TestOwnerScope:
    @pytest.mark.asyncio
    async def test_owner_header_reports_only_that_tenant(self, as_user):
        for tenant in TENANTS:
            assert _rows(await report(as_user("Super Admin", "platform-admin"), header=tenant)) == _ids(tenant)

    @pytest.mark.asyncio
    async def test_owner_without_a_tenant_is_asked_to_pick_one(self, as_user):
        response = await report(as_user("Super Admin", "platform-admin"))
        assert response.status_code == 400, response.text


class TestTenantUserScope:
    @pytest.mark.asyncio
    async def test_tenant_user_reports_their_own_tenant(self, as_user):
        assert _rows(await report(as_user("admin", "tenant-a"))) == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_tenant_user_header_for_another_tenant_changes_nothing(self, as_user):
        assert _rows(await report(as_user("admin", "tenant-a"), header="tenant-b")) == _ids("tenant-a")
