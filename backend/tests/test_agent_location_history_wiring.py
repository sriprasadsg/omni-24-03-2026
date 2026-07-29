"""
Wiring tests for Phase 46 Plan 05 (Public-IP ASN/VPN Enrichment + Location-
History Audit, GAUD-01) — heartbeat + registration handlers.

Verifies the surgical in-place extension of the existing geo blocks in
agent_heartbeat_endpoints.py / agent_registry_endpoints.py:
  - toggle_on: track_agent_location ON -> agent_asn_service.lookup AND
    record_location_change are both invoked; geo.asn/geo.vpn_heuristic land
    in the agents.update_one $set payload.
  - toggle_off: track_agent_location OFF -> neither agent_asn_service.lookup
    NOR record_location_change is invoked, but the pre-existing
    geoip_service.lookup (city/country) enrichment is STILL called exactly
    once and geo still persists (scope boundary, T-46-05-B — the toggle
    must never blank the existing city/country geo enrichment).
  - register_first_seen: first-ever registration (no existing_agent) with a
    public IP and the toggle ON calls record_location_change with
    existing_agent=None so the service's first-ever branch can write an
    initial history row.
  - private_ip: no public IP in the payload performs no ASN lookup, no
    geoip lookup, and no record_location_change call.

Hermetic — no real Mongo, no network. FastAPI TestClient wired with the
real shared rate limiters (matching test_trust_center.py's precedent),
since both @agent_limiter.limit(...) / @limiter.limit(...) decorators
enforce inside the wrapped function itself and require a real
starlette.requests.Request bound to an app with app.state.limiter set.
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
import agent_registry_endpoints as reg_mod


# ─── shared rate-limiter hygiene (mirrors test_trust_center.py) ───────────────

@pytest.fixture(autouse=True)
def _reset_shared_rate_limit_storage():
    from rate_limiter import limiter as shared_limiter, agent_limiter as shared_agent_limiter
    shared_limiter._storage.reset()
    shared_agent_limiter._storage.reset()
    yield
    shared_limiter._storage.reset()
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


def _register_app():
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from rate_limiter import limiter as shared_limiter

    app = FastAPI()
    app.state.limiter = shared_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(reg_mod.router)
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


def _mock_reg_db(existing_agent=None, tenant_doc=None, existing_asset=None):
    db = MagicMock()
    db.tenants = MagicMock()
    db.tenants.find_one = AsyncMock(return_value=tenant_doc)
    db.agents = MagicMock()
    db.agents.find_one = AsyncMock(return_value=existing_agent)
    db.agents.update_one = AsyncMock()
    db.agents.count_documents = AsyncMock(return_value=0)
    db.assets = MagicMock()
    db.assets.find_one = AsyncMock(return_value=existing_asset)
    db.assets.update_one = AsyncMock()
    return db


_TENANT = {"id": "t1"}
_GEO = {"city": "Mountain View", "country": "US"}
_ASN = {"asn": {"number": 15169, "org": "Google LLC"}, "vpn_heuristic": False}


def _hb_set_payload(db):
    """Extract the $set dict from agents.update_one's call in the heartbeat handler."""
    assert db.agents.update_one.call_count >= 1
    args, kwargs = db.agents.update_one.call_args
    update_doc = args[1] if len(args) > 1 else kwargs.get("_")
    return update_doc["$set"]


# ─── toggle_on ────────────────────────────────────────────────────────────────

class TestToggleOn:
    def test_heartbeat_toggle_on_invokes_asn_and_history_and_persists_geo_asn(self):
        db = _mock_hb_db(existing_agent={"id": "agent-1", "tenantId": "t1", "hostname": "host1"})
        payload = {"publicIp": "8.8.8.8", "platform": "Linux", "version": "1.0.0"}

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True) as m_toggle, \
             patch("agent_heartbeat_endpoints.geoip_service.lookup", return_value=dict(_GEO)) as m_geoip, \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)) as m_asn, \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock) as m_record:
            with TestClient(_heartbeat_app(_TENANT)) as client:
                resp = client.post("/api/agents/agent-1/heartbeat", json=payload)

        assert resp.status_code == 200
        m_geoip.assert_called_once_with("8.8.8.8")
        m_asn.assert_called_once_with("8.8.8.8")
        m_record.assert_called_once()
        set_doc = _hb_set_payload(db)
        assert set_doc["geo"]["asn"] == _ASN["asn"]
        assert set_doc["geo"]["vpn_heuristic"] == _ASN["vpn_heuristic"]
        # scope boundary: city/country enrichment must still be present too
        assert set_doc["geo"]["city"] == _GEO["city"]

    def test_register_toggle_on_invokes_asn_and_history(self):
        tenant_doc = {"id": "t1", "registrationKey": "regkey-1", "maxAgents": 5}
        db = _mock_reg_db(existing_agent={"id": "agent-9", "hostname": "host9", "tenantId": "t1"},
                           tenant_doc=tenant_doc)
        payload = {"registrationKey": "regkey-1", "hostname": "host9", "publicIp": "8.8.8.8"}

        with patch("agent_registry_endpoints.get_database", return_value=db), \
             patch("agent_registry_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True), \
             patch("agent_registry_endpoints.geoip_service.lookup", return_value=dict(_GEO)), \
             patch("agent_registry_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)) as m_asn, \
             patch("agent_registry_endpoints.record_location_change", new_callable=AsyncMock) as m_record, \
             patch("finops_service.finops_service.recalculate_tenant_costs", new_callable=AsyncMock), \
             patch("admin_evidence_service.run_evidence_collection_for_asset", new_callable=AsyncMock):
            with TestClient(_register_app()) as client:
                resp = client.post("/api/agents/register", json=payload)

        assert resp.status_code == 200
        m_asn.assert_called_once_with("8.8.8.8")
        m_record.assert_called_once()


