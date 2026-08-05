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
from itam_models import ManualAssetCreate


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
