"""
Tests for Phase 50 Plan 04 (NSCAN-03) — agent_security_scan_endpoints
POST /api/agents/{agent_id}/security/scan-result: ingest a native scan verdict,
persist it, and raise a critical native alert on Malicious. Hermetic.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agent_auth import verify_agent_key


def _client(router, mock_db, tenant_id="tenant-a"):
    import agent_security_scan_endpoints as m
    m.get_database = lambda: mock_db  # patch module-level accessor
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[verify_agent_key] = lambda: {"id": tenant_id}
    return TestClient(app)


def _mock_db():
    db = MagicMock()
    db.security_scan_results = MagicMock(insert_one=AsyncMock())
    db.security_alerts = MagicMock(insert_one=AsyncMock())
    return db


def test_clean_verdict_persisted_no_alert():
    import agent_security_scan_endpoints as m
    db = _mock_db()
    r = _client(m.router, db).post(
        "/api/agents/agent-1/security/scan-result",
        json={"type": "file", "target": "/tmp/ok", "verdict": "Clean", "confidence": 1.0, "sha256": "abc"},
    )
    assert r.status_code == 200
    assert r.json()["alerted"] is False
    db.security_scan_results.insert_one.assert_awaited()
    db.security_alerts.insert_one.assert_not_awaited()
    # persisted doc carries tenant + agent
    doc = db.security_scan_results.insert_one.call_args[0][0]
    assert doc["tenantId"] == "tenant-a" and doc["agentId"] == "agent-1"


def test_malicious_raises_native_alert():
    import agent_security_scan_endpoints as m
    db = _mock_db()
    r = _client(m.router, db).post(
        "/api/agents/agent-1/security/scan-result",
        json={"type": "file", "target": "/tmp/evil", "verdict": "Malicious", "confidence": 0.95,
              "sha256": "deadbeef", "matched": ["hash"]},
    )
    assert r.status_code == 200
    assert r.json()["alerted"] is True
    db.security_alerts.insert_one.assert_awaited()
    alert = db.security_alerts.insert_one.call_args[0][0]
    assert alert["source"] == "native"
    assert alert["severity"] == "critical"
    assert alert["tenantId"] == "tenant-a"
    assert "deadbeef" in alert["description"]


def test_tenant_scoping_from_agent_key():
    import agent_security_scan_endpoints as m
    db = _mock_db()
    _client(m.router, db, tenant_id="tenant-z").post(
        "/api/agents/a1/security/scan-result",
        json={"type": "hash", "target": "h", "verdict": "Clean"},
    )
    doc = db.security_scan_results.insert_one.call_args[0][0]
    assert doc["tenantId"] == "tenant-z"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