# ─── toggle_off ───────────────────────────────────────────────────────────────

class TestToggleOff:
    def test_heartbeat_toggle_off_skips_asn_and_history_but_keeps_geoip(self):
        db = _mock_hb_db(existing_agent={"id": "agent-2", "tenantId": "t1", "hostname": "host2"})
        payload = {"publicIp": "8.8.8.8", "platform": "Linux", "version": "1.0.0"}

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=False), \
             patch("agent_heartbeat_endpoints.geoip_service.lookup", return_value=dict(_GEO)) as m_geoip, \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)) as m_asn, \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock) as m_record:
            with TestClient(_heartbeat_app(_TENANT)) as client:
                resp = client.post("/api/agents/agent-2/heartbeat", json=payload)

        assert resp.status_code == 200
        # scope boundary (T-46-05-B): geoip city/country enrichment is NOT gated
        m_geoip.assert_called_once_with("8.8.8.8")
        m_asn.assert_not_called()
        m_record.assert_not_called()
        set_doc = _hb_set_payload(db)
        assert set_doc["geo"]["city"] == _GEO["city"]
        assert "asn" not in set_doc["geo"]


# ─── register_first_seen ──────────────────────────────────────────────────────

class TestRegisterFirstSeen:
    def test_first_ever_registration_writes_initial_row(self):
        tenant_doc = {"id": "t1", "registrationKey": "regkey-2", "maxAgents": 5}
        db = _mock_reg_db(existing_agent=None, tenant_doc=tenant_doc)
        payload = {"registrationKey": "regkey-2", "hostname": "new-host", "publicIp": "8.8.8.8"}

        with patch("agent_registry_endpoints.get_database", return_value=db), \
             patch("agent_registry_endpoints.get_track_agent_location", new_callable=AsyncMock, return_value=True), \
             patch("agent_registry_endpoints.geoip_service.lookup", return_value=dict(_GEO)), \
             patch("agent_registry_endpoints.agent_asn_service.lookup", return_value=dict(_ASN)), \
             patch("agent_registry_endpoints.record_location_change", new_callable=AsyncMock) as m_record, \
             patch("finops_service.finops_service.recalculate_tenant_costs", new_callable=AsyncMock), \
             patch("admin_evidence_service.run_evidence_collection_for_asset", new_callable=AsyncMock):
            with TestClient(_register_app()) as client:
                resp = client.post("/api/agents/register", json=payload)

        assert resp.status_code == 200
        m_record.assert_called_once()
        call_args = m_record.call_args.args
        # record_location_change(db, existing_agent, agent_id, tenant_id, public_ip, geo, asn_enrichment)
        assert call_args[1] is None, "existing_agent must be None on first-ever registration"


# ─── private_ip (no public IP present) ────────────────────────────────────────

class TestPrivateIp:
    def test_heartbeat_no_public_ip_skips_everything(self):
        db = _mock_hb_db(existing_agent={"id": "agent-3", "tenantId": "t1", "hostname": "host3"})
        payload = {"platform": "Linux", "version": "1.0.0"}  # no publicIp

        with patch("agent_heartbeat_endpoints.get_database", return_value=db), \
             patch("agent_heartbeat_endpoints.get_track_agent_location", new_callable=AsyncMock) as m_toggle, \
             patch("agent_heartbeat_endpoints.geoip_service.lookup") as m_geoip, \
             patch("agent_heartbeat_endpoints.agent_asn_service.lookup") as m_asn, \
             patch("agent_heartbeat_endpoints.record_location_change", new_callable=AsyncMock) as m_record:
            with TestClient(_heartbeat_app(_TENANT)) as client:
                resp = client.post("/api/agents/agent-3/heartbeat", json=payload)

        assert resp.status_code == 200
        m_geoip.assert_not_called()
        m_asn.assert_not_called()
        m_record.assert_not_called()
        set_doc = _hb_set_payload(db)
        assert "geo" not in set_doc
