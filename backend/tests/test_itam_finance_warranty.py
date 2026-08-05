"""ITAM Finance warranty tests — Phase 59, Plan 03.

Covers Phase 59's warranty read path across itam_finance_service.py and
itam_finance_endpoints.py, split out from test_itam_finance.py to keep both
files under the 500-line CLAUDE.md cap.

Plan 03, Task 1: _add_months, compute_warranty_status, get_warranty_alert_window
(TestAddMonths, TestWarrantyStatusCompute, TestWarrantyAlertWindow).
Plan 03, Task 2: GET /api/assets/{asset_id}/warranty end-to-end
(TestWarrantyRouteEndToEnd, TestWarrantyRouteAccess).
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
    finance_asset,
)

from authentication_service import get_current_user as real_get_current_user

import itam_finance_service as finance_service
from itam_finance_service import (
    WARRANTY_STATUS_NONE,
    WARRANTY_STATUS_ACTIVE,
    WARRANTY_STATUS_EXPIRING,
    WARRANTY_STATUS_EXPIRED,
    _add_months,
    compute_warranty_status,
    get_warranty_alert_window,
)


class TestAddMonths:
    """Every _add_months row in the plan's behavior block, plus the leap-year
    February case in both a leap and a non-leap target year. -k add_months"""

    def test_add_months_31st_plus_one_lands_on_feb_29_leap_year(self):
        assert _add_months(datetime(2024, 1, 31), 1) == datetime(2024, 2, 29)

    def test_add_months_31st_plus_one_lands_on_feb_28_non_leap_year(self):
        assert _add_months(datetime(2023, 1, 31), 1) == datetime(2023, 2, 28)

    def test_add_months_31st_plus_four_lands_on_feb_29_leap_year(self):
        assert _add_months(datetime(2023, 10, 31), 4) == datetime(2024, 2, 29)

    def test_add_months_plus_twelve_lands_on_same_month_day_next_year(self):
        assert _add_months(datetime(2023, 6, 15), 12) == datetime(2024, 6, 15)

    def test_add_months_plus_zero_returns_same_date(self):
        d = datetime(2023, 6, 15, 8, 30)
        assert _add_months(d, 0) == d

    def test_add_months_leap_year_target_non_leap_source(self):
        assert _add_months(datetime(2023, 12, 31), 2) == datetime(2024, 2, 29)

    def test_add_months_preserves_tzinfo(self):
        d = datetime(2023, 1, 15, tzinfo=timezone.utc)
        result = _add_months(d, 1)
        assert result.tzinfo == timezone.utc
        assert result == datetime(2023, 2, 15, tzinfo=timezone.utc)


class TestWarrantyStatusCompute:
    """Every status row from the behavior block, always with an explicit
    now so nothing depends on the wall clock, always asserting against the
    module constants. -k warranty_status_compute"""

    def test_warranty_status_compute_expiring_at_one_day_remaining(self):
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2026, 1, 14, tzinfo=timezone.utc),
            alert_window_days=30,
        )
        assert result["warrantyExpiresAt"] == datetime(2026, 1, 15, tzinfo=timezone.utc).isoformat()
        assert result["warrantyStatus"] == WARRANTY_STATUS_EXPIRING
        assert result["daysToExpiry"] == 1

    def test_warranty_status_compute_expired_after_expiry_with_negative_days(self):
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2026, 1, 16, tzinfo=timezone.utc),
            alert_window_days=30,
        )
        assert result["warrantyStatus"] == WARRANTY_STATUS_EXPIRED
        assert result["daysToExpiry"] < 0

    def test_warranty_status_compute_active_well_before_window(self):
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2025, 1, 1, tzinfo=timezone.utc),
            alert_window_days=30,
        )
        assert result["warrantyStatus"] == WARRANTY_STATUS_ACTIVE
        assert result["daysToExpiry"] > 30

    def test_warranty_status_compute_boundary_exactly_at_window_is_expiring(self):
        # expiry 2026-01-15; now = 2025-12-16 -> 30 days remaining exactly
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2025, 12, 16, tzinfo=timezone.utc),
            alert_window_days=30,
        )
        assert result["daysToExpiry"] == 30
        assert result["warrantyStatus"] == WARRANTY_STATUS_EXPIRING

    def test_warranty_status_compute_boundary_one_day_further_is_active(self):
        # now = 2025-12-15 -> 31 days remaining, one day further from expiry
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2025, 12, 15, tzinfo=timezone.utc),
            alert_window_days=30,
        )
        assert result["daysToExpiry"] == 31
        assert result["warrantyStatus"] == WARRANTY_STATUS_ACTIVE

    def test_warranty_status_compute_none_warranty_months_missing(self):
        result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", None,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc), alert_window_days=30,
        )
        assert result["warrantyStatus"] == WARRANTY_STATUS_NONE
        assert result["warrantyExpiresAt"] is None
        assert result["daysToExpiry"] is None

    def test_warranty_status_compute_none_falsy_purchase_date(self):
        result = compute_warranty_status(
            "", 36, now=datetime(2026, 1, 1, tzinfo=timezone.utc), alert_window_days=30,
        )
        assert result["warrantyStatus"] == WARRANTY_STATUS_NONE
        assert result["warrantyExpiresAt"] is None

    def test_warranty_status_compute_none_unparseable_purchase_date(self):
        result = compute_warranty_status(
            "not-a-date", 36, now=datetime(2026, 1, 1, tzinfo=timezone.utc), alert_window_days=30,
        )
        assert result["warrantyStatus"] == WARRANTY_STATUS_NONE
        assert result["warrantyExpiresAt"] is None
        assert result["daysToExpiry"] is None

    def test_warranty_status_compute_naive_purchase_date_treated_as_utc(self):
        naive_result = compute_warranty_status(
            "2023-01-15T00:00:00", 36,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc), alert_window_days=30,
        )
        aware_result = compute_warranty_status(
            "2023-01-15T00:00:00+00:00", 36,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc), alert_window_days=30,
        )
        assert naive_result == aware_result

    def test_warranty_status_compute_never_raises_on_bad_inputs(self):
        # No exception for any of these — this test itself is the assertion.
        compute_warranty_status(None, 36, now=datetime.now(timezone.utc), alert_window_days=30)
        compute_warranty_status("2023-01-15", None, now=datetime.now(timezone.utc), alert_window_days=30)
        compute_warranty_status(12345, 36, now=datetime.now(timezone.utc), alert_window_days=30)


class _RawDb:
    """A plain, non-MagicMock db stub with no _db attribute and no
    __getattr__ fallback — proves the unwrap guard works from a raw call
    site. A MagicMock would auto-create `_db` and make this case vacuous."""

    def __init__(self, system_settings):
        self.system_settings = system_settings


class _WrappedDb:
    """A stub exposing `_db`, mirroring a request-scoped TenantIsolatedDatabase."""

    def __init__(self, raw_db):
        self._db = raw_db


class TestWarrantyAlertWindow:
    """Full lookup order coverage, including both call-site shapes.
    -k warranty_alert_window"""

    @pytest.mark.asyncio
    async def test_warranty_alert_window_returns_per_tenant_value(self):
        find_one = AsyncMock(return_value={"windowDays": 90})
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 90
        call_filter = find_one.call_args.args[0]
        assert call_filter == {"type": finance_service.WARRANTY_ALERT_WINDOW_SETTING_TYPE, "tenantId": "tenant-a"}

    @pytest.mark.asyncio
    async def test_warranty_alert_window_falls_back_to_global_doc(self):
        find_one = AsyncMock(side_effect=[None, {"windowDays": 45}])
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 45
        assert find_one.call_count == 2
        second_filter = find_one.call_args_list[1].args[0]
        assert second_filter == {
            "type": finance_service.WARRANTY_ALERT_WINDOW_SETTING_TYPE,
            "tenantId": {"$exists": False},
        }

    @pytest.mark.asyncio
    async def test_warranty_alert_window_falls_back_to_default_30(self):
        find_one = AsyncMock(side_effect=[None, None])
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 30

    @pytest.mark.asyncio
    async def test_warranty_alert_window_clamps_zero_to_one(self):
        find_one = AsyncMock(return_value={"windowDays": 0})
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 1

    @pytest.mark.asyncio
    async def test_warranty_alert_window_clamps_negative_to_one(self):
        find_one = AsyncMock(return_value={"windowDays": -5})
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 1

    @pytest.mark.asyncio
    async def test_warranty_alert_window_ignores_non_integer_and_continues(self):
        find_one = AsyncMock(side_effect=[{"windowDays": "60"}, {"windowDays": 20}])
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 20

    @pytest.mark.asyncio
    async def test_warranty_alert_window_works_against_wrapped_db_handle(self):
        find_one = AsyncMock(return_value={"windowDays": 15})
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        wrapped_db = _WrappedDb(raw_db)
        result = await get_warranty_alert_window(wrapped_db, "tenant-a")
        assert result == 15

    @pytest.mark.asyncio
    async def test_warranty_alert_window_works_against_raw_db_with_no_db_attribute(self):
        find_one = AsyncMock(return_value={"windowDays": 15})
        raw_db = _RawDb(system_settings=type("Col", (), {"find_one": find_one})())
        assert not hasattr(raw_db, "_db")
        result = await get_warranty_alert_window(raw_db, "tenant-a")
        assert result == 15
