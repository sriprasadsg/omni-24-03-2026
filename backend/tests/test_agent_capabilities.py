"""Per-tenant agent capabilities: a Super Admin ticks what a tenant's agents may use.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Tests that touch MongoDB use a throwaway database.
"""
import glob
import os
import re
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_capabilities as ac
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.real_agent_capabilities

T = "tenant-a"
RUST_CAPABILITIES = os.path.join(os.path.dirname(__file__), "..", "..", "agent-install", "omni-agent-rs", "src")


# ── The rule ──────────────────────────────────────────────────────────────────

def test_what_a_tenant_may_use():
    """protects=a tenant's agents get exactly the ticked capabilities plus the always-on ones, "all" and
    the Platform tenant get everything, and no list fails closed; fails_when=an unticked capability is
    allowed, agent self-update can be unticked, or a missing list allows everything; no_claim=MongoDB."""
    assert ac.allowed({"id": T, "agentCapabilities": ["fim", "bogus"]}) == {"fim", "agent_update"}
    assert ac.allowed({"id": T, "agentCapabilities": ["all"]}) == ac.CAPABILITY_IDS
    assert ac.allowed({"id": "platform-admin"}) == ac.CAPABILITY_IDS
    for tenant in (None, {"id": T}, {"id": T, "agentCapabilities": "fim"}):
        assert ac.allowed(tenant) == ac.ALWAYS_ON == {"agent_update"}


def test_a_selection_is_checked():
    """protects=only catalogue ids (or "all") are stored, always-on ones are added and duplicates go;
    fails_when=a typo or a non-string is stored; no_claim=none beyond protects."""
    assert ac.validate(["fim", "fim", "pii_scanner"]) == ["agent_update", "fim", "pii_scanner"]
    assert ac.validate(["fim", "all"]) == ["all"]
    for bad in (["fim", "telepathy"], [1]):
        with pytest.raises(ValueError):
            ac.validate(bad)


def test_the_catalogue_names_every_capability_an_agent_reports():
    """protects=every capability the Rust agent implements (and the backend's capability definitions)
    is in the shared catalogue, so the Super Admin can switch each one; fails_when=a new agent capability
    ships without a catalogue entry (its data could never be switched off); no_claim=the Python agent."""
    import capability_endpoints
    rust_ids = set()
    for path in glob.glob(os.path.join(RUST_CAPABILITIES, "capabilities", "*.rs")):
        rust_ids |= set(re.findall(r'fn id\(&self\)[^{]*\{\s*"([a-z_]+)"', open(path, encoding="utf-8").read()))
    rust_ids |= set(re.findall(r'ids\.push\("([a-z_]+)"\)', open(os.path.join(RUST_CAPABILITIES, "capabilities", "mod.rs")).read()))
    assert len(rust_ids) >= 18
    assert rust_ids <= ac.CAPABILITY_IDS
    assert set(capability_endpoints.CAPABILITY_DEFINITIONS) <= ac.CAPABILITY_IDS


def test_heartbeat_data_of_an_unticked_capability_is_dropped():
    """protects=the meta of an unticked capability (and its renamed inventory keys) is removed while
    ticked capabilities, system metrics and names outside the catalogue stay; fails_when=FIM data
    survives with FIM unticked or CPU usage is dropped; no_claim=storage (see the heartbeat test)."""
    payload = {"meta": {"fim": {"violations": [1]}, "log_collection": [1], "software_inventory": [1],
                        "installed_software": [1], "current_cpu": 9, "task_feedback": [], "capabilities": ["fim"]}}
    dropped = ac.strip_heartbeat(payload, frozenset({"log_collection"}))
    assert dropped == ["fim", "software_management"]
    assert set(payload["meta"]) == {"log_collection", "current_cpu", "task_feedback", "capabilities"}


