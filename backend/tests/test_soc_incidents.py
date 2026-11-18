"""SOC incidents (soc_incidents, migration 037): grouping an endpoint's alerts, and what analysts do to them.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Real MongoDB via tests/_mongo_test_db.py.
"""
import asyncio
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_actions
import soc_alerts
import soc_incidents
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio
T0 = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
ANALYST = SimpleNamespace(username="ana@t1.test", role="tenant_admin", tenant_id="t1")
migration = importlib.import_module("migrations.037_soc_incidents")


def _at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


async def _record(db, minutes, agent="ag1", severity="medium", **kw):
    return await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": agent, "type": kw.pop("type", "ueba_anomaly"),
                                              "severity": severity, "title": kw.pop("title", f"alert at {minutes}"),
                                              "created_at": _at(minutes), **kw})


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    await soc_incidents.ensure_indexes(mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def test_alerts_less_than_an_hour_apart_share_an_incident(db):
    """protects=same endpoint within the hour -> one incident (count, worst severity, tactics in attack order);
    an hour of quiet or another endpoint -> a new one; fails_when=alerts scatter or an endpoint's day becomes
    one endless incident; no_claim=-"""
    a = await _record(db, 0, description="MITRE: T1003.001")
    b = await _record(db, 40, severity="critical", description="initial T1566 phishing")
    c = await _record(db, 100 + 1)          # 61 minutes after b: a new incident
    d = await _record(db, 41, agent="ag2")
    assert a["incidentId"] == b["incidentId"] != c["incidentId"] and d["incidentId"] not in (a["incidentId"], c["incidentId"])
    inc = await soc_incidents.get_incident(db, "t1", a["incidentId"])
    assert inc["alertCount"] == 2 and inc["severity"] == "critical"
    assert inc["tactics"] == ["Initial Access", "Credential Access"]
    assert inc["title"] == "alert at 40 and 1 more" and [x["id"] for x in inc["timeline"]] == [a["id"], b["id"]]
    assert (await db.soc_incidents.find_one({"id": a["incidentId"]}))["grouping"] is False


async def test_racing_alerts_open_one_incident_and_repeats_do_not_count(db):
    """protects=two alerts arriving together on one endpoint end on one incident (unique grouping index);
    a repeat of an alert does not add to the incident; fails_when=a race splits the incident; no_claim=-"""
    first, second = await asyncio.gather(_record(db, 0), _record(db, 1))
    assert first["incidentId"] == second["incidentId"]
    await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag1", "type": "shadow_ai_process", "title": "x",
                                       "created_at": _at(2)}, group="g")
    await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag1", "type": "shadow_ai_process", "title": "x",
                                       "created_at": _at(3)}, group="g")
    assert (await db.soc_incidents.find_one({"id": first["incidentId"]}))["alertCount"] == 3


async def test_closing_an_incident_can_close_its_alerts_and_stops_grouping(db):
    """protects=close records who/why, closes its active alerts when asked, and the next alert opens a new
    incident; another tenant cannot touch it; a case collects its alerts once; fails_when=closing leaves the
    incident collecting or crosses tenants; no_claim=-"""
    a = await _record(db, 0)
    await _record(db, 10)
    token = set_tenant_id("t2")
    try:
        with pytest.raises(soc_actions.ActionError) as other:
            await soc_incidents.act("t2", a["incidentId"], "acknowledge", ANALYST)
        assert other.value.status == 404
    finally:
        reset_tenant_id(token)
    case = await soc_incidents.open_case("t1", a["incidentId"], ANALYST)
    again = await soc_incidents.open_case("t1", a["incidentId"], ANALYST)
    assert case["created"] and not again["created"] and len(case["case"]["relatedEvents"]) == 2
    out = await soc_incidents.act("t1", a["incidentId"], "close", ANALYST, resolution="benign", note="night shift", close_alerts=True)
    assert out["status"] == "closed" and out["resolution"] == "benign" and out["closedAlerts"] == 2
    assert {x["status"] for x in out["timeline"]} == {"closed"}
    later = await _record(db, 20)
    assert later["incidentId"] != a["incidentId"]


async def test_migration_groups_stored_alerts_once(db):
    """protects=existing alerts are grouped per endpoint by the hour rule, endpoint ids are lifted from
    metadata, an all-closed group is closed with its most common resolution, and a second run changes
    nothing; fails_when=re-running doubles incidents or no-endpoint alerts share one; no_claim=-"""
    await db.security_alerts.insert_many([
        {"id": "x1", "tenantId": "t1", "agent_id": "ag1", "severity": "high", "status": "closed", "resolution": "benign", "created_at": _at(0)},
        {"id": "x2", "tenantId": "t1", "agent_id": "ag1", "severity": "low", "status": "closed", "resolution": "benign", "created_at": _at(30)},
        {"id": "x3", "tenantId": "t1", "agent_id": "ag1", "severity": "low", "status": "open", "created_at": _at(200)},
        {"id": "p1", "tenantId": "t1", "metadata": {"agent_id": "gone-1"}, "severity": "high", "status": "open", "created_at": _at(5)},
        {"id": "p2", "tenantId": "t1", "metadata": {"agent_id": "gone-2"}, "severity": "high", "status": "open", "created_at": _at(6)},
        {"id": "m1", "tenantId": "t1", "agent_id": "ag1", "severity": "high", "status": "merged", "created_at": _at(1)},
    ])
    await migration.up(db)
    first = sorted([(i["agentId"], i["alertCount"], i["status"], i.get("resolution")) for i in await db.soc_incidents.find({}, {"_id": 0}).to_list(10)])
    await migration.up(db)
    assert await db.soc_incidents.count_documents({}) == 4
    assert first == [("ag1", 1, "open", None), ("ag1", 2, "closed", "benign"), ("gone-1", 1, "open", None), ("gone-2", 1, "open", None)]
    assert (await db.security_alerts.find_one({"id": "m1"})).get("incidentId") is None
