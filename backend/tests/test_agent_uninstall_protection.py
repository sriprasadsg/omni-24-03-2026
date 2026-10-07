"""Uninstall protection: platform-issued, single-use uninstall codes for agents."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent_uninstall_endpoints as mod
from auth_types import TokenData
from authentication_service import get_current_user, get_current_user_or_agent


class _Agents:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, flt, projection=None):
        return next((dict(d) for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)

    async def update_one(self, flt, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                d.update(update["$set"])


def _db(agent):
    db = MagicMock()
    db.agents = _Agents([agent])
    db.audit_logs.insert_one = AsyncMock()
    return db


def _client(db, user, alerts=None):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_or_agent] = lambda: user
    patches = [patch.object(mod, "get_database", return_value=db),
               patch("rbac_utils.get_database", return_value=MagicMock(roles=MagicMock(find_one=AsyncMock(return_value=None)))),
               patch("ueba_service.persist_security_alert", alerts or AsyncMock())]
    for p in patches:
        p.start()
    return TestClient(app), patches


ADMIN = TokenData(username="admin@t1.test", role="Tenant Admin", tenant_id="t1")
VIEWER = TokenData(username="viewer@t1.test", role="viewer", tenant_id="t1")
AGENT = TokenData(username="agent-1", role="agent", tenant_id="t1")


@pytest.fixture
def agent():
    return {"id": "agent-1", "hostname": "host-1", "tenantId": "t1"}


def _stop(patches):
    for p in patches:
        p.stop()


def test_codes_are_case_and_separator_insensitive():
    salt = "00" * 16
    assert mod.hash_code("abcd-efgh-jkmn", salt) == mod.hash_code("ABCD EFGH JKMN", salt)


def test_heartbeat_issues_verification_data_but_never_the_code(agent):
    db = _db(agent)
    public = asyncio.run(mod.heartbeat_uninstall_protection(db, {"id": "agent-1"}))
    assert set(public) == {"version", "salt", "iterations", "hash"}
    again = asyncio.run(mod.heartbeat_uninstall_protection(db, {"id": "agent-1"}))
    assert again == public  # issued once, stable until rotated


def test_admin_reveals_code_that_matches_the_agents_hash(agent):
    db = _db(agent)
    client, patches = _client(db, ADMIN)
    try:
        r = client.get("/api/agents/agent-1/uninstall-code")
    finally:
        _stop(patches)
    assert r.status_code == 200
    code, prot = r.json()["code"], agent["uninstallProtection"]
    assert mod.hash_code(code, prot["salt"], prot["iterations"]) == prot["hash"]
    assert db.audit_logs.insert_one.await_args.args[0]["action"] == "REVEAL_UNINSTALL_CODE"


def test_viewer_cannot_reveal_or_rotate(agent):
    client, patches = _client(_db(agent), VIEWER)
    try:
        assert client.get("/api/agents/agent-1/uninstall-code").status_code == 403
        assert client.post("/api/agents/agent-1/uninstall-code/rotate").status_code == 403
    finally:
        _stop(patches)


def test_authorized_uninstall_is_recorded_and_the_code_is_single_use(agent):
    db = _db(agent)
    alerts = AsyncMock()
    client, patches = _client(db, ADMIN, alerts)
    try:
        code = client.get("/api/agents/agent-1/uninstall-code").json()["code"]
        client.app.dependency_overrides[get_current_user_or_agent] = lambda: AGENT
        r = client.post("/api/agents/agent-1/uninstall-report", json={"code": code, "method": "msi"})
    finally:
        _stop(patches)
    assert r.json()["authorized"] is True
    assert agent["status"] == "Uninstalled" and agent["uninstallAuthorized"] is True
    prot = agent["uninstallProtection"]
    assert prot["version"] == 2 and mod.hash_code(code, prot["salt"], prot["iterations"]) != prot["hash"]
    assert alerts.await_args.kwargs["alert_type"] == "agent_uninstalled"


def test_removal_without_a_valid_code_raises_a_tamper_alert(agent):
    db = _db(agent)
    asyncio.run(mod.heartbeat_uninstall_protection(db, {"id": "agent-1"}))
    alerts = AsyncMock()
    client, patches = _client(db, AGENT, alerts)
    try:
        r = client.post("/api/agents/agent-1/uninstall-report", json={"code": "WRONG-CODE-0000"})
    finally:
        _stop(patches)
    assert r.json()["authorized"] is False
    assert alerts.await_args.kwargs["alert_type"] == "agent_tamper"
    assert alerts.await_args.kwargs["severity"] == "high"


@pytest.mark.parametrize("caller", [TokenData(username="agent-2", role="agent", tenant_id="t1"), ADMIN])
def test_only_the_agent_itself_can_report_its_uninstall(agent, caller):
    client, patches = _client(_db(agent), caller)
    try:
        r = client.post("/api/agents/agent-1/uninstall-report", json={"code": "X"})
    finally:
        _stop(patches)
    assert r.status_code == 403


@pytest.mark.parametrize("binary,protected", [(b"MZ ... --verify-uninstall-code ...", True), (b"MZ ... older build ...", False)])
def test_installer_asks_for_the_code_only_when_the_bundled_agent_can_check_it(tmp_path, binary, protected):
    # An older omni-agent.exe ignores the flag and starts its agent loop, which
    # would hang the uninstaller, so it gets the plain uninstaller instead.
    from agent_rust_builder import _build_nsi_rust
    (tmp_path / "omni-agent.exe").write_bytes(binary)
    nsi = _build_nsi_rust("Tenant", tmp_path, str(tmp_path / "Setup.exe"), "2.0.0")
    assert ("UninstPage custom un.CodePageCreate" in nsi) is protected
    assert ("--report-uninstall" in nsi) is protected
    assert 'Section "Uninstall"' in nsi
