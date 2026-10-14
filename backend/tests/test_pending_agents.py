"""Spec C3: Pending enrollment and over-limit alerts, against a real MongoDB (skips without one).

Value: protects=an enrollment past the seat limit is held as Pending (202 for agents that
understand it, the old 403 for older builds) without taking a seat or storing capability
data; it raises exactly one alert per recipient (collapsing bursts into one summary); a
super admin approves (seat claimed, optionally raising the limit) or rejects (machine
denylisted); Pending/Rejected agents are hidden from list reads and blocked from every
agent route except their heartbeat; tenant admins can neither decide nor flip a status by
hand; fails_when=a Pending agent holds a seat, stores data, reaches a data route, shows in
agent lists or counts, alerts more than once, or a non-super-admin admits it;
no_claim=the HTTP layer and JWT handling (endpoint functions are called directly with a
TokenData; the slowapi limiters are disabled), WebSocket delivery, multi-process caches.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_heartbeat_endpoints as hb
import agent_registry_endpoints as reg
import licensing
import pending_agent_endpoints as pae
import pending_agents
from auth_types import TokenData
from database import TenantIsolatedDatabase
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

T = "tenant-a"
SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
ADMIN_A = TokenData(username="admin@a.example", role="Tenant Admin", tenant_id=T, mfa_verified=True)
HW = {"serialNumber": "PF3ABC12", "smbiosUuid": "4c4c4544-0042-3010-8051-b4c04f4d3132",
      "macAddresses": ["3c:52:82:aa:bb:cc"], "osFamily": "windows", "osVersion": "10.0.26100",
      "deviceType": "workstation", "loggedInUser": "CORP\\jdoe"}


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    pending_agents._status_cache.clear()
    yield
    pending_agents._status_cache.clear()


async def _tenant(db, max_agents=1, online=1):
    await db.tenants.insert_one({"id": T, "name": "Acme", "registrationKey": "k",
                                 "license": {"maxAgents": max_agents, "seatsUsed": online, "inactiveReclaimDays": 30}})
    for i in range(online):
        await db.agents.insert_one({"id": f"agent-old-{i}", "tenantId": T, "hostname": f"old-{i}", "status": "Online"})


def _request(path="/api/agents/register"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": [], "client": ("203.0.113.7", 5555)})


async def _register(db, hostname, capable=True, **body):
    """(status code, result) of POST /api/agents/register; raises HTTPException on refusal."""
    payload = {"registrationKey": "k", "hostname": hostname, "platform": "Windows", "version": "2.1.13",
               "ipAddress": "10.1.2.3", "supportsPending": capable, **body}
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()
    response = Response()
    with patch.object(reg, "get_database", return_value=db), patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), patch.dict(sys.modules, {"finops_service": stub}):
        out = await reg.register_agent(_request(), response, payload, background_tasks=MagicMock())
    return response.status_code, out


async def _heartbeat(db, agent_id, payload):
    tenant = await db.tenants.find_one({"id": T})
    response = Response()
    with patch.object(hb, "get_database", return_value=db), patch.object(hb.agent_limiter, "enabled", False):
        out = await hb.report_heartbeat(_request(f"/api/agents/{agent_id}/heartbeat"), response, agent_id,
                                        MagicMock(), payload, tenant)
    return response.status_code, out


async def _used(db):
    return (await db.tenants.find_one({"id": T}))["license"]["seatsUsed"]


def _platform_feed(db):
    return db.notifications.find({"tenantId": "platform-admin"}).to_list(length=100)


# ── enrollment past the limit ─────────────────────────────────────────────────

async def test_enrollment_at_the_limit_is_held_pending_without_a_seat(mongo_db):
    """AC1. protects=202 pending + Pending doc + seatsUsed unchanged + no token handed out;
    fails_when=the agent is refused outright, admitted, or given a token; no_claim=HTTP layer."""
    await _tenant(mongo_db)
    code, out = await _register(mongo_db, "new-pc", hardware=HW)
    assert code == 202 and out["status"] == "pending" and out["pendingReason"] == "seat_limit"
    assert out["agentSecret"] and "token" not in out
    agent = await mongo_db.agents.find_one({"id": out["agentId"]})
    assert agent["status"] == "Pending" and agent["seatKey"] == "serial:PF3ABC12"
    assert agent["sourceIp"] == "203.0.113.7" and agent["hardware"]["smbiosUuid"] == HW["smbiosUuid"]
    assert await _used(mongo_db) == 1
    assert await mongo_db.assets.count_documents({}) == 0  # no inventory for an unadmitted machine


async def test_pending_agent_polls_register_and_alerts_only_once(mongo_db):
    """AC3. protects=one agent.pending notification per recipient carrying every host detail,
    however often the agent checks back; fails_when=each poll alerts again or a field is missing;
    no_claim=WS push (best effort)."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW, publicIp="198.51.100.4")
    for _ in range(3):
        code, again = await _register(mongo_db, "new-pc", hardware=HW, agentSecret=out["agentSecret"])
        assert code == 202 and "agentSecret" not in again
    platform = await _platform_feed(mongo_db)
    tenant_feed = await mongo_db.notifications.find({"tenantId": T}).to_list(length=100)
    assert len(platform) == 1 and len(tenant_feed) == 1
    assert tenant_feed[0]["metadata"]["audience"] == "tenant_admins"
    meta = platform[0]["metadata"]
    assert meta["event"] == "agent.pending"
    expected = {"tenantId": T, "tenantName": "Acme", "seatsUsed": 1, "maxAgents": 1, "reason": "seat_limit",
                "hostname": "new-pc", "ipAddress": "10.1.2.3", "publicIp": "198.51.100.4", "sourceIp": "203.0.113.7",
                "macAddresses": ["3c:52:82:aa:bb:cc"], "serialNumber": "PF3ABC12", "smbiosUuid": HW["smbiosUuid"],
                "osFamily": "windows", "osVersion": "10.0.26100", "deviceType": "workstation",
                "loggedInUser": "CORP\\jdoe", "agentVersion": "2.1.13"}
    assert {k: meta[k] for k in expected} == expected and meta["firstSeen"]


