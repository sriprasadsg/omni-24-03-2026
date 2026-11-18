"""ATT&CK coverage (soc_mitre) and detection techniques (mitre_service). protects/fails_when/no_claim per test."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import mitre_service
import soc_mitre
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.parametrize("doc,expected", [
    ({"type": "persistence_mechanism", "location": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce"}, ["T1547.001"]),
    ({"type": "persistence_mechanism", "location": "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"}, ["T1547.004"]),
    ({"type": "persistence_mechanism", "location": "Windows Task Scheduler"}, ["T1053.005"]),
    ({"type": "persistence_mechanism", "location": "/etc/systemd/system/x.service"}, ["T1543.002"]),
    ({"type": "persistence_mechanism", "location": "/root/.bashrc"}, ["T1546.004"]),
    ({"type": "runtime_security", "description": "Process 'mimikatz.exe' (PID 7) matches suspicious pattern 'mimikatz'"}, ["T1003"]),
    ({"type": "runtime_security", "description": "Process 'certutil.exe' (PID 7) matches suspicious pattern 'certutil' (outside system directory: C:\\x)"}, ["T1036"]),
    ({"type": "runtime_security", "description": "YARA Match (executable)"}, []),
    ({"type": "ueba_anomaly", "title": "UEBA Anomaly: Unusual Login Time"}, ["T1078"]),
    ({"type": "fim_violation"}, ["T1565.001"]),
    ({"type": "shadow_ai_process", "title": "Unapproved AI process: ollama"}, []),
])
def test_detection_techniques_follow_what_the_agent_reported(doc, expected):
    """protects=each built-in detection maps to the technique of what it reported, unknown reports to none;
    fails_when=a YARA hit or an AI process is labelled with a technique it does not show; no_claim=-"""
    assert mitre_service.detection_techniques(doc) == expected


@pytest.mark.asyncio
async def test_coverage_counts_endpoint_checks_rules_and_alerts_separately(db):
    """protects=a technique is "detected" only where an endpoint runs the check; a SIEM-rule-only technique is
    "rule" and never covered; seen counts the range's alerts (sub-techniques roll up); another tenant's agents and
    alerts do not count; tactics come in ATT&CK order; fails_when=rules or other tenants inflate coverage; no_claim=-"""
    await db.agents.insert_many([
        {"id": "h1", "tenantId": "t1", "hostname": "h1", "status": "Online", "availableCapabilities": ["fim", "persistence_detection"]},
        {"id": "h2", "tenantId": "t1", "hostname": "h2", "status": "Online", "availableCapabilities": ["fim"]},
        {"id": "h9", "tenantId": "t2", "hostname": "h9", "status": "Online", "availableCapabilities": ["ueba"]},
    ])
    await db.siem_rules.insert_many([
        {"tenant_id": "platform-admin", "name": "Kerberoasting", "enabled": True, "mitre_technique": "T1558.003 — Kerberoasting"},
        {"tenant_id": "t2", "name": "Other tenant rule", "enabled": True, "mitre_technique": "T1190"},
    ])
    recent, old = (NOW - timedelta(days=2)).isoformat(), (NOW - timedelta(days=60)).isoformat()
    await db.security_alerts.insert_many([
        {"id": "a1", "tenantId": "t1", "type": "persistence_mechanism", "location": "Windows Task Scheduler", "status": "open", "created_at": recent},
        {"id": "a2", "tenantId": "t1", "type": "fim_violation", "status": "closed", "created_at": recent},
        {"id": "a3", "tenantId": "t1", "type": "fim_violation", "status": "open", "created_at": old},
        {"id": "a9", "tenantId": "t2", "type": "fim_violation", "status": "open", "created_at": recent},
    ])
    out = await soc_mitre.coverage(db, "t1", "30d", now=NOW)
    cells = {t["id"]: t for tac in out["tactics"] for t in tac["techniques"]}
    assert cells["T1565"]["level"] == "detected" and cells["T1565"]["seen"] == 1 and cells["T1565"]["active"] == 0
    assert cells["T1565"]["subTechniques"] == ["T1565.001"]
    assert next(d for d in cells["T1565"]["detections"])["endpoints"] == 2
    assert cells["T1053"]["level"] == "detected" and cells["T1053"]["seen"] == 1 and cells["T1053"]["active"] == 1
    assert cells["T1078"]["level"] == "none"            # ueba runs only on the other tenant's endpoint
    assert cells["T1558"]["level"] == "rule" and cells["T1558"]["rules"][0]["library"] is True
    assert cells["T1190"]["level"] == "none"            # the other tenant's rule
    assert [t["id"] for t in out["tactics"]][:3] == ["TA0043", "TA0042", "TA0001"]
    assert out["endpoints"] == 2 and out["siemLogs"] == 0
    assert out["totals"]["detected"] == sum(t["level"] == "detected" for t in cells.values())


@pytest.mark.asyncio
async def test_a_technique_outside_the_matrix_goes_under_other(db):
    """protects=an alert naming T1611 (not in the embedded matrix, no parent there) is shown under Other;
    fails_when=an unknown technique vanishes from the map; no_claim=-"""
    await db.security_alerts.insert_one({"id": "a1", "tenantId": "t1", "type": "x", "status": "open",
                                         "description": "container escape T1611", "created_at": (NOW - timedelta(hours=1)).isoformat()})
    out = await soc_mitre.coverage(db, "t1", "24h", now=NOW)
    other = next(t for t in out["tactics"] if t["id"] == "other")
    assert other["techniques"][0]["id"] == "T1611" and other["techniques"][0]["seen"] == 1