@pytest.mark.parametrize("instruction,capability", [
    ({"instruction": "upgrade_software: 7zip"}, "software_management"),
    ({"instruction": "Start Network Scan"}, "network_discovery"),
    ({"instruction": "Start Remote Session abc wss://x", "type": "start_remote_session"}, "remote_access"),
    ({"type": "install_patches"}, "patch_installer"),
    ({"type": "agent_chat_message"}, "chat_window"),
    ({"instruction": "kill_process"}, "remediation_executor"),
    ({"instruction": "agent_update"}, None),
    ({"instruction": "Run something new"}, None),
])
def test_instructions_map_to_the_capability_that_carries_them_out(instruction, capability):
    """protects=each instruction name format producers use resolves to its capability, unknown ones to
    none; fails_when="upgrade_software: pkg" or a remote-session string slips past the check;
    no_claim=instructions whose producer uses a name not in the table (they are delivered)."""
    assert ac.instruction_capability(instruction) == capability


# ── Enforcement ───────────────────────────────────────────────────────────────

def _request(path):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("203.0.113.7", 5555)})


async def test_heartbeat_stores_nothing_of_an_unticked_capability(mongo_db):
    """protects=an Online agent's heartbeat keeps FIM data (ticked) but stores no logs or inventory
    (unticked), and the reply tells the agent what it may use; fails_when=logs land in the store or
    the agent document keeps log data; no_claim=background tasks (mocked)."""
    import agent_heartbeat_endpoints as hb
    await mongo_db.tenants.insert_one({"id": T, "name": "Acme", "agentCapabilities": ["fim", "metrics_collection"],
                                       "license": {"maxAgents": 5, "seatsUsed": 1, "inactiveReclaimDays": 30}})
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": T, "hostname": "pc1", "status": "Online"})
    payload = {"hostname": "pc1", "platform": "Windows", "version": "2.1.13", "ipAddress": "10.0.0.5", "meta": {
        "current_cpu": 12, "log_collection": [{"message": "x"}], "software_inventory": [{"name": "7zip"}],
        "fim": {"violations": [{"path": "C:/x", "hash": "h"}]}}}
    tenant = await mongo_db.tenants.find_one({"id": T})
    with patch.object(hb, "get_database", return_value=mongo_db), patch.object(hb.agent_limiter, "enabled", False):
        body = await hb.report_heartbeat(_request("/api/agents/a1/heartbeat"), Response(), "a1", MagicMock(), payload, tenant)
    assert body["enabledCapabilities"] == ["agent_update", "fim", "metrics_collection"]
    assert await mongo_db.logs.count_documents({}) == 0
    assert await mongo_db.fim_violations.count_documents({}) == 1
    agent = await mongo_db.agents.find_one({"id": "a1"})
    assert "fim" in agent["meta"] and "log_collection" not in agent["meta"]


async def test_an_instruction_needing_an_unticked_capability_is_refused_not_delivered(mongo_db):
    """protects=the agent's instruction poll hands over only instructions its tenant's capabilities
    allow and marks the rest refused (so they are never sent later either); fails_when=a remote
    session is delivered with Remote Access unticked; no_claim=the producers' own screens."""
    import agent_tasks_endpoints as tasks
    await mongo_db.tenants.insert_one({"id": T, "agentCapabilities": ["software_management"]})
    await mongo_db.agent_instructions.insert_many([
        {"id": "i1", "agent_id": "a1", "tenantId": T, "status": "pending", "instruction": "start_remote_session"},
        {"id": "i2", "agent_id": "a1", "tenantId": T, "status": "pending", "instruction": "install_software: x.msi"},
        {"id": "i3", "agent_id": "a1", "tenantId": T, "status": "pending", "instruction": "check_agent_update"},
    ])
    tenant = {"id": T, "tenantId": T, "_agent_id": "a1"}
    with patch.object(tasks, "get_database", return_value=mongo_db), \
            patch.object(tasks, "caller_agent_id", return_value="a1"):
        delivered = await tasks.get_agent_instructions("a1", _request("/api/agents/a1/instructions"), tenant)
    assert sorted(i["task_id"] for i in delivered) == ["i2", "i3"]
    refused = await mongo_db.agent_instructions.find_one({"id": "i1"})
    assert refused["status"] == ac.REFUSED and refused["error"] == "capability_not_enabled: remote_access"


