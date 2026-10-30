"""Platform health for the Super Admin (Phase 82, plan 82-08): the summary on the shared status poller,
the full health document, and the dead-man switch.

Real Mongo through the throwaway database of tests/_mongo_test_db.py. The watchdog is played by the
loopback sync client of the 82-01 tests, so the snapshot is stored by the real ingest code.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-status")

from autonomous_ops import PLATFORM_TENANT_ID, ledger, oncall, selfheal
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_platform_health_sync import Watchdog, _body

STATUS = "/api/platform/autonomous-ops/status"
HEALTH = "/api/platform/autonomous-ops/health"
STOP = "/api/platform/autonomous-ops/stop"
RESUME = "/api/platform/autonomous-ops/resume"


class World:
    """The platform API and the watchdog on one database."""

    def __init__(self, api, dog):
        self.api, self.dog, self.db = api, dog, api.db

    async def sync(self, **extra):
        res = await self.dog.post(body=_body(**extra))
        assert res.status_code == 200, res.text
        return res

    async def get(self, path, role="super_admin"):
        return await self.api.call("GET", path, role=role)

    async def summary(self):
        res = await self.get(STATUS)
        assert res.status_code == 200, res.text
        return res.json()["health"]


@pytest.fixture
async def world(api, monkeypatch, tmp_path):
    await selfheal.ensure_indexes(api.db)
    await oncall.ensure_indexes(api.db)
    dog = Watchdog(api.db, monkeypatch, tmp_path)
    dog.set_token()
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", datetime.now(timezone.utc).timestamp() - 3600)
    return World(api, dog)


T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def _oncall(kind="pagerduty", last=None):
    return {"type": kind, "heartbeatConfigured": False, "last": last}


async def _test_result(db, rid, state, sent_at, error=None):
    await db.oncall_test_requests.insert_one({"id": rid, "requestedAt": sent_at - timedelta(minutes=1), "requestedBy": {},
                                              "state": state, "sentAt": sent_at, "error": error})


# ------------------------------------------------------------------ Task 1: the tracer

async def test_no_heartbeat_the_summary_says_not_installed(world):
    res = await world.get(STATUS)
    assert res.status_code == 200
    assert res.json()["health"] == {"watchdog": "not_installed", "lastSeenAt": None, "channel": None, "channelError": None}


async def test_after_one_sync_the_watchdog_is_running_and_the_channel_untested(world):
    await world.sync(oncall=_oncall())
    health = await world.summary()
    assert health["watchdog"] == "running" and health["channel"] == "untested" and health["channelError"] is None
    assert datetime.fromisoformat(health["lastSeenAt"]).tzinfo is not None
    assert set(health) == {"watchdog", "lastSeenAt", "channel", "channelError"}


async def test_oncall_type_none_means_no_channel(world):
    await world.sync(oncall=_oncall("none"))
    health = await world.summary()
    assert health["channel"] == "none" and health["channelError"] is None


async def test_a_failed_delivery_then_a_later_successful_test(world):
    last = {"at": T0.isoformat(), "ok": False, "error": "HTTP 400", "kind": "page"}
    await world.sync(oncall=_oncall(last=last))
    health = await world.summary()
    assert health["channel"] == "failing" and health["channelError"] == "HTTP 400"
    await _test_result(world.db, "TR-1", "delivered", T0 + timedelta(minutes=5))
    health = await world.summary()
    assert health["channel"] == "working" and health["channelError"] is None


async def test_an_older_successful_test_does_not_hide_a_newer_failed_delivery(world):
    await _test_result(world.db, "TR-1", "delivered", T0 - timedelta(minutes=5))
    await world.sync(oncall=_oncall(last={"at": T0.isoformat(), "ok": False, "error": "HTTP 502"}))
    health = await world.summary()
    assert health["channel"] == "failing" and health["channelError"] == "HTTP 502"


async def test_the_newest_acknowledged_outbox_message_counts(world):
    await world.sync(oncall=_oncall(last={"at": T0.isoformat(), "ok": True, "error": None}))
    await world.db.oncall_outbox.insert_one({"id": "OB-1", "deliveredAt": T0 + timedelta(minutes=2), "ok": False,
                                             "error": "timeout", "expiresAt": T0 + timedelta(days=1)})
    health = await world.summary()
    assert health["channel"] == "failing" and health["channelError"] == "timeout"


async def test_a_failure_computing_health_leaves_the_stop_status_intact(world, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("database fell over")
    monkeypatch.setattr(selfheal, "health_summary", boom)
    res = await world.get(STATUS)
    assert res.status_code == 200
    body = res.json()
    assert body["health"] is None and body["scope"] == "platform"
    assert body["stop"] == {"platform": None} and body["canStopPlatform"] is True and body["tenantStopsCount"] == 0


# ------------------------------------------------------------------ orchestrator note 1: mixed time forms

NAIVE = lambda dt: dt.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731  (as MongoDB returns it)


async def test_newest_is_a_string_and_the_older_is_a_naive_datetime(world):
    await world.sync(oncall=_oncall(last={"at": (T0 + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
                                          "ok": False, "error": "HTTP 400"}))
    await world.db.oncall_test_requests.insert_one({"id": "TR-1", "state": "delivered", "error": None, "requestedBy": {},
                                                    "requestedAt": NAIVE(T0), "sentAt": NAIVE(T0 + timedelta(minutes=2))})
    assert (await world.summary())["channel"] == "failing"


async def test_newest_is_a_naive_datetime_and_the_older_is_a_string(world):
    await world.sync(oncall=_oncall(last={"at": T0.isoformat(), "ok": False, "error": "HTTP 400"}))
    await world.db.oncall_test_requests.insert_one({"id": "TR-1", "state": "delivered", "error": None, "requestedBy": {},
                                                    "requestedAt": NAIVE(T0), "sentAt": NAIVE(T0 + timedelta(minutes=2))})
    assert (await world.summary())["channel"] == "working"


async def test_a_string_with_another_offset_is_compared_as_the_instant_it_is(world):
    plus_two = timezone(timedelta(hours=2))
    later_local = (T0 + timedelta(minutes=30)).astimezone(plus_two)           # 14:30+02:00 is 12:30 UTC
    await world.sync(oncall=_oncall(last={"at": later_local.isoformat(), "ok": False, "error": "x"}))
    await _test_result(world.db, "TR-1", "delivered", NAIVE(T0 + timedelta(minutes=20)))   # 12:20 UTC, older
    assert (await world.summary())["channel"] == "failing"


async def test_a_time_that_cannot_be_read_counts_as_oldest_and_never_raises(world):
    await _test_result(world.db, "TR-1", "delivered", T0)
    await world.sync(oncall=_oncall(last={"at": "not a time", "ok": False, "error": "HTTP 400"}))
    assert (await world.summary())["channel"] == "working"                       # the readable one is newer
    await world.sync(oncall=_oncall(last={"at": None, "ok": False, "error": "HTTP 400"}))
    assert (await world.summary())["channel"] == "working"
    await world.db.oncall_test_requests.delete_many({})
    await world.sync(oncall=_oncall(last={"at": {"nested": 1}, "ok": False, "error": "HTTP 400"}))
    health = await world.summary()                                               # only candidate: used, oldest or not
    assert health["channel"] == "failing" and health["channelError"] == "HTTP 400"


async def test_a_request_nobody_picked_up_says_nothing_about_the_channel(world):
    await world.sync(oncall=_oncall())
    await world.db.oncall_test_requests.insert_one({"id": "TR-1", "state": "failed", "sentAt": None, "requestedBy": {},
                                                    "requestedAt": T0, "error": oncall.TEST_NO_ANSWER})
    assert (await world.summary())["channel"] == "untested"


async def test_a_delivery_error_never_carries_a_url(world):
    err = "POST https://events.pagerduty.com/v2/enqueue?key=SECRET failed: HTTP 400"
    await world.sync(oncall=_oncall(last={"at": T0.isoformat(), "ok": False, "error": err}))
    health = await world.summary()
    assert "SECRET" not in json.dumps(health) and "https://" not in json.dumps(health)
    assert health["channelError"].startswith("POST [url]")
