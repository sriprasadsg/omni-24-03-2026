"""Tests for the 5 endpoints that closed dead frontend calls (Group C).

Covers: POST /api/agent/analyze, POST /api/mcp/execute/{tool},
POST /api/finops/budget/update, GET /api/advanced-hunting/geo-sources,
GET /api/advanced-hunting/timeline.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
from auth_types import TokenData


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="u@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _client(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class _AsyncCursor:
    """Minimal async cursor supporting .sort().limit() and async iteration."""
    def __init__(self, docs):
        self._docs = docs
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


# ─── agent/analyze ───────────────────────────────────────────────────────────

def test_analyze_bad_type_422():
    import agent_analyze_endpoints as m
    r = _client(m.router, _user()).post("/api/agent/analyze", json={"type": "widget", "id": "x"})
    assert r.status_code == 422


@patch("agent_analyze_endpoints.get_database")
def test_analyze_not_found_404(mock_db):
    import agent_analyze_endpoints as m
    db = MagicMock()
    db.__getitem__ = lambda self, name: MagicMock(find_one=AsyncMock(return_value=None))
    mock_db.return_value = db
    r = _client(m.router, _user()).post("/api/agent/analyze", json={"type": "alert", "id": "missing"})
    assert r.status_code == 404


@patch("agent_analyze_endpoints.get_database")
def test_analyze_success_shape(mock_db):
    import agent_analyze_endpoints as m
    col = MagicMock(find_one=AsyncMock(return_value={"id": "a1", "message": "Brute force", "severity": "high"}))
    db = MagicMock(); db.__getitem__ = lambda self, name: col
    mock_db.return_value = db
    r = _client(m.router, _user()).post("/api/agent/analyze", json={"type": "alert", "id": "a1"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"severityAssessment", "summary", "rootCauseAnalysis", "mitigationSteps"}
    assert isinstance(body["mitigationSteps"], list) and body["mitigationSteps"]
    assert "High" in body["severityAssessment"]


# ─── mcp/execute ─────────────────────────────────────────────────────────────

def test_mcp_unknown_tool_404():
    import mcp_rest_endpoints as m
    r = _client(m.router, _user()).post("/api/mcp/execute/no_such_tool", json={})
    assert r.status_code == 404


def test_mcp_known_tool_dispatches():
    import mcp_rest_endpoints as m
    with patch.object(m, "_ALLOWED_TOOLS", {"list_frameworks": AsyncMock(return_value=[{"id": "soc2", "name": "SOC 2"}])}):
        r = _client(m.router, _user()).post("/api/mcp/execute/list_frameworks", json={})
    assert r.status_code == 200
    assert r.json() == [{"id": "soc2", "name": "SOC 2"}]


def test_mcp_bad_params_422():
    import mcp_rest_endpoints as m
    async def needs_arg(control_id):  # missing arg -> TypeError -> 422
        return {}
    with patch.object(m, "_ALLOWED_TOOLS", {"get_control_status": needs_arg}):
        r = _client(m.router, _user()).post("/api/mcp/execute/get_control_status", json={})
    assert r.status_code == 422


# ─── finops/budget/update ────────────────────────────────────────────────────

@patch("rbac_utils.verify_permission", new=AsyncMock(return_value=True))
@patch("finops_endpoints.get_database")
def test_budget_update_persists(mock_db):
    import finops_endpoints as m
    db = MagicMock(); db.tenants.update_one = AsyncMock()
    mock_db.return_value = db
    r = _client(m.router, _user()).post("/api/finops/budget/update?amount=5000")
    assert r.status_code == 200
    assert r.json() == {"success": True, "budget": 5000.0}
    db.tenants.update_one.assert_awaited_once()


# ─── advanced-hunting geo + timeline ─────────────────────────────────────────

@patch("advanced_hunting_endpoints.get_database")
def test_geo_sources_aggregates(mock_db):
    import advanced_hunting_endpoints as m
    docs = [
        {"id": "1", "country_code": "RU", "type": "BruteForce", "severity": "high", "timestamp": "2026-07-14T10:00:00+00:00"},
        {"id": "2", "country_code": "RU", "type": "C2", "severity": "critical", "timestamp": "2026-07-14T11:00:00+00:00"},
        {"id": "3", "severity": "low", "timestamp": "2026-07-14T09:00:00+00:00"},  # no geo -> skipped
    ]
    db = MagicMock(); db.security_events.find = MagicMock(return_value=_AsyncCursor(docs))
    mock_db.return_value = db
    r = _client(m.router, _user("Super Admin")).get("/api/advanced-hunting/geo-sources?range=7d")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    ru = data[0]
    assert ru["country_code"] == "RU" and ru["event_count"] == 2
    assert ru["severity"] == "critical"
    assert sorted(ru["threat_types"]) == ["BruteForce", "C2"]


@patch("advanced_hunting_endpoints.get_database")
def test_timeline_maps_events(mock_db):
    import advanced_hunting_endpoints as m
    docs = [{"id": "e1", "type": "Login", "source": "WIN-DC01", "severity": "High", "timestamp": "2026-07-14T10:00:00+00:00"}]
    db = MagicMock(); db.security_events.find = MagicMock(return_value=_AsyncCursor(docs))
    mock_db.return_value = db
    r = _client(m.router, _user()).get("/api/advanced-hunting/timeline?hours=24")
    assert r.status_code == 200
    ev = r.json()[0]
    assert ev["event_type"] == "Login" and ev["asset"] == "WIN-DC01" and ev["severity"] == "high"
