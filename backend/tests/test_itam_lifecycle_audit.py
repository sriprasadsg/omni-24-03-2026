"""ITAM Lifecycle tests — Phase 57 Plan 03: physical-audit mark and the
overdue-audit report (ITAM-LIFE-05).

Shared mock DB/fixtures live in itam_lifecycle_test_support.py (split out to keep
every test file under the CLAUDE.md 500-line limit; see test_itam_lifecycle.py for
checkin coverage and test_itam_lifecycle_history.py for the history-read route).

New file (not appended to test_itam_lifecycle.py, which is already near the
500-line cap) — same split precedent 57-01/57-02 established.
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_lifecycle_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    patch_get_database_globally,
    lifecycle_app,
)

from authentication_service import get_current_user as real_get_current_user


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds")


def _matches_or_query(doc, query):
    """Minimal local evaluator for the $or/$lt/$exists query shape this plan
    produces — lets a test prove real query-construction correctness (does a
    given document satisfy the filter?) without a live MongoDB."""
    for clause in query["$or"]:
        if _matches_clause(doc, clause):
            return True
    return False


def _matches_clause(doc, clause):
    for key, cond in clause.items():
        if isinstance(cond, dict):
            if "$exists" in cond and (key in doc) != cond["$exists"]:
                return False
            if "$lt" in cond and not (key in doc and doc[key] < cond["$lt"]):
                return False
        elif doc.get(key) != cond:
            return False
    return True


class TestAuditMark:
    """Task 1 — POST /api/assets/{asset_id}/audit: attributed, and orthogonal
    to checkout state (ITAM-LIFE-05, first half)."""

    @pytest.mark.asyncio
    async def test_audit_mark_sets_last_audited_at(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable",
            "lastAuditedAt": "2026-08-04T00:00:00.000+00:00",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert "lastAuditedAt" in update["$set"]

    @pytest.mark.asyncio
    async def test_audit_mark_accepts_caller_supplied_date(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={"auditedAt": "2026-07-01T00:00:00.000+00:00"})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert update["$set"]["lastAuditedAt"] == "2026-07-01T00:00:00.000+00:00"

    @pytest.mark.asyncio
    async def test_audit_mark_records_asserter_and_recording_time(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={"auditedAt": "2026-07-01T00:00:00.000+00:00"})

        assert r.status_code == 200, r.text
        set_doc = mock_db.assets.find_one_and_update.call_args[0][1]["$set"]
        assert set_doc["lastAuditedBy"] == "admin@example.com"
        assert "lastAuditRecordedAt" in set_doc
        # The claim (auditedAt) and the filing (lastAuditRecordedAt) are never
        # collapsed into one field — present even for a backdated assertion.
        assert set_doc["lastAuditRecordedAt"] != set_doc["lastAuditedAt"]

    @pytest.mark.asyncio
    async def test_audit_mark_does_not_touch_lifecycle_or_assignment(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={})

        assert r.status_code == 200, r.text
        update = mock_db.assets.find_one_and_update.call_args[0][1]
        assert set(update["$set"].keys()) == {
            "lastAuditedAt", "lastAuditedBy", "lastAuditRecordedAt", "updatedAt",
        }
        assert "$unset" not in update

    @pytest.mark.asyncio
    async def test_audit_mark_works_on_checked_out_asset(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={
            "id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployed",
            "assignedToType": "user", "assignedToId": "user-7",
        })
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={})

        assert r.status_code == 200, r.text
        filt = mock_db.assets.find_one_and_update.call_args[0][0]
        assert "lifecycleStatus" not in filt

    @pytest.mark.asyncio
    async def test_audit_mark_of_missing_asset_returns_404(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=None)
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-missing/audit", json={})

        assert r.status_code == 404, r.text
        mock_db.assignment_history.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_mark_writes_history_entry(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one_and_update = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={
                "auditedAt": "2026-07-01T00:00:00.000+00:00", "note": "Walked the floor",
            })

        assert r.status_code == 200, r.text
        assert mock_db.assignment_history.insert_one.await_count == 1
        inserted_doc = mock_db.assignment_history.insert_one.call_args[0][0]
        assert inserted_doc["assetId"] == "asset-1"
        assert inserted_doc["action"] == "audit"
        assert inserted_doc["actorUsername"] == "admin@example.com"
        assert inserted_doc["auditedAt"] == "2026-07-01T00:00:00.000+00:00"

    @pytest.mark.asyncio
    async def test_audit_mark_rejects_unknown_field(self, mock_db, lifecycle_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={"bogusField": True})

        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_audit_mark_requires_manage_assets_permission(self, mock_db, lifecycle_app, patch_get_database_globally, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/assets/asset-1/audit", json={})

        assert r.status_code == 403, r.text


class TestOverdueAuditReport:
    """Task 2 — GET /api/assets/reports/overdue-audit: honest population,
    explicit age basis, unshadowable route (ITAM-LIFE-05, second half)."""

    @pytest.mark.asyncio
    async def test_overdue_includes_stale_audited_asset(self, mock_db, lifecycle_app, patch_get_database_globally):
        stale_doc = {"id": "asset-1", "lastAuditedAt": _iso_days_ago(400)}
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[stale_doc])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert len(rows) == 1
        assert rows[0]["ageBasis"] == "lastAuditedAt"
        assert rows[0]["neverAudited"] is False
        assert isinstance(rows[0]["daysOverdue"], int) and rows[0]["daysOverdue"] > 0

    @pytest.mark.asyncio
    async def test_overdue_excludes_recently_audited_asset(self, mock_db, lifecycle_app, patch_get_database_globally):
        """The cutoff branch for lastAuditedAt uses a strict $lt, so an asset
        audited today would never satisfy branch one."""
        import itam_lifecycle_endpoints as m

        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        query = mock_db.assets.find.call_args[0][0]
        cutoff = query["$or"][0]["lastAuditedAt"]["$lt"]
        audited_today = m._now_iso()
        # cutoff is AUDIT_INTERVAL_DAYS in the past, so "now" never satisfies
        # a strict-less-than comparison against it.
        assert not (audited_today < cutoff)

    def test_overdue_boundary_is_strictly_older_than_cutoff(self):
        """An asset whose lastAuditedAt equals the cutoff exactly is not
        overdue; one an instant older is — pinned by the $lt operator (not
        $lte) plus a direct evaluation against the query shape."""
        import itam_lifecycle_endpoints as m

        cutoff = m._audit_cutoff_iso()
        query = m._overdue_query(cutoff)
        assert query["$or"][0]["lastAuditedAt"] == {"$lt": cutoff}

        at_cutoff = {"id": "a1", "lastAuditedAt": cutoff}
        assert not _matches_or_query(at_cutoff, query)

        one_ms_older = {"id": "a2", "lastAuditedAt": (
            datetime.fromisoformat(cutoff) - timedelta(milliseconds=1)
        ).isoformat(timespec="milliseconds")}
        assert _matches_or_query(one_ms_older, query)

    @pytest.mark.asyncio
    async def test_overdue_falls_back_to_created_at(self, mock_db, lifecycle_app, patch_get_database_globally):
        never_audited_doc = {"id": "asset-2", "createdAt": _iso_days_ago(400)}
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[never_audited_doc])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["ageBasis"] == "createdAt"
        assert row["neverAudited"] is True

    @pytest.mark.asyncio
    async def test_overdue_parses_real_create_manual_asset_timestamp(self, mock_db, lifecycle_app, patch_get_database_globally):
        """Regression for CR-01: create_manual_asset must produce a createdAt value
        that _overdue_row can actually parse into a non-null daysOverdue. Round-trips
        the exact timestamp expression itam_asset_endpoints.create_manual_asset uses
        (rather than a hand-crafted well-formed string) through the report's date math."""
        from datetime import datetime, timezone, timedelta

        real_created_at = (
            (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(timespec="milliseconds")
        )
        never_audited_doc = {"id": "asset-4", "createdAt": real_created_at}
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[never_audited_doc])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["ageBasis"] == "createdAt"
        assert row["neverAudited"] is True
        assert row["daysOverdue"] is not None
        assert row["daysOverdue"] >= 30

    @pytest.mark.asyncio
    async def test_overdue_includes_asset_with_no_dates_as_unknown_basis(self, mock_db, lifecycle_app, patch_get_database_globally):
        no_dates_doc = {"id": "asset-3", "name": "Agent-discovered box"}
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[no_dates_doc])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        row = r.json()["rows"][0]
        assert row["ageBasis"] == "unknown"
        assert row["neverAudited"] is True
        assert row["daysOverdue"] is None

    @pytest.mark.asyncio
    async def test_overdue_query_has_three_or_branches(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        query = mock_db.assets.find.call_args[0][0]
        assert len(query["$or"]) == 3

    @pytest.mark.asyncio
    async def test_overdue_marking_audited_removes_from_report(self, mock_db, lifecycle_app, patch_get_database_globally):
        import itam_lifecycle_endpoints as m

        cutoff = m._audit_cutoff_iso()
        query = m._overdue_query(cutoff)

        stale_doc = {"id": "asset-1", "lastAuditedAt": _iso_days_ago(400)}
        assert _matches_or_query(stale_doc, query)

        freshly_audited_doc = {"id": "asset-1", "lastAuditedAt": m._now_iso()}
        assert not _matches_or_query(freshly_audited_doc, query)

    @pytest.mark.asyncio
    async def test_overdue_report_is_tenant_scoped(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        # The TenantIsolatedCollection wrapper injects tenantId into every
        # filter handed to the raw collection — the report never queries
        # cross-tenant.
        query = mock_db.assets.find.call_args[0][0]
        assert query["tenantId"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_overdue_report_requires_manage_assets_permission(self, mock_db, lifecycle_app, patch_get_database_globally, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_overdue_route_is_not_shadowed_by_legacy_asset_lookup(self, mock_db, patch_get_database_globally, monkeypatch):
        """Mounts asset_endpoints.router FIRST and the lifecycle router SECOND,
        then confirms the report path still reaches overdue_audit_report — the
        regression test for the stale-registration-order trap. This must fail
        if the route is ever shortened to a single segment."""
        import asset_endpoints
        import itam_asset_endpoints
        import itam_lifecycle_endpoints
        from fastapi import FastAPI

        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
        monkeypatch.setattr(itam_lifecycle_endpoints, "invalidate_cache", MagicMock())
        mock_db.assets.find.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")

        app = FastAPI()
        app.include_router(asset_endpoints.router)          # legacy single-segment router, FIRST
        app.include_router(itam_lifecycle_endpoints.router)  # lifecycle router, SECOND
        app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/reports/overdue-audit")

        assert r.status_code == 200, r.text
        assert "intervalDays" in r.json()
        assert "rows" in r.json()
