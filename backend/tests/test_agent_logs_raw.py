"""Regression test for the log_shipper.py 404 bug: agent/capabilities/log_shipper.py
has always POSTed batches to POST /api/agents/{agent_id}/logs/raw, but that route
never existed anywhere in the backend — every attempt 404'd and every log line was
silently buffered to local disk forever, never actually shipped. Verifies the new
route exists, is agent-key gated (mirrors agent_heartbeat_endpoints.py's precedent),
stores into db.logs (the same collection GET /api/logs already reads), and is capped.

Hermetic — no real Mongo, no network.
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

import agent_telemetry_endpoints as telemetry_mod

_TENANT = {"id": "tenant-a"}


def _mock_db():
    db = MagicMock()
    db.logs = MagicMock()
    db.logs.insert_many = AsyncMock()
    return db


def _app(db):
    app = FastAPI()
    app.include_router(telemetry_mod.router)
    app.dependency_overrides[telemetry_mod.verify_agent_key] = lambda: _TENANT
    app.dependency_overrides[telemetry_mod.get_database] = lambda: db
    return app


def test_route_exists_and_accepts_a_batch():
    db = _mock_db()
    with TestClient(_app(db)) as client:
        resp = client.post(
            "/api/agents/agent-1/logs/raw",
            json={"agent_id": "agent-1", "logs": [
                {"source": "syslog", "raw_message": "kernel: eth0 link up", "collected_at": "2026-08-24T00:00:00Z"},
            ]},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "stored": 1}
    db.logs.insert_many.assert_awaited_once()
    docs = db.logs.insert_many.await_args.args[0]
    assert docs[0]["message"] == "kernel: eth0 link up"
    assert docs[0]["service"] == "syslog"
    assert docs[0]["agentId"] == "agent-1"
    assert docs[0]["tenantId"] == "tenant-a"


def test_empty_or_missing_logs_list_stores_nothing():
    db = _mock_db()
    with TestClient(_app(db)) as client:
        resp = client.post("/api/agents/agent-1/logs/raw", json={"agent_id": "agent-1"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "stored": 0}
    db.logs.insert_many.assert_not_awaited()


def test_non_dict_entries_in_the_batch_are_skipped_not_fatal():
    db = _mock_db()
    with TestClient(_app(db)) as client:
        resp = client.post(
            "/api/agents/agent-1/logs/raw",
            json={"agent_id": "agent-1", "logs": ["not-a-dict", {"source": "syslog", "raw_message": "ok"}]},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "stored": 1}


def test_batch_is_capped_at_max_raw_log_lines():
    db = _mock_db()
    oversized = [{"source": "syslog", "raw_message": f"line {i}"} for i in range(telemetry_mod._MAX_RAW_LOG_LINES + 50)]
    with TestClient(_app(db)) as client:
        resp = client.post("/api/agents/agent-1/logs/raw", json={"agent_id": "agent-1", "logs": oversized})
    assert resp.status_code == 200
    assert resp.json()["stored"] == telemetry_mod._MAX_RAW_LOG_LINES


def test_requires_agent_authentication():
    app = FastAPI()
    app.include_router(telemetry_mod.router)
    app.dependency_overrides[telemetry_mod.get_database] = lambda: _mock_db()
    # No verify_agent_key override — the real dependency runs and must reject
    # an unauthenticated request (no X-Tenant-Key or Bearer token supplied).
    with TestClient(app) as client:
        resp = client.post("/api/agents/agent-1/logs/raw", json={"agent_id": "agent-1", "logs": []})
    assert resp.status_code in (401, 403)
