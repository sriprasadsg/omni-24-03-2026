"""On-call outbox and test alert (Phase 82, plan 82-07, HEAL-05, D-04, D-21, D-01).

notify() feeds ``oncall_outbox``; the watchdog drains it through the sync round trip and reports
delivery; the Super Admin's test alert goes the same way. Real Mongo through the throwaway
database of tests/_mongo_test_db.py; the watchdog is played by the loopback sync client of the
82-01 tests.
"""
import importlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-oncall")

from autonomous_ops import PLATFORM_TENANT_ID, health_messages, ledger, notify, oncall, selfheal
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.test_platform_health_sync import Watchdog, _body

SYNC = "/api/internal/watchdog/sync"
RESULTS = "/api/internal/watchdog/results"
TEST_ALERT = "/api/platform/autonomous-ops/health/test-alert"
PLATFORM_LIST = "/api/platform/autonomous-ops/actions?bucket=platform_health"


@pytest.fixture
async def wd(mongo_db, monkeypatch, tmp_path):
    await ledger.ensure_indexes(mongo_db)
    await selfheal.ensure_indexes(mongo_db)
    await oncall.ensure_indexes(mongo_db)
    dog = Watchdog(mongo_db, monkeypatch, tmp_path)
    dog.set_token()
    return dog


async def _notify(db, title="Automatic actions stopped", severity="warning", tenant="t1", message="Stopped by Ana."):
    await notify.notify(db, tenant, title=title, message=message, severity=severity)


# ------------------------------------------------------------------ Task 1: the tracer

async def test_notify_posts_in_app_and_queues_one_outbox_message(wd):
    await seed_tenant(wd.db, "t1")
    await _notify(wd.db)
    assert await wd.db.notifications.count_documents({}) >= 1                  # the in-app notice is unchanged
    docs = [d async for d in wd.db.oncall_outbox.find({}, {"_id": 0})]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "trigger" and doc["dedupKey"] is None and doc["severity"] == "warning"
    assert doc["tenantId"] == "t1" and doc["source"] == "autonomous_ops"
    assert "Automatic actions stopped" in doc["summary"]
    assert doc["deliveredAt"] is None and doc["ok"] is None and doc["error"] is None
    assert doc["expiresAt"] - doc["createdAt"] == timedelta(hours=24)


async def test_notify_still_returns_none_and_posts_in_app_when_enqueue_raises(wd, monkeypatch):
    await seed_tenant(wd.db, "t1")
    monkeypatch.setattr(oncall, "enqueue", AsyncMock(side_effect=RuntimeError("queue down")))
    assert await notify.notify(wd.db, "t1", title="Breaker tripped", message="x", severity="warning") is None
    assert await wd.db.notifications.count_documents({}) >= 1
    assert await wd.db.oncall_outbox.count_documents({}) == 0


async def test_enqueue_never_raises_when_the_insert_fails(wd, monkeypatch):
    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("no database")
    assert await oncall.enqueue(Broken(), tenant_id="t1", title="x", message="y", severity="info") is None


async def test_sync_hands_out_the_message_and_a_delivered_entry_marks_it(wd):
    await _notify(wd.db, severity="warning")
    first = await wd.post(body=_body())
    outbox = first.json()["outbox"]
    assert len(outbox) == 1
    item = outbox[0]
    assert set(item) == {"id", "kind", "dedupKey", "severity", "summary", "details"}
    assert item["kind"] == "trigger" and item["dedupKey"] is None and item["severity"] == "warning"
    assert "Automatic actions stopped" in item["summary"]
    assert (await wd.post(body=_body())).json()["outbox"] == [item]            # not delivered yet: offered again

    ack = _body(delivered=[{"id": item["id"], "ok": True, "at": datetime.now(timezone.utc).isoformat()}])
    assert (await wd.post(body=ack)).json()["outbox"] == []
    doc = await wd.db.oncall_outbox.find_one({"id": item["id"]})
    assert doc["deliveredAt"] is not None and doc["ok"] is True and doc["error"] is None


async def test_results_endpoint_marks_a_message_delivered_with_a_capped_error(wd):
    await _notify(wd.db)
    item = (await wd.post(body=_body())).json()["outbox"][0]
    res = await wd.post(RESULTS, {"v": 1, "delivered": [{"id": item["id"], "ok": False, "error": "x" * 500}]})
    assert res.status_code == 200 and res.json() == {"ok": True}
    doc = await wd.db.oncall_outbox.find_one({"id": item["id"]})
    assert doc["ok"] is False and len(doc["error"]) == 300 and doc["deliveredAt"] is not None
    assert (await wd.post(body=_body())).json()["outbox"] == []


async def test_a_second_delivered_entry_changes_nothing(wd):
    await _notify(wd.db)
    item = (await wd.post(body=_body())).json()["outbox"][0]
    await wd.post(body=_body(delivered=[{"id": item["id"], "ok": True}]))
    first = await wd.db.oncall_outbox.find_one({"id": item["id"]})
    await wd.post(RESULTS, {"v": 1, "delivered": [{"id": item["id"], "ok": False, "error": "late"}]})
    assert await wd.db.oncall_outbox.find_one({"id": item["id"]}) == first


async def test_an_expired_message_is_never_returned(wd):
    await _notify(wd.db)
    await wd.db.oncall_outbox.update_many({}, {"$set": {"expiresAt": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert (await wd.post(body=_body())).json()["outbox"] == []


@pytest.mark.parametrize("given,expected", [("critical", "critical"), ("warning", "warning"), ("info", "info"),
                                            ("weird", "warning"), (None, "warning"), ("INFO", "info")])
def test_notify_severity_maps_to_oncall_severity(given, expected):
    assert oncall.map_severity(given) == expected
