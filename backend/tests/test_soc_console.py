"""SOC console (Security Overview) and the shared alert queue: soc_alerts, soc_service, soc_actions,
soc_endpoints and migration 036.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real-MongoDB cases use the throwaway database of
tests/_mongo_test_db.py (point MONGO_TEST_URL at a private mongod, never the live one).
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_actions
import soc_alerts
import soc_endpoints
import soc_service
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
ANALYST = SimpleNamespace(username="ana@t1.test", role="tenant_admin", tenant_id="t1")
migration = importlib.import_module("migrations.036_soc_alerts")


def _at(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def _alert(**kw):
    doc = {"id": kw.pop("id", "a1"), "tenantId": "t1", "agent_id": "ag1", "type": "fim_violation",
           "severity": "high", "title": "File Integrity Violation: /etc/passwd", "created_at": _at(1), "status": "open"}
    doc.update(kw)
    return doc


# ── pure functions ───────────────────────────────────────────────────────────────────────────


def test_status_of_reads_every_writer_and_the_legacy_collection():
    """protects=one status vocabulary in the console; fails_when=a UEBA "new" alert or a legacy
    "resolved" one is miscounted as closed/open; no_claim=-"""
    assert soc_alerts.status_of({"status": "new"}) == ("open", None)
    assert soc_alerts.status_of({}) == ("open", None)
    assert soc_alerts.status_of({"status": "open", "acknowledged": True}) == ("acknowledged", None)
    assert soc_alerts.status_of({"status": "resolved"}) == ("closed", "resolved")
    assert soc_alerts.status_of({"status": "dismissed"}) == ("closed", "benign")
    assert soc_alerts.status_of({"status": "closed", "resolution": "false_positive"}) == ("closed", "false_positive")
    assert soc_alerts.status_of({"status": "merged"}) == ("merged", None)


def test_view_lifts_tenant_and_endpoint_and_names_only_stated_techniques():
    """protects=a UEBA alert with tenant/agent only in metadata still belongs to its tenant, and MITRE
    techniques come from the alert itself or the mitre_service type map; fails_when=techniques are
    invented for types with no mapping; no_claim=-"""
    ueba = soc_service.view({"_id": "x", "type": "ueba_anomaly", "severity": "Medium", "status": "new",
                             "metadata": {"tenantId": "t9", "agent_id": "ag9", "user": "bob"}, "timestamp": _at(2)})
    assert (ueba["id"], ueba["tenantId"], ueba["agentId"], ueba["status"], ueba["severity"]) == ("x", "t9", "ag9", "open", "medium")
    assert ueba["mitre"] == [] and ueba["evidence"] == {"user": "bob"}
    yara = soc_service.view(_alert(type="runtime_security", description="matched 'Mimikatz' (MITRE: T1003.001 - LSASS Memory)"))
    assert yara["mitre"] == ["T1003.001"]
    assert soc_service.view(_alert(type="brute_force"))["mitre"] == ["T1110"]


def test_summary_counts_trend_response_times_and_endpoints():
    """protects=the overview numbers: active by severity, new vs previous range, trend buckets, response
    times only from analyst actions (a system auto-close never counts), endpoints ranked by severity;
    fails_when=merged repeats are counted, an auto-closed alert drags the time to close, or a removed
    endpoint disappears; no_claim=Mongo query shape (see the real-Mongo tests)"""
    rows = [
        _alert(id="c", severity="critical", agent_id="ag2", created_at=_at(0.5)),
        _alert(id="h", status="acknowledged", created_at=_at(3), acknowledgedAt=_at(2)),
        _alert(id="closed", status="closed", resolution="resolved", created_at=_at(30), closedAt=_at(22)),
        _alert(id="auto", status="closed", resolution="approved", created_at=_at(200), closedAt=_at(1), autoClosed=True),
        _alert(id="m", status="merged", created_at=_at(2)),
        _alert(id="gone", agent_id="removed-agent", severity="medium", created_at=_at(40)),
    ]
    agents = [{"id": "ag1", "hostname": "pc-1", "lastSeen": _at(0.01), "availableCapabilities": ["fim", "ueba"]},
              {"id": "ag2", "hostname": "pc-2", "lastSeen": _at(5), "availableCapabilities": ["fim"]}]
    s = soc_service.build_summary([soc_service.view(r) for r in rows], agents, "24h", NOW)
    k = s["kpis"]
    assert (k["active"], k["open"]) == (3, 2)
    assert k["activeBySeverity"]["critical"] == 1 and k["activeBySeverity"]["high"] == 1
    assert (k["newInRange"], k["newPrevious"]) == (2, 2)  # c, h | closed (30h), gone (40h)
    assert k["timeToAcknowledge"] == {"seconds": 3600, "count": 1}
    assert k["timeToClose"] == {"seconds": 8 * 3600, "count": 1}  # 'closed' only: 'auto' was closed by the system
    assert (k["endpointsWithActive"], k["removedWithActive"], k["endpointsOnline"]) == (3, 1, 1)
    assert sum(b["critical"] for b in s["trend"]) == 1 and len(s["trend"]) == 24
    assert s["trend"][-1]["critical"] == 1
    assert [e["hostname"] for e in s["endpoints"]] == ["pc-2", "pc-1", "removed-agent"]
    assert s["endpoints"][2]["known"] is False and s["endpoints"][0]["online"] is False
    assert {c["check"]: c["agents"] for c in s["coverage"]}["fim"] == 2


def test_queue_filter_always_scopes_and_escapes_search():
    """protects=a tenant's queue query always carries its tenant, legacy capitalised severities match,
    a search string is literal; fails_when=a filter drops the tenant or a regex search is injected;
    no_claim=-"""
    f = soc_service.queue_filter("t1", "open", "high", None, None, "a.*b")
    assert f["tenantId"] == "t1" and f["status"] == {"$in": ["open", "new"]}
    assert f["severity"] == {"$in": ["high", "High", "HIGH"]}
    assert f["$or"][0]["title"]["$regex"] == r"a\.\*b"
    assert soc_service.queue_filter(None, "all")["status"] == {"$nin": ["merged", "archived"]}
    assert "tenantId" not in soc_service.queue_filter(None)


def test_change_for_needs_a_resolution_and_guards_the_current_state():
    """protects=close needs a resolution (and never "approved", which only approve_ai sets), acknowledge
    only applies to open alerts; fails_when=an alert can be closed without a reason; no_claim=-"""
    with pytest.raises(soc_actions.ActionError) as bad:
        soc_actions.change_for("close", ANALYST, _at(0))
    assert bad.value.status == 400
    with pytest.raises(soc_actions.ActionError):
        soc_actions.change_for("close", ANALYST, _at(0), resolution="approved")
    pre, update = soc_actions.change_for("acknowledge", ANALYST, _at(0))
    assert pre == {"$in": ["open", "new"]} and update[0]["$set"]["status"] == "acknowledged"


def test_scope_is_the_callers_tenant_unless_super_admin():
    """protects=a tenant user can never widen the scope with tenantId; a Super Admin sees the tenant they
    view (X-Tenant-ID), else all tenants or the one asked for; fails_when=a tenant reads another tenant;
    no_claim=the catalogue guards (next test)"""
    assert soc_endpoints.soc_scope(ANALYST, "t2") == "t1"
    with pytest.raises(HTTPException) as no_tenant:
        soc_endpoints.soc_scope(SimpleNamespace(role="analyst", tenant_id=None))
    assert no_tenant.value.status_code == 403
    owner = SimpleNamespace(role="Super Admin", tenant_id="platform-admin")
    token = set_tenant_id("platform-admin")
    try:
        assert soc_endpoints.soc_scope(owner) is None and soc_endpoints.soc_scope(owner, "t2") == "t2"
    finally:
        reset_tenant_id(token)
    token = set_tenant_id("t3")
    try:
        assert soc_endpoints.soc_scope(owner, "t2") == "t3"
    finally:
        reset_tenant_id(token)


def test_every_soc_route_carries_its_screens_catalogue_guard():
    """protects=/api/security/soc/* needs Security Overview, /api/alerts/queue* Alert Management;
    fails_when=a route is mounted without a guard; no_claim=the permission strings themselves"""
    for router, catalogue in ((soc_endpoints.router, "security"), (soc_endpoints.queue_router, "alertManagement")):
        for route in router.routes:
            tags = [getattr(d.dependency, "__catalogue_guard__", None) for d in route.dependencies]
            assert any(t and t["catalogue"] == catalogue for t in tags), route.path


# ── real MongoDB ─────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def soc_db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_record_alert_lifts_metadata_counts_repeats_and_skips_approved_ai(soc_db):
    """protects=writers' alerts get an id, tenant and endpoint; a repeat of an active finding raises
    occurrences instead of a row; an approved AI process is recognised; fails_when=every scan adds a row
    (the 389-row Ollama flood); no_claim=the websocket push reaches a browser"""
    ueba = await soc_alerts.record_alert(soc_db, {"type": "ueba_anomaly", "severity": "Medium", "status": "new",
                                                  "metadata": {"tenantId": "t1", "agent_id": "ag1"}})
    assert ueba["id"] and ueba["tenantId"] == "t1" and ueba["agent_id"] == "ag1" and ueba["status"] == "open"
    for when in (_at(3), _at(2), _at(1)):
        await soc_alerts.record_alert(soc_db, {"tenantId": "t1", "agent_id": "ag1", "type": "shadow_ai_process",
                                               "title": "Unapproved AI process: ollama", "created_at": when},
                                      group="shadow_ai_process:ag1:ollama")
    rows = await soc_db.security_alerts.find({"type": "shadow_ai_process"}).to_list(10)
    assert len(rows) == 1 and rows[0]["occurrences"] == 3 and rows[0]["lastSeenAt"] == _at(1)
    assert rows[0]["created_at"] == _at(3)
    await soc_db.approved_ai_processes.insert_one({"tenantId": "t1", "process": "ollama", "agentId": None})
    assert await soc_alerts.is_approved_ai(soc_db, "t1", "ag7", "Ollama")
    assert not await soc_alerts.is_approved_ai(soc_db, "t2", "ag7", "ollama")


@pytest.mark.asyncio
async def test_migration_036_folds_names_lifts_and_approves_the_server_llm_once(soc_db, monkeypatch):
    """protects=old rows get ids and tenants, AI-process alerts get the name from their scan, repeats fold
    into the first (counted, nothing deleted), the server's own Ollama is approved and its alerts closed
    without counting toward response times, and a second run changes nothing; fails_when=rows are
    deleted, counts reset on re-run, or another endpoint's Ollama is approved; no_claim=live data shape
    beyond these rows"""
    import network_topology_service
    monkeypatch.setattr(network_topology_service, "server_identity", lambda: {"hostname": "srv", "names": {"srv"}})
    await soc_db.agents.insert_many([{"id": "srv-agent", "tenantId": "platform-admin", "hostname": "srv"},
                                     {"id": "pc", "tenantId": "t1", "hostname": "pc"}])
    for i in range(3):
        when = _at(10 - i)
        await soc_db.shadow_ai_scans.insert_one({"agent_id": "srv-agent", "scanned_at": when,
                                                 "local_ai_processes": [{"process": "ollama", "pid": 7, "exe": "/usr/bin/ollama"}]})
        await soc_db.security_alerts.insert_one({"tenantId": "platform-admin", "agent_id": "srv-agent", "type": "shadow_ai_process",
                                                 "title": "Unauthorized AI process: unknown", "status": "open",
                                                 "description": "Local AI process 'None' (PID 7) detected", "created_at": when})
    await soc_db.security_alerts.insert_many([
        {"tenantId": "t1", "agent_id": "pc", "type": "shadow_ai_process", "process": "ollama", "status": "open", "created_at": _at(4)},
        {"type": "ueba_anomaly", "status": "new", "metadata": {"tenantId": "t1", "agent_id": "pc"}, "created_at": _at(5)},
    ])
    await migration.up(soc_db)
    first = await soc_db.security_alerts.find({}, {"_id": 0}).sort("created_at", 1).to_list(20)
    await migration.up(soc_db)
    assert await soc_db.security_alerts.find({}, {"_id": 0}).sort("created_at", 1).to_list(20) == first

    assert len(first) == 5 and all(r.get("id") and r.get("tenantId") for r in first)
    srv = [r for r in first if r["agent_id"] == "srv-agent"]
    kept = next(r for r in srv if r["status"] == "closed")
    assert kept["process"] == "ollama" and kept["occurrences"] == 3 and kept["created_at"] == _at(10)
    assert kept["lastSeenAt"] == _at(8) and kept["resolution"] == "approved" and kept["autoClosed"] is True
    assert sorted(r["status"] for r in srv) == ["closed", "merged", "merged"]
    assert {r.get("mergedInto") for r in srv if r["status"] == "merged"} == {kept["id"]}
    pc = next(r for r in first if r["agent_id"] == "pc" and r["type"] == "shadow_ai_process")
    assert pc["status"] == "open"  # only the server's own LLM is approved
    ueba = next(r for r in first if r["type"] == "ueba_anomaly")
    assert (ueba["tenantId"], ueba["agent_id"], ueba["status"]) == ("t1", "pc", "open")
    approvals = await soc_db.approved_ai_processes.find({}, {"_id": 0, "process": 1, "agentId": 1}).to_list(10)
    assert sorted((a["process"], a["agentId"]) for a in approvals) == [("llama-server", "srv-agent"), ("ollama", "srv-agent")]


@pytest.mark.asyncio
async def test_actions_record_who_and_when_and_stay_inside_the_tenant(soc_db):
    """protects=acknowledge/close stamp the analyst and time (the console's response times), a second
    acknowledge is refused, another tenant's alert is "not found", bulk reaches legacy alerts, a case
    from an alert carries the alert's tenant and is reused; fails_when=a tenant can change another
    tenant's alert or a case is created twice; no_claim=the HTTP layer (see the guard test)"""
    await soc_db.security_alerts.insert_many([_alert(id="a1"), _alert(id="a2"), _alert(id="other", tenantId="t2")])
    await soc_db.alerts.insert_one({"id": "legacy", "tenantId": "t1", "severity": "High", "title": "Agent alert",
                                    "status": "open", "timestamp": _at(1)})
    token = set_tenant_id("t1")
    try:
        acked = await soc_actions.apply_action("t1", "a1", "acknowledge", ANALYST)
        assert acked["status"] == "acknowledged" and acked["acknowledgedBy"] == "ana@t1.test" and acked["acknowledgedAt"]
        with pytest.raises(soc_actions.ActionError) as again:
            await soc_actions.apply_action("t1", "a1", "acknowledge", ANALYST)
        assert again.value.status == 409
        with pytest.raises(soc_actions.ActionError) as foreign:
            await soc_actions.apply_action("t1", "other", "close", ANALYST, resolution="benign")
        assert foreign.value.status == 404
        closed = await soc_actions.apply_action("t1", "a1", "close", ANALYST, resolution="false_positive", note="test binary")
        assert (closed["status"], closed["resolution"], closed["closeNote"]) == ("closed", "false_positive", "test binary")
        assert closed["acknowledgedAt"] == acked["acknowledgedAt"]  # first response kept

        result = await soc_actions.bulk_action("t1", ["a2", "legacy", "other"], "acknowledge", ANALYST)
        assert result == {"matched": 2, "modified": 2}
        made = await soc_actions.open_case("t1", "a2", ANALYST)
        again_case = await soc_actions.open_case("t1", "a2", ANALYST)
        assert made["created"] and not again_case["created"] and again_case["case"]["id"] == made["case"]["id"]
        assert made["case"]["tenantId"] == "t1" and made["case"]["severity"] == "High"
    finally:
        reset_tenant_id(token)
    other = await soc_db.security_alerts.find_one({"id": "other"})
    assert other["status"] == "open"
    assert (await soc_db.security_alerts.find_one({"id": "a2"}))["caseId"] == made["case"]["id"]


@pytest.mark.asyncio
async def test_approving_an_ai_process_closes_its_alerts_and_can_be_revoked(soc_db):
    """protects=approve closes the endpoint's alerts for that process (resolution approved) and writes a
    revocable approval; fails_when=a non-AI alert can be approved or other processes close; no_claim=-"""
    await soc_db.security_alerts.insert_many([
        _alert(id="ai", type="shadow_ai_process", title="Unapproved AI process: ollama", process="ollama"),
        _alert(id="ai2", type="shadow_ai_process", title="Unapproved AI process: lmstudio", process="lmstudio"),
        _alert(id="fim"),
    ])
    with pytest.raises(soc_actions.ActionError):
        await soc_actions.approve_ai("t1", "fim", ANALYST)
    out = await soc_actions.approve_ai("t1", "ai", ANALYST, reason="IT-approved")
    assert out["closed"] == 1 and out["approval"]["process"] == "ollama" and out["approval"]["agentId"] == "ag1"
    statuses = {r["id"]: r["status"] for r in await soc_db.security_alerts.find({}).to_list(10)}
    assert statuses == {"ai": "closed", "ai2": "open", "fim": "open"}
    approvals = await soc_actions.list_approvals("t1")
    await soc_actions.revoke_approval("t1", approvals[0]["id"], ANALYST)
    assert await soc_actions.list_approvals("t1") == []


@pytest.mark.asyncio
async def test_queue_and_summary_read_both_collections_within_scope(soc_db):
    """protects=the queue lists the tenant's alerts from security_alerts and legacy alerts, active first
    then by severity, never merged rows or other tenants; the summary matches; fails_when=Alert
    Management and the console disagree; no_claim=-"""
    now = datetime.now(timezone.utc)
    recent = lambda h: (now - timedelta(hours=h)).isoformat()  # noqa: E731
    await soc_db.security_alerts.insert_many([
        _alert(id="low", severity="low", created_at=recent(1)),
        _alert(id="crit", severity="critical", created_at=recent(2)),
        _alert(id="done", status="closed", resolution="resolved", severity="critical", created_at=recent(1)),
        _alert(id="dup", status="merged", created_at=recent(1)),
        _alert(id="t2", tenantId="t2", severity="critical", created_at=recent(1)),
    ])
    await soc_db.alerts.insert_one({"id": "legacy", "tenantId": "t1", "severity": "High", "title": "Agent alert",
                                    "status": "open", "timestamp": recent(1)})
    await soc_db.agents.insert_one({"id": "ag1", "tenantId": "t1", "hostname": "pc-1", "lastSeen": recent(0)})
    page = await soc_service.alert_queue("t1", "all")
    assert [i["id"] for i in page["items"]] == ["crit", "legacy", "low", "done"] and page["total"] == 4
    assert page["items"][0]["hostname"] == "pc-1" and page["items"][1]["source"] == "legacy"
    summary = await soc_service.soc_summary("t1", "24h")
    assert summary["kpis"]["active"] == 3 and summary["kpis"]["newInRange"] == 4
    assert {t["type"] for t in summary["byType"]} == {"fim_violation", ""}
