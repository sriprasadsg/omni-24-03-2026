"""ITAM Finance tests — Phase 59.

Plan 01, Task 1: "record a purchase on one asset and read back its book
value" end-to-end (TestFinanceTracerEndToEnd).
Plan 01, Task 2: supplier reference, RBAC, cross-tenant, value floors,
alert-marker reset, create-time fields hardening (TestPurchasePatchValidation,
TestPurchaseAlertMarkerReset, TestFinanceRbacAndTenantIsolation,
TestPurchaseFieldsAtCreateTime).

Shared mock DB/fixtures live in itam_finance_test_support.py (split out to
keep this file under the CLAUDE.md 500-line limit). Depreciation-arithmetic
and no-policy-contract tests live in test_itam_finance_bookvalue.py.
"""
import sys
import os
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_finance_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_finance_get_database,
    finance_app,
    asset_create_app,
    finance_asset,
    depreciating_model,
)

from authentication_service import get_current_user as real_get_current_user
from api_key_auth import get_current_user_or_api_key  # Phase 73 (D-01/D-02): routes gated by _require_itam_admin now resolve through this dependency, not get_current_user
from itam_models import ManualAssetCreate

import pydantic


class TestFinanceTracerEndToEnd:
    """Task 1 — end-to-end 'record a purchase then read back its book
    value', one path only."""

    @pytest.mark.asyncio
    async def test_purchase_then_book_value_end_to_end(self, mock_db, finance_app):
        mock_db.assets.find_one_and_update = AsyncMock(
            return_value=finance_asset(
                purchaseCostCents=150000,
                purchaseDate="2023-01-15T00:00:00+00:00",
                poNumber="PO-4417",
                supplierId="sup-1",
                warrantyMonths=36,
            )
        )
        mock_db.suppliers.find_one = AsyncMock(return_value={"id": "sup-1", "tenantId": "tenant-a", "name": "Acme"})

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=finance_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.patch(
                "/api/assets/asset-1/purchase",
                json={
                    "purchaseCostCents": 150000,
                    "purchaseDate": "2023-01-15T00:00:00+00:00",
                    "poNumber": "PO-4417",
                    "supplierId": "sup-1",
                    "warrantyMonths": 36,
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["purchaseCostCents"] == 150000
            assert body["poNumber"] == "PO-4417"

            mock_db.assets.find_one = AsyncMock(return_value=body)
            mock_db.asset_models.find_one = AsyncMock(return_value=depreciating_model())

            r2 = await ac.get("/api/assets/asset-1/book-value")

        assert r2.status_code == 200, r2.text
        bv_body = r2.json()
        annual = (150000 - 15000) // 3
        expected = max(150000 - bv_body["yearsElapsed"] * annual, 15000)
        assert bv_body["bookValueCents"] == expected
        assert bv_body["bookValueCents"] >= 15000
        assert "reason" not in bv_body


class TestPurchasePatchValidation:
    """Task 2 — drives the PATCH route: supplier reference (D-02), value
    floors (D-01), and 400/422 boundary behavior."""

    def _client(self, finance_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        return AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver")

    @pytest.mark.asyncio
    async def test_purchase_patch_unresolvable_supplier_returns_400(self, mock_db, finance_app):
        mock_db.suppliers.find_one = AsyncMock(return_value=None)
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"supplierId": "sup-missing"})
        assert r.status_code == 400, r.text
        assert "supplierId" in r.text

    @pytest.mark.asyncio
    async def test_purchase_patch_resolving_supplier_returns_200(self, mock_db, finance_app):
        mock_db.suppliers.find_one = AsyncMock(return_value={"id": "sup-1", "tenantId": "tenant-a"})
        mock_db.assets.find_one_and_update = AsyncMock(return_value=finance_asset(supplierId="sup-1"))
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"supplierId": "sup-1"})
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_purchase_patch_unresolvable_purchase_order_id_returns_400(self, mock_db, finance_app):
        """T-71-04 (71-01-PLAN.md) — declared mitigate but was never
        implemented: any purchase_order_id string was previously accepted
        and persisted with no existence/ownership check at all."""
        mock_db.purchase_orders.find_one = AsyncMock(return_value=None)
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"purchase_order_id": "po-missing"})
        assert r.status_code == 400, r.text
        assert "purchase_order_id" in r.text
        assert mock_db.assets.find_one_and_update.call_count == 0

    @pytest.mark.asyncio
    async def test_purchase_patch_resolving_purchase_order_id_returns_200(self, mock_db, finance_app):
        mock_db.purchase_orders.find_one = AsyncMock(return_value={"id": "po-1", "tenantId": "tenant-a"})
        mock_db.assets.find_one_and_update = AsyncMock(return_value=finance_asset(purchase_order_id="po-1"))
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"purchase_order_id": "po-1"})
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_purchase_patch_empty_body_returns_400(self, mock_db, finance_app):
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={})
        assert r.status_code == 400, r.text
        assert mock_db.assets.find_one_and_update.call_count == 0

    @pytest.mark.asyncio
    async def test_purchase_patch_negative_cost_returns_422(self, mock_db, finance_app):
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"purchaseCostCents": -1})
        assert r.status_code == 422, r.text
        assert mock_db.assets.find_one_and_update.call_count == 0

    @pytest.mark.asyncio
    async def test_purchase_patch_negative_warranty_months_returns_422(self, mock_db, finance_app):
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"warrantyMonths": -1})
        assert r.status_code == 422, r.text
        assert mock_db.assets.find_one_and_update.call_count == 0

    @pytest.mark.asyncio
    async def test_purchase_patch_unrecognised_key_returns_422(self, mock_db, finance_app):
        async with self._client(finance_app) as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"purchaseCostCentsTypo": 100})
        assert r.status_code == 422, r.text
        assert mock_db.assets.find_one_and_update.call_count == 0

    @pytest.mark.asyncio
    async def test_purchase_patch_useful_life_zero_rejected_on_model_contract(self):
        with pytest.raises(pydantic.ValidationError):
            from itam_models import AssetModelCreate
            AssetModelCreate(name="x", usefulLifeYears=0)


