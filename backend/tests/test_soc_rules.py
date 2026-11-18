"""SOC automation rules (soc_rules): what a rule may say, and what it does to a new alert.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB via tests/_mongo_test_db.py.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_alerts
import soc_rules
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


def _rule(**actions):
    return {"name": "Lab logins", "conditions": {"types": ["ueba_anomaly"], "text": "LOGIN"}, "actions": actions}


def test_a_rule_needs_a_condition_an_action_and_known_values():
    """protects=no rule can match every alert, do nothing, both close and open a case, or name unknown values;
    fails_when=a typo silently becomes a catch-all; no_claim=-"""
    for bad in ({"name": "x", "conditions": {}, "actions": {"close": "benign"}},
                {"name": "x", "conditions": {"text": "a"}, "actions": {}},
                {"name": "x", "conditions": {"text": "a"}, "actions": {"close": "benign", "openCase": True}},
                {"name": "x", "conditions": {"techniques": ["T12"]}, "actions": {"close": "benign"}},
                {"name": "x", "conditions": {"text": "a"}, "actions": {"suggestResponse": "rm -rf"}},
                {"name": "", "conditions": {"text": "a"}, "actions": {"close": "benign"}}):
        with pytest.raises(soc_rules.RuleError):
            soc_rules.clean(bad)
    ok = soc_rules.clean({"name": " Lab ", "conditions": {"techniques": ["t1003.001"], "severities": ["high"]}, "actions": {"notify": ["in_app"]}})
    assert ok["name"] == "Lab" and ok["conditions"]["techniques"] == ["T1003.001"]


def test_conditions_are_anded_and_lists_are_any_of():
    """protects=every given condition must hold, any value of a list may; text is case-insensitive over title and
    details; techniques come from the alert; fails_when=one matching field is enough; no_claim=-"""
    cond = soc_rules.clean({"name": "r", "conditions": {"types": ["a", "b"], "severities": ["high", "critical"], "text": "passwd"},
                            "actions": {"close": "benign"}})["conditions"]
    assert soc_rules.matches(cond, {"type": "b", "severity": "High", "title": "Change to /etc/PASSWD"})
    assert not soc_rules.matches(cond, {"type": "b", "severity": "medium", "title": "Change to /etc/passwd"})
    assert not soc_rules.matches(cond, {"type": "c", "severity": "high", "title": "passwd"})
    tech = soc_rules.clean({"name": "r", "conditions": {"techniques": ["T1003.001"]}, "actions": {"close": "benign"}})["conditions"]
    assert soc_rules.matches(tech, {"description": "MITRE: T1003.001 - LSASS"})


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def _new(db, **kw):
    return await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag1", "type": "ueba_anomaly", "severity": "medium",
                                              "title": "Unusual login time", "created_at": datetime.now(timezone.utc).isoformat(), **kw})


@pytest.mark.asyncio
async def test_rules_close_assign_raise_and_suggest_but_never_respond(db):
    """protects=a closing rule closes the new alert as the system (outside response times) and keeps it off
    incidents; assign/raise/suggest apply in rule order; the rule counts its match; no response is sent;
    fails_when=a rule sends an endpoint action or a later rule overrides the first close; no_claim=-"""
    await soc_rules.save(db, "t1", _rule(close="benign"), "ana")
    await soc_rules.save(db, "t1", {"name": "Second", "conditions": {"text": "login"}, "actions": {"close": "resolved", "assignTo": "bob"}}, "ana")
    closed = await _new(db)
    assert (closed["status"], closed["resolution"], closed["autoClosed"], closed["assignee"]) == ("closed", "benign", True, "bob")
    assert [r["name"] for r in closed["rules"]] == ["Lab logins", "Second"] and not closed.get("incidentId")
    raised = await _new(db, type="fim_violation", title="Change", severity="low")
    assert not raised.get("rules")
    await soc_rules.save(db, "t1", {"name": "FIM", "conditions": {"types": ["fim_violation"]},
                                    "actions": {"raiseTo": "critical", "suggestResponse": "isolate_host"}}, "ana")
    raised = await _new(db, type="fim_violation", title="Change", severity="low")
    assert raised["severity"] == "critical" and raised["suggestedResponse"] == {"action": "isolate_host", "rule": "FIM"}
    assert raised["incidentId"] and await db.agent_instructions.count_documents({}) == 0
    rules = {r["name"]: r for r in await soc_rules.list_rules(db, "t1")}
    assert rules["Lab logins"]["stats"]["matched"] == 1 and rules["FIM"]["stats"]["matched"] == 1


@pytest.mark.asyncio
async def test_notify_reaches_only_this_tenants_webhooks_and_admins(db, monkeypatch):
    """protects=webhooks are picked by the alert's tenant explicitly; admins get an in-app notice; fails_when=a
    platform-context alert is sent to another tenant's webhook; no_claim=delivery over the network"""
    sent, posted = [], []

    async def fake_send(self, client, hook, payload, raw):
        sent.append((hook["id"], payload["data"]["id"]))
    monkeypatch.setattr("webhook_service.WebhookService._send_single_webhook", fake_send)

    async def fake_post(raw, tenant, title, message, severity, metadata):
        posted.append((tenant["id"], title))
    monkeypatch.setattr("pending_agents.post_to_recipients", fake_post)
    await db.webhooks.insert_many([
        {"id": "h1", "tenantId": "t1", "status": "Active", "events": ["soc.rule_match"], "url": "https://t1.example"},
        {"id": "h2", "tenantId": "t2", "status": "Active", "events": ["soc.rule_match"], "url": "https://t2.example"},
    ])
    await soc_rules.save(db, "t1", _rule(notify=["in_app", "webhook"]), "ana")
    alert = await _new(db)
    assert sent == [("h1", alert["id"])] and posted == [("t1", "SOC rule “Lab logins” matched")]


@pytest.mark.asyncio
async def test_rules_belong_to_one_tenant_and_preview_counts_past_alerts(db):
    """protects=a tenant lists, edits and deletes only its rules; the preview counts the last week's matches;
    fails_when=another tenant's rule is changed or applied; no_claim=-"""
    mine = await soc_rules.save(db, "t1", _rule(close="benign"), "ana")
    with pytest.raises(soc_rules.RuleError) as other:
        await soc_rules.save(db, "t2", _rule(close="resolved"), "eve", mine["id"])
    assert other.value.status == 404 and await soc_rules.list_rules(db, "t2") == []
    await soc_rules.save(db, "t1", {**_rule(close="benign"), "enabled": False}, "ana", mine["id"])
    plain = await _new(db)
    assert plain["status"] == "open"
    preview = await soc_rules.preview(db, "t1", {"conditions": {"text": "login"}})
    assert preview["matched"] == 1 and preview["examples"][0]["id"] == plain["id"]
    await soc_rules.delete(db, "t1", mine["id"])
    assert await soc_rules.list_rules(db, "t1") == []
