"""SOC hunting (soc_hunt, migration 040). protects/fails_when/no_claim per test; real MongoDB.

Events mirror what siem_pipeline stores from this server's auth.log on 2026-11-18 (internet SSH probes).
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import siem_pipeline
import soc_hunt
import soc_service
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)
FAILED = {"source": "events", "filters": [{"field": "source", "op": "eq", "value": "linux_auth"},
                                          {"field": "action", "op": "eq", "value": "login_failed"}],
          "range": "24h", "countBy": "srcIp"}


def _event(tenant, minutes_ago, ip, user="admin", action="login_failed", agent="ag1"):
    at = NOW - timedelta(minutes=minutes_ago)
    return {"tenantId": tenant, "agentId": agent, "host": "Omniai-copy", "source": "linux_auth", "action": action,
            "outcome": "failure", "user": user, "srcIp": ip, "process": "sshd", "at": at, "timestamp": at.isoformat(),
            "message": f"Invalid user {user} from {ip} port 13712", "key": f"k|{tenant}|{minutes_ago}|{ip}|{user}"}


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    await mongo_db.agents.insert_one({"id": "ag1", "tenantId": "t1", "hostname": "Omniai-copy"})
    await mongo_db.soc_log_events.insert_many(
        [_event("t1", m, "2.57.121.25") for m in (1, 2, 3, 4)] + [_event("t1", 5, "35.187.231.181", user="root")]
        + [_event("t1", 60 * 30, "2.57.121.25")]  # 30 hours ago: outside 24h
        + [_event("t1", 6, "2.57.121.25", action="sudo_command", user="azureuser")]
        + [_event("t2", 1, "9.9.9.9", agent="ag2")])
    await mongo_db.security_alerts.insert_many([
        {"id": "a1", "tenantId": "t1", "agent_id": "ag1", "type": "ueba_anomaly", "severity": "high", "status": "open",
         "title": "Unusual sign-in for root (3.1 sigma)", "created_at": (NOW - timedelta(hours=1)).isoformat()},
        {"id": "a2", "tenantId": "t1", "agent_id": "ag1", "type": "ueba_anomaly", "severity": "high", "status": "merged",
         "title": "Unusual sign-in for root", "created_at": (NOW - timedelta(hours=1)).isoformat()},
        {"id": "a3", "tenantId": "t1", "agent_id": "ag1", "type": "shadow_ai_process", "severity": "medium",
         "status": "closed", "title": "ollama.exe axb", "created_at": (NOW - timedelta(hours=2)).isoformat()},
    ])
    await mongo_db.logs.insert_many([
        {"tenantId": "t1", "agentId": "ag1", "service": "auth", "severity": "INFO", "timestamp": (NOW - timedelta(minutes=m)).isoformat(),
         "message": f"2026-11-18T15:00:00+00:00 Omniai-copy CRON[{m}]: pam_unix(cron:session): session closed for user root"}
        for m in (1, 2, 3)])
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.parametrize("query,message", [
    ({"source": "mail"}, "source must be"),
    ({"source": "events", "filters": [{"field": "$where", "op": "eq", "value": "1"}]}, "Unknown field"),
    ({"source": "events", "filters": [{"field": "tenantId", "op": "eq", "value": "t2"}]}, "Unknown field"),
    ({"source": "events", "filters": [{"field": "user", "op": "$ne", "value": "x"}]}, "op must be"),
    ({"source": "events", "filters": [{"field": "user", "op": "regex", "value": "(a"}]}, "not valid"),
    ({"source": "events", "filters": [{"field": "eventId", "op": "eq", "value": "abc"}]}, "takes a number"),
    ({"source": "events", "filters": [{"field": "user", "op": "eq", "value": "a"}] * 11}, "at most 10"),
    ({"source": "events", "range": "1y"}, "range must be"),
    ({"source": "alerts", "countBy": "srcIp"}, "Cannot count"),
])
def test_a_hunt_names_only_known_fields_ops_and_ranges(query, message):
    """protects=fields come from each source's list, ops and ranges from theirs, a pattern must compile, a tenant
    user cannot filter by organization; fails_when=a hunt reaches a Mongo operator, another tenant or any field;
    no_claim=-"""
    with pytest.raises(soc_hunt.HuntError, match=message):
        soc_hunt.normalize(query)


@pytest.mark.asyncio
async def test_a_hunt_counts_what_a_direct_count_counts_inside_the_tenant(db):
    """protects=the total equals count_documents over the tenant, range and filters; groups count by a field; other
    tenants and older rows stay out; fails_when=the console shows a number the database does not hold, or t2's
    events; no_claim=-"""
    out = await soc_hunt.run(db, "t1", FAILED, now=NOW)
    direct = await db.soc_log_events.count_documents({"tenantId": "t1", "source": "linux_auth", "action": "login_failed",
                                                      "at": {"$gte": NOW - timedelta(hours=24)}})
    assert out["total"] == direct == 5
    assert out["groups"] == [{"value": "2.57.121.25", "count": 4}, {"value": "35.187.231.181", "count": 1}]
    assert out["groupCount"] == 2 and {r["srcIp"] for r in out["rows"]} == {"2.57.121.25", "35.187.231.181"}
    assert out["rows"][0]["hostname"] == "Omniai-copy" and out["rows"][0]["time"].startswith("2026-11-18T15:59")
    week = await soc_hunt.run(db, "t1", {**FAILED, "range": "7d"}, now=NOW)
    assert week["total"] == 6
    everyone = await soc_hunt.run(db, None, {**FAILED, "filters": FAILED["filters"][:1], "countBy": "tenantId"}, now=NOW)
    assert {g["value"]: g["count"] for g in everyone["groups"]} == {"t1": 6, "t2": 1}


@pytest.mark.asyncio
async def test_text_and_contains_are_matched_literally_and_patterns_only_when_asked(db):
    """protects=free text and contains are escaped, case-insensitive; matches takes a pattern; merged alerts stay
    hidden as in the queue; fails_when='a.b' matches 'axb' or a typed regex runs as text; no_claim=-"""
    alerts = {"source": "alerts", "range": "24h"}
    assert (await soc_hunt.run(db, "t1", alerts, now=NOW))["total"] == 2  # a2 is merged
    assert (await soc_hunt.run(db, "t1", {**alerts, "text": "ollama.exe"}, now=NOW))["total"] == 1
    assert (await soc_hunt.run(db, "t1", {**alerts, "text": "a.b"}, now=NOW))["total"] == 0
    assert (await soc_hunt.run(db, "t1", {**alerts, "filters": [{"field": "title", "op": "regex", "value": "a.b"}]}, now=NOW))["total"] == 1
    root = await soc_hunt.run(db, "t1", {**alerts, "filters": [{"field": "title", "op": "contains", "value": "ROOT"},
                                                                {"field": "status", "op": "ne", "value": "closed"}]}, now=NOW)
    assert [r["id"] for r in root["rows"]] == ["a1"]
    logs = await soc_hunt.run(db, "t1", {"source": "logs", "text": "session closed", "countBy": "agentId"}, now=NOW)
    assert logs["total"] == 3 and logs["groups"] == [{"value": "ag1", "count": 3, "label": "Omniai-copy"}]


@pytest.mark.asyncio
async def test_the_tenant_database_wrapper_runs_hunts_unchanged(db):
    """protects=count, find with a time limit and aggregate pass through TenantIsolatedDatabase, whose tenant
    context wins over the hunt's scope; fails_when=a hunt breaks on the live wrapper or reads past its tenant;
    no_claim=-"""
    wrapped = database.TenantIsolatedDatabase(db)
    token = set_tenant_id("t2")
    try:
        out = await soc_hunt.run(wrapped, "t2", {**FAILED, "countBy": "agentId"}, now=NOW)
    finally:
        reset_tenant_id(token)
    assert out["total"] == 1 and out["groups"][0]["value"] == "ag2"


@pytest.mark.asyncio
async def test_a_saved_hunt_reruns_with_its_count_and_stays_with_its_organization(db):
    """protects=a rerun records time and total, equal to a direct count; another tenant cannot run, change or remove
    it; the console counts saved hunts, not seeded templates; fails_when=hunts leak or the count is stale;
    no_claim=-"""
    hunt = await soc_hunt.save(db, "t1", {"name": "SSH failures by address", "query": FAILED}, "ana@t1")
    again = await soc_hunt.rerun(db, "t1", hunt["id"], now=NOW)
    assert again["total"] == 5 and again["hunt"]["lastCount"] == 5 and again["hunt"]["runCount"] == 1
    stored = await db.soc_hunts.find_one({"id": hunt["id"]})
    assert stored["lastCount"] == 5 and stored["lastRunAt"] == NOW.isoformat()
    for call in (soc_hunt.rerun(db, "t2", hunt["id"]), soc_hunt.delete(db, "t2", hunt["id"]),
                 soc_hunt.save(db, "t2", {"name": "x", "query": FAILED}, "eve@t2", hunt["id"])):
        with pytest.raises(soc_hunt.HuntError, match="not found"):
            await call
    await db.xdr_hunts.insert_one({"id": "hunt-phishing", "tenantId": "global", "status": "active"})
    counts = await soc_service._counts(db, "t1")
    assert counts["savedHunts"] == 1 and "activeHunts" not in counts
    assert [h["id"] for h in await soc_hunt.list_hunts(db, "t2")] == []


@pytest.mark.asyncio
async def test_a_hunt_becomes_a_siem_rule_that_records_hits_for_its_tenant(db):
    """protects=exact filters become logic.match, count by becomes groupBy, the rule records for 7 days, runs on its
    tenant's events only; fails_when=the rule never runs, alerts on day one, or fires on another tenant;
    no_claim=the library rules"""
    hunt = await soc_hunt.save(db, "t1", {"name": "SSH failures by address", "query": FAILED}, "ana@t1")
    rule = await soc_hunt.to_rule(db, "t1", hunt["id"], {"count": 4, "windowMinutes": 10, "severity": "high"}, "ana@t1", now=NOW)
    assert rule["logSource"] == "linux_auth" and rule["logic"] == {"match": {"action": "login_failed"},
                                                                   "threshold": {"count": 4, "windowSeconds": 600, "groupBy": "srcIp"}}
    assert rule["tenant_id"] == "t1" and rule["mode"] == "record" and rule["severity"] == "High"
    assert (await db.soc_hunts.find_one({"id": hunt["id"]}))["ruleId"] == rule["id"]
    with pytest.raises(soc_hunt.HuntError, match="already has a rule"):
        await soc_hunt.to_rule(db, "t1", hunt["id"], {}, "ana@t1")
    events = await db.soc_log_events.find({"at": {"$gte": NOW - timedelta(hours=1)}}, {"_id": 0}).to_list(50)
    hits = await siem_pipeline.evaluate(db, events, now=NOW)
    mine = [h for h in hits if h["ruleId"] == rule["id"]]
    assert [(h["tenantId"], h["group"], h["count"], h["alerted"]) for h in mine] == [("t1", "2.57.121.25", 4, False)]
    assert await db.security_alerts.count_documents({"type": "siem_rule"}) == 0


@pytest.mark.parametrize("query,message", [
    ({"source": "alerts"}, "SIEM events"),
    ({**FAILED, "text": "admin"}, "free text"),
    ({**FAILED, "filters": FAILED["filters"][1:]}, "one log source"),
    ({**FAILED, "filters": FAILED["filters"][:1]}, "at least one filter"),
    ({**FAILED, "filters": FAILED["filters"] + [{"field": "user", "op": "contains", "value": "adm"}]}, "only 'equals'"),
])
def test_only_exact_event_hunts_can_become_rules(query, message):
    """protects=a rule gets only what siem_pipeline can run (one source, equals/any of); fails_when=a rule is saved
    that silently never matches or matches every event; no_claim=-"""
    with pytest.raises(soc_hunt.HuntError, match=message):
        soc_hunt.rule_logic(soc_hunt.normalize(query))


@pytest.mark.asyncio
async def test_the_field_catalogue_offers_this_tenants_values(db):
    """protects=the console's field lists show the tenant's own frequent values and which fields a rule can use;
    fails_when=a tenant sees another tenant's IPs; no_claim=-"""
    out = await soc_hunt.catalogue(db, "t1", now=NOW)
    ip = next(f for f in out["sources"]["events"]["fields"] if f["name"] == "srcIp")
    assert ip["values"] == ["2.57.121.25", "35.187.231.181"] and ip["ruleable"]
    assert "tenantId" not in {f["name"] for f in out["sources"]["alerts"]["fields"]}
    assert "tenantId" in {f["name"] for f in (await soc_hunt.catalogue(db, None, now=NOW))["sources"]["logs"]["fields"]}


@pytest.mark.asyncio
async def test_migration_040_adds_indexes_and_runs_twice(db):
    """protects=saved hunts get a unique id and logs a tenant/time index; a second run changes nothing;
    fails_when=startup fails on a rerun; no_claim=-"""
    migration = importlib.import_module("migrations.040_soc_hunts")
    await migration.up(db)
    await migration.up(db)
    assert "logs_tenant_time" in await db.logs.index_information()
    assert (await db.soc_hunts.index_information())["soc_hunt_id"]["unique"]
