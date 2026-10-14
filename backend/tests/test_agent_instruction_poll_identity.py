"""
GET /api/agents/{hostname}/instructions hands out an agent's pending
instructions and marks them sent. Their payloads can carry deployment
credentials (e.g. SSH passwords), so only the agent itself may read them.

It used to accept anything verify_agent_key accepts: the tenant registration
key (shipped in every installer), any user session (they carry tenant_id) or
another agent's token. Any of those could read, and so steal from the real
agent, every host's instructions in the tenant. The result route likewise let
any of them overwrite another agent's instruction results.

These tests go through the real routes, the real verify_agent_key and the real
TenantIsolatedDatabase over an in-memory store.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent_tasks_endpoints as mod
from database import get_database
from tests.agent_identity_test_support import Collection, agent_token, bearer, tenant_db, user_token

TENANT = {"id": "t1", "name": "Acme", "registrationKey": "reg-key-t1"}
OTHER_TENANT = {"id": "t2", "name": "Other", "registrationKey": "reg-key-t2"}
VICTIM = {"id": "agent-victim", "hostname": "DB-SERVER-01", "tenantId": "t1"}
ATTACKER = {"id": "agent-attacker", "hostname": "KIOSK-07", "tenantId": "t1"}
SECRET_INSTRUCTION = {
    "_id": 1, "id": "task-1", "agent_id": "agent-victim", "status": "pending", "tenantId": "t1",
    "instruction": "deploy_package", "payload": {"ssh_password": "s3cret"},
}


@pytest.fixture
def platform():
    db, raw = tenant_db(
        tenants=Collection([TENANT, OTHER_TENANT]),
        agents=Collection([VICTIM, ATTACKER]),
        agent_instructions=Collection([SECRET_INSTRUCTION]),
        revoked_tokens=Collection(),
    )
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_database] = lambda: db
    with patch.object(mod, "get_database", return_value=db), TestClient(app) as client:
        yield client, raw


def _victim_instruction_status(raw):
    return raw.agent_instructions.docs[0]["status"]


@pytest.mark.parametrize("path_name", ["DB-SERVER-01", "agent-victim"])
def test_agent_receives_its_own_instructions(platform, path_name):
    client, raw = platform
    resp = client.get(f"/api/agents/{path_name}/instructions", headers=bearer(agent_token("agent-victim")))
    assert resp.status_code == 200
    assert [i["task_id"] for i in resp.json()] == ["task-1"]
    assert _victim_instruction_status(raw) == "sent"


def _refused(client, raw, headers):
    resp = client.get("/api/agents/DB-SERVER-01/instructions", headers=headers)
    assert resp.status_code == 403, resp.text
    assert "s3cret" not in resp.text
    assert _victim_instruction_status(raw) == "pending", "a refused poll must not consume the instructions"


def test_another_agent_in_the_tenant_cannot_read_them(platform):
    client, raw = platform
    _refused(client, raw, bearer(agent_token("agent-attacker")))


def test_registration_key_alone_cannot_read_them(platform):
    client, raw = platform
    _refused(client, raw, {"X-Tenant-Key": "reg-key-t1"})


def test_registration_key_does_not_vouch_for_another_agents_token(platform):
    client, raw = platform
    _refused(client, raw, {"X-Tenant-Key": "reg-key-t1", **bearer(agent_token("agent-attacker"))})


def test_user_session_cannot_read_them(platform):
    client, raw = platform
    _refused(client, raw, bearer(user_token()))


def test_token_of_a_deleted_agent_is_refused(platform):
    client, raw = platform
    _refused(client, raw, bearer(agent_token("agent-deleted")))


def test_same_agent_id_in_another_tenant_is_refused(platform):
    client, raw = platform
    _refused(client, raw, bearer(agent_token("agent-victim", tenant_id="t2")))


def test_revoked_agent_token_is_refused(platform):
    client, raw = platform
    raw.revoked_tokens.docs.append({"jti": "jti-revoked"})
    _refused(client, raw, bearer(agent_token("agent-victim", jti="jti-revoked")))


def _report(client, as_agent, path_name):
    return client.post(f"/api/agents/{path_name}/instructions/result",
                       json={"task_id": "task-1", "status": "success", "message": "done"},
                       headers=bearer(agent_token(as_agent)))


def test_agent_cannot_report_results_for_another_agents_instruction(platform):
    client, raw = platform
    assert _report(client, "agent-attacker", "DB-SERVER-01").status_code == 403
    # Under its own name the request passes, but the task is not its own.
    assert _report(client, "agent-attacker", "KIOSK-07").status_code == 200
    assert _victim_instruction_status(raw) == "pending"


def test_agent_reports_results_for_its_own_instruction(platform):
    client, raw = platform
    assert _report(client, "agent-victim", "DB-SERVER-01").status_code == 200
    assert _victim_instruction_status(raw) == "SUCCESS"
