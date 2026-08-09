"""
Tests for Phase 52 Plan 01 (FIM-02) — agent_security_endpoints
POST /api/agents/{agent_id}/fim-events: persist the rich FIM change-event shape
(change_type / hash_before / hash_after / process / user / ts) while preserving
the VirusTotal enrichment + malware-alert path, the legacy-shape fallback, and
the GET list contract. Hermetic — mocked db + patched VT client.
"""
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from agent_auth import verify_agent_key
from database import get_database


def _stub_vt(verdicts):
    """Inject a stub `virustotal_client` so the endpoint's local
    `from virustotal_client import enrich_file_hashes` resolves without loading
    the real module. Returns a patch.dict context manager and the recording mock."""
    mock = MagicMock(return_value=verdicts)
    mod = types.ModuleType("virustotal_client")
    mod.enrich_file_hashes = mock
    return patch.dict(sys.modules, {"virustotal_client": mod}), mock


def _mock_db():
    db = MagicMock()
    db.fim_events = MagicMock(insert_one=AsyncMock())
    db.security_alerts = MagicMock(insert_one=AsyncMock())
    return db


def _client(db, tenant_id="tenant-a"):
    import agent_security_endpoints as m
    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[verify_agent_key] = lambda: {"id": tenant_id}
    app.dependency_overrides[get_database] = lambda: db
    return TestClient(app)


def test_rich_event_fields_persisted():
    db = _mock_db()
    ctx, _ = _stub_vt({})
    with ctx:
        r = _client(db).post(
            "/api/agents/agent-1/fim-events",
            json={"changes": [{
                "path": "/etc/hosts",
                "change_type": "modify",
                "hash_before": "aaa",
                "hash_after": "bbb",
                "process": {"name": "vim", "pid": 42},
                "user": "root",
                "ts": "2026-07-30T00:00:00Z",
            }]},
        )
    assert r.status_code == 200
    db.fim_events.insert_one.assert_awaited()
    doc = db.fim_events.insert_one.call_args[0][0]
    assert doc["change_type"] == "modify"
    assert doc["hash_before"] == "aaa"
    assert doc["hash_after"] == "bbb"
    assert doc["process"] == {"name": "vim", "pid": 42}
    assert doc["user"] == "root"
    assert doc["ts"] == "2026-07-30T00:00:00Z"
    assert doc["tenantId"] == "tenant-a" and doc["agent_id"] == "agent-1"


def test_vt_enrichment_and_alert_use_hash_after():
    db = _mock_db()
    verdict = {"verdict": "Malicious", "detectionRatio": "40/70", "malicious": 40}
    ctx, vt = _stub_vt({"bbb": verdict})
    with ctx:
        r = _client(db).post(
            "/api/agents/agent-1/fim-events",
            json={"changes": [{"path": "/bin/x", "change_type": "modify",
                               "hash_before": "aaa", "hash_after": "bbb"}]},
        )
    assert r.status_code == 200
    # VT enriched on hash_after, malware alert raised.
    assert vt.call_args[0][0] == ["bbb"]
    assert r.json()["malicious_count"] == 1
    db.security_alerts.insert_one.assert_awaited()
    doc = db.fim_events.insert_one.call_args[0][0]
    assert doc["sha256"] == "bbb"
    assert doc["vt_verdict"] == "Malicious"


def test_legacy_shape_still_ingests():
    db = _mock_db()
    ctx, _ = _stub_vt({})
    with ctx:
        r = _client(db).post(
            "/api/agents/agent-1/fim-events",
            json={"changes": [{"path": "/etc/hosts", "new_hash": "ccc"}]},
        )
    assert r.status_code == 200
    doc = db.fim_events.insert_one.call_args[0][0]
    assert doc["sha256"] == "ccc"  # new_hash still used as the primary hash
    assert doc["change_type"] is None  # rich field absent → None, no crash


def test_tenant_scoped():
    db = _mock_db()
    ctx, _ = _stub_vt({})
    with ctx:
        _client(db, tenant_id="tenant-z").post(
            "/api/agents/agent-9/fim-events",
            json={"changes": [{"path": "/etc/hosts", "change_type": "create", "hash_after": "d"}]},
        )
    doc = db.fim_events.insert_one.call_args[0][0]
    assert doc["tenantId"] == "tenant-z"
