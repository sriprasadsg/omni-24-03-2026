"""
Tests for Phase 49 Plan 01 (Fleet Geo Map, GMAP-02/03) —
`agent_fleet_geo_endpoints` GET /api/fleet/geo: cross-tenant fleet-geo
aggregate returning map-relevant fields (identity, status, tenant, LAN/public
IP, resolved lat/lon geo), tenant-scoped for non-super-admins.

Clones the 48-03 tenant-gating harness verbatim (`is_super_admin` gate,
request-scoped wrapped `get_database()` — never `db._db`; T-48-07). Unlocated
agents (no lat/lon) are surfaced as unlocated, never dropped (D-07).
Hermetic — no real Mongo, no network.
"""
import os
import sys
from unittest.mock import MagicMock, patch

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

    def to_list(self, *a, **k):
        async def _inner():
            return self._docs
        return _inner()


def _mock_db(agents):
    """Mock db exposing db.agents.find(query, projection) -> cursor(agents).

    Captures the query filter so tests can assert tenant scoping (T-48-07 —
    must use the request-scoped wrapped db, never db._db).
    """
    find_mock = MagicMock(return_value=_AsyncCursor(agents))
    agents_col = MagicMock(find=find_mock)
    db = MagicMock()
    db.agents = agents_col
    return db, find_mock


def _located(id, tenant, lat, lon, status="Online"):
    return {
        "id": id, "hostname": f"host-{id}", "status": status, "tenantId": tenant,
        "ipAddress": "10.0.0.5", "publicIp": "203.0.113.9",
        "geo": {"city": "Berlin", "country": "Germany", "country_code": "DE",
                "latitude": lat, "longitude": lon},
    }


def _unlocated(id, tenant, status="Offline"):
    return {"id": id, "hostname": f"host-{id}", "status": status, "tenantId": tenant,
            "ipAddress": "10.0.0.6", "publicIp": None, "geo": None}


class TestFleetGeoEndpoint:
    @patch("agent_fleet_geo_endpoints.get_database")
    def test_super_admin_sees_agents_across_all_tenants(self, mock_get_db):
        import agent_fleet_geo_endpoints as m

        agents = [_located("a1", "tenant-a", 52.5, 13.4), _located("a2", "tenant-b", 48.8, 2.3)]
        db, find_mock = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin", tenant_id="tenant-a")).get("/api/fleet/geo")

        assert res.status_code == 200
        body = res.json()
        assert {a["tenantId"] for a in body["agents"]} == {"tenant-a", "tenant-b"}
        # Super admin's query must NOT be tenant-scoped.
        assert "tenantId" not in find_mock.call_args[0][0]
        assert body["tenants"] == ["tenant-a", "tenant-b"]

    @patch("agent_fleet_geo_endpoints.get_database")
    def test_non_super_admin_scoped_to_own_tenant(self, mock_get_db):
        import agent_fleet_geo_endpoints as m

        db, find_mock = _mock_db([_located("a1", "tenant-a", 52.5, 13.4)])
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="security_analyst", tenant_id="tenant-a")).get("/api/fleet/geo")

        assert res.status_code == 200
        assert find_mock.call_args[0][0].get("tenantId") == "tenant-a"

    @patch("agent_fleet_geo_endpoints.get_database")
    def test_located_and_unlocated_counting(self, mock_get_db):
        import agent_fleet_geo_endpoints as m

        agents = [
            _located("a1", "tenant-a", 52.5, 13.4),
            _located("a2", "tenant-a", 48.8, 2.3),
            _unlocated("a3", "tenant-a"),
        ]
        db, _ = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/geo")

        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 3
        assert body["located_count"] == 2
        assert body["unlocated_count"] == 1
        a3 = next(a for a in body["agents"] if a["id"] == "a3")
        assert a3["geo"] is None  # unlocated present, not dropped (D-07)

    @patch("agent_fleet_geo_endpoints.get_database")
    def test_projection_carries_drilldown_fields(self, mock_get_db):
        import agent_fleet_geo_endpoints as m

        db, _ = _mock_db([_located("a1", "tenant-a", 52.5, 13.4, status="Quarantined")])
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/geo")

        assert res.status_code == 200
        a = res.json()["agents"][0]
        assert a["hostname"] == "host-a1"
        assert a["lanIp"] == "10.0.0.5"
        assert a["publicIp"] == "203.0.113.9"
        assert a["status"] == "Quarantined"
        assert a["geo"]["latitude"] == 52.5 and a["geo"]["longitude"] == 13.4
        assert a["geo"]["country_code"] == "DE"

    @patch("agent_fleet_geo_endpoints.get_database")
    def test_partial_coords_treated_as_unlocated(self, mock_get_db):
        import agent_fleet_geo_endpoints as m

        agents = [
            {"id": "a1", "hostname": "h1", "status": "Online", "tenantId": "tenant-a",
             "ipAddress": "10.0.0.1", "geo": {"city": "X", "latitude": 10.0}},  # lon missing
        ]
        db, _ = _mock_db(agents)
        mock_get_db.return_value = db

        res = _client(m.router, _user(role="Super Admin")).get("/api/fleet/geo")

        assert res.status_code == 200
        body = res.json()
        assert body["located_count"] == 0
        assert body["unlocated_count"] == 1
        assert body["agents"][0]["geo"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
