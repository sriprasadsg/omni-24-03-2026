"""ITAM KPI cost rules - Phase 78 Plan 04 (COST-01, COST-06, COST-07).

D-01 / D-04: disposed and retired assets leave the tile's money and `inScopeAssetCount`, while the
lifecycle pie and `assetCount` still count every status. D-10: no valued asset -> null, never 0,
and `hasData` stays true. D-13 / D-15 (amended 2026-11-16): the KPI route covers exactly one
resolved tenant, and the licence, warranty and overdue reads follow the Owner's X-Tenant-ID choice.
Pitfall 9: one clock read per `compute_itam_kpis` call.

The pure KPI cases use the mock-database helpers of the Phase 72 KPI tests; the Owner-with-header
case uses a real throwaway MongoDB with the production TenantIsolatedDatabase wrapper, because the
licence, warranty and overdue reads carry no explicit tenant filter and only the resolver's ambient
tenant write scopes them.
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
from tests.itam_reporting_test_support import (  # noqa: F401 - fixtures re-exported for pytest
    MockTenantIsolatedDatabase,
    mock_db,
    report_asset,
)

import database
import itam_asset_endpoints
import itam_cost_service
import itam_kpi_endpoints
import tenant_context
from api_key_auth import get_current_user_or_api_key
from authentication_service import get_current_user as real_get_current_user
from itam_cost_service import compute_asset_cost, compute_tenant_costs
from itam_reporting_kpis import compute_itam_kpis

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()
MODEL = {"id": "model-1", "usefulLifeYears": 3, "salvageValueCents": 10000}
URL = "/api/itam/kpis"


@pytest.fixture(autouse=True)
def _clean_ambient_tenant():
    """The resolver sets the ambient tenant in the handler's context; TenantMiddleware restores
    it in production, so a test app without that middleware must do it here."""
    token = tenant_context.set_tenant_id(None)
    yield
    tenant_context.reset_tenant_id(token)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED_NOW)


def _seed_defaults(db):
    db.assets.find.return_value.to_list.return_value = []
    db.licenses.find.return_value.to_list.return_value = []
    db.asset_models.find.return_value.to_list.return_value = [MODEL]
    db.system_settings.find_one = AsyncMock(return_value=None)
    db.assets.count_documents = AsyncMock(return_value=0)
    db.license_assignments.count_documents = AsyncMock(return_value=0)


def _valued(asset_id, status, cost=120000):
    return report_asset(
        id=asset_id, lifecycleStatus=status, modelId="model-1",
        purchaseCostCents=cost, purchaseDate=PURCHASE,
    )


def _expected_book_value(cost=120000):
    return compute_asset_cost(
        {"id": "x", "lifecycleStatus": "deployed", "modelId": "model-1",
         "purchaseCostCents": cost, "purchaseDate": PURCHASE},
        MODEL, FIXED_NOW,
    )["bookValueCents"]


async def _kpi(db, assets):
    db.assets.find.return_value.to_list.return_value = assets
    return (await compute_itam_kpis(MockTenantIsolatedDatabase(db, "tenant-a"), "tenant-a"))["assetValue"]


class TestAssetValueRules:
    @pytest.mark.asyncio
    async def test_disposed_and_retired_leave_value_but_stay_in_pie(self, mock_db):
        _seed_defaults(mock_db)
        no_status = _valued("a7", "deployed")
        del no_status["lifecycleStatus"]  # genuinely absent -> deployable by default
        assets = [
            _valued("a1", "deployable"), _valued("a2", "deployed"), _valued("a3", "archived"),
            _valued("a4", "broken"), _valued("a5", "retired"), _valued("a6", "disposed"),
            no_status,
        ]
        asset_value = await _kpi(mock_db, assets)

        # The five in-scope assets (deployable, deployed, archived, broken, no status) are valued.
        assert asset_value["totalBookValueCents"] == 5 * _expected_book_value()
        assert asset_value["inScopeAssetCount"] == 5
        assert asset_value["valuedCount"] == 5
        assert asset_value["withoutPolicyCount"] == 0
        assert asset_value["assetCount"] == 7
        counts = {seg["status"]: seg["count"] for seg in asset_value["statusBreakdown"]}
        assert counts["retired"] == 1
        assert counts["disposed"] == 1
        assert counts["deployable"] == 2  # a1 plus the asset with no lifecycleStatus
        assert sum(counts.values()) == 7

    @pytest.mark.asyncio
    async def test_unhashable_lifecycle_status_reads_as_default(self, mock_db):
        # IN-02: a list or dict status must not raise TypeError; it counts under the default status.
        _seed_defaults(mock_db)
        asset_value = await _kpi(mock_db, [_valued("a1", ["x"]), _valued("a2", {"x": 1}), _valued("a3", "retired")])

        assert asset_value["assetCount"] == 3 and asset_value["inScopeAssetCount"] == 2
        counts = {seg["status"]: seg["count"] for seg in asset_value["statusBreakdown"]}
        assert counts["deployable"] == 2 and counts["retired"] == 1

    @pytest.mark.asyncio
    async def test_disposed_value_does_not_count_even_when_it_has_a_policy(self, mock_db):
        _seed_defaults(mock_db)
        before = await _kpi(mock_db, [_valued("a1", "deployed")])
        after = await _kpi(mock_db, [_valued("a1", "deployed"), _valued("a2", "disposed", cost=999999)])
        assert before["totalBookValueCents"] == after["totalBookValueCents"] == _expected_book_value()
        assert after["assetCount"] == 2 and before["assetCount"] == 1

    @pytest.mark.asyncio
    async def test_null_book_value_with_assets_keeps_has_data(self, mock_db):
        _seed_defaults(mock_db)
        assets = [
            report_asset(id="a1", purchaseCostCents=None, purchaseDate=None),
            report_asset(id="a2", modelId="model-missing", purchaseCostCents=5000, purchaseDate=PURCHASE),
            report_asset(id="a3", lifecycleStatus="deployable"),
        ]
        asset_value = await _kpi(mock_db, assets)

        assert asset_value["hasData"] is True
        assert asset_value["totalBookValueCents"] is None
        assert asset_value["valuedCount"] == 0
        assert asset_value["inScopeAssetCount"] == 3
        assert asset_value["withoutPolicyCount"] == 3

    @pytest.mark.asyncio
    async def test_all_assets_inactive(self, mock_db):
        _seed_defaults(mock_db)
        asset_value = await _kpi(mock_db, [_valued("a1", "disposed"), _valued("a2", "disposed")])

        assert asset_value["hasData"] is True
        assert asset_value["totalBookValueCents"] is None
        assert asset_value["inScopeAssetCount"] == 0
        assert asset_value["valuedCount"] == 0
        assert asset_value["withoutPolicyCount"] == 0
        assert asset_value["assetCount"] == 2

    @pytest.mark.asyncio
    async def test_no_assets_payload(self, mock_db):
        _seed_defaults(mock_db)
        asset_value = await _kpi(mock_db, [])

        assert asset_value["hasData"] is False
        assert asset_value["totalBookValueCents"] is None
        assert asset_value["inScopeAssetCount"] is None
        assert asset_value["valuedCount"] is None
        assert asset_value["withoutPolicyCount"] is None
        assert asset_value["assetCount"] == 0

    @pytest.mark.asyncio
    async def test_kpi_equals_shared_computation(self, mock_db):
        _seed_defaults(mock_db)
        assets = [
            _valued("a1", "deployed", cost=120000),
            _valued("a2", "deployable", cost=45000),
            _valued("a3", "retired", cost=80000),
            report_asset(id="a4", modelId="model-missing", purchaseCostCents=5000, purchaseDate=PURCHASE),
            report_asset(id="a5", purchaseCostCents=None, purchaseDate=None),
        ]
        asset_value = await _kpi(mock_db, assets)

        direct = [
            compute_asset_cost(a, MODEL if a.get("modelId") == "model-1" else None, FIXED_NOW)
            for a in assets
        ]
        in_scope_valued = [r["bookValueCents"] for r in direct
                           if r["lifecycleStatus"] not in ("disposed", "retired") and r["valued"]]
        assert asset_value["totalBookValueCents"] == sum(in_scope_valued)

        # And the cost summary over the same documents and clock reports the same figures.
        summary = (await compute_tenant_costs(
            MockTenantIsolatedDatabase(mock_db, "tenant-a"), "tenant-a"))["summary"]
        assert asset_value["totalBookValueCents"] == summary["bookValueTotal"]["cents"]
        assert asset_value["valuedCount"] == summary["coverage"]["valued"]
        assert asset_value["inScopeAssetCount"] == summary["coverage"]["total"]

    @pytest.mark.asyncio
    async def test_one_utc_now_per_kpi_request(self, mock_db, monkeypatch):
        _seed_defaults(mock_db)
        mock_db.assets.find.return_value.to_list.return_value = [_valued("a1", "deployed")]
        calls = []

        def _counting_clock():
            calls.append(1)
            return FIXED_NOW

        monkeypatch.setattr(itam_cost_service, "utc_now", _counting_clock)
        await compute_itam_kpis(MockTenantIsolatedDatabase(mock_db, "tenant-a"), "tenant-a")
        assert len(calls) == 1


def _client(app, user):
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    app.dependency_overrides[real_get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _app(monkeypatch, db=None):
    if db is not None:
        monkeypatch.setattr(itam_kpi_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(db))
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    app, _ = make_test_app(itam_kpi_endpoints.router)
    return app


def _never_db(monkeypatch):
    def _never():
        raise AssertionError("get_database must not be reached before the tenant is resolved")

    monkeypatch.setattr(itam_kpi_endpoints, "get_database", _never)


def _owner():
    return make_token_data(role="Super Admin", tenant_id="platform-admin", username="owner@example.com")


class TestTenantScoping:
    @pytest.mark.asyncio
    async def test_owner_header_scopes_every_kpi(self, mongo_db, monkeypatch):
        past = (FIXED_NOW - timedelta(days=3)).isoformat(timespec="milliseconds")
        await mongo_db.asset_models.insert_many([
            {"tenantId": "tenant-a", **MODEL},
            {"tenantId": "tenant-b", "id": "model-1", "usefulLifeYears": 4, "salvageValueCents": 0},
        ])
        await mongo_db.assets.insert_many([
            {"tenantId": "tenant-a", "id": "A1", "lifecycleStatus": "deployed", "modelId": "model-1",
             "purchaseCostCents": 120000, "purchaseDate": PURCHASE, "warrantyMonths": 24,
             "expectedReturnDate": past},
            {"tenantId": "tenant-a", "id": "A2", "lifecycleStatus": "deployed", "modelId": "model-1",
             "purchaseCostCents": 120000, "purchaseDate": PURCHASE, "expectedReturnDate": past},
            {"tenantId": "tenant-b", "id": "B1", "lifecycleStatus": "deployed", "modelId": "model-1",
             "purchaseCostCents": 400000, "purchaseDate": PURCHASE},
        ])
        await mongo_db.licenses.insert_many([
            {"tenantId": "tenant-a", "id": "LA", "name": "A suite", "seatCount": 7},
            {"tenantId": "tenant-b", "id": "LB", "name": "B suite", "seatCount": 30},
            {"tenantId": "tenant-b", "id": "LB2", "name": "B extra", "seatCount": 12},
        ])
        app = _app(monkeypatch, mongo_db)

        async with _client(app, _owner()) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-b"})

        assert r.status_code == 200, r.text
        body = r.json()
        b_expected = compute_asset_cost(
            {"id": "B1", "lifecycleStatus": "deployed", "modelId": "model-1",
             "purchaseCostCents": 400000, "purchaseDate": PURCHASE},
            {"id": "model-1", "usefulLifeYears": 4, "salvageValueCents": 0}, FIXED_NOW,
        )["bookValueCents"]
        assert body["assetValue"]["assetCount"] == 1
        assert body["assetValue"]["totalBookValueCents"] == b_expected
        assert body["licenseUtilization"]["seatsTotal"] == 42
        assert body["overdue"]["overdueCheckinCount"] == 0
        assert body["warrantyExpirations"]["hasData"] is False
        assert "tenant-a" not in r.text

    @pytest.mark.asyncio
    async def test_tenant_user_reads_own_tenant_only(self, mongo_db, monkeypatch):
        await mongo_db.licenses.insert_many([
            {"tenantId": "tenant-a", "id": "LA", "name": "A suite", "seatCount": 7},
            {"tenantId": "tenant-b", "id": "LB", "name": "B suite", "seatCount": 30},
        ])
        app = _app(monkeypatch, mongo_db)
        user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")

        async with _client(app, user) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-b"})

        assert r.status_code == 200, r.text
        assert r.json()["licenseUtilization"]["seatsTotal"] == 7

    @pytest.mark.asyncio
    async def test_kpi_owner_without_tenant_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        _never_db(monkeypatch)
        async with _client(app, _owner()) as ac:
            r = await ac.get(URL)
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_kpi_support_with_header_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        _never_db(monkeypatch)
        support = make_token_data(role="platform_support", tenant_id="platform-admin")
        async with _client(app, support) as ac:
            r = await ac.get(URL, headers={"X-Tenant-ID": "tenant-a"})
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")
