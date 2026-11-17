"""GET /api/itam/costs/summary - Phase 78 Plan 01 (COST-01, COST-02, COST-06, COST-07).

The tracer test runs against a real throwaway MongoDB (mongo_db fixture) with the production
TenantIsolatedDatabase wrapper, so the tenant resolver's ambient-tenant write is what scopes
the reads, exactly as in production. The resolver matrix patches nothing but the clock.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest
from tests.conftest import make_test_app, make_token_data

import database
import itam_asset_endpoints
import itam_cost_endpoints
import itam_cost_service
import tenant_context
from api_key_auth import get_current_user_or_api_key
from auth_types import TokenData
from authentication_service import get_current_user as real_get_current_user
from itam_finance_service import compute_book_value
from itam_tenant_scope import UNKNOWN_TENANT_DETAIL

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
A1_PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()
A2_PURCHASE = (FIXED_NOW - timedelta(days=100)).isoformat()
A3_PURCHASE = (FIXED_NOW - timedelta(days=500)).isoformat()


@pytest.fixture(autouse=True)
def _clean_ambient_tenant():
    """The resolver sets the ambient tenant inside the handler's context; TenantMiddleware
    restores it in production, so a test app without that middleware must do it here."""
    token = tenant_context.set_tenant_id(None)
    yield
    tenant_context.reset_tenant_id(token)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED_NOW)


def _asset(tenant, asset_id, *, status, cost, purchase_date, model_id, name=None):
    return {
        "tenantId": tenant, "id": asset_id, "assetTag": f"TAG-{asset_id}", "name": name or asset_id,
        "lifecycleStatus": status, "modelId": model_id,
        "purchaseCostCents": cost, "purchaseDate": purchase_date,
    }


async def _seed(db):
    # An Owner's X-Tenant-ID must name an existing tenant (IN-01).
    await db.tenants.insert_many([{"id": "tenant-a", "name": "Tenant A"}, {"id": "tenant-b", "name": "Tenant B"}])
    await db.asset_models.insert_many([
        {"tenantId": "tenant-a", "id": "model-ok", "usefulLifeYears": 3, "salvageValueCents": 10000},
        {"tenantId": "tenant-b", "id": "model-b", "usefulLifeYears": 4, "salvageValueCents": 0},
    ])
    await db.assets.insert_many([
        _asset("tenant-a", "A1", status="deployed", cost=120000, purchase_date=A1_PURCHASE, model_id="model-ok"),
        _asset("tenant-a", "A2", status="deployable", cost=50000, purchase_date=A2_PURCHASE, model_id="model-missing"),
        _asset("tenant-a", "A3", status="disposed", cost=90000, purchase_date=A3_PURCHASE, model_id="model-ok"),
        _asset("tenant-b", "B1", status="deployed", cost=777000, purchase_date=A1_PURCHASE, model_id="model-b"),
        _asset("tenant-b", "B2", status="deployed", cost=333000, purchase_date=A1_PURCHASE, model_id="model-b"),
    ])


def _client(app, user):
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    app.dependency_overrides[real_get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _app(monkeypatch, db=None, permission_ok=True):
    if db is not None:
        monkeypatch.setattr(itam_cost_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(db))
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=permission_ok))
    app, _ = make_test_app(itam_cost_endpoints.router)
    return app


def _tenant_admin(tenant="tenant-a"):
    return make_token_data(tenant_id=tenant, role="admin", username="admin@example.com")


def _owner():
    return make_token_data(role="Super Admin", tenant_id="platform-admin", username="owner@example.com")


URL = "/api/itam/costs/summary"


class TestSummaryTracer:
    @pytest.mark.asyncio
    async def test_summary_tracer_real_mongo(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(URL)
        assert r.status_code == 200, r.text
        body = r.json()
        expected_bv = compute_book_value(A1_PURCHASE, 120000, 3, 10000, FIXED_NOW)["bookValueCents"]
        assert body["tenantId"] == "tenant-a"
        assert body["includeDisposed"] is False
        assert body["computedAt"] == FIXED_NOW.isoformat(timespec="milliseconds")
        assert body["bookValueTotal"] == {"cents": expected_bv, "hasData": True}
        assert body["purchaseTotal"] == {"cents": 170000, "hasData": True}
        cov = body["coverage"]
        assert (cov["total"], cov["priced"], cov["valued"], cov["excludedByLifecycle"]) == (2, 2, 1, 1)
        assert cov["reasons"]["no_depreciation_policy_assigned"] == 1
        assert sum(cov["reasons"].values()) + cov["valued"] == cov["total"]
        assert "777000" not in r.text and "tenant-b" not in r.text

    @pytest.mark.asyncio
    async def test_summary_include_disposed(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(URL, params={"includeDisposed": "true"})
        assert r.status_code == 200, r.text
        body = r.json()
        expected_bv = compute_book_value(A1_PURCHASE, 120000, 3, 10000, FIXED_NOW)["bookValueCents"]
        assert body["includeDisposed"] is True
        assert body["purchaseTotal"]["cents"] == 260000
        assert body["bookValueTotal"]["cents"] == expected_bv
        cov = body["coverage"]
        assert (cov["total"], cov["excludedByLifecycle"]) == (3, 0)
        assert cov["reasons"]["disposed"] == 1

    @pytest.mark.asyncio
    async def test_empty_tenant_summary(self, mongo_db, monkeypatch):
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _tenant_admin("tenant-empty")) as ac:
            r = await ac.get(URL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["purchaseTotal"] == {"cents": None, "hasData": False}
        assert body["bookValueTotal"] == {"cents": None, "hasData": False}
        cov = body["coverage"]
        assert (cov["total"], cov["priced"], cov["valued"], cov["excludedByLifecycle"]) == (0, 0, 0, 0)
        assert set(cov["reasons"].values()) == {0}


class TestTenantResolver:
    @pytest.mark.asyncio
    async def test_owner_without_tenant_gets_400_before_db(self, monkeypatch):
        app = _app(monkeypatch)

        def _never():
            raise AssertionError("get_database must not be reached before the tenant is resolved")

        monkeypatch.setattr(itam_cost_endpoints, "get_database", _never)
        async with _client(app, _owner()) as ac:
            r = await ac.get(URL)
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_owner_with_header_reads_that_tenant(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _owner()) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-b"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenantId"] == "tenant-b"
        assert body["purchaseTotal"]["cents"] == 1110000

    @pytest.mark.asyncio
    async def test_owner_header_for_an_unknown_tenant_is_400(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _owner()) as ac:
            for url in (URL, "/api/itam/costs/assets", "/api/itam/costs/assets/A1"):
                r = await ac.get(url, headers={"X-Tenant-ID": "tenant-typo"})
                assert r.status_code == 400, url
                assert r.json()["detail"] == UNKNOWN_TENANT_DETAIL
                assert "tenant-typo" not in r.text

    @pytest.mark.asyncio
    async def test_owner_header_platform_admin_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        async with _client(app, _owner()) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "platform-admin"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_support_cannot_choose_a_tenant(self, monkeypatch):
        app = _app(monkeypatch)
        support = make_token_data(role="platform_support", tenant_id="platform-admin")
        async with _client(app, support) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-a"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_tenant_user_header_is_ignored(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        app = _app(monkeypatch, mongo_db)
        async with _client(app, _tenant_admin("tenant-a")) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-b"})
        assert r.status_code == 200, r.text
        assert r.json()["tenantId"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_api_key_owner_header_is_ignored(self, monkeypatch):
        app = _app(monkeypatch)
        key = TokenData(username="key", role="Super Admin", tenant_id="platform-admin",
                        auth_source="api_key", scopes=["view:itam"])
        async with _client(app, key) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-a"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_tenant_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        async with _client(app, _tenant_admin(None)) as ac:
            r = await ac.get(URL)
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_resolver_sets_ambient_tenant(self, monkeypatch):
        app = _app(monkeypatch)

        class _Tenants:
            @staticmethod
            async def find_one(*args, **kwargs):
                return {"id": "tenant-b"}

        monkeypatch.setattr(itam_cost_endpoints, "get_database", lambda: type("Db", (), {"tenants": _Tenants})())
        seen = {}

        async def _spy(db, tenant_id, **kwargs):
            seen["ambient"] = tenant_context.get_tenant_id()
            seen["tenant_id"] = tenant_id
            return {"rows": [], "summary": {"tenantId": tenant_id}}

        monkeypatch.setattr(itam_cost_endpoints, "compute_tenant_costs", _spy)
        async with _client(app, _owner()) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-b"})
        assert r.status_code == 200, r.text
        assert seen == {"ambient": "tenant-b", "tenant_id": "tenant-b"}


class TestGuardAndErrors:
    @pytest.mark.asyncio
    async def test_summary_403_without_view_itam(self, monkeypatch):
        app = _app(monkeypatch, permission_ok=False)
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(URL)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_500_generic_detail(self, monkeypatch):
        app = _app(monkeypatch)
        monkeypatch.setattr(itam_cost_endpoints, "get_database", lambda: object())

        async def _boom(db, tenant_id, **kwargs):
            raise RuntimeError("boom secret")

        monkeypatch.setattr(itam_cost_endpoints, "compute_tenant_costs", _boom)
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(URL)
        assert r.status_code == 500
        assert r.json()["detail"] == "Internal server error"
        assert "boom" not in r.text
