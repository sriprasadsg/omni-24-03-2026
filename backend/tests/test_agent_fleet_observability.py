"""
Tests for Phase 48 Plan 03 (Fleet Observability & Uptime Rollups, FOBS-03) —
`agent_fleet_observability_endpoints` GET /api/fleet/observability: offline
set + version-drift list, tenant-scoped for non-super-admins.

Reuses `monitor_agent_status()`'s existing `status == "Offline"` set (no new
offline heuristic) and `agent_auto_update_service._parse_ver` /
`_LATEST_AGENT_VERSION` (no new version parser) per D-03 / Don't Hand-Roll.
Hermetic — no real Mongo, no network.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from authentication_service import get_current_user
from auth_types import TokenData


def _user(role="security_analyst", tenant_id="tenant-a"):
    return TokenData(username="u@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _client(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class _AsyncCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def to_list(self, *a, **k):
        async def _inner():
            return self._docs
        return _inner()


def _mock_db(agents):
    """Mock db exposing db.agents.find(query, projection) -> cursor(agents).

    Captures the query filter passed in so tests can assert tenant scoping
    (Pitfall 5 — must use the request-scoped wrapped db, never db._db).
    """
    find_mock = MagicMock(return_value=_AsyncCursor(agents))
    agents_col = MagicMock(find=find_mock)
    db = MagicMock()
    db.agents = agents_col
    return db, find_mock


class TestFleetObservabilityEndpoint:
    """Behavior cases from 48-03-PLAN.md Task 1 <behavior>."""

    @patch("agent_fleet_observability_endpoints.get_database")
    def test_super_admin_sees_agents_across_all_tenants(self, mock_get_db):
        import agent_fleet_observability_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Offline", "version": "2.1.4", "tenantId": "tenant-a"},
            {"id": "a2", "hostname": "h2", "status": "Online", "version": "2.1.4", "tenantId": "tenant-b"},
        ]
        db, find_mock = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin", tenant_id="tenant-a")).get(
            "/api/fleet/observability"
        )

        assert res.status_code == 200
        body = res.json()
        assert body["offline_count"] == 1
        assert [a["id"] for a in body["offline_agents"]] == ["a1"]
        # Super admin's query filter must NOT be scoped to a single tenant.
        called_query = find_mock.call_args[0][0]
        assert "tenantId" not in called_query

    @patch("agent_fleet_observability_endpoints.get_database")
    def test_tenant_admin_scoped_to_own_tenant(self, mock_get_db):
        import agent_fleet_observability_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Offline", "version": "2.1.4", "tenantId": "tenant-a"},
        ]
        db, find_mock = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Tenant Admin", tenant_id="tenant-a")).get(
            "/api/fleet/observability"
        )

        assert res.status_code == 200
        called_query = find_mock.call_args[0][0]
        assert called_query.get("tenantId") == "tenant-a"

    @patch("agent_fleet_observability_endpoints.get_database")
    def test_version_drift_includes_only_older_parseable_versions(self, mock_get_db):
        import agent_fleet_observability_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Online", "version": "2.1.5", "tenantId": "tenant-a"},  # current
            {"id": "a2", "hostname": "h2", "status": "Online", "version": "2.0.0", "tenantId": "tenant-a"},  # drifted
            {"id": "a3", "hostname": "h3", "status": "Online", "version": "2.2.0", "tenantId": "tenant-a"},  # newer, not drift
        ]
        db, _ = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/observability")

        assert res.status_code == 200
        body = res.json()
        assert [a["id"] for a in body["version_drift"]] == ["a2"]
        assert body["drift_count"] == 1
        assert body["latest_version"] == "2.1.5"

    @patch("agent_fleet_observability_endpoints.get_database")
    def test_malformed_or_missing_version_excluded_without_crash(self, mock_get_db):
        import agent_fleet_observability_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Online", "version": "not-a-version", "tenantId": "tenant-a"},
            {"id": "a2", "hostname": "h2", "status": "Online", "tenantId": "tenant-a"},  # missing version
            {"id": "a3", "hostname": "h3", "status": "Online", "version": None, "tenantId": "tenant-a"},
        ]
        db, _ = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/observability")

        assert res.status_code == 200
        body = res.json()
        assert body["version_drift"] == []
        assert body["drift_count"] == 0

    @patch("agent_fleet_observability_endpoints.get_database")
    def test_offline_set_read_from_status_field_not_new_heuristic(self, mock_get_db):
        import agent_fleet_observability_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Offline", "version": "2.1.4", "tenantId": "tenant-a"},
            {"id": "a2", "hostname": "h2", "status": "Online", "version": "2.1.4", "tenantId": "tenant-a"},
            {"id": "a3", "hostname": "h3", "status": "Degraded", "version": "2.1.4", "tenantId": "tenant-a"},
        ]
        db, _ = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/observability")

        assert res.status_code == 200
        body = res.json()
        assert [a["id"] for a in body["offline_agents"]] == ["a1"]
        assert body["offline_count"] == 1
        assert body["latest_version"] == m._LATEST_AGENT_VERSION


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