async def test_a_burst_collapses_into_ten_alerts_and_one_summary(mongo_db):
    """AC4. protects=15 Pending in an hour -> 10 individual + 1 summary per feed, summary counts 15;
    fails_when=15 alerts are sent or the summary count goes stale; no_claim=window rollover timing."""
    await _tenant(mongo_db, max_agents=0, online=0)
    for i in range(15):
        await _register(mongo_db, f"pc-{i}", hardware={"serialNumber": f"SN{i:04d}X"})
    platform = await _platform_feed(mongo_db)
    summaries = [n for n in platform if n["metadata"]["event"] == "agent.pending.summary"]
    assert len(platform) == 11 and len(summaries) == 1
    assert summaries[0]["metadata"]["count"] == 15 and "15 agents" in summaries[0]["message"]
    assert await mongo_db.notifications.count_documents({"tenantId": T}) == 11


async def test_older_build_gets_403_but_is_kept_and_can_enroll_once_approved(mongo_db):
    """protects=an agent without supportsPending keeps today's 403 yet leaves a record that, once
    approved, enrolls with no secret to prove; fails_when=the old agent can never enroll after
    approval (409 already enrolled) or gets credentials while Pending; no_claim=agent retry timing."""
    await _tenant(mongo_db)
    with pytest.raises(HTTPException) as exc:
        await _register(mongo_db, "old-build", capable=False)
    assert exc.value.status_code == 403 and "waiting for approval" in exc.value.detail
    placeholder = await mongo_db.agents.find_one({"hostname": "old-build"})
    assert placeholder["status"] == "Pending" and placeholder["awaitingCredentials"] is True
    assert "agentSecretHash" not in placeholder
    await pending_agents.approve(mongo_db, placeholder["id"], "root", raise_limit_by=1)
    code, out = await _register(mongo_db, "old-build", capable=False)
    assert code == 200 and out["token"] and out["agentSecret"] and out["agentId"] == placeholder["id"]
    agent = await mongo_db.agents.find_one({"id": placeholder["id"]})
    assert agent["status"] == "Online" and agent["awaitingCredentials"] is False
    assert await _used(mongo_db) == 2


