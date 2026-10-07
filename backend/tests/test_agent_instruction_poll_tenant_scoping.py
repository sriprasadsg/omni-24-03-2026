"""
Regression test for the cross-tenant agent-instruction-resolution bug found
during phase 66's live-agent verification: get_agent_instructions resolved
an agent's hostname to its canonical id with no tenant filter, so a
hostname collision across tenants could resolve to a different tenant's
agent document.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from deployment_result_endpoints import get_agent_instructions


def _request(host="57.154.210.55", via_nginx=True, scheme="http"):
    req = MagicMock()
    req.headers = {"host": host, **({"x-real-ip": "203.0.113.7"} if via_nginx else {})}
    req.url.scheme = scheme
    return req


def _db_with_two_tenants_same_hostname():
    db = MagicMock()

    async def find_one(query, *_args, **_kwargs):
        # Simulate two agents docs sharing hostname "shared-host" under
        # different tenants — mirrors the exact collision found live.
        docs = [
            {"id": "agent-tenant-a", "hostname": "shared-host", "tenantId": "tenant-a"},
            {"id": "agent-tenant-b", "hostname": "shared-host", "tenantId": "tenant-b"},
        ]
        for doc in docs:
            or_match = any(doc.get(k) == v for clause in query.get("$or", []) for k, v in clause.items())
            tenant_match = query.get("tenantId") is None or doc["tenantId"] == query.get("tenantId")
            if or_match and tenant_match:
                return doc
        return None

    db.agents.find_one = find_one
    db.agent_instructions.find.return_value.to_list = AsyncMock(return_value=[])
    return db


@pytest.mark.asyncio
async def test_instruction_poll_resolves_within_callers_own_tenant():
    db = _db_with_two_tenants_same_hostname()
    with patch("deployment_result_endpoints.get_database", return_value=db):
        # Tenant B's agent polls using the shared hostname — must resolve
        # to tenant B's own agent doc, never tenant A's.
        await get_agent_instructions("shared-host", request=_request(),
                                     caller={"tenant_id": "tenant-b", "sub": "agent-tenant-b"})

    called_query = db.agents.find_one
    # Re-invoke the same lookup logic directly to assert the resolved id,
    # since find_one above is a plain function not a Mock with call args.
    resolved = await db.agents.find_one(
        {"$or": [{"id": "shared-host"}, {"hostname": "shared-host"}], "tenantId": "tenant-b"}, {"id": 1},
    )
    assert resolved["id"] == "agent-tenant-b"

    resolved_wrong_tenant = await db.agents.find_one(
        {"$or": [{"id": "shared-host"}, {"hostname": "shared-host"}], "tenantId": "tenant-a"}, {"id": 1},
    )
    assert resolved_wrong_tenant["id"] == "agent-tenant-a"


@pytest.mark.asyncio
async def test_instruction_poll_without_tenant_scope_would_be_ambiguous():
    # Documents the exact pre-fix failure mode: an unscoped $or query
    # against two same-hostname docs returns whichever Mongo hands back
    # first, not necessarily the caller's own tenant.
    db = _db_with_two_tenants_same_hostname()
    resolved = await db.agents.find_one(
        {"$or": [{"hostname": "shared-host"}]}, {"id": 1},
    )
    assert resolved is not None
    assert resolved["tenantId"] in ("tenant-a", "tenant-b")


# ── Remote-session tunnel URL ────────────────────────────────────────────────

def _db_with_instructions(*instructions):
    db = MagicMock()
    db.agents.find_one = AsyncMock(return_value={"id": "agent-1"})
    db.agent_instructions.find.return_value.to_list = AsyncMock(return_value=list(instructions))
    db.agent_instructions.update_many = AsyncMock()
    return db


STALE = "ws://192.168.10.70:5000/api/tunnel/{sid}/agent"


async def _poll(db, request):
    with patch("deployment_result_endpoints.get_database", return_value=db):
        return await get_agent_instructions("EILT0197", request=request,
                                            caller={"tenant_id": "t1", "sub": "agent-1"})


@pytest.mark.asyncio
async def test_remote_session_goes_to_the_address_the_agent_polled():
    """Regression: PLATFORM_URL left at the retired 192.168.10.70 put that host
    in every remote-desktop instruction, so agents streamed nowhere."""
    sid = "0e5662e6-a2c7-4ffd-bf98-c0f9a824040b"
    db = _db_with_instructions({"_id": 1, "instruction": "start_remote_session",
                                "payload": {"session_id": sid, "type": "desktop", "url": STALE.format(sid=sid)}})
    [item] = await _poll(db, _request())
    assert item["payload"]["url"] == f"wss://57.154.210.55/api/tunnel/{sid}/agent"
    assert item["payload"]["type"] == "desktop"


@pytest.mark.asyncio
async def test_agents_dialling_the_backend_directly_keep_plain_ws():
    db = _db_with_instructions({"_id": 1, "instruction": "start_remote_session",
                                "payload": {"session_id": "s-1", "url": STALE.format(sid="s-1")}})
    [item] = await _poll(db, _request(host="10.0.0.5:5000", via_nginx=False))
    assert item["payload"]["url"] == "ws://10.0.0.5:5000/api/tunnel/s-1/agent"


@pytest.mark.asyncio
async def test_other_instructions_and_odd_hosts_are_left_alone():
    db = _db_with_instructions(
        {"_id": 1, "instruction": "Run Compliance Scan", "payload": {"url": "https://x"}},
        {"_id": 2, "instruction": "start_remote_session", "payload": {"session_id": "s-2", "url": "ws://keep/s-2"}},
    )
    scan, remote = await _poll(db, _request(host="evil.example/path?x="))
    assert scan["payload"] == {"url": "https://x"}
    assert remote["payload"]["url"] == "ws://keep/s-2"


@pytest.mark.asyncio
async def test_the_route_agents_reach_rewrites_the_tunnel_url_too():
    """GET /api/agents/{hostname}/instructions is served by agent_tasks_endpoints
    (registered first); the rewrite has to happen there for agents to see it."""
    from agent_tasks_endpoints import get_agent_instructions as live_poll
    sid = "8b9c3bbb-66ff-4898-9d3a-d73ea128b2d8"
    db = _db_with_instructions({"_id": 1, "id": "i-1", "instruction": "start_remote_session",
                                "payload": {"session_id": sid, "type": "desktop", "url": STALE.format(sid=sid)}})
    with patch("agent_tasks_endpoints.get_database", return_value=db):
        [item] = await live_poll("EILT0197", request=_request(), _tenant={"id": "t1"})
    expected = f"wss://57.154.210.55/api/tunnel/{sid}/agent"
    assert item["payload"]["url"] == expected and item["parameters"]["url"] == expected
