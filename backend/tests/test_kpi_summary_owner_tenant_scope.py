"""GET /api/kpi/summary counts the tenant the Platform Owner selected.

Value: protects=the Agents screen's agent, online and asset counts: an Owner who picks an
organization (X-Tenant-ID) counts only that organization, an Owner who picks none (or sends the
platform's own id) counts every tenant, and a tenant user counts only their own tenant whatever
header they send; fails_when=the Owner's header is ignored (a tenant shows every tenant's agents,
the Platform's own included), "platform-admin" narrows the Owner's all-tenants view to the
platform's own agents, or a tenant user's header widens or moves their count; no_claim=the
browser and /api/kpi/business-metrics.

Real MongoDB (skipped without one, and a skip is a failed gate), the real TenantMiddleware, real
signed session tokens and the real route and permission check.
"""
import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest

import database
import kpi_endpoints
import rbac_service
from authentication_service import create_access_token
from tenant_middleware import TenantMiddleware

SUMMARY = "/api/kpi/summary"
OWNER = ("Super Admin", "platform-admin")
# Agents per tenant, and how many of them are online.
FLEET = {"platform-admin": (1, 1), "tenant-a": (2, 1), "tenant-b": (3, 2)}


def token(role, tenant):
    return create_access_token({"sub": f"{role}@{tenant}", "role": role, "tenant_id": tenant, "mfa_verified": True})


def expected(*tenants):
    return {
        "totalAgents": sum(FLEET[t][0] for t in tenants),
        "onlineAgents": sum(FLEET[t][1] for t in tenants),
        "totalAssets": sum(FLEET[t][0] for t in tenants),
    }


@pytest_asyncio.fixture
async def fleet(mongo_db):
    for tenant, (total, online) in FLEET.items():
        await mongo_db.agents.insert_many([
            {"tenantId": tenant, "id": f"{tenant}-agent-{n}", "hostname": f"{tenant}-host-{n}",
             "status": "Online" if n < online else "Offline"}
            for n in range(total)
        ])
        await mongo_db.assets.insert_many([
            {"tenantId": tenant, "id": f"{tenant}-asset-{n}", "hostname": f"{tenant}-host-{n}"}
            for n in range(total)
        ])
    return mongo_db


@pytest_asyncio.fixture
async def client(monkeypatch, fleet):
    isolated = lambda: database.TenantIsolatedDatabase(fleet)  # noqa: E731
    monkeypatch.setattr(kpi_endpoints, "get_database", isolated)
    # The role store the permission check reads is the same throwaway database.
    monkeypatch.setattr(rbac_service, "get_database", isolated)
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(kpi_endpoints.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def counts(client, bearer, header=None):
    headers = {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}
    response = await client.get(SUMMARY, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {key: body[key] for key in ("totalAgents", "onlineAgents", "totalAssets")}


class TestOwnerScope:
    @pytest.mark.asyncio
    async def test_owner_without_a_tenant_counts_every_tenant(self, client):
        assert await counts(client, token(*OWNER)) == expected(*FLEET)

    @pytest.mark.asyncio
    async def test_owner_sending_the_platforms_own_id_still_counts_every_tenant(self, client):
        assert await counts(client, token(*OWNER), header="platform-admin") == expected(*FLEET)

    @pytest.mark.asyncio
    async def test_owner_header_counts_only_that_tenant(self, client):
        owner = token(*OWNER)
        assert await counts(client, owner, header="tenant-a") == expected("tenant-a")
        assert await counts(client, owner, header="tenant-b") == expected("tenant-b")


class TestTenantUserScope:
    @pytest.mark.asyncio
    async def test_tenant_user_counts_only_their_own_tenant(self, client):
        for tenant in ("tenant-a", "tenant-b"):
            assert await counts(client, token("admin", tenant)) == expected(tenant)

    @pytest.mark.asyncio
    async def test_tenant_user_header_for_another_tenant_changes_nothing(self, client):
        user = token("admin", "tenant-a")
        assert await counts(client, user, header="tenant-b") == expected("tenant-a")
        assert await counts(client, user, header="platform-admin") == expected("tenant-a")