async def test_only_the_super_admin_sets_a_tenants_capabilities(mongo_db):
    """protects=PATCH /api/tenants/{id} stores a checked list for a Super Admin, refuses an unknown id
    (400) and a tenant admin (403); fails_when=a tenant admin grants its own agents a capability;
    no_claim=the Manage Tenant screen."""
    import tenant_endpoints
    await mongo_db.tenants.insert_one({"id": T, "name": "Acme", "agentCapabilities": ["fim"]})
    app = FastAPI()
    app.include_router(tenant_endpoints.router)
    user = {"value": TokenData(username="o", role="Super Admin", tenant_id="platform-admin")}
    app.dependency_overrides[tenant_endpoints.get_current_user] = lambda: user["value"]
    with patch.object(tenant_endpoints.mongodb, "db", mongo_db), patch.object(tenant_endpoints, "get_database", lambda: mongo_db):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            ok = await client.patch(f"/api/tenants/{T}", json={"agentCapabilities": ["pii_scanner", "fim"]})
            bad = await client.patch(f"/api/tenants/{T}", json={"agentCapabilities": ["telepathy"]})
            user["value"] = TokenData(username="a", role="Tenant Admin", tenant_id=T)
            refused = await client.patch(f"/api/tenants/{T}", json={"agentCapabilities": ["all"]})
    assert (ok.status_code, bad.status_code, refused.status_code) == (200, 400, 403)
    stored = (await mongo_db.tenants.find_one({"id": T}))["agentCapabilities"]
    assert stored == ["agent_update", "fim", "pii_scanner"]


async def test_migration_020_gives_existing_tenants_every_capability_once(mongo_db):
    """protects=on deploy a tenant without a list gets every capability and a tenant that already has a
    list keeps it; fails_when=existing agents lose data on deploy or a Super Admin's choice is reset;
    no_claim=the runner bookkeeping."""
    import importlib
    await mongo_db.tenants.insert_many([{"id": "old"}, {"id": "chosen", "agentCapabilities": ["fim"]}])
    migration = importlib.import_module("migrations.020_tenant_agent_capabilities")
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    caps = {t["id"]: t["agentCapabilities"] async for t in mongo_db.tenants.find({}, {"_id": 0})}
    assert caps == {"old": sorted(ac.CAPABILITY_IDS), "chosen": ["fim"]}


@pytest.mark.parametrize("module,call", [
    ("agent_security_scan_endpoints", lambda m, t: m.ingest_scan_result("a1", {}, t)),
    ("agent_security_endpoints", lambda m, t: m.post_persistence_findings("a1", {}, t)),
    ("agent_tasks_endpoints", lambda m, t: m.create_ticket_from_agent("a1", m.RaiseTicketRequest(title="x"), t)),
    ("agent_chat_endpoints", lambda m, t: m.initiate_session(m.InitiateSessionRequest(agent_id="a1", subject="s", message="hi"), t)),
])
async def test_an_agent_upload_of_an_unticked_capability_is_refused(module, call):
    """protects=an agent's direct uploads (scan verdicts, persistence findings, tickets, chat) are refused
    with 403 before anything is read or stored when its tenant lacks the capability; fails_when=a ticket
    or chat opens with the capability unticked; no_claim=uploads of a ticked capability (route tests)."""
    import importlib
    from fastapi import HTTPException
    mod = importlib.import_module(module)
    with pytest.raises(HTTPException) as refused:
        await call(mod, {"id": T, "agentCapabilities": ["fim"]})
    assert refused.value.status_code == 403 and "not enabled" in refused.value.detail
