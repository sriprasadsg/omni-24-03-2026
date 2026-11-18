"""One-click response from a SOC alert (soc_response) and the gate's "analyst" origin.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB via tests/_mongo_test_db.py (point MONGO_TEST_URL
at a private mongod, never the live one).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_response
from autonomous_ops import STAMP_SOURCE, gate
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio

ACTOR = {"username": "ana@t1.test", "display": "Ana", "tier": "tenant"}
USER = type("U", (), {"username": "ana@t1.test", "role": "tenant_admin", "tenant_id": "t1"})()
SHA = "a" * 64
TOKENS = ["block_ip_ttl", "quarantine_file", "unquarantine_file", "kill_process_exe", "isolate_host", "restore_host"]


def _agent(agent_id="ag1", tenant="t1", **kw):
    doc = {"id": agent_id, "tenantId": tenant, "hostname": f"pc-{agent_id}", "status": "Online", "platform": "windows",
           "lastSeen": datetime.now(timezone.utc).isoformat(), "meta": {"response_actions": {"v": 1, "tokens": TOKENS}}}
    doc.update(kw)
    return doc


def _alert(alert_id="al1", **kw):
    doc = {"id": alert_id, "tenantId": "t1", "agent_id": "ag1", "type": "malware_detected", "severity": "critical",
           "title": "Malware on pc-ag1", "status": "open", "created_at": datetime.now(timezone.utc).isoformat(),
           "target": "C:\\Users\\bob\\Downloads\\evil.exe", "sha256": SHA, "metadata": {"remote_ip": "45.33.32.156"}}
    doc.update(kw)
    return doc


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    await mongo_db.tenants.insert_many([{"id": "t1", "name": "T1", "agentCapabilities": ["remediation_executor"]},
                                        {"id": "t2", "name": "T2", "agentCapabilities": ["remediation_executor"]}])
    await mongo_db.agents.insert_many([_agent(), _agent("srv", "platform-admin")])
    token = set_tenant_id("t1")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def test_options_follow_the_alert_evidence_and_the_endpoint(db):
    """protects=an action is offered only when the alert names what it needs and the endpoint can do it now;
    kill needs pid + start time + program; the platform's own computers and removed endpoints get none;
    fails_when=a button would send an action built from guesses; no_claim=the agent's own checks"""
    await db.security_alerts.insert_many([
        _alert(), _alert("plat", tenantId="platform-admin", agent_id="srv"), _alert("gone", agent_id="removed"),
        _alert("sys", target="C:\\Windows\\System32\\drivers\\evil.sys"),
    ])
    out = await soc_response.options("t1", "al1")
    by = {o["action"]: o for o in out["options"]}
    assert by["isolate_host"]["available"] and by["quarantine_file"]["available"] and by["block_ip"]["available"]
    assert not by["kill_process"]["available"] and "start time" in by["kill_process"]["reason"]
    assert by["block_ip"]["target"]["ip"] == "45.33.32.156" and out["host"] == "pc-ag1"
    token = set_tenant_id("platform-admin")  # a Super Admin's own view
    try:
        plat = await soc_response.options(None, "plat")
    finally:
        reset_tenant_id(token)
    assert not any(o["available"] for o in plat["options"]) and "platform" in plat["options"][0]["reason"]
    gone = await soc_response.options("t1", "gone")
    assert gone["options"][0]["reason"] == "The endpoint is no longer enrolled."
    protected = {o["action"]: o for o in (await soc_response.options("t1", "sys"))["options"]}
    assert not protected["quarantine_file"]["available"] and "protected" in protected["quarantine_file"]["reason"]
    token = set_tenant_id("t2")
    try:
        with pytest.raises(soc_response.ResponseError) as other:
            await soc_response.options("t2", "al1")
    finally:
        reset_tenant_id(token)
    assert other.value.status == 404


