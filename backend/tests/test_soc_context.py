"""SOC enrichment, risk scores and threat-intel feeds (soc_context, soc_threat_intel).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB via tests/_mongo_test_db.py; no network.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_alerts
import soc_context
import soc_service
import soc_threat_intel
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
BAD_IP = "45.33.32.156"


def _v(**kw):
    base = {"status": "open", "severity": "high", "occurrences": 1, "lastSeenAt": NOW.isoformat(), "threatIntel": []}
    return {**base, **kw}


def test_risk_follows_severity_importance_repeats_age_and_threat_intel():
    """protects=a critical alert on a critical endpoint outranks the same on a low one; repeats add a little,
    age discounts, a feed hit adds 20, closed is 0, the score stays in 0-100; fails_when=risk ignores the
    endpoint or a closed alert still ranks; no_claim=the weights are the right ones for every organization"""
    assert soc_context.risk(_v(severity="critical"), "critical", NOW) == 100
    assert soc_context.risk(_v(), "low", NOW) == 52 < soc_context.risk(_v(), None, NOW) == 65 < soc_context.risk(_v(), "high", NOW) == 78
    assert soc_context.risk(_v(occurrences=8), None, NOW) == 74
    old = (NOW - timedelta(days=3)).isoformat()
    assert soc_context.risk(_v(lastSeenAt=old), None, NOW) == 55
    assert soc_context.risk(_v(threatIntel=[{"source": "feodo"}]), None, NOW) == 85
    assert soc_context.risk(_v(status="closed"), "critical", NOW) == 0
    assert soc_context.combined([40, 65, 0, 20]) == 74 and soc_context.combined([]) == 0


def test_feeds_parse_only_well_formed_indicators():
    """protects=Feodo lines and ThreatFox items become ip/sha256/domain indicators, comments and junk are
    dropped; fails_when=a comment or a malformed value becomes an indicator; no_claim=the live feed format"""
    assert soc_threat_intel.parse_feodo("# header\n45.33.32.156\nnot-an-ip\n\n1.2.3.4\n") == [
        {"value": "45.33.32.156", "kind": "ip", "malware": "botnet C2 (Feodo Tracker)"},
        {"value": "1.2.3.4", "kind": "ip", "malware": "botnet C2 (Feodo Tracker)"}]
    tf = soc_threat_intel.parse_threatfox({"data": [
        {"ioc_type": "ip:port", "ioc": "8.8.4.4:443", "malware_printable": "Cobalt Strike"},
        {"ioc_type": "sha256_hash", "ioc": "A" * 64, "malware": "x"}, {"ioc_type": "md5_hash", "ioc": "b" * 32},
        {"ioc_type": "domain", "ioc": "Evil.Example."}, "junk"]})
    assert [(i["kind"], i["value"]) for i in tf] == [("ip", "8.8.4.4"), ("sha256", "a" * 64), ("domain", "evil.example")]


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    await mongo_db.agents.insert_many([{"id": "ag1", "tenantId": "t1", "hostname": "pc-1"}, {"id": "ag2", "tenantId": "t2", "hostname": "pc-2"}])
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_refresh_records_each_feed_and_says_when_a_key_is_needed(db, monkeypatch):
    """protects=Feodo is stored with an expiry, ThreatFox without ABUSECH_AUTH_KEY is reported as needing one
    (nothing invented), and a second refresh does not duplicate; fails_when=a missing key looks like an empty
    feed; no_claim=abuse.ch's servers"""
    monkeypatch.delenv("ABUSECH_AUTH_KEY", raising=False)

    class Resp:
        text = f"# Feodo\n{BAD_IP}\n"

        def raise_for_status(self):
            return None

    async def fake_get(self, url, **kw):
        return Resp()
    monkeypatch.setattr(soc_threat_intel.httpx.AsyncClient, "get", fake_get)
    out = await soc_threat_intel.refresh(db, NOW)
    await soc_threat_intel.refresh(db, NOW)
    assert out == {"feodo": 1, "threatfox": "needs ABUSECH_AUTH_KEY"}
    assert await db.ti_indicators.count_documents({}) == 1
    status = {f["source"]: f for f in (await soc_threat_intel.feed_status(db))["feeds"]}
    assert status["feodo"]["ok"] and status["threatfox"]["needsKey"] is True


@pytest.mark.asyncio
async def test_new_alert_is_matched_and_ranks_by_risk_with_endpoint_importance(db):
    """protects=a new alert naming a listed IP stores the hit; importance set for an endpoint changes the queue's
    risk order at once; context is tenant-scoped; fails_when=risk ignores importance or another tenant's
    endpoint can be set; no_claim=-"""
    await db.ti_indicators.insert_one({"value": BAD_IP, "source": "feodo", "kind": "ip", "malware": "botnet C2"})
    hit = await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag1", "type": "edr", "severity": "medium",
                                             "title": "Connection", "metadata": {"remote_ip": BAD_IP}})
    assert hit["threatIntel"][0]["source"] == "feodo"
    await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag3", "type": "edr", "severity": "high", "title": "Other"})
    page = await soc_service.alert_queue("t1", "active", sort="risk")
    assert [(a["title"], a["risk"]) for a in page["items"]] == [("Other", 65), ("Connection", 60)]   # medium 40 + feed hit 20
    await soc_context.set_context(db, "t1", "ag1", "critical", "IT desk", "ana")
    again = (await soc_service.alert_queue("t1", "active", sort="risk"))["items"]
    assert [(a["title"], a["risk"], a["importance"]) for a in again][0] == ("Connection", 76, "critical")
    with pytest.raises(soc_context.ContextError) as other:
        await soc_context.set_context(db, "t1", "ag2", "critical", None, "ana")
    assert other.value.status == 404
    ctx = await soc_context.alert_context(db, "t1", hit["id"])
    assert ctx["host"]["importance"] == "critical" and ctx["host"]["owner"] == "IT desk" and ctx["host"]["otherActiveAlerts"] == 0
    assert ctx["threatIntel"][0]["value"] == BAD_IP


def test_sla_due_times_and_breaches_follow_the_targets():
    """protects=an open critical alert past 15 min is overdue to acknowledge, an acknowledged one only counts its
    close target, a closed one has none; fails_when=acknowledged alerts stay overdue; no_claim=-"""
    t = {k: dict(v) for k, v in soc_context.SLA_DEFAULTS.items()}
    start = (NOW - timedelta(minutes=30)).isoformat()
    s = soc_context.sla_state({"status": "open", "severity": "critical", "createdAt": start}, t, NOW)
    assert s["ackBreached"] and not s["closeBreached"]
    s = soc_context.sla_state({"status": "acknowledged", "severity": "critical", "createdAt": start}, t, NOW)
    assert s["ackDue"] is None and not s["ackBreached"]
    assert soc_context.sla_state({"status": "closed", "createdAt": start}, t, NOW) is None


@pytest.mark.asyncio
async def test_sla_targets_are_per_tenant_and_checked(db):
    """protects=a tenant's targets are stored and read back, bad values refused; fails_when=a close target shorter
    than acknowledge is accepted; no_claim=-"""
    with pytest.raises(soc_context.ContextError):
        await soc_context.set_sla(db, "t1", {"acknowledge": {"high": 120}, "close": {"high": 60}}, "ana")
    await soc_context.set_sla(db, "t1", {"acknowledge": {"critical": 5}}, "ana")
    assert (await soc_context.sla_targets(db, "t1"))["acknowledge"]["critical"] == 5
    assert (await soc_context.sla_targets(db, "t2"))["acknowledge"]["critical"] == 15
