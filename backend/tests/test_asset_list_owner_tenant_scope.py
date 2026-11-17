"""GET /api/assets (and /api/assets/search) scopes the Platform Owner's list to the tenant the Owner selected.

Value: protects=an Owner who picks an organization (X-Tenant-ID, or the tenantId/tenant_id query
parameter) sees only that organization's assets, an Owner who picks none keeps the all-tenants
list, a tenant user always and only sees their own tenant whatever header or parameter they send,
and the 60-second list cache never hands one scope's list to another; fails_when=the Owner's
header or parameter is ignored (every tenant's assets come back), a tenant user's header or
parameter widens or moves their scope, or an Owner who switches tenant inside the cache window is
served the previous tenant's list; no_claim=the browser, the tenant switcher UI, and the finance
field strip (test_asset_finance_fields owns that).

Real MongoDB (skipped without one, and a skip is a failed gate), the real TenantMiddleware, real
signed session tokens and the real route. The list cache is an in-memory stand-in so the test never
reads or writes the live Redis.
"""
import json
import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest

import asset_endpoints
import cache_service
import database
import rbac_utils
from authentication_service import create_access_token
from tenant_middleware import TenantMiddleware

LIST = "/api/assets"
TENANTS = ("tenant-a", "tenant-b")


def _ids(tenant):
    return {f"{tenant}-asset-{n}" for n in (1, 2)}


def token(role, tenant, sub=None):
    return create_access_token({"sub": sub or f"{role}@{tenant}", "role": role, "tenant_id": tenant, "mfa_verified": True})


OWNER = ("Super Admin", "platform-admin")


class _JsonCache:
    """What Redis does to a value: it is stored as JSON text and read back as new objects."""
    enabled = True

    def __init__(self):
        self.store = {}

    def get(self, key):
        raw = self.store.get(key)
        return json.loads(raw) if raw is not None else None

    def set(self, key, value, ttl=None):
        self.store[key] = json.dumps(value, default=str)
        return True

    def delete_pattern(self, _pattern):
        self.store.clear()


@pytest.fixture(autouse=True)
def _private_cache(monkeypatch):
    monkeypatch.setattr(cache_service, "cache", _JsonCache())


@pytest_asyncio.fixture
async def two_tenants(mongo_db):
    for tenant in TENANTS:
        await mongo_db.assets.insert_many([
            {"tenantId": tenant, "id": asset_id, "hostname": f"{asset_id}-host", "name": asset_id,
             "lastScanned": "2026-11-16T10:00:00Z"}
            for asset_id in sorted(_ids(tenant))
        ])
    return mongo_db


@pytest.fixture
def app(monkeypatch, two_tenants):
    # The role store the permission check reads is the same throwaway database.
    monkeypatch.setattr(rbac_utils, "get_database", lambda: database.TenantIsolatedDatabase(two_tenants))
    application = FastAPI()
    application.add_middleware(TenantMiddleware)
    application.include_router(asset_endpoints.router)
    application.dependency_overrides[database.get_database] = lambda: database.TenantIsolatedDatabase(two_tenants)
    return application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def listing(client, bearer, *, header=None, params=None):
    headers = {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}
    response = await client.get(LIST, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


class TestOwnerScope:
    @pytest.mark.asyncio
    async def test_owner_without_a_tenant_gets_every_tenants_assets(self, client):
        assert await listing(client, token(*OWNER)) == _ids("tenant-a") | _ids("tenant-b")

    @pytest.mark.asyncio
    async def test_owner_header_gets_only_that_tenant(self, client):
        assert await listing(client, token(*OWNER), header="tenant-a") == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_owner_camel_case_param_gets_only_that_tenant(self, client):
        assert await listing(client, token(*OWNER), params={"tenantId": "tenant-a"}) == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_owner_snake_case_param_still_works(self, client):
        assert await listing(client, token(*OWNER), params={"tenant_id": "tenant-b"}) == _ids("tenant-b")

    @pytest.mark.asyncio
    async def test_owner_switching_tenant_inside_the_cache_window_gets_the_new_tenants_list(self, client):
        owner = token(*OWNER)
        assert await listing(client, owner, header="tenant-a") == _ids("tenant-a")
        assert await listing(client, owner, header="tenant-b") == _ids("tenant-b")
        assert await listing(client, owner) == _ids("tenant-a") | _ids("tenant-b")
        assert await listing(client, owner, params={"tenantId": "tenant-a"}) == _ids("tenant-a")
        assert cache_service.cache.store, "the repeated reads below must be served from the cache"
        assert await listing(client, owner, header="tenant-b") == _ids("tenant-b")
        assert await listing(client, owner, header="tenant-a") == _ids("tenant-a")


class TestTenantUserScope:
    @pytest.mark.asyncio
    async def test_tenant_user_sees_only_their_own_tenant(self, client):
        for tenant in TENANTS:
            assert await listing(client, token("admin", tenant)) == _ids(tenant)

    @pytest.mark.asyncio
    async def test_tenant_user_header_for_another_tenant_changes_nothing(self, client):
        assert await listing(client, token("admin", "tenant-a"), header="tenant-b") == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_tenant_user_params_for_another_tenant_change_nothing(self, client):
        user = token("admin", "tenant-a")
        assert await listing(client, user, params={"tenantId": "tenant-b"}) == _ids("tenant-a")
        assert await listing(client, user, params={"tenant_id": "tenant-b"}) == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_tenant_user_probing_other_tenants_never_poisons_the_cache_for_the_owner_or_the_other_tenant(self, client):
        user_a = token("admin", "tenant-a")
        assert await listing(client, user_a, header="tenant-b") == _ids("tenant-a")
        assert await listing(client, user_a, params={"tenantId": "tenant-b"}) == _ids("tenant-a")
        assert await listing(client, token("admin", "tenant-b")) == _ids("tenant-b")
        assert await listing(client, token(*OWNER), header="tenant-b") == _ids("tenant-b")


async def searching(client, bearer, *, header=None):
    headers = {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}
    response = await client.get(f"{LIST}/search", headers=headers, params={"q": "asset"})
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()}


class TestSearchScope:
    """GET /api/assets/search covers the same tenant as the list."""

    @pytest.mark.asyncio
    async def test_owner_without_a_tenant_searches_every_tenant(self, client):
        assert await searching(client, token(*OWNER)) == _ids("tenant-a") | _ids("tenant-b")

    @pytest.mark.asyncio
    async def test_owner_header_searches_only_that_tenant_even_inside_the_cache_window(self, client):
        owner = token(*OWNER)
        assert await searching(client, owner, header="tenant-a") == _ids("tenant-a")
        assert await searching(client, owner, header="tenant-b") == _ids("tenant-b")
        assert await searching(client, owner, header="tenant-a") == _ids("tenant-a")

    @pytest.mark.asyncio
    async def test_tenant_user_header_for_another_tenant_changes_nothing(self, client):
        assert await searching(client, token("admin", "tenant-a"), header="tenant-b") == _ids("tenant-a")