# ── heartbeat of a Pending agent ──────────────────────────────────────────────

async def test_pending_heartbeat_stores_identity_only_and_returns_no_tasks(mongo_db):
    """AC2. protects=a Pending agent's heartbeat drops all capability data and gets 202 with no
    tasks; fails_when=metrics, logs, inventory, FIM or assets are written for it;
    no_claim=background tasks (none may be queued, checked via the mock)."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW)
    payload = {"hostname": "new-pc", "platform": "Windows", "version": "2.1.13", "supportsPending": True,
               "ipAddress": "10.9.9.9", "meta": {
                   "current_cpu": 12, "current_memory": 40, "logged_in_user": "CORP\\jdoe",
                   "log_collection": [{"message": "x"}], "software_inventory": [{"name": "7zip"}],
                   "fim": {"violations": [{"path": "C:/x"}]}, "compliance_enforcement": {"checks": []}}}
    code, body = await _heartbeat(mongo_db, out["agentId"], payload)
    assert code == 202 and body["status"] == "pending" and body["retryAfterSeconds"] == 300
    assert not ({"instructions", "tasks", "uninstall_protection"} & body.keys())
    for coll in ("agent_metrics", "asset_metrics", "agent_metrics_history", "logs", "software_inventory",
                 "fim_violations", "assets", "vulnerabilities"):
        assert await mongo_db[coll].count_documents({}) == 0, coll
    agent = await mongo_db.agents.find_one({"id": out["agentId"]})
    assert agent["status"] == "Pending" and agent["ipAddress"] == "10.9.9.9" and "meta" not in agent


async def test_inactive_agent_returning_to_a_full_tenant_goes_pending(mongo_db):
    """protects=a seat-less agent with a valid token that heartbeats into a full tenant is held
    Pending (202) and is then shut out of data routes; fails_when=it goes Online or posts data;
    no_claim=token validation (the tenant dict stands in for verify_agent_key)."""
    await _tenant(mongo_db)
    await mongo_db.agents.insert_one({"id": "agent-back", "tenantId": T, "hostname": "back", "status": "Inactive"})
    code, body = await _heartbeat(mongo_db, "agent-back", {"hostname": "back", "supportsPending": True})
    assert code == 202 and body["status"] == "pending"
    assert (await mongo_db.agents.find_one({"id": "agent-back"}))["status"] == "Pending"
    assert await _used(mongo_db) == 1
    with pytest.raises(HTTPException) as exc:
        await pending_agents.assert_admitted(mongo_db, "agent-back", "/api/agents/agent-back/metrics")
    assert exc.value.status_code == 403 and exc.value.detail.startswith("agent_pending")


async def test_admission_gate_lets_pending_reach_only_heartbeat_and_uninstall_report(mongo_db):
    """protects=the gate wired into both agent-token entry points; fails_when=a Pending agent
    reaches a data route, a Rejected one reaches anything, or an admitted one is blocked."""
    await mongo_db.agents.insert_many([{"id": "p", "tenantId": T, "hostname": "p", "status": "Pending"},
                                       {"id": "r", "tenantId": T, "hostname": "r", "status": "Rejected"},
                                       {"id": "ok", "tenantId": T, "hostname": "ok", "status": "Online"}])
    await pending_agents.assert_admitted(mongo_db, "p", "/api/agents/p/heartbeat")
    await pending_agents.assert_admitted(mongo_db, "p", "/api/agents/heartbeat")
    await pending_agents.assert_admitted(mongo_db, "p", "/api/agents/p/uninstall-report")
    await pending_agents.assert_admitted(mongo_db, "ok", "/api/agents/ok/telemetry")
    for agent_id, path in (("p", "/api/agents/p/instructions"), ("p", "/api/edr/telemetry"),
                           ("r", "/api/agents/r/heartbeat"), ("r", "/api/agents/r/telemetry")):
        with pytest.raises(HTTPException) as exc:
            await pending_agents.assert_admitted(mongo_db, agent_id, path)
        assert exc.value.status_code == 403, (agent_id, path)


# ── decisions ─────────────────────────────────────────────────────────────────

async def test_approve_with_a_free_seat_then_the_agent_comes_online(mongo_db):
    """AC5a. protects=approval claims one seat and the agent's next check-in gets a token and goes
    Online; fails_when=approval skips the seat or the agent stays Pending."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW)
    await licensing.update_license(mongo_db, T, max_agents=2)
    result = await pending_agents.approve(mongo_db, out["agentId"], "root")
    assert result["status"] == "Offline" and result["license"]["seatsUsed"] == 2
    code, enrolled = await _register(mongo_db, "new-pc", hardware=HW, agentSecret=out["agentSecret"])
    assert code == 200 and enrolled["token"]
    assert (await mongo_db.agents.find_one({"id": out["agentId"]}))["status"] == "Online"
    assert await _used(mongo_db) == 2


