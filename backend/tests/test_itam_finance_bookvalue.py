"""ITAM Finance book-value tests — Phase 59, Plan 01, Task 3.

Pins ITAM-FIN-03's straight-line depreciation arithmetic, its salvage floor,
its whole-year anniversary rule, its degraded-policy responses (PD-02), and
its no-persistence guarantee (D-04).

A separate file from test_itam_finance.py so both stay well under the
CLAUDE.md 500-line cap. Shared mock DB/fixtures live in
itam_finance_test_support.py.
"""
import sys
import os
from datetime import datetime, timezone
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
from itam_finance_service import (
    REASON_NO_DEPRECIATION_POLICY,
    REASON_NO_PURCHASE_RECORD,
    compute_book_value,
)


class TestBookValueCompute:
    """Pure unit tests calling compute_book_value directly, with an
    explicitly constructed `now` so nothing depends on the wall clock."""

    def test_book_value_compute_at_zero_years_elapsed(self):
        now = datetime(2023, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result == {"bookValueCents": 150000, "yearsElapsed": 0, "annualDepreciationCents": 45000}

    def test_book_value_compute_at_one_year_elapsed(self):
        now = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-06-15", 150000, 3, 15000, now)
        assert result == {"bookValueCents": 105000, "yearsElapsed": 1, "annualDepreciationCents": 45000}

    def test_book_value_compute_at_two_years_elapsed(self):
        now = datetime(2025, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result == {"bookValueCents": 60000, "yearsElapsed": 2, "annualDepreciationCents": 45000}

    def test_book_value_compute_at_three_years_elapsed(self):
        now = datetime(2026, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result == {"bookValueCents": 15000, "yearsElapsed": 3, "annualDepreciationCents": 45000}

    def test_book_value_compute_clamps_at_four_years_past_useful_life(self):
        now = datetime(2027, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result["yearsElapsed"] == 3
        assert result["bookValueCents"] == 15000

    def test_book_value_compute_clamps_at_forty_years_past_useful_life(self):
        now = datetime(2063, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result["yearsElapsed"] == 3
        assert result["bookValueCents"] == 15000

    def test_book_value_compute_anniversary_boundary_not_yet_reached(self):
        now = datetime(2024, 6, 14, tzinfo=timezone.utc)
        result = compute_book_value("2023-06-15", 150000, 3, 15000, now)
        assert result["yearsElapsed"] == 0

    def test_book_value_compute_anniversary_boundary_reached(self):
        now = datetime(2024, 6, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-06-15", 150000, 3, 15000, now)
        assert result["yearsElapsed"] == 1

    def test_book_value_compute_now_before_purchase_date_yields_zero(self):
        now = datetime(2022, 1, 1, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 150000, 3, 15000, now)
        assert result["yearsElapsed"] == 0

    def test_book_value_compute_salvage_equal_cost_zero_annual_depreciation(self):
        now = datetime(2025, 1, 15, tzinfo=timezone.utc)
        result = compute_book_value("2023-01-15", 100000, 3, 100000, now)
        assert result["annualDepreciationCents"] == 0
        assert result["bookValueCents"] == 100000

    def test_book_value_compute_all_returned_values_are_int(self):
        now = datetime(2025, 1, 15, tzinfo=timezone.utc)
        table = [
            ("2023-01-15", 150000, 3, 15000, now),
            ("2023-01-15", 100000, 3, 100000, now),
            ("2023-06-15", 150000, 3, 15000, datetime(2024, 6, 15, tzinfo=timezone.utc)),
        ]
        for args in table:
            result = compute_book_value(*args)
            for v in result.values():
                assert isinstance(v, int)
                assert not isinstance(v, bool)

    def test_book_value_compute_raises_on_zero_useful_life(self):
        with pytest.raises(ValueError):
            compute_book_value("2023-01-15", 150000, 0, 15000, datetime(2025, 1, 15, tzinfo=timezone.utc))

    def test_book_value_compute_raises_on_unparseable_purchase_date(self):
        with pytest.raises(ValueError):
            compute_book_value("not-a-date", 150000, 3, 15000, datetime(2025, 1, 15, tzinfo=timezone.utc))


class TestBookValueNoPolicy:
    """Drives GET /api/assets/asset-1/book-value for each degraded state.
    Every existing Model in every tenant predates this phase and has
    neither depreciation field — these are the ordinary states, not exotic
    edge cases."""

    async def _get(self, finance_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            return await ac.get("/api/assets/asset-1/book-value")

    @pytest.mark.asyncio
    async def test_book_value_no_policy_missing_purchase_date(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(purchaseCostCents=100000))
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_PURCHASE_RECORD

    @pytest.mark.asyncio
    async def test_book_value_no_policy_missing_purchase_cost(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(purchaseDate="2023-01-15"))
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_PURCHASE_RECORD

    @pytest.mark.asyncio
    async def test_book_value_no_policy_missing_model_id(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(
            purchaseCostCents=100000, purchaseDate="2023-01-15", modelId=None,
        ))
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_DEPRECIATION_POLICY

    @pytest.mark.asyncio
    async def test_book_value_no_policy_unresolvable_model_id(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(
            purchaseCostCents=100000, purchaseDate="2023-01-15", modelId="model-missing",
        ))
        mock_db.asset_models.find_one = AsyncMock(return_value=None)
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_DEPRECIATION_POLICY

    @pytest.mark.asyncio
    async def test_book_value_no_policy_model_missing_salvage_value(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(
            purchaseCostCents=100000, purchaseDate="2023-01-15",
        ))
        mock_db.asset_models.find_one = AsyncMock(return_value=depreciating_model(salvageValueCents=None))
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_DEPRECIATION_POLICY

    @pytest.mark.asyncio
    async def test_book_value_no_policy_model_missing_useful_life(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(
            purchaseCostCents=100000, purchaseDate="2023-01-15",
        ))
        mock_db.asset_models.find_one = AsyncMock(return_value=depreciating_model(usefulLifeYears=None))
        r = await self._get(finance_app)
        assert r.status_code == 200, r.text
        assert r.json()["bookValueCents"] is None
        assert r.json()["reason"] == REASON_NO_DEPRECIATION_POLICY


class TestBookValueNeverPersists:
    """Pins D-04's no-stored-book-value rule behaviorally: a book-value
    request performs no write of any kind."""

    @pytest.mark.asyncio
    async def test_book_value_never_persists_no_write_awaited(self, mock_db, finance_app):
        mock_db.assets.find_one = AsyncMock(return_value=finance_asset(
            purchaseCostCents=150000, purchaseDate="2023-01-15",
        ))
        mock_db.asset_models.find_one = AsyncMock(return_value=depreciating_model())

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        finance_app.dependency_overrides[real_get_current_user] = lambda: current_user
        async with AsyncClient(transport=ASGITransport(app=finance_app), base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/book-value")

        assert r.status_code == 200, r.text
        assert "bookValueCents" in r.json()
        assert mock_db.assets.insert_one.call_count == 0
        assert mock_db.assets.update_one.call_count == 0
        assert mock_db.assets.find_one_and_update.call_count == 0
        assert mock_db.asset_models.insert_one.call_count == 0
        assert mock_db.asset_models.update_one.call_count == 0
        assert mock_db.asset_models.find_one_and_update.call_count == 0