async def test_isolate_is_approved_by_the_click_and_reaches_the_agent_with_autonomy_off(db):
    """protects=with Autonomous Ops never switched on for the tenant, an analyst's isolate is recorded with the
    person as approver, written as one stamped instruction and acknowledges the alert; a second click is a
    duplicate; fails_when=the analyst path needs Autonomous Ops on, skips the ledger, or sends twice;
    no_claim=the agent carries it out"""
    await db.security_alerts.insert_one(_alert())
    out = await soc_response.respond("t1", "al1", "isolate_host", ACTOR, USER)
    assert out["status"] == "dispatched"
    row = await db.autonomy_actions.find_one({"id": out["actionId"]}, {"_id": 0})
    assert row["origin"] == gate.ANALYST_ORIGIN and row["state"] == "dispatching"
    assert row["approval"]["approver"]["username"] == "ana@t1.test" and row["reason"]["inputs"]["alertId"] == "al1"
    instr = await db.agent_instructions.find_one({"agent_id": "ag1"}, {"_id": 0})
    assert instr["type"] == "isolate_host" and instr["triggered_by"] == STAMP_SOURCE
    assert instr["autonomy"]["actionId"] == out["actionId"]
    alert = await db.security_alerts.find_one({"id": "al1"})
    assert alert["status"] == "acknowledged" and alert["acknowledgedBy"] == "Ana"
    with pytest.raises(soc_response.ResponseError):
        await soc_response.respond("t1", "al1", "isolate_host", ACTOR, USER)
    assert await db.agent_instructions.count_documents({}) == 1
    history = (await soc_response.options("t1", "al1"))["history"]
    assert [h["action"] for h in history] == ["isolate_host"] and history[0]["requestedBy"] == "Ana"


async def test_block_and_quarantine_carry_only_the_alerts_own_values(db):
    """protects=a block names the alert's IP and the chosen length; a quarantine the alert's path and hash;
    an offline endpoint is refused; fails_when=parameters come from the request or a block has no expiry;
    no_claim=-"""
    await db.security_alerts.insert_one(_alert())
    with pytest.raises(soc_response.ResponseError) as no_ttl:
        await soc_response.respond("t1", "al1", "block_ip", ACTOR, USER)
    assert no_ttl.value.status == 400
    await soc_response.respond("t1", "al1", "block_ip", ACTOR, USER, ttl="1h")
    await soc_response.respond("t1", "al1", "quarantine_file", ACTOR, USER)
    sent = {d["type"]: d["parameters"] for d in await db.agent_instructions.find({}, {"_id": 0}).to_list(5)}
    assert sent["block_ip"] == {"ip_address": "45.33.32.156", "ttl_seconds": 3600}
    assert sent["quarantine_file"] == {"path": "C:\\Users\\bob\\Downloads\\evil.exe", "sha256": SHA}
    await db.agents.update_one({"id": "ag1"}, {"$set": {"lastSeen": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}})
    await db.security_alerts.insert_one(_alert("al2", sha256="b" * 64))
    with pytest.raises(soc_response.ResponseError) as offline:
        await soc_response.respond("t1", "al2", "quarantine_file", ACTOR, USER)
    assert "offline" in str(offline.value).lower() or "online" in str(offline.value).lower()


async def test_undo_and_keep_isolated_only_for_this_alerts_actions(db):
    """protects=Undo of an executed isolate sends restore_host; actions are found only through the alert that
    started them; fails_when=one alert can undo another alert's (or tenant's) action; no_claim=-"""
    await db.security_alerts.insert_many([_alert(), _alert("al2")])
    out = await soc_response.respond("t1", "al1", "isolate_host", ACTOR, USER)
    with pytest.raises(soc_response.ResponseError) as other:
        await soc_response.undo("t1", "al2", out["actionId"], ACTOR, USER)
    assert other.value.status == 404
    await db.autonomy_actions.update_one({"id": out["actionId"]}, {"$set": {"state": "executed"}})
    assert (await soc_response.options("t1", "al1"))["history"][0]["canUndo"] is True
    assert (await soc_response.undo("t1", "al1", out["actionId"], ACTOR, USER))["status"] == "undone"
    types = [d["type"] for d in await db.agent_instructions.find({}, {"_id": 0}).sort("created_at", 1).to_list(5)]
    assert types == ["isolate_host", "restore_host"]


async def test_the_sweep_origin_still_needs_autonomy_switched_on(db):
    """protects=only the analyst origin skips the tenant switch and level; fails_when=the change lets
    automatic requests act for a tenant that never switched Autonomous Ops on; no_claim=-"""
    decision = await gate.decide(db, gate.ActionRequest(
        tenant_id="t1", kind="security", origin="sweep", actions=["isolate_host"], targets=["ag1"], params={},
        dedupe_key="t1|sweep|iso|ag1", dispatcher="security_response"))
    assert decision.outcome == "refuse" and decision.reason == "not_enabled" and not decision.recorded