async def test_approve_without_a_free_seat_needs_a_limit_raise(mongo_db):
    """AC5b. protects=no free seat -> 409 no_free_seat with the license; "raise by 1" adds a seat
    and admits; fails_when=approval overshoots the limit silently."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW)
    with pytest.raises(pending_agents.DecisionError) as exc:
        await pending_agents.approve(mongo_db, out["agentId"], "root")
    assert exc.value.status_code == 409 and exc.value.detail.startswith("no_free_seat")
    assert exc.value.extra["maxAgents"] == 1 and exc.value.extra["seatsUsed"] == 1
    assert (await mongo_db.agents.find_one({"id": out["agentId"]}))["status"] == "Pending"
    await pending_agents.approve(mongo_db, out["agentId"], "root", raise_limit_by=1)
    tenant = await mongo_db.tenants.find_one({"id": T})
    assert tenant["license"]["maxAgents"] == 2 and tenant["license"]["seatsUsed"] == 2


async def test_reject_refuses_the_agent_and_its_hardware(mongo_db):
    """AC6. protects=after reject the agent's heartbeat and re-enrollment get 403 rejected, and the
    same machine under a new hostname goes straight to Rejected; approving it later lifts that;
    fails_when=a rejected machine can enroll again."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW)
    await pending_agents.reject(mongo_db, out["agentId"], "root")
    with pytest.raises(HTTPException) as exc:
        await _heartbeat(mongo_db, out["agentId"], {"hostname": "new-pc", "supportsPending": True})
    assert exc.value.status_code == 403 and exc.value.detail.startswith("agent_rejected")
    with pytest.raises(HTTPException) as exc:
        await _register(mongo_db, "new-pc", hardware=HW, agentSecret=out["agentSecret"])
    assert exc.value.status_code == 403 and exc.value.detail.startswith("agent_rejected")
    with pytest.raises(HTTPException) as exc:
        await _register(mongo_db, "renamed-pc", hardware=HW)
    assert exc.value.status_code == 403
    assert (await mongo_db.agents.find_one({"hostname": "renamed-pc"}))["status"] == "Rejected"
    assert await mongo_db.agent_denylist.count_documents({"tenantId": T, "seatKey": "serial:PF3ABC12"}) == 1
    await pending_agents.approve(mongo_db, out["agentId"], "root", raise_limit_by=1)
    assert await mongo_db.agent_denylist.count_documents({}) == 0


async def test_rejecting_a_hardware_duplicate_does_not_lock_out_the_live_agent(mongo_db):
    """protects=a duplicate_hardware_id reject leaves the shared serial off the denylist;
    fails_when=the genuine agent with that serial is refused later."""
    await _tenant(mongo_db, max_agents=5, online=0)
    await mongo_db.agents.insert_one({"id": "live", "tenantId": T, "hostname": "real-pc", "status": "Online",
                                      "hardware": {"serialNumber": "PF3ABC12"}, "lastSeen": "2999-01-01T00:00:00+00:00"})
    await licensing.recount_seats(mongo_db, T)
    code, out = await _register(mongo_db, "clone", hardware=HW)
    assert code == 202 and out["pendingReason"] == "duplicate_hardware_id"
    await pending_agents.reject(mongo_db, out["agentId"], "root")
    assert await mongo_db.agent_denylist.count_documents({}) == 0


