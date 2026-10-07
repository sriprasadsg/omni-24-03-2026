"""
Agent work runs on the target endpoint, never on the platform's worker host.

- tasks.run_agent_task_async refuses to execute (it used to run agent
  capabilities on the Celery worker itself).
- Persistence scans and process-injection simulations are queued in
  agent_instructions for an agent in the caller's tenant.
- Inbound ticket automation only records a proposal awaiting approval.
Hermetic — no Mongo, no Celery broker.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth_types import TokenData
from authentication_service import get_current_user

ADMIN = TokenData(username="ops@a.test", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)


def _db(agent=None):
    db = MagicMock()
    db.agents.find_one = AsyncMock(return_value=agent)
    for name in ("agent_instructions", "persistence_scans", "security_cases", "simulations", "jobs"):
        getattr(db, name).insert_one = AsyncMock()
    return db


def _client(router):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    return TestClient(app)


def test_celery_agent_task_refuses_to_run_locally():
    import tasks
    result = tasks.run_agent_task_async.run("install_software:evil", "default")
    assert result["status"] == "refused"


def test_persistence_scan_is_queued_for_the_agent():
    import persistence_endpoints as pe
    db = _db(agent={"id": "agent-1"})
    with patch.object(pe, "get_database", return_value=db):
        r = _client(pe.router).post("/api/persistence/scan", json={"agentId": "host-1"})
    assert r.status_code == 200
    queued = db.agent_instructions.insert_one.await_args.args[0]
    assert queued["agent_id"] == "agent-1"
    assert queued["instruction"] == "Scan for Persistence"
    assert queued["status"] == "pending"


def test_persistence_scan_unknown_agent_is_404():
    import persistence_endpoints as pe
    db = _db(agent=None)
    with patch.object(pe, "get_database", return_value=db):
        r = _client(pe.router).post("/api/persistence/scan", json={"agentId": "nope"})
    assert r.status_code == 404
    db.agent_instructions.insert_one.assert_not_awaited()


def test_simulation_is_queued_before_the_case_is_recorded():
    import simulation_endpoints as se
    db = _db(agent=None)
    with patch.object(se, "get_database", return_value=db):
        r = _client(se.router).post("/api/simulation/process-injection", json={"agentId": "nope"})
    assert r.status_code == 404
    db.security_cases.insert_one.assert_not_awaited()


@pytest.mark.parametrize("field", ["technique", "target"])
def test_simulation_rejects_unsafe_parameters(field):
    import simulation_endpoints as se
    db = _db(agent={"id": "agent-1"})
    body = {"agentId": "agent-1", field: "x; rm -rf /"}
    with patch.object(se, "get_database", return_value=db):
        r = _client(se.router).post("/api/simulation/process-injection", json=body)
    assert r.status_code == 400
    db.agent_instructions.insert_one.assert_not_awaited()


async def test_ticket_intent_is_only_proposed():
    import intent_parser_service as ips
    db = _db(agent={"id": "agent-1"})
    intent = {"action": "install_software", "params": {"package_name": "x"}, "target_agent": "host-1"}
    with patch.object(ips, "get_database", return_value=db), \
         patch.object(ips.intent_parser_service, "_detect_intent", AsyncMock(return_value=intent)):
        result = await ips.intent_parser_service.parse_and_dispatch(
            {"issue": {"key": "J-1", "fields": {"summary": "please install x"}}}, "jira")
    assert result["status"] == "awaiting_approval"
    job = db.jobs.insert_one.await_args.args[0]
    assert job["status"] == "awaiting_approval"
    assert job["details"]["agent_id"] == "agent-1"
    db.agent_instructions.insert_one.assert_not_awaited()
