"""
Wiring tests for Phase 47 Plan 03 (Agent-Scoped Geo Security Detectors,
GSEC-02/GSEC-03) — heartbeat handler call-through.

Verifies the surgical extension of agent_heartbeat_endpoints.py, added
immediately after Phase 46's record_location_change call-through (same
toggle-gated `if public_ip and track_location:` region):
  - alert_returned: run_geo_security_detectors returns one alert payload ->
    persist_security_alert is awaited exactly once with those kwargs.
  - no_alerts: run_geo_security_detectors returns [] -> persist_security_alert
    is never called.
  - detector_exception: run_geo_security_detectors raises -> the heartbeat
    still returns {"success": True} and persist_security_alert is never
    called (D-04 alert-only — a detector fault must never fail the
    heartbeat response).

Hermetic — no real Mongo, no network. FastAPI TestClient wired with the
real shared rate limiter, mirroring test_agent_location_history_wiring.py's
precedent (cloned setup per 47-03-PLAN.md Task 1 <read_first>).
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

import agent_heartbeat_endpoints as hb_mod


# ─── shared rate-limiter hygiene (mirrors test_agent_location_history_wiring.py) ──

@pytest.fixture(autouse=True)
def _reset_shared_rate_limit_storage():
    from rate_limiter import agent_limiter as shared_agent_limiter
    shared_agent_limiter._storage.reset()
    yield
    shared_agent_limiter._storage.reset()


def _heartbeat_app(tenant: dict):
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from rate_limiter import agent_limiter as shared_agent_limiter

    app = FastAPI()
    app.state.limiter = shared_agent_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(hb_mod.router)
    app.dependency_overrides[hb_mod.verify_agent_key] = lambda: tenant
    return app


def _mock_hb_db(existing_agent=None):
    db = MagicMock()
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=existing_agent)
    db.agents.update_one = AsyncMock()
    db.agents.count_documents = AsyncMock(return_value=0)
    db.tenants = MagicMock()
    db.tenants.find_one = AsyncMock(return_value=None)
    return db


_TENANT = {"id": "t1"}
_GEO = {"city": "Mountain View", "country": "US", "latitude": 37.4, "longitude": -122.1}
_ASN = {"asn": {"number": 15169, "org": "Google LLC"}, "vpn_heuristic": False}
_EXISTING_AGENT = {
    "id": "agent-1", "tenantId": "t1", "hostname": "host1",
    "geo": {"latitude": 40.7, "longitude": -74.0, "country": "US"},
    "lastSeen": "2026-07-29T00:00:00+00:00",
}
_PAYLOAD = {"publicIp": "8.8.8.8", "platform": "Linux", "version": "1.0.0"}
_ALERT_PAYLOAD = {
    "alert_type": "impossible_travel",
    "severity": "high",
    "title": "Impossible travel detected for agent agent-1",
    "description": "Agent agent-1 checked in from a location that is physically impossible.",
    "metadata": {"agent_id": "agent-1", "tenant_id": "t1"},
}


def _post_heartbeat():
    with TestClient(_heartbeat_app(_TENANT)) as client:
        return client.post("/api/agents/agent-1/heartbeat", json=_PAYLOAD)


class TestAlertReturned:
    def test_one_alert_payload_persisted(self):
        db = _mock_hb_db(existing_agent=dict(_EXISTING_AGENT))

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True), \
             patch("agent_heartbeat_endpoints.geoip_service.lookup", return_value=dict(_GEO)), \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)), \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock), \
             patch("agent_heartbeat_endpoints.run_geo_security_detectors", new_callable=AsyncMock,
                   return_value=[dict(_ALERT_PAYLOAD)]), \
             patch("agent_heartbeat_endpoints.persist_security_alert", new_callable=AsyncMock) as m_persist:
            resp = _post_heartbeat()

        assert resp.status_code == 200
        m_persist.assert_awaited_once()
        _, kwargs = m_persist.call_args
        assert kwargs["alert_type"] == _ALERT_PAYLOAD["alert_type"]
        assert kwargs["severity"] == _ALERT_PAYLOAD["severity"]
        assert kwargs["title"] == _ALERT_PAYLOAD["title"]
        assert kwargs["description"] == _ALERT_PAYLOAD["description"]
        assert kwargs["metadata"] == _ALERT_PAYLOAD["metadata"]


class TestNoAlerts:
    def test_empty_payload_list_skips_persist(self):
        db = _mock_hb_db(existing_agent=dict(_EXISTING_AGENT))

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True), \
             patch("agent_heartbeat_endpoints.geoip_service.lookup", return_value=dict(_GEO)), \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)), \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock), \
             patch("agent_heartbeat_endpoints.run_geo_security_detectors", new_callable=AsyncMock,
                   return_value=[]), \
             patch("agent_heartbeat_endpoints.persist_security_alert", new_callable=AsyncMock) as m_persist:
            resp = _post_heartbeat()

        assert resp.status_code == 200
        m_persist.assert_not_called()


class TestDetectorException:
    def test_detector_fault_never_fails_heartbeat(self):
        db = _mock_hb_db(existing_agent=dict(_EXISTING_AGENT))

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True), \
             patch("agent_heartbeat_endpoints.geoip_service.lookup", return_value=dict(_GEO)), \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)), \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock), \
             patch("agent_heartbeat_endpoints.run_geo_security_detectors", new_callable=AsyncMock,
                   side_effect=RuntimeError("boom")), \
             patch("agent_heartbeat_endpoints.persist_security_alert", new_callable=AsyncMock) as m_persist:
            resp = _post_heartbeat()

        assert resp.status_code == 200
        assert resp.json() == {"success": True}
        m_persist.assert_not_called()