async def test_only_super_admin_decides_and_tenant_admin_reads_its_own_list(mongo_db):
    """AC8. protects=tenant admin approve/reject/bulk -> 403 and a read-only list of its own
    tenant; fails_when=a tenant admin admits an agent or sees another tenant's Pending agents."""
    await _tenant(mongo_db)
    _, out = await _register(mongo_db, "new-pc", hardware=HW)
    await mongo_db.agents.insert_one({"id": "other", "tenantId": "tenant-b", "hostname": "x", "status": "Pending"})
    with patch.object(pae, "get_database", return_value=mongo_db):
        for call in (lambda: pae.approve_pending_agent(out["agentId"], pae.ApproveBody(raiseLimitBy=5), ADMIN_A),
                     lambda: pae.reject_pending_agent(out["agentId"], ADMIN_A),
                     lambda: pae.bulk_decide(pae.BulkBody(action="approve", agentIds=[out["agentId"]]), ADMIN_A)):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 403
        listed = await pae.list_pending_agents(tenant_id="tenant-b", status=None, reason=None, current_user=ADMIN_A)
        everything = await pae.list_pending_agents(tenant_id=None, status=None, reason=None, current_user=SUPER)
    assert [a["id"] for a in listed["agents"]] == [out["agentId"]] and listed["canDecide"] is False
    assert {a["id"] for a in everything["agents"]} == {out["agentId"], "other"} and everything["canDecide"]
    assert "agentSecretHash" not in listed["agents"][0]
    assert (await mongo_db.agents.find_one({"id": out["agentId"]}))["status"] == "Pending"


async def test_bulk_approve_can_raise_the_limit_one_seat_per_agent(mongo_db):
    """protects=bulk approve with raiseLimit adds exactly the seats it needs; fails_when=it
    over-raises or stops at the first agent without a seat."""
    await _tenant(mongo_db)
    ids = [(await _register(mongo_db, f"pc-{i}", hardware={"serialNumber": f"SN{i:04d}X"}))[1]["agentId"]
           for i in range(3)]
    with patch.object(pae, "get_database", return_value=mongo_db), patch.object(pae, "invalidate_cache"):
        out = await pae.bulk_decide(pae.BulkBody(action="approve", agentIds=ids, raiseLimit=True), SUPER)
    assert out["succeeded"] == 3 and out["failed"] == 0
    tenant = await mongo_db.tenants.find_one({"id": T})
    assert tenant["license"]["maxAgents"] == 4 and tenant["license"]["seatsUsed"] == 4


# ── hidden from lists, protected from hand edits ──────────────────────────────

async def test_list_reads_hide_pending_and_rejected_agents(mongo_db):
    """AC7. protects=every list read through the tenant wrapper (find, count, distinct, aggregate)
    and the tenant list counts leave Pending/Rejected out while single reads still see them;
    fails_when=GET /api/agents or a KPI counts them; no_claim=raw-collection callers (audited by grep)."""
    await mongo_db.agents.insert_many([
        {"id": "on", "tenantId": T, "hostname": "on", "status": "Online"},
        {"id": "off", "tenantId": T, "hostname": "off", "status": "Offline"},
        {"id": "pen", "tenantId": T, "hostname": "pen", "status": "Pending"},
        {"id": "rej", "tenantId": T, "hostname": "rej", "status": "Rejected"}])
    for tenant_ctx in (T, "platform-admin"):
        token = set_tenant_id(tenant_ctx)
        try:
            db = TenantIsolatedDatabase(mongo_db)
            assert {a["id"] for a in await db.agents.find({}).to_list(length=10)} == {"on", "off"}
            assert await db.agents.count_documents({}) == 2
            assert await db.agents.count_documents({"status": "Pending"}) == 0
            assert await db.agents.count_documents({"status": {"$ne": "Offline"}}) == 1
            assert sorted(await db.agents.distinct("hostname")) == ["off", "on"]
            assert [d async for d in db.agents.aggregate([{"$count": "n"}])] == [{"n": 2}]
            assert (await db.agents.find_one({"id": "pen"}))["status"] == "Pending"
        finally:
            reset_tenant_id(token)
    import tenant_endpoints as te
    from types import SimpleNamespace
    await mongo_db.tenants.insert_one({"id": T, "name": "Acme", "license": {"maxAgents": 5, "seatsUsed": 2}})
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)):
        tenants = await te.get_tenants(current_user=SUPER)
    acme = next(t for t in tenants if t["id"] == T)
    assert (acme["agentCount"], acme["pendingCount"]) == (2, 1)