class TestPurchaseAlertMarkerReset:
    """Task 2 — the reset half of the idempotency contract Plan 59-04's sweep
    depends on: a PATCH supplying purchaseDate or warrantyMonths clears
    warrantyAlertSentAt; a PATCH supplying only poNumber does not."""

    def _client(self, finance_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        return AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver")

    @pytest.mark.asyncio
    async def test_alert_marker_reset_on_purchase_date_change(self, mock_db, finance_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=finance_asset())
        async with self._client(finance_app) as ac:
            await ac.patch("/api/assets/asset-1/purchase", json={"purchaseDate": "2024-01-01"})
        _, mutation = mock_db.assets.find_one_and_update.call_args.args[:2]
        assert "warrantyAlertSentAt" in mutation.get("$unset", {})

    @pytest.mark.asyncio
    async def test_alert_marker_reset_on_warranty_months_change(self, mock_db, finance_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=finance_asset())
        async with self._client(finance_app) as ac:
            await ac.patch("/api/assets/asset-1/purchase", json={"warrantyMonths": 12})
        _, mutation = mock_db.assets.find_one_and_update.call_args.args[:2]
        assert "warrantyAlertSentAt" in mutation.get("$unset", {})

    @pytest.mark.asyncio
    async def test_alert_marker_reset_not_triggered_by_po_number_only(self, mock_db, finance_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=finance_asset())
        async with self._client(finance_app) as ac:
            await ac.patch("/api/assets/asset-1/purchase", json={"poNumber": "PO-9"})
        _, mutation = mock_db.assets.find_one_and_update.call_args.args[:2]
        assert "$unset" not in mutation


class TestFinanceRbacAndTenantIsolation:
    """Task 2 — 403 without manage:assets; cross-tenant asset id is
    indistinguishable from an unknown one."""

    @pytest.mark.asyncio
    async def test_rbac_denied_patch_returns_403(self, mock_db, finance_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"poNumber": "PO-1"})
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_rbac_denied_book_value_returns_403(self, mock_db, finance_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/book-value")
        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_patch_returns_404(self, mock_db, finance_app, patch_finance_get_database):
        stored = [finance_asset()]
        mock_db.assets.find_one_and_update = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_finance_get_database("tenant-b")
        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.patch("/api/assets/asset-1/purchase", json={"poNumber": "PO-1"})
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_book_value_returns_404(self, mock_db, finance_app, patch_finance_get_database):
        stored = [finance_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_finance_get_database("tenant-b")
        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/book-value")
        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_404_matches_unknown_id_404(self, mock_db, finance_app, patch_finance_get_database):
        stored = [finance_asset()]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))
        patch_finance_get_database("tenant-b")
        current_user = make_token_data(tenant_id="tenant-b", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            cross_tenant_resp = await ac.get("/api/assets/asset-1/book-value")
            unknown_id_resp = await ac.get("/api/assets/does-not-exist/book-value")
        assert cross_tenant_resp.status_code == unknown_id_resp.status_code == 404
        assert cross_tenant_resp.text == unknown_id_resp.text


class TestPurchaseFieldsAtCreateTime:
    """Task 2 — purchase fields are optional at manual-asset creation time,
    and POST /api/assets carries them onto the new asset document when
    supplied (ITAM-FIN-01)."""

    def test_create_time_manual_asset_no_purchase_fields_validates(self):
        m = ManualAssetCreate(name="x")
        dumped = m.model_dump(exclude_none=True)
        for key in ("purchaseCostCents", "purchaseDate", "poNumber", "warrantyMonths"):
            assert key not in dumped

    def test_create_time_manual_asset_round_trips_purchase_fields(self):
        m = ManualAssetCreate(
            name="x",
            purchaseCostCents=99,
            purchaseDate="2024-02-29",
            poNumber="PO-1",
            supplierId="sup-1",
            warrantyMonths=12,
        )
        dumped = m.model_dump(exclude_none=True)
        assert dumped["purchaseCostCents"] == 99
        assert dumped["purchaseDate"] == "2024-02-29"
        assert dumped["poNumber"] == "PO-1"
        assert dumped["supplierId"] == "sup-1"
        assert dumped["warrantyMonths"] == 12

    def test_create_time_malformed_purchase_date_raises_validation_error(self):
        with pytest.raises(pydantic.ValidationError):
            ManualAssetCreate(name="x", purchaseDate="not-a-date")

    @pytest.mark.asyncio
    async def test_create_time_post_asset_includes_purchase_fields(self, mock_db, asset_create_app):
        mock_db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
        mock_db.assets.find_one = AsyncMock(return_value=None)
        mock_db.assets.insert_one = AsyncMock()

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        asset_create_app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
        asset_create_app.dependency_overrides[real_get_current_user] = lambda: current_user

        payload = {
            "name": "Laptop X2",
            "purchaseCostCents": 200000,
            "purchaseDate": "2024-03-01",
            "poNumber": "PO-77",
            "supplierId": "sup-1",
            "warrantyMonths": 24,
        }
        async with AsyncClient(transport=ASGITransport(app=asset_create_app), base_url="http://testserver") as ac:
            r = await ac.post("/api/assets", json=payload)

        assert r.status_code == 201, r.text
        inserted = mock_db.assets.insert_one.call_args.args[0]
        assert inserted["purchaseCostCents"] == 200000
        assert inserted["purchaseDate"] == "2024-03-01"
        assert inserted["poNumber"] == "PO-77"
        assert inserted["supplierId"] == "sup-1"
        assert inserted["warrantyMonths"] == 24
