"""Platform health for the Super Admin (Phase 82, plan 82-08): the summary on the shared status poller,
the full health document, and the dead-man switch.

Real Mongo through the throwaway database of tests/_mongo_test_db.py. The watchdog is played by the
loopback sync client of the 82-01 tests, so the snapshot is stored by the real ingest code.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-status")

from autonomous_ops import oncall, selfheal
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._platform_health_world import (HEALTH, NAIVE, RESUME, STATUS, STOP, T0, World, _oncall,  # noqa: F401
                                          _test_result, world)
from tests.test_platform_health_sync import _body


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


# ------------------------------------------------------------------ Task 2: the health document

ORDER = ["mongod", "omni-backend", "nginx", "ollama"]
NAMES = [("MongoDB", "mongod"), ("Backend", "omni-backend"), ("nginx", "nginx"), ("Ollama", "ollama")]


def _service(**over):
    base = {"state": "healthy", "since": "2026-10-30T10:00:00Z", "failedChecks": 0, "restartsInWindow": 0,
            "nextRestartAt": None, "budgetReturnsAt": None, "pagedAt": None, "waitingOn": None, "detail": ""}
    base.update(over)
    return base


# The exact shapes 82-04 and 82-03 document (certs, disks incl. forecast and paths, service fields).
CERTS = [
    {"path": "/etc/nginx/ssl/omni.crt", "notAfter": "2028-12-20T00:00:00Z", "daysLeft": 811.25, "rung": 0, "pinned": True,
     "error": None},
    {"path": "/etc/ssl/extra.pem", "notAfter": "2026-11-11T12:00:00Z", "daysLeft": 12.5, "rung": 1, "pinned": False,
     "error": None},
    {"path": "/etc/ssl/gone.pem", "notAfter": None, "daysLeft": None, "rung": 2, "pinned": False, "error": "unreadable"},
]
DISKS = [
    {"mount": "/", "paths": ["/", "/var/lib/mongodb"], "usedPct": 69.4, "freeBytes": 30600000000, "totalBytes": 100000000000,
     "rung": 0, "forecast": {"state": "ok", "days": 9.5, "rung": 1}},
    {"mount": "/data", "paths": ["/data"], "usedPct": 91.2, "freeBytes": 8800000000, "totalBytes": 100000000000,
     "rung": 2, "forecast": {"state": "insufficient", "days": None, "rung": 0}},
]
SERVICES = {
    "ollama": _service(state="expected_off", detail="expected_off"),
    "nginx": _service(state="checking", failedChecks=1, detail="HTTP 502"),
    "omni-backend": _service(state="down", failedChecks=3, waitingOn="mongod", restartsInWindow=1,
                             nextRestartAt="2026-10-30T11:05:00Z", detail="connection refused"),
    "mongod": _service(state="gave_up", failedChecks=9, restartsInWindow=3, budgetReturnsAt="2026-10-30T12:30:00Z",
                       pagedAt="2026-10-30T11:00:00Z", detail="not responding"),
}


async def _age_heartbeat(db, seconds):
    await db.platform_health.update_one({"_id": "heartbeat"},
                                        {"$set": {"lastSeenAt": datetime.now(timezone.utc) - timedelta(seconds=seconds)}})


async def test_not_installed_the_document_is_honest_about_having_nothing(world):
    res = await world.get(HEALTH)
    assert res.status_code == 200
    doc = res.json()
    assert doc["watchdog"] == {"state": "not_installed", "lastSeenAt": None, "firstSeenAt": None, "cadenceSeconds": 60,
                               "silentAfterSeconds": 300}
    assert doc["installChecklist"] == {"path": "deploy/omni-watchdog/INSTALL.md", "url": None}
    assert [s["id"] for s in doc["services"]] == ORDER
    for service, (name, unit) in zip(doc["services"], NAMES):
        assert (service["name"], service["unit"]) == (name, unit)
        assert service["state"] is None and service["stale"] is True and service["since"] is None
    assert doc["certs"] == [] and doc["disks"] == []
    assert doc["updatedAt"] is None and doc["host"] is None and doc["testAlert"] is None
    assert doc["stop"] == {"effective": False, "source": "none"}
    assert doc["oncall"] == {"type": None, "heartbeatConfigured": False, "status": "not_set_up", "last": None}


async def test_running_services_come_back_in_the_fixed_order_and_certs_soonest_first(world):
    await world.sync(services=SERVICES, certs=[CERTS[0], CERTS[1]])
    doc = (await world.get(HEALTH)).json()
    assert doc["watchdog"]["state"] == "running" and doc["host"] == "omni"
    assert [s["id"] for s in doc["services"]] == ORDER and not any(s["stale"] for s in doc["services"])
    assert [c["daysLeft"] for c in doc["certs"]] == [12.5, 811.25] and not any(c["stale"] for c in doc["certs"])
    assert doc["watchdog"]["firstSeenAt"] and doc["watchdog"]["lastSeenAt"] and doc["updatedAt"]


async def test_silent_keeps_every_last_known_value_marked_stale(world):
    await world.sync(services=SERVICES, certs=CERTS, disks=DISKS)
    await _age_heartbeat(world.db, 400)
    doc = (await world.get(HEALTH)).json()
    assert doc["watchdog"]["state"] == "silent"
    assert [s["state"] for s in doc["services"]] == ["gave_up", "down", "checking", "expected_off"]
    assert all(s["stale"] for s in doc["services"]) and all(c["stale"] for c in doc["certs"])
    assert all(d["stale"] for d in doc["disks"]) and len(doc["certs"]) == 3 and len(doc["disks"]) == 2
    summary = await world.summary()
    assert summary["watchdog"] == "silent"


async def test_just_after_a_backend_start_an_old_heartbeat_is_not_yet_silent(world, monkeypatch):
    await world.sync(services=SERVICES)
    await _age_heartbeat(world.db, 400)
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", datetime.now(timezone.utc).timestamp() - 60)
    doc = (await world.get(HEALTH)).json()
    assert doc["watchdog"]["state"] == "running" and not any(s["stale"] for s in doc["services"])


@pytest.mark.parametrize("oncall_block,expected,kind", [
    (_oncall("none"), "not_set_up", "none"),
    (_oncall(last={"at": T0.isoformat(), "ok": False, "error": "HTTP 400"}), "not_working", "pagerduty"),
    (_oncall("webhook", last={"at": T0.isoformat(), "ok": True, "error": None}), "working", "webhook"),
    (_oncall(), "not_tested", "pagerduty"),
])
async def test_oncall_status_is_derived_from_the_newest_outcome(world, oncall_block, expected, kind):
    await world.sync(oncall={**oncall_block, "heartbeatConfigured": True})
    block = (await world.get(HEALTH)).json()["oncall"]
    assert block["status"] == expected and block["type"] == kind and block["heartbeatConfigured"] is True
    assert (block["last"] is None) == (expected in ("not_set_up", "not_tested"))


async def test_test_alert_equals_the_latest_test_view(world):
    await world.sync(oncall=_oncall())
    await world.db.users.insert_one({"email": "root@example.test", "name": "Root Admin"})
    alert = (await world.api.call("POST", HEALTH + "/test-alert", role="super_admin", username="root@example.test")).json()
    doc = (await world.get(HEALTH)).json()
    assert doc["testAlert"] == alert["testAlert"] == await oncall.test_view(world.db)
    assert doc["testAlert"]["state"] == "pending" and doc["testAlert"]["requestedBy"] == "Root Admin"


@pytest.mark.parametrize("role", ["tenant_admin", "viewer", "analyst", "platform_support"])
async def test_only_the_platform_owner_can_read_health_or_the_status_summary(world, role):
    await world.sync(oncall=_oncall())
    for path in (HEALTH, STATUS):
        res = await world.get(path, role=role)
        assert res.status_code == 403, (path, role)
        assert "channel" not in res.text and "services" not in res.text
    for method, path in (("POST", STOP), ("POST", RESUME)):                     # the other routes that answer with health
        assert (await world.api.call(method, path, role=role, json={"reason": "x"})).status_code == 403


async def test_an_api_key_cannot_read_the_health_document(world):
    res = await world.api.call("GET", HEALTH, role="super_admin", auth="api_key", scopes=["control:platform_autonomous_ops"])
    assert res.status_code == 403


SECRET_KEYS = ("routingKey", "routing_key", "webhookUrl", "heartbeatUrl", "token", "password", "secret")   # installChecklist.url is a legitimate null


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


async def test_no_secret_key_or_value_reaches_the_document_or_the_summary(world):
    secrets = ["R0UT1NGK3Y", "https://hooks.example.test/T000/B000/XXXX", "https://hc.example.test/ping/abc", "t0ps3cr3t"]
    channel = {"type": "pagerduty", "heartbeatConfigured": True, "routingKey": secrets[0], "webhookUrl": secrets[1],
               "heartbeatUrl": secrets[2], "token": secrets[3], "last": {"at": T0.isoformat(), "ok": False,
                                                                         "error": f"POST {secrets[1]} -> 400",
                                                                         "token": secrets[3], "url": secrets[2]}}
    services = {sid: {**_service(), "token": secrets[3], "url": secrets[1]} for sid in ORDER}
    await world.sync(oncall=channel, services=services,
                     certs=[{**CERTS[0], "key": secrets[0]}], disks=[{**DISKS[0], "heartbeatUrl": secrets[2]}])
    doc, summary = (await world.get(HEALTH)).json(), await world.summary()
    for payload in (doc, summary):
        text = json.dumps(payload)
        assert not any(secret in text for secret in secrets)
        assert not [k for k in _keys(payload) if k in SECRET_KEYS]


# ------------------------------------------------------------------ orchestrator note 2: real shapes, real door

async def test_the_real_certs_disks_and_service_shapes_survive_the_sync_door(world):
    await world.sync(services=SERVICES, certs=CERTS, disks=DISKS, stop={"effective": True, "source": "cache"},
                     oncall={"type": "webhook", "heartbeatConfigured": True,
                             "last": {"at": T0.isoformat(), "ok": True, "error": None, "kind": "page"}})
    stored = await world.db.platform_health.find_one({"_id": "snapshot"})
    assert stored["disks"][0]["forecast"] == {"state": "ok", "days": 9.5, "rung": 1}     # inside the depth limit
    assert stored["disks"][1]["paths"] == ["/data"]
    doc = (await world.get(HEALTH)).json()

    assert [s["id"] for s in doc["services"]] == ORDER
    for service in doc["services"]:
        posted = SERVICES[service["id"]]
        assert {k: service[k] for k in posted} == posted
        assert service["stale"] is False

    unreadable, soon, far = doc["certs"]
    for got, posted in ((unreadable, CERTS[2]), (soon, CERTS[1]), (far, CERTS[0])):
        assert {k: got[k] for k in posted} == posted and got["stale"] is False

    assert len(doc["disks"]) == 2
    for got, posted in zip(doc["disks"], DISKS):
        assert {k: got[k] for k in posted} == posted and got["stale"] is False
    assert doc["disks"][0]["paths"] == ["/", "/var/lib/mongodb"]
    assert doc["disks"][0]["forecast"] == {"state": "ok", "days": 9.5, "rung": 1}
    assert doc["disks"][1]["forecast"] == {"state": "insufficient", "days": None, "rung": 0}

    assert doc["stop"] == {"effective": True, "source": "cache"}
    assert doc["oncall"]["type"] == "webhook" and doc["oncall"]["status"] == "working"
    assert doc["oncall"]["last"] == {"at": T0.isoformat(), "ok": True, "error": None}


async def test_a_second_sync_replaces_the_values_the_backend_shows(world):
    await world.sync(certs=CERTS, disks=DISKS)
    await world.sync(certs=[CERTS[0]], disks=[])
    doc = (await world.get(HEALTH)).json()
    assert [c["path"] for c in doc["certs"]] == ["/etc/nginx/ssl/omni.crt"] and doc["disks"] == []


def test_the_backend_never_reads_a_certificate_or_measures_a_disk():
    text = open(os.path.join(os.path.dirname(__file__), "..", "autonomous_ops", "selfheal.py"), encoding="utf-8").read()
    assert not any(word in text for word in ("statvfs", "openssl", "x509", "disk_usage"))