async def test_hand_written_status_cannot_admit_a_pending_agent(mongo_db):
    """protects=PUT /api/agents/{id} and PATCH /api/agents/bulk refuse status writes into or out of
    seat-less states; fails_when=a tenant admin sets a Pending agent Online without a seat."""
    await mongo_db.agents.insert_many([{"id": "pen", "tenantId": T, "hostname": "pen", "status": "Pending"},
                                       {"id": "on", "tenantId": T, "hostname": "on", "status": "Online"}])
    with patch.object(reg, "get_database", return_value=mongo_db), patch.object(reg, "invalidate_cache"):
        with pytest.raises(HTTPException) as exc:
            await reg.update_agent("pen", {"status": "Online"}, current_user=ADMIN_A)
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException) as exc:
            await reg.update_agent("on", {"status": "Rejected"}, current_user=ADMIN_A)
        assert exc.value.status_code == 409
        await reg.update_agent("on", {"status": "Degraded", "alias": "x"}, current_user=ADMIN_A)
    import agent_core_endpoints as core
    out = await core.bulk_update_agents_route(body={"ids": ["pen", "on"], "patch": {"status": "Online"}},
                                              db=mongo_db, current_user=ADMIN_A)
    assert out["matched"] == 1
    assert (await mongo_db.agents.find_one({"id": "pen"}))["status"] == "Pending"
    with pytest.raises(HTTPException) as exc:
        await core.bulk_update_agents_route(body={"ids": ["on"], "patch": {"status": "Inactive"}},
                                            db=mongo_db, current_user=ADMIN_A)
    assert exc.value.status_code == 409


async def test_notification_feed_keeps_admin_alerts_from_other_users(mongo_db):
    """protects=alerts addressed to tenant admins (host details) are not served to users who
    cannot manage agents; fails_when=a viewer reads them or an admin misses them;
    no_claim=role resolution (permissions are stubbed)."""
    import notification_endpoints as ne
    await mongo_db.notifications.insert_many([
        {"alert_id": "a1", "tenantId": T, "sent_at": "2026-10-14T00:00:01", "metadata": {"audience": "tenant_admins"}},
        {"alert_id": "a2", "tenantId": T, "sent_at": "2026-10-14T00:00:02", "metadata": {}}])
    token = set_tenant_id(T)
    try:
        with patch.object(ne, "get_database", return_value=TenantIsolatedDatabase(mongo_db)):
            with patch.object(ne.rbac_service, "get_user_permissions", AsyncMock(return_value=["view:dashboard"])):
                viewer = await ne.get_notifications(current_user=ADMIN_A, limit=50)
            with patch.object(ne.rbac_service, "get_user_permissions", AsyncMock(return_value=["manage:agents"])):
                admin = await ne.get_notifications(current_user=ADMIN_A, limit=50)
    finally:
        reset_tenant_id(token)
    assert [n["alert_id"] for n in viewer] == ["a2"]
    assert [n["alert_id"] for n in admin] == ["a2", "a1"]


def test_manual_status_change_rule():
    """protects=the rule behind the PUT/PATCH guards; fails_when=a seat-state crossing is allowed."""
    assert licensing.manual_status_change_error("Online", "Offline") is None
    assert licensing.manual_status_change_error("Pending", "Pending") is None
    assert licensing.manual_status_change_error("Pending", "Online")
    assert licensing.manual_status_change_error("Online", "Decommissioned")
    assert licensing.manual_status_change_error("Inactive", "Online")
