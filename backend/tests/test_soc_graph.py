"""Investigation graph (soc_graph). protects/fails_when/no_claim per test; real MongoDB."""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_graph
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio
SHA = "ab" * 32


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


def _alert(i, agent, tenant="t1", **kw):
    return {"id": i, "tenantId": tenant, "agent_id": agent, "status": "open", "created_at": datetime.now(timezone.utc).isoformat(),
            "severity": "high", "title": f"alert {i}", **kw}


async def test_incident_graph_links_alerts_to_what_they_name_and_other_endpoints(db):
    """protects=host -> alerts -> user/process/file/IP/technique, and the same user and hash on another host of the
    tenant as pivots; another tenant's host with the same hash never appears; fails_when=pivots cross tenants or an
    alert's entities are lost; no_claim=layout (the UI's job)"""
    await db.agents.insert_many([{"id": "h1", "tenantId": "t1", "hostname": "web-1"}, {"id": "h2", "tenantId": "t1", "hostname": "db-1"},
                                 {"id": "h9", "tenantId": "t2", "hostname": "other"}])
    await db.soc_incidents.insert_one({"id": "SINC-1", "tenantId": "t1", "agentId": "h1", "status": "open"})
    await db.security_alerts.insert_many([
        _alert("a1", "h1", incidentId="SINC-1", type="malware_detected", path="C:\\Temp\\evil.exe", sha256=SHA,
               metadata={"user": "Alice"}, remote_ip="45.33.32.156", description="MITRE T1059.001"),
        _alert("a2", "h1", incidentId="SINC-1", type="runtime_security",
               description="Process 'mimikatz.exe' (PID 7) matches suspicious pattern 'mimikatz'"),
        _alert("a3", "h2", sha256=SHA, metadata={"user": "alice"}),
        _alert("a9", "h9", tenant="t2", sha256=SHA),
    ])
    g = await soc_graph.incident_graph(db, "t1", "SINC-1")
    ids = {n["id"] for n in g["nodes"]}
    assert {"host:h1", "alert:a1", "alert:a2", "user:alice", "process:mimikatz.exe", f"file:{SHA}", "ip:45.33.32.156",
            "technique:T1059.001", "technique:T1003", "host:h2"} <= ids
    assert "host:h9" not in ids
    pivots = {(e["from"], e["to"]) for e in g["edges"] if e["label"].startswith("also seen")}
    assert pivots == {("user:alice", "host:h2"), (f"file:{SHA}", "host:h2")}
    assert next(n for n in g["nodes"] if n["id"] == "host:h1")["label"] == "web-1"


async def test_alert_graph_is_its_incidents_graph_with_the_alert_marked(db):
    """protects=an alert with an incident shows that incident's graph with focus on it; one without shows itself;
    another tenant's alert is 404; fails_when=the alert graph loses its incident or leaks across scopes; no_claim=-"""
    await db.soc_incidents.insert_one({"id": "SINC-1", "tenantId": "t1", "agentId": "h1", "status": "open"})
    await db.security_alerts.insert_many([_alert("a1", "h1", incidentId="SINC-1"), _alert("a2", "h1", incidentId="SINC-1"),
                                          _alert("solo", "h1", path="/etc/passwd", type="fim_violation")])
    g = await soc_graph.alert_graph(db, "t1", "a2")
    assert g["incidentId"] == "SINC-1" and g["focus"] == "alert:a2" and g["alerts"] == 2
    assert next(n for n in g["nodes"] if n["id"] == "alert:a2")["focus"] is True
    solo = await soc_graph.alert_graph(db, "t1", "solo")
    assert solo["incidentId"] is None and {"file:/etc/passwd", "technique:T1565.001"} <= {n["id"] for n in solo["nodes"]}
    with pytest.raises(soc_graph.GraphError):
        await soc_graph.alert_graph(db, "t2", "a1")


async def test_big_incident_keeps_the_worst_alerts_and_says_it_was_cut(db):
    """protects=at most MAX_ALERTS alerts, the critical one kept, truncated set; fails_when=an unbounded graph or the
    worst alert dropped; no_claim=-"""
    await db.soc_incidents.insert_one({"id": "SINC-1", "tenantId": "t1", "agentId": "h1", "status": "open"})
    rows = [_alert(f"a{i}", "h1", incidentId="SINC-1", severity="low") for i in range(soc_graph.MAX_ALERTS + 5)]
    rows.append(_alert("worst", "h1", incidentId="SINC-1", severity="critical"))
    await db.security_alerts.insert_many(rows)
    g = await soc_graph.incident_graph(db, "t1", "SINC-1")
    assert g["truncated"] and g["alerts"] == soc_graph.MAX_ALERTS and g["alertsTotal"] == len(rows)
    assert "alert:worst" in {n["id"] for n in g["nodes"]}
