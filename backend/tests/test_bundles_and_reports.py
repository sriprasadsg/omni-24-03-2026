"""
Tests for bundle_endpoints and ticket_reports_endpoints.

Each test mounts only the relevant router, patches get_database() and
rate_limiter so no real MongoDB, JWT, or Redis is required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _async_iter(items):
    """Return an async iterable over items for mocking aggregate()."""
    class _Iter:
        def __init__(self):
            self._items = iter(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration:
                raise StopAsyncIteration
        async def to_list(self, length=None):
            return list(items)
    return _Iter()


def _col():
    col = MagicMock()
    col.find_one      = AsyncMock(return_value=None)
    col.insert_one    = AsyncMock(return_value=MagicMock(inserted_id="id"))
    col.update_one    = AsyncMock(return_value=MagicMock(matched_count=1))
    col.count_documents = AsyncMock(return_value=0)
    col.find          = MagicMock()
    col.find.return_value.sort = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    col.aggregate     = MagicMock(side_effect=lambda _: _async_iter([]))
    return col


def _db():
    db = MagicMock()
    db.tenants = _col()
    db.tickets = _col()
    db.__getitem__ = lambda self, key: getattr(self, key, _col())
    return db


def _app_with_limiter(router, user):
    """Build a minimal FastAPI app with limiter disabled and permissions bypassed."""
    from authentication_service import get_current_user as _gcu
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_gcu] = lambda: user

    # Disable slowapi rate-limiter in tests
    try:
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        test_limiter = Limiter(key_func=get_remote_address, enabled=False)
        app.state.limiter = test_limiter
    except ImportError:
        pass
    return app


# ===========================================================================
# bundle_endpoints
# ===========================================================================

class TestBundleEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import bundle_endpoints as mod
        self.mod = mod
        self.db  = _db()
        self.app = _app_with_limiter(mod.router, tenant_user)
        self.client = TestClient(self.app)

    def test_list_bundles_returns_200(self):
        with patch("bundle_endpoints.get_current_user", return_value=True):
            resp = self.client.get("/api/bundles")
        assert resp.status_code == 200
        body = resp.json()
        assert "bundles" in body
        assert isinstance(body["bundles"], list)
        assert body["total"] > 0

    def test_list_bundles_includes_ticketing_only(self):
        with patch("bundle_endpoints.get_current_user", return_value=True):
            resp = self.client.get("/api/bundles")
        keys = [b["key"] for b in resp.json()["bundles"]]
        assert "ticketing_only" in keys

    def test_get_bundle_detail(self):
        with patch("bundle_endpoints.get_current_user", return_value=True):
            resp = self.client.get("/api/bundles/security")
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "security"
        assert "features" in body
        assert len(body["features"]) > 0

    def test_get_unknown_bundle_returns_404(self):
        with patch("bundle_endpoints.get_current_user", return_value=True):
            resp = self.client.get("/api/bundles/nonexistent_bundle_xyz")
        assert resp.status_code == 404

    def test_catalog_returns_grouped_features(self):
        with patch("bundle_endpoints.get_current_user", return_value=True):
            resp = self.client.get("/api/bundles/catalog")
        assert resp.status_code == 200
        body = resp.json()
        assert "catalog" in body
        assert "core" in body["catalog"]
        assert body["total"] > 0

    def test_get_tenant_features_not_found(self):
        self.db.tenants.find_one = AsyncMock(return_value=None)
        with patch("bundle_endpoints.get_database", return_value=self.db):
            resp = self.client.get("/api/bundles/tenant/no-such-tenant/features")
        assert resp.status_code == 404

    def test_get_tenant_features_legacy_mode(self):
        """Tenant with no assignedBundles returns empty feature list."""
        self.db.tenants.find_one = AsyncMock(return_value={
            "id": "t1", "assignedBundles": [], "customFeatures": [], "blockedFeatures": []
        })
        with patch("bundle_endpoints.get_database", return_value=self.db):
            resp = self.client.get("/api/bundles/tenant/t1/features")
        assert resp.status_code == 200
        body = resp.json()
        assert body["assigned_bundles"] == []
        assert isinstance(body["effective_features"], list)

    def test_assign_bundles_valid(self, super_admin_user):
        self.db.tenants.find_one = AsyncMock(return_value={"id": "t1"})
        app = _app_with_limiter(self.mod.router, super_admin_user)
        client = TestClient(app)
        with patch("bundle_endpoints.get_database", return_value=self.db), \
             patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True)):
            resp = client.put("/api/bundles/tenant/t1/assign", json={
                "assigned_bundles": ["ticketing_only", "security"],
                "custom_features": [],
                "blocked_features": [],
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["effective_feature_count"] > 0

    def test_assign_unknown_bundle_returns_400(self, super_admin_user):
        self.db.tenants.find_one = AsyncMock(return_value={"id": "t1"})
        app = _app_with_limiter(self.mod.router, super_admin_user)
        client = TestClient(app)
        with patch("bundle_endpoints.get_database", return_value=self.db), \
             patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True)):
            resp = client.put("/api/bundles/tenant/t1/assign", json={
                "assigned_bundles": ["does_not_exist_xyz"],
                "custom_features": [],
                "blocked_features": [],
            })
        assert resp.status_code == 400

    def test_clear_tenant_bundles(self, super_admin_user):
        self.db.tenants.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        app = _app_with_limiter(self.mod.router, super_admin_user)
        client = TestClient(app)
        with patch("bundle_endpoints.get_database", return_value=self.db), \
             patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True)):
            resp = client.delete("/api/bundles/tenant/t1/assign")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_clear_nonexistent_tenant_returns_404(self, super_admin_user):
        self.db.tenants.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
        app = _app_with_limiter(self.mod.router, super_admin_user)
        client = TestClient(app)
        with patch("bundle_endpoints.get_database", return_value=self.db), \
             patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True)):
            resp = client.delete("/api/bundles/tenant/ghost/assign")
        assert resp.status_code == 404


# ===========================================================================
# ticket_reports_endpoints
# ===========================================================================

class TestTicketReportEndpoints:

    @pytest.fixture(autouse=True)
    def setup(self, tenant_user):
        import ticket_reports_endpoints as mod
        self.mod = mod
        self.db  = _db()
        self.app = _app_with_limiter(mod.router, tenant_user)
        self.client = TestClient(self.app)

    # Patch both the DB and rbac permission check for all report tests
    def _patches(self):
        return (
            patch("ticket_reports_endpoints.get_database", return_value=self.db),
            patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True)),
        )

    def test_summary_empty_db(self, tenant_user):
        self.db.tickets.count_documents = AsyncMock(return_value=0)
        self.db.tickets.aggregate = MagicMock(side_effect=lambda _: _async_iter([]))
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["open"]  == 0
        assert body["closed"] == 0

    def test_summary_with_data(self, tenant_user):
        self.db.tickets.count_documents = AsyncMock(side_effect=[
            10, 4, 6, 1, 0,   # total, open, closed, overdue, escalated
            5, 1,              # sla_met, sla_breached
        ])
        self.db.tickets.aggregate = MagicMock(
            side_effect=lambda _: _async_iter([{"avg_ms": 7_200_000}])  # 2h avg
        )
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"]  == 10
        assert body["open"]   == 4
        assert body["closed"] == 6
        assert body["sla_compliance_rate"] == 83.3
        assert body["avg_resolution_hours"] == 2.0

    def test_trends_default_days(self, tenant_user):
        self.db.tickets.aggregate = MagicMock(side_effect=lambda _: _async_iter([]))
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/trends")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["period"] == "daily"
        assert len(body["data"]) >= 28

    def test_trends_weekly_period(self, tenant_user):
        self.db.tickets.aggregate = MagicMock(side_effect=lambda _: _async_iter([]))
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/trends?days=30&period=weekly")
        assert resp.status_code == 200
        assert resp.json()["period"] == "weekly"

    def test_sla_report_empty(self, tenant_user):
        self.db.tickets.count_documents = AsyncMock(return_value=0)
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/sla")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sla_met"] == 0
        assert body["compliance_rate"] is None
        assert len(body["by_priority"]) == 4

    def test_resolution_empty(self, tenant_user):
        self.db.tickets.aggregate = MagicMock(
            side_effect=lambda _: _async_iter([{"overall": [], "by_priority": [], "by_type": []}])
        )
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/resolution")
        assert resp.status_code == 200
        body = resp.json()
        assert "overall" in body
        assert "by_priority" in body

    def test_ageing_empty(self, tenant_user):
        self.db.tickets.find = MagicMock()
        self.db.tickets.find.return_value.to_list = AsyncMock(return_value=[])
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/ageing")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["buckets"]) == 6
        assert body["total_open"] == 0

    def test_ageing_buckets_shape(self, tenant_user):
        from datetime import datetime, timezone, timedelta
        old    = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        recent = datetime.now(timezone.utc).isoformat()
        self.db.tickets.find.return_value.to_list = AsyncMock(return_value=[
            {"created_at": old,    "priority": "critical"},
            {"created_at": recent, "priority": "low"},
        ])
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/ageing")
        body = resp.json()
        assert body["total_open"] == 2
        last = body["buckets"][-1]
        assert last["label"] == "> 4 weeks"
        assert last["count"] == 1
        assert last["critical"] == 1

    def test_assignee_empty(self, tenant_user):
        self.db.tickets.aggregate = MagicMock(side_effect=lambda _: _async_iter([]))
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/reports/assignee")
        assert resp.status_code == 200
        assert resp.json()["assignees"] == []

    def test_csv_export_returns_csv(self, tenant_user):
        find_mock = MagicMock()
        find_mock.sort = MagicMock(return_value=find_mock)
        find_mock.to_list = AsyncMock(return_value=[
            {"ticket_number": "TKT-0001", "title": "Test ticket",
             "type": "bug", "status": "open", "priority": "high",
             "assignee": "alice", "reporter": "bob", "tags": ["urgent"]},
        ])
        self.db.tickets.find = MagicMock(return_value=find_mock)
        with self._patches()[0], self._patches()[1]:
            resp = self.client.get("/api/tickets/export/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "TKT-0001" in resp.text
        assert "ticket_number" in resp.text


# ===========================================================================
# feature_bundles unit tests (pure Python, no DB/HTTP)
# ===========================================================================

class TestFeatureBundles:

    def test_all_bundle_features_exist_in_catalog(self):
        from feature_bundles import PREDEFINED_BUNDLES, FEATURE_CATALOG
        for bundle_key, bundle in PREDEFINED_BUNDLES.items():
            for fkey in bundle["features"]:
                assert fkey in FEATURE_CATALOG, \
                    f"Bundle '{bundle_key}' references unknown feature '{fkey}'"

    def test_ticketing_only_contains_tickets(self):
        from feature_bundles import PREDEFINED_BUNDLES
        assert "tickets" in PREDEFINED_BUNDLES["ticketing_only"]["features"]

    def test_full_platform_contains_all_features(self):
        from feature_bundles import PREDEFINED_BUNDLES, FEATURE_CATALOG
        fp = set(PREDEFINED_BUNDLES["full_platform"]["features"])
        catalog = set(FEATURE_CATALOG.keys())
        assert fp == catalog

    def test_resolve_tenant_features_union(self):
        from feature_bundles import resolve_tenant_features
        effective = resolve_tenant_features(
            assigned_bundles=["ticketing_only", "security"],
        )
        assert "tickets" in effective
        assert "edr" in effective

    def test_resolve_tenant_features_custom(self):
        from feature_bundles import resolve_tenant_features
        effective = resolve_tenant_features(
            assigned_bundles=["ticketing_only"],
            custom_features=["finops"],
        )
        assert "finops" in effective

    def test_resolve_tenant_features_blocked(self):
        from feature_bundles import resolve_tenant_features
        effective = resolve_tenant_features(
            assigned_bundles=["security"],
            blocked_features=["dlp"],
        )
        assert "dlp" not in effective

    def test_get_bundle_list_shape(self):
        from feature_bundles import get_bundle_list
        bundles = get_bundle_list()
        assert all("key" in b for b in bundles)
        assert all("features" in b for b in bundles)
        assert all("feature_count" in b for b in bundles)
        assert all(b["feature_count"] > 0 for b in bundles)
