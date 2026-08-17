"""ITAM Lifecycle tests — Phase 57 Plan 02, Task 2: the history read route, its
edge semantics (empty / identical timestamps / tie ordering), and the router-level
append-only regression guard.

Shared mock DB/fixtures live in itam_lifecycle_test_support.py (split out to keep
every test file under the CLAUDE.md 500-line limit; see test_itam_lifecycle.py for
Task 1's checkin coverage and test_itam_lifecycle_expansion.py for 57-01's
checkout expansion coverage).

New file (not appended to test_itam_lifecycle.py or test_itam_lifecycle_expansion.py)
because both are already near the 500-line cap after Task 1's checkin tests.
"""
import sys
import os
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


class TestAssignmentHistory:
    """Task 2 — GET /api/assets/{asset_id}/history, its edge semantics, and the
    append-only regression guard (ITAM-LIFE-04)."""

    @pytest.mark.asyncio
    async def test_history_returns_entries_newest_first(self, mock_db, lifecycle_app, patch_get_database_globally):
        entries = [
            {"id": "ah-3", "assetId": "asset-1", "action": "checkin", "ts": "2026-08-03T00:00:00.000+00:00"},
            {"id": "ah-2", "assetId": "asset-1", "action": "checkout", "ts": "2026-08-02T00:00:00.000+00:00"},
            {"id": "ah-1", "assetId": "asset-1", "action": "checkout", "ts": "2026-08-01T00:00:00.000+00:00"},
        ]
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=entries
        )

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history")

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["assetId"] == "asset-1"
        assert [e["id"] for e in data["entries"]] == ["ah-3", "ah-2", "ah-1"]

    @pytest.mark.asyncio
    async def test_history_sort_is_a_deterministic_total_order(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history")

        assert r.status_code == 200, r.text
        sort_call = mock_db.assignment_history.find.return_value.sort.call_args
        assert sort_call[0][0] == [("ts", -1), ("_id", -1)]

    @pytest.mark.asyncio
    async def test_history_identical_timestamps_both_returned(self, mock_db, lifecycle_app, patch_get_database_globally):
        entries = [
            {"id": "ah-2", "assetId": "asset-1", "action": "checkin", "ts": "2026-08-03T00:00:00.000+00:00"},
            {"id": "ah-1", "assetId": "asset-1", "action": "checkout", "ts": "2026-08-03T00:00:00.000+00:00"},
        ]
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=entries
        )

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["entries"]) == 2
        assert {e["id"] for e in data["entries"]} == {"ah-1", "ah-2"}

    @pytest.mark.asyncio
    async def test_history_empty_returns_200_and_empty_list(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one = AsyncMock(return_value={"id": "asset-1", "tenantId": "tenant-a"})
        mock_db.assignment_history.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history")

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["entries"] == []

    @pytest.mark.asyncio
    async def test_history_unknown_asset_returns_404(self, mock_db, lifecycle_app, patch_get_database_globally):
        mock_db.assets.find_one = AsyncMock(return_value=None)

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-missing/history")

        assert r.status_code == 404, r.text

    @pytest.mark.asyncio
    async def test_history_cross_tenant_asset_returns_404(self, mock_db, lifecycle_app, patch_get_database_globally):
        """An asset id that resolves only under another tenant gets the same 404 as
        an unknown id, and zero assignment_history rows are ever read."""
        stored = [{"id": "asset-b", "tenantId": "tenant-b"}]
        mock_db.assets.find_one = AsyncMock(side_effect=lambda f, *a, **kw:
            next((d for d in stored if d.get("tenantId") == f.get("tenantId") and d.get("id") == f.get("id")), None))

        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-b/history")

        assert r.status_code == 404, r.text
        mock_db.assignment_history.find.assert_not_called()

    @pytest.mark.asyncio
    async def test_history_respects_limit_cap(self, mock_db, lifecycle_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history", params={"limit": 501})

        assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_history_requires_manage_assets_permission(self, mock_db, lifecycle_app, patch_get_database_globally, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))

        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        patch_get_database_globally("tenant-a")
        lifecycle_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/history")

        assert r.status_code == 403, r.text

    def test_no_mutating_route_exists_on_the_lifecycle_router(self):
        """The 57-01 append-only prohibition, regression-tested at the routing
        layer: no route on this router uses PUT, PATCH or DELETE, under any path."""
        import itam_lifecycle_endpoints as m
        bad = [
            (r.path, sorted(r.methods))
            for r in m.router.routes
            if {"PUT", "PATCH", "DELETE"} & set(r.methods)
        ]
        assert bad == [], bad

    def test_history_service_module_exposes_no_mutating_function(self):
        """Re-assert the 57-01 introspection check from inside the test suite so a
        future edit to itam_lifecycle_service.py fails a test, not only a
        plan-time gate."""
        import itam_lifecycle_service as s
        public = sorted(
            n for n in dir(s)
            if not n.startswith("_")
            and callable(getattr(s, n))
            and getattr(getattr(s, n), "__module__", "") == "itam_lifecycle_service"
        )
        assert public == ["list_history", "write_history"]
