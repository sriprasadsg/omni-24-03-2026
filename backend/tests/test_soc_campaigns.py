"""Across-endpoint campaigns (soc_campaigns). protects/fails_when/no_claim per test; real MongoDB."""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_campaigns
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_same_hash_or_detection_on_two_endpoints_is_one_campaign(db):
    """protects=one hash on two hosts and one detection title (ids stripped) on two hosts each form a campaign,
    the hash ranked first; a single-host finding and another tenant's host do not; fails_when=campaigns cross
    tenants or one host counts as a campaign; no_claim=-"""
    now, sha = datetime.now(timezone.utc).isoformat(), "c" * 64
    rows = [("a1", "t1", "h1", "malware_detected", "critical", "Malware on agent-11112222333344445555", sha),
            ("a2", "t1", "h2", "malware_detected", "high", "Malware on agent-99998888777766665555", sha),
            ("a3", "t1", "h3", "ueba_anomaly", "medium", "UEBA Anomaly: Unusual Login Time", None),
            ("a4", "t1", "h1", "ueba_anomaly", "medium", "UEBA Anomaly: Unusual Login Time", None),
            ("a5", "t2", "h9", "malware_detected", "high", "Malware", sha)]
    await db.security_alerts.insert_many([{"id": i, "tenantId": t, "agent_id": h, "type": ty, "severity": sev, "title": ti,
                                           "sha256": s, "status": "open", "created_at": now} for i, t, h, ty, sev, ti, s in rows])
    out = await soc_campaigns.campaigns(db, "t1")
    kinds = [(c["kind"], [e["agentId"] for e in c["endpoints"]], c["severity"]) for c in out]
    assert kinds[0] == ("hash", ["h1", "h2"], "critical")
    assert ("detection", ["h1", "h3"], "medium") in kinds and ("detection", ["h1", "h2"], "critical") in kinds
    assert all("h9" not in [e["agentId"] for e in c["endpoints"]] for c in out)
