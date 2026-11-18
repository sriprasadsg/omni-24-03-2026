"""Tenant watchlists (soc_watchlist): checked values, retro-hunt of past alerts, matching of new ones.

protects/fails_when/no_claim cards per test. Real MongoDB via tests/_mongo_test_db.py.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import soc_alerts
import soc_watchlist
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    monkeypatch.setenv("SOC_AUTO_TRIAGE", "0")
    token = set_tenant_id("platform-admin")
    try:
        yield mongo_db
    finally:
        reset_tenant_id(token)


async def test_adding_retro_hunts_past_alerts_and_new_alerts_match(db):
    """protects=an added IP marks the tenant's past alerts naming it (not another tenant's), a domain matches text,
    a new alert matches at once, bad values and duplicates are refused; fails_when=retro-hunt crosses tenants or
    a typo is watched; no_claim=-"""
    now = datetime.now(timezone.utc).isoformat()
    await db.security_alerts.insert_many([
        {"id": "p1", "tenantId": "t1", "title": "conn", "metadata": {"remote_ip": "45.33.32.156"}, "created_at": now, "status": "open"},
        {"id": "p2", "tenantId": "t2", "title": "conn", "metadata": {"remote_ip": "45.33.32.156"}, "created_at": now, "status": "open"},
        {"id": "p3", "tenantId": "t1", "title": "DNS to Evil.Example seen", "created_at": now, "status": "open"},
    ])
    for bad in ("not a thing", "999.1.1.1"):
        with pytest.raises(soc_watchlist.WatchlistError):
            await soc_watchlist.add(db, "t1", bad, None, "ana")
    item = await soc_watchlist.add(db, "t1", "45.33.32.156", "known C2", "ana")
    assert item["kind"] == "ip" and item["retroMatches"] == 1
    assert (await db.security_alerts.find_one({"id": "p1"}))["threatIntel"][0] == {"value": "45.33.32.156", "kind": "ip", "source": "watchlist", "malware": "known C2"}
    assert "threatIntel" not in await db.security_alerts.find_one({"id": "p2"})
    assert (await soc_watchlist.add(db, "t1", "evil.example", None, "ana"))["retroMatches"] == 1
    with pytest.raises(soc_watchlist.WatchlistError) as dup:
        await soc_watchlist.add(db, "t1", "45.33.32.156", None, "ana")
    assert dup.value.status == 409
    new = await soc_alerts.record_alert(db, {"tenantId": "t1", "agent_id": "ag1", "type": "edr", "title": "beacon", "metadata": {"ip": "45.33.32.156"}})
    assert [h["source"] for h in new["threatIntel"]] == ["watchlist"]
    await soc_watchlist.remove(db, "t1", item["id"])
    assert [i["value"] for i in await soc_watchlist.list_items(db, "t1")] == ["evil.example"]
