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
)

from authentication_service import get_current_user as real_get_current_user
from itam_finance_service import REASON_NO_DEPRECIATION_POLICY, compute_book_value
from itam_lifecycle_endpoints import _overdue_query
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


def _client(app, tenant_id="tenant-a", role="admin", username="admin@example.com"):
    current_user = make_token_data(tenant_id=tenant_id, role=role, username=username)
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
    def test_all_reports_registered_so_far(self):
        assert {"warranty_expiring", "asset_value", "checkout_activity", "overdue_audits"} <= set(
            PREBUILT_REPORTS
        )


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
