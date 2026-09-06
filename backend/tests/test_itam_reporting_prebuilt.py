"""ITAM Reporting prebuilt-report tests — Phase 72, Plan 02.

Task 1 covers the three PREBUILT_REPORTS entries this plan's first task
adds (asset_value, checkout_activity, overdue_audits). Task 2 extends this
file with license_utilization, low_stock_consumables, and the
reorderThreshold consumable-model round-trip.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_reporting_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_reporting_get_database,
    reporting_app,
    report_asset,
    report_consumable,
    report_license,
)

from authentication_service import get_current_user as real_get_current_user
from api_key_auth import get_current_user_or_api_key  # Phase 73 (D-01/D-02): routes gated by _require_itam_admin now resolve through this dependency, not get_current_user
from itam_finance_service import REASON_NO_DEPRECIATION_POLICY, compute_book_value
from itam_lifecycle_endpoints import _overdue_query
from itam_models import ConsumableCreate
from itam_reporting_prebuilt import PREBUILT_REPORTS


def _cursor(rows):
    """A self-referencing MagicMock cursor whose .sort()/.limit() return the
    same cursor and whose .to_list() is the only async leaf — _make_col()'s
    bare find()/to_list() double does not survive a .sort().to_list() chain
    (an AsyncMock's own unconfigured child attributes default to AsyncMock
    too, so `.sort(...)` would return an unawaited coroutine rather than a
    chainable cursor); precedent: itam_lifecycle_test_support.py's identical
    _history_cursor fix."""
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=rows)
    return cur

_ASSET_VALUE_COLUMNS = [
    "Asset Tag", "Name", "Purchase Date", "Purchase Cost", "Book Value", "Years Elapsed", "Reason",
]
_CHECKOUT_ACTIVITY_COLUMNS = [
    "When", "Action", "Asset Tag", "Asset Name", "Target Type", "Target", "Actor", "Note",
]
_OVERDUE_AUDITS_COLUMNS = [
    "Asset Tag", "Name", "Lifecycle Status", "Last Audited", "Age Basis", "Days Overdue", "Never Audited",
]
_LICENSE_UTILIZATION_COLUMNS = [
    "License", "Manufacturer", "Seats Total", "Seats Assigned", "Seats Available",
    "Utilization %", "Expiry Date", "Status",
]
_LOW_STOCK_CONSUMABLES_COLUMNS = [
    "Consumable", "Unit Type", "Available", "Initial", "Reorder Threshold", "Basis",
]


def _client(app, tenant_id="tenant-a", role="admin", username="admin@example.com"):
    current_user = make_token_data(tenant_id=tenant_id, role=role, username=username)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
    app.dependency_overrides[real_get_current_user] = lambda: current_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _run(app, key):
    async with _client(app) as ac:
        return await ac.post(f"/api/itam/reports/prebuilt/{key}/run")


def _iso(days_offset: float) -> str:
    """An ISO timestamp `days_offset` days in the past (positive) or future
    (negative)."""
    return (datetime.now(timezone.utc) - timedelta(days=days_offset)).isoformat()


class TestRegistry:
    def test_all_six_reports_registered(self):
        assert set(PREBUILT_REPORTS) == {
            "warranty_expiring", "asset_value", "checkout_activity",
            "overdue_audits", "license_utilization", "low_stock_consumables",
        }
        assert len(PREBUILT_REPORTS) == 6


class TestAssetValueReport:
    """POST /api/itam/reports/prebuilt/asset_value/run"""

    @pytest.mark.asyncio
    async def test_returns_rows_sorted_desc_by_book_value(self, mock_db, reporting_app):
        model = {"id": "model-1", "usefulLifeYears": 5, "salvageValueCents": 10000}
        low_value = report_asset(
            id="asset-low", assetTag="IT-0001", modelId="model-1",
            purchaseCostCents=100000, purchaseDate=_iso(365 * 3),
        )
        high_value = report_asset(
            id="asset-high", assetTag="IT-0002", modelId="model-1",
            purchaseCostCents=500000, purchaseDate=_iso(30),
        )
        mock_db.assets.find.return_value.to_list.return_value = [low_value, high_value]
        mock_db.asset_models.find.return_value.to_list.return_value = [model]

        r = await _run(reporting_app, "asset_value")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == _ASSET_VALUE_COLUMNS
        assert [row["Asset Tag"] for row in body["rows"]] == ["IT-0002", "IT-0001"]

    @pytest.mark.asyncio
    async def test_book_value_equals_direct_compute_book_value_call(self, mock_db, reporting_app):
        model = {"id": "model-1", "usefulLifeYears": 5, "salvageValueCents": 10000}
        purchase_date = _iso(400)
        asset = report_asset(
            id="asset-1", assetTag="IT-0001", modelId="model-1",
            purchaseCostCents=250000, purchaseDate=purchase_date,
        )
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.asset_models.find.return_value.to_list.return_value = [model]

        r = await _run(reporting_app, "asset_value")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]

        expected = compute_book_value(
            purchase_date=purchase_date,
            purchase_cost_cents=250000,
            useful_life_years=5,
            salvage_value_cents=10000,
            now=datetime.now(timezone.utc),
        )
        assert row["Book Value"] == f"${expected['bookValueCents'] / 100:,.2f}"

    @pytest.mark.asyncio
    async def test_missing_depreciation_policy_yields_dash_and_reason(self, mock_db, reporting_app):
        asset = report_asset(
            id="asset-1", assetTag="IT-0001", modelId="model-missing",
            purchaseCostCents=250000, purchaseDate=_iso(10),
        )
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.asset_models.find.return_value.to_list.return_value = []  # model doc never resolves

        r = await _run(reporting_app, "asset_value")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["Book Value"] == "—"
        assert row["Reason"] == REASON_NO_DEPRECIATION_POLICY

    @pytest.mark.asyncio
    async def test_zero_rows_returns_declared_columns(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []

        r = await _run(reporting_app, "asset_value")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rows"] == []
        assert body["columns"] == _ASSET_VALUE_COLUMNS


class TestCheckoutActivityReport:
    """POST /api/itam/reports/prebuilt/checkout_activity/run"""

    @pytest.mark.asyncio
    async def test_returns_events_newest_first_with_resolved_asset(self, mock_db, reporting_app):
        asset = report_asset(id="asset-1", assetTag="IT-0001", name="Laptop X1")
        checkout = {
            "assetId": "asset-1", "action": "checkout", "targetType": "user",
            "targetId": "user-1", "actorUsername": "admin", "note": None, "ts": _iso(5),
        }
        checkin = {
            "assetId": "asset-1", "action": "checkin", "actorUsername": "admin",
            "note": "returned", "ts": _iso(2),
        }
        audit = {
            "assetId": "asset-1", "action": "audit", "actorUsername": "admin",
            "note": None, "ts": _iso(0.5),
        }
        mock_db.assignment_history.find = MagicMock(return_value=_cursor([audit, checkin, checkout]))
        mock_db.assets.find.return_value.to_list.return_value = [asset]

        r = await _run(reporting_app, "checkout_activity")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == _CHECKOUT_ACTIVITY_COLUMNS
        assert [row["Action"] for row in body["rows"]] == ["audit", "checkin", "checkout"]
        assert body["rows"][0]["Asset Tag"] == "IT-0001"
        assert body["rows"][0]["Asset Name"] == "Laptop X1"
        assert body["rows"][2]["Target Type"] == "user"
        assert body["rows"][2]["Target"] == "user-1"
        assert body["rows"][1]["Target Type"] == "—"  # checkin carries no target

    @pytest.mark.asyncio
    async def test_zero_rows_returns_declared_columns(self, mock_db, reporting_app):
        mock_db.assignment_history.find = MagicMock(return_value=_cursor([]))
        mock_db.assets.find.return_value.to_list.return_value = []

        r = await _run(reporting_app, "checkout_activity")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rows"] == []
        assert body["columns"] == _CHECKOUT_ACTIVITY_COLUMNS


class TestOverdueAuditsReport:
    """POST /api/itam/reports/prebuilt/overdue_audits/run"""

    @pytest.mark.asyncio
    async def test_returns_exactly_the_assets_overdue_query_matches(self, mock_db, reporting_app):
        cutoff_probe = _overdue_query("2000-01-01T00:00:00.000+00:00")
        # Sanity: _overdue_query's own shape is what this test relies on to
        # hand-evaluate which of the seeded assets a real Mongo would match.
        assert "$or" in cutoff_probe

        overdue_by_last_audit = report_asset(
            id="asset-overdue-1", assetTag="IT-1001", lifecycleStatus="deployed",
            lastAuditedAt=_iso(400), createdAt=_iso(500),
        )
        overdue_by_created = report_asset(
            id="asset-overdue-2", assetTag="IT-1002", lifecycleStatus="deployable",
            lastAuditedAt=None, createdAt=_iso(400),
        )
        never_audited_no_created = report_asset(
            id="asset-overdue-3", assetTag="IT-1003", lifecycleStatus="deployable",
            lastAuditedAt=None, createdAt=None,
        )
        # NOT overdue (recently audited) — deliberately excluded from the
        # mocked return below, simulating what the real _overdue_query filter
        # would exclude at the MongoDB layer.
        recently_audited = report_asset(
            id="asset-recent", assetTag="IT-2001", lifecycleStatus="deployed",
            lastAuditedAt=_iso(10), createdAt=_iso(500),
        )
        assert recently_audited  # constructed only to document the exclusion

        mock_db.assets.find.return_value.to_list.return_value = [
            overdue_by_last_audit, overdue_by_created, never_audited_no_created,
        ]

        r = await _run(reporting_app, "overdue_audits")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == _OVERDUE_AUDITS_COLUMNS
        returned_tags = {row["Asset Tag"] for row in body["rows"]}
        assert returned_tags == {"IT-1001", "IT-1002", "IT-1003"}

    @pytest.mark.asyncio
    async def test_sorted_ascending_by_days_overdue_with_unknown_basis_last(self, mock_db, reporting_app):
        far_overdue = report_asset(
            id="asset-a", assetTag="IT-A", lifecycleStatus="deployed",
            lastAuditedAt=_iso(1000), createdAt=_iso(1100),
        )
        recently_overdue = report_asset(
            id="asset-b", assetTag="IT-B", lifecycleStatus="deployed",
            lastAuditedAt=_iso(400), createdAt=_iso(500),
        )
        unknown_basis = report_asset(
            id="asset-c", assetTag="IT-C", lifecycleStatus="deployable",
            lastAuditedAt=None, createdAt=None,
        )
        mock_db.assets.find.return_value.to_list.return_value = [
            unknown_basis, far_overdue, recently_overdue,
        ]

        r = await _run(reporting_app, "overdue_audits")

        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert [row["Asset Tag"] for row in rows] == ["IT-B", "IT-A", "IT-C"]
        assert rows[-1]["Age Basis"] == "unknown"
        assert rows[-1]["Never Audited"] is True

    @pytest.mark.asyncio
    async def test_zero_rows_returns_declared_columns(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []

        r = await _run(reporting_app, "overdue_audits")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rows"] == []
        assert body["columns"] == _OVERDUE_AUDITS_COLUMNS


class TestLicenseUtilizationReport:
    """POST /api/itam/reports/prebuilt/license_utilization/run"""

    @pytest.mark.asyncio
    async def test_returns_rows_sorted_desc_by_utilization(self, mock_db, reporting_app):
        low_util = report_license(id="lic-low", name="Low Util Suite", seatCount=10)
        high_util = report_license(id="lic-high", name="High Util Suite", seatCount=10)
        mock_db.licenses.find.return_value.to_list.return_value = [low_util, high_util]
        # Iteration order matches the seeded list above: low_util first (2
        # assigned -> 20%), then high_util (9 assigned -> 90%).
        mock_db.license_assignments.count_documents = AsyncMock(side_effect=[2, 9])

        r = await _run(reporting_app, "license_utilization")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == _LICENSE_UTILIZATION_COLUMNS
        assert [row["License"] for row in body["rows"]] == ["High Util Suite", "Low Util Suite"]
        assert body["rows"][0]["Seats Assigned"] == 9
        assert body["rows"][0]["Seats Available"] == 1
        assert body["rows"][0]["Utilization %"] == 90.0

    @pytest.mark.asyncio
    async def test_zero_seat_count_reports_zero_percent_not_division_error(self, mock_db, reporting_app):
        lic = report_license(id="lic-zero", name="Zero Seats", seatCount=0)
        mock_db.licenses.find.return_value.to_list.return_value = [lic]
        mock_db.license_assignments.count_documents = AsyncMock(return_value=0)

        r = await _run(reporting_app, "license_utilization")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["Utilization %"] == 0

    @pytest.mark.asyncio
    async def test_zero_rows_returns_declared_columns(self, mock_db, reporting_app):
        mock_db.licenses.find.return_value.to_list.return_value = []

        r = await _run(reporting_app, "license_utilization")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rows"] == []
        assert body["columns"] == _LICENSE_UTILIZATION_COLUMNS


class TestLowStockConsumablesReport:
    """POST /api/itam/reports/prebuilt/low_stock_consumables/run"""

    @pytest.mark.asyncio
    async def test_flags_at_or_below_configured_threshold(self, mock_db, reporting_app):
        below_threshold = report_consumable(
            id="con-1", name="Low Stock Widget", availableQuantity=6, reorderThreshold=10,
        )
        above_threshold = report_consumable(
            id="con-2", name="Plenty Widget", availableQuantity=50, reorderThreshold=10,
        )
        mock_db.itam_consumables.find.return_value.to_list.return_value = [below_threshold, above_threshold]

        r = await _run(reporting_app, "low_stock_consumables")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["columns"] == _LOW_STOCK_CONSUMABLES_COLUMNS
        assert [row["Consumable"] for row in body["rows"]] == ["Low Stock Widget"]
        assert body["rows"][0]["Basis"] == "Configured threshold"

    @pytest.mark.asyncio
    async def test_no_threshold_uses_default_fallback_of_five(self, mock_db, reporting_app):
        flagged = report_consumable(
            id="con-1", name="No Threshold Low", availableQuantity=5, reorderThreshold=None,
        )
        not_flagged = report_consumable(
            id="con-2", name="No Threshold High", availableQuantity=6, reorderThreshold=None,
        )
        mock_db.itam_consumables.find.return_value.to_list.return_value = [flagged, not_flagged]

        r = await _run(reporting_app, "low_stock_consumables")

        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert [row["Consumable"] for row in rows] == ["No Threshold Low"]
        assert rows[0]["Basis"] == "Default (5)"

    @pytest.mark.asyncio
    async def test_above_threshold_and_fallback_is_absent(self, mock_db, reporting_app):
        comfortable = report_consumable(
            id="con-1", name="Comfortable Stock", availableQuantity=6, reorderThreshold=None,
        )
        mock_db.itam_consumables.find.return_value.to_list.return_value = [comfortable]

        r = await _run(reporting_app, "low_stock_consumables")

        assert r.status_code == 200, r.text
        assert r.json()["rows"] == []

    @pytest.mark.asyncio
    async def test_zero_rows_returns_declared_columns(self, mock_db, reporting_app):
        mock_db.itam_consumables.find.return_value.to_list.return_value = []

        r = await _run(reporting_app, "low_stock_consumables")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rows"] == []
        assert body["columns"] == _LOW_STOCK_CONSUMABLES_COLUMNS


class TestReorderThresholdField:
    """D-19: ConsumableCreate.reorderThreshold is optional and validates
    both absent and present."""

    def test_consumable_create_validates_with_field_absent(self):
        payload = ConsumableCreate(name="Cable", initialQuantity=20, unitType="unit")
        assert payload.reorderThreshold is None

    def test_consumable_create_validates_with_field_set(self):
        payload = ConsumableCreate(
            name="Cable", initialQuantity=20, unitType="unit", reorderThreshold=10,
        )
        assert payload.reorderThreshold == 10
