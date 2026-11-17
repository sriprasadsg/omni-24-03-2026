"""POST /api/agents/{agent_id}/discovery/results: the agent's LAN scan reaches the network map.

The Windows agent names itself by hostname in this URL, the Python agent by id; both must land on
the caller's own agent record, and nothing else. Hermetic: no real Mongo, no network.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import agent_tasks_endpoints as tasks_mod
from agent_auth import CALLER_AGENT_KEY

_AGENTS = [{"id": "agent-1", "tenantId": "tenant-a", "hostname": "EILT0197"}]


def _mock_db():
    db = MagicMock()

    async def find_agent(query, *_a, **_k):
        return next((a for a in _AGENTS if all(a.get(k) == v for k, v in query.items())), None)

    db.agents.find_one = AsyncMock(side_effect=find_agent)
    db._db = db
    db.patches.find.return_value.to_list = AsyncMock(return_value=[])
    db.network_devices.update_one = AsyncMock()
    return db


def _client(db, monkeypatch, caller="agent-1"):
    app = FastAPI()
    app.state.limiter = tasks_mod.limiter
    app.include_router(tasks_mod.router)
    app.dependency_overrides[tasks_mod.verify_agent_key] = lambda: {"id": "tenant-a", CALLER_AGENT_KEY: caller}
    monkeypatch.setattr(tasks_mod, "get_database", lambda: db)
    return TestClient(app)


SCAN = [{"ip": "192.168.0.1", "mac": "60-32-b1-08-ba-d6", "type": "dynamic", "device_type": "Web Server", "open_ports": [80, 53, 443, 99999, "x"]}]


def test_windows_agent_reporting_by_hostname_lands_on_its_own_record_with_map_fields(monkeypatch):
    """protects=a scan posted under the hostname is stored for the caller, with deviceType and open
    ports where the map reads them; fails_when=the hostname 404s (agent 2.1.19 always did) or ports
    keep junk; no_claim=-"""
    db = _mock_db()
    resp = _client(db, monkeypatch).post("/api/agents/EILT0197/discovery/results", json=SCAN)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"success": True, "processed": 1}
    stored = db.network_devices.update_one.await_args.args[1]["$set"]
    assert stored["discoveredBy"] == "agent-1" and stored["tenantId"] == "tenant-a"
    assert stored["deviceType"] == "Web Server" and stored["openPorts"] == [53, 80, 443]


def test_an_agent_cannot_report_for_another_agent(monkeypatch):
    """protects=only the named agent may post its scan; fails_when=any agent key writes devices under
    another agent's name; no_claim=-"""
    db = _mock_db()
    resp = _client(db, monkeypatch, caller="agent-2").post("/api/agents/EILT0197/discovery/results", json=SCAN)
    assert resp.status_code == 403
    db.network_devices.update_one.assert_not_awaited()
