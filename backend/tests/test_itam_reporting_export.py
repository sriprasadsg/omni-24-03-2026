"""ITAM Reporting export/download tests — Phase 72, Plan 01 (tracer).

The tracer's end-to-end proof: a run returning the expiring asset while
excluding an in-warranty and an expired one; a CSV export writing a real
file whose header matches the declared columns and whose data rows equal
the full match set (not the preview page); a zero-row export still writing
a valid header-only file; download of that filename returning 200 for the
owning tenant and 403 for a different tenant; a filename containing
traversal segments returning 400 before any filesystem read; and an
unregistered export format returning 400.
"""
import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
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
import itam_reporting_endpoints
from itam_reporting_service import _REPORTS_DIR

_WARRANTY_COLUMNS = ["Asset Tag", "Name", "Lifecycle Status", "Warranty Expires", "Days To Expiry", "Status"]


def _client(app, tenant_id="tenant-a", role="admin", username="admin@example.com"):
    current_user = make_token_data(tenant_id=tenant_id, role=role, username=username)
    app.dependency_overrides[real_get_current_user] = lambda: current_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _offset_iso(days: int) -> str:
    """purchaseDate that, with warrantyMonths=0 (0 months added is a no-op —
    _add_months returns the purchase date unchanged), makes the warranty
    expire exactly `days` from now — sidesteps calendar-month arithmetic
    entirely for test setup."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class TestWarrantyExpiringRun:
    """POST /api/itam/reports/prebuilt/warranty_expiring/run"""

    @pytest.mark.asyncio
    async def test_run_returns_expiring_excludes_active_and_expired(self, mock_db, reporting_app):
        expiring = report_asset(
            id="asset-expiring", assetTag="IT-0001",
            purchaseDate=_offset_iso(15), warrantyMonths=0,  # expires in 15 days -> within 30-day default window
        )
        active = report_asset(
            id="asset-active", assetTag="IT-0002",
            purchaseDate=_offset_iso(200), warrantyMonths=0,  # expires in 200 days -> active
        )
        expired = report_asset(
            id="asset-expired", assetTag="IT-0003",
            purchaseDate=_offset_iso(-10), warrantyMonths=0,  # expired 10 days ago
        )
        mock_db.assets.find.return_value.to_list.return_value = [expiring, active, expired]
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        async with _client(reporting_app) as ac:
            r = await ac.post("/api/itam/reports/prebuilt/warranty_expiring/run")

        assert r.status_code == 200, r.text
        body = r.json()
        assert [row["Asset Tag"] for row in body["rows"]] == ["IT-0001"]
        assert body["rowCount"] == 1
        assert body["columns"] == _WARRANTY_COLUMNS
        assert body["truncated"] is False

    @pytest.mark.asyncio
    async def test_run_unknown_report_key_returns_404(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)
        async with _client(reporting_app) as ac:
            r = await ac.post("/api/itam/reports/prebuilt/not_a_real_report/run")
        assert r.status_code == 404


class TestWarrantyExpiringExport:
    """POST /api/itam/reports/prebuilt/warranty_expiring/export"""

    @pytest.mark.asyncio
    async def test_csv_export_writes_full_match_set_not_just_preview_page(self, mock_db, reporting_app):
        assets = [
            report_asset(id=f"asset-{i}", assetTag=f"IT-{i:04d}", purchaseDate=_offset_iso(15), warrantyMonths=0)
            for i in range(3)
        ]
        mock_db.assets.find.return_value.to_list.return_value = assets
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        async with _client(reporting_app) as ac:
            r = await ac.post("/api/itam/reports/prebuilt/warranty_expiring/export?format=csv")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rowCount"] == 3
        assert body["truncated"] is False

        file_path = os.path.join(_REPORTS_DIR, body["filename"])
        assert os.path.isfile(file_path)
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
        assert reader[0] == _WARRANTY_COLUMNS
        assert len(reader) - 1 == 3  # header + all 3 matches, not a paged subset

    @pytest.mark.asyncio
    async def test_zero_row_export_writes_header_only_file(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        async with _client(reporting_app) as ac:
            r = await ac.post("/api/itam/reports/prebuilt/warranty_expiring/export?format=csv")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["rowCount"] == 0

        file_path = os.path.join(_REPORTS_DIR, body["filename"])
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
        assert len(reader) == 1  # exactly one header line, zero data lines — never an error
        assert reader[0] == _WARRANTY_COLUMNS

    @pytest.mark.asyncio
    async def test_unregistered_format_returns_400(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)
        async with _client(reporting_app) as ac:
            r = await ac.post("/api/itam/reports/prebuilt/warranty_expiring/export?format=pdf")
        assert r.status_code == 400


class TestReportDownload:
    """GET /api/itam/reports/download/{filename}"""

    async def _export_and_get_filename(self, reporting_app):
        async with _client(reporting_app, tenant_id="tenant-a") as ac:
            r = await ac.post("/api/itam/reports/prebuilt/warranty_expiring/export?format=csv")
        assert r.status_code == 200, r.text
        return r.json()["filename"]

    @pytest.mark.asyncio
    async def test_download_owning_tenant_returns_200(self, mock_db, reporting_app):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)
        filename = await self._export_and_get_filename(reporting_app)
        mock_db.itam_report_exports.find_one = AsyncMock(
            return_value={"filename": filename, "tenantId": "tenant-a"}
        )

        async with _client(reporting_app, tenant_id="tenant-a") as ac:
            r = await ac.get(f"/api/itam/reports/download/{filename}")
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_download_cross_tenant_returns_403(self, mock_db, reporting_app, patch_reporting_get_database):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)
        filename = await self._export_and_get_filename(reporting_app)
        # The export was persisted under tenant-a; a tenant-b caller must be
        # rejected even though the filename is exact and correct.
        mock_db.itam_report_exports.find_one = AsyncMock(
            return_value={"filename": filename, "tenantId": "tenant-a"}
        )

        patch_reporting_get_database("tenant-b")
        async with _client(reporting_app, tenant_id="tenant-b") as ac:
            r = await ac.get(f"/api/itam/reports/download/{filename}")
        assert r.status_code == 403


class TestPathTraversalGuard:
    """T-72-03: a filename whose resolved path escapes the reports directory
    is rejected with 400 before any filesystem read. Called directly against
    the route function (bypassing ASGI routing) because a URL-encoded '/'
    segment is normalised away by Starlette's own router before reaching
    application code, which would 404 rather than exercise this module's
    containment check — the defense under test."""

    @pytest.mark.asyncio
    async def test_traversal_filename_rejected_with_400(self):
        admin = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        with pytest.raises(HTTPException) as exc_info:
            await itam_reporting_endpoints.download_report(
                filename="../../../../etc/passwd", current_user=admin,
            )
        assert exc_info.value.status_code == 400
