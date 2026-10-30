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


# ------------------------------------------------------------------ Task 2: send test alert

NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def _beat(seconds_old, now=NOW):
    return {"_id": "heartbeat", "firstSeenAt": now - timedelta(days=1), "lastSeenAt": now - timedelta(seconds=seconds_old),
            "host": "omni"}


async def _seed_heartbeat(db, seconds_old):
    """A heartbeat ``seconds_old`` seconds old by the real clock."""
    now = datetime.now(timezone.utc)
    await db.platform_health.replace_one({"_id": "heartbeat"}, _beat(seconds_old, now), upsert=True)


@pytest.fixture
def long_running(monkeypatch):
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", datetime.now(timezone.utc).timestamp() - 3600)


@pytest.fixture
async def beat(api, long_running):
    await _seed_heartbeat(api.db, 10)
    return api


def test_watchdog_state_not_installed_running_silent_and_grace():
    started_long_ago = NOW.timestamp() - 3600
    assert selfheal.watchdog_state(None, NOW, started_long_ago) == "not_installed"
    assert selfheal.watchdog_state({}, NOW, started_long_ago) == "not_installed"
    assert selfheal.watchdog_state(_beat(10), NOW, started_long_ago) == "running"
    assert selfheal.watchdog_state(_beat(300), NOW, started_long_ago) == "running"       # exactly 300 s is not yet silent
    assert selfheal.watchdog_state(_beat(301), NOW, started_long_ago) == "silent"
    assert selfheal.watchdog_state(_beat(400), NOW, NOW.timestamp() - 60) == "running"    # grace after a backend start
    assert selfheal.watchdog_state(_beat(400), NOW, NOW.timestamp() - 180) == "running"
    assert selfheal.watchdog_state(_beat(400), NOW, NOW.timestamp() - 181) == "silent"
    assert selfheal.SILENT_AFTER == 300 and selfheal.STARTUP_GRACE == 180


def test_watchdog_state_accepts_naive_datetimes_as_stored_by_motor():
    naive = {"lastSeenAt": (NOW - timedelta(seconds=10)).replace(tzinfo=None)}
    assert selfheal.watchdog_state(naive, NOW, NOW - timedelta(hours=1)) == "running"
    stale = {"lastSeenAt": (NOW - timedelta(seconds=999)).replace(tzinfo=None)}
    assert selfheal.watchdog_state(stale, NOW, NOW - timedelta(hours=1)) == "silent"


async def test_super_admin_requests_a_test_alert_and_a_second_click_gets_the_same_one(beat):
    first = await beat.call("POST", TEST_ALERT, role="super_admin", username="root@example.test")
    assert first.status_code == 200
    alert = first.json()["testAlert"]
    assert set(alert) == {"id", "requestedAt", "requestedBy", "state", "sentAt", "error"}
    assert alert["state"] == "pending" and alert["sentAt"] is None and alert["requestedBy"] == "root@example.test"
    second = await beat.call("POST", TEST_ALERT, role="super_admin")
    assert second.status_code == 200 and second.json()["testAlert"]["id"] == alert["id"]
    assert await beat.db.oncall_test_requests.count_documents({}) == 1
    stored = await beat.db.oncall_test_requests.find_one({"id": alert["id"]})
    assert stored["requestedBy"] == {"id": "root@example.test", "name": "root@example.test"}


async def test_requested_by_uses_the_users_display_name(beat):
    await beat.db.users.insert_one({"email": "root@example.test", "name": "Root Admin"})
    res = await beat.call("POST", TEST_ALERT, role="super_admin", username="root@example.test")
    assert res.json()["testAlert"]["requestedBy"] == "Root Admin"
    stored = await beat.db.oncall_test_requests.find_one({})
    assert stored["requestedBy"] == {"id": "root@example.test", "name": "Root Admin"}


async def test_the_next_sync_carries_the_test_request_and_the_result_closes_it(beat, monkeypatch, tmp_path):
    await beat.db.users.insert_one({"email": "root@example.test", "name": "Ana Root"})
    alert = (await beat.call("POST", TEST_ALERT, role="super_admin", username="root@example.test")).json()["testAlert"]
    dog = Watchdog(beat.db, monkeypatch, tmp_path)
    dog.set_token()
    sync = (await dog.post(body=_body())).json()
    assert sync["testRequest"] == {"id": alert["id"], "requestedAt": alert["requestedAt"]}
    sent = datetime.now(timezone.utc).replace(microsecond=0)
    res = await dog.post(RESULTS, {"v": 1, "testResult": {"id": alert["id"], "ok": True, "at": sent.isoformat()}})
    assert res.status_code == 200
    stored = await beat.db.oncall_test_requests.find_one({"id": alert["id"]})
    assert stored["state"] == "delivered" and stored["error"] is None
    assert stored["sentAt"].replace(tzinfo=timezone.utc) == sent
    assert (await dog.post(body=_body())).json()["testRequest"] is None

    rows = (await beat.call("GET", PLATFORM_LIST, role="super_admin")).json()["items"]
    tests = [r for r in rows if r["actionLabel"] == "Test alert"]
    assert len(tests) == 1
    row = tests[0]
    assert row["reasonText"] == "Requested by Ana Root."
    assert row["resultText"] == f"Sent at {sent:%H:%M}, delivered."
    assert row["healthChip"] == "healthy" and row["id"] == "PH-test-" + alert["id"]


async def test_a_repeated_result_writes_no_second_row(beat, monkeypatch, tmp_path):
    alert = (await beat.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]
    dog = Watchdog(beat.db, monkeypatch, tmp_path)
    dog.set_token()
    for _ in range(2):
        await dog.post(RESULTS, {"v": 1, "testResult": {"id": alert["id"], "ok": True}})
    assert await beat.db.autonomy_actions.count_documents({"healthEvent": "test_alert"}) == 1


async def test_a_failed_result_stores_the_capped_error_and_a_critical_chip(beat, monkeypatch, tmp_path):
    alert = (await beat.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]
    dog = Watchdog(beat.db, monkeypatch, tmp_path)
    dog.set_token()
    await dog.post(RESULTS, {"v": 1, "testResult": {"id": alert["id"], "ok": False, "error": "e" * 500}})
    stored = await beat.db.oncall_test_requests.find_one({"id": alert["id"]})
    assert stored["state"] == "failed" and len(stored["error"]) == 300 and stored["sentAt"] is not None
    row = (await beat.db.autonomy_actions.find_one({"healthEvent": "test_alert"}))
    assert row["healthChip"] == "critical" and len(row["healthParams"]["error"]) == 300
    shown = (await beat.call("GET", PLATFORM_LIST, role="super_admin")).json()["items"][0]
    assert shown["healthChip"] == "critical" and "not delivered: " in shown["resultText"]
    # the latest request is visible to a status reader
    view = await oncall.test_view(beat.db)
    assert view["state"] == "failed" and view["id"] == alert["id"]


async def test_a_result_for_an_unknown_request_is_ignored(beat, monkeypatch, tmp_path):
    dog = Watchdog(beat.db, monkeypatch, tmp_path)
    dog.set_token()
    res = await dog.post(RESULTS, {"v": 1, "testResult": {"id": "TR-nope", "ok": True}})
    assert res.status_code == 200
    assert await beat.db.autonomy_actions.count_documents({"healthEvent": "test_alert"}) == 0


async def test_no_heartbeat_ever_answers_409_install_the_watchdog_first(api, long_running):
    res = await api.call("POST", TEST_ALERT, role="super_admin")
    assert res.status_code == 409 and res.json()["detail"] == "Install the watchdog first."
    assert await api.db.oncall_test_requests.count_documents({}) == 0


async def test_a_silent_watchdog_answers_409_with_the_silent_copy(api, long_running):
    await _seed_heartbeat(api.db, 400)
    res = await api.call("POST", TEST_ALERT, role="super_admin")
    assert res.status_code == 409
    assert res.json()["detail"] == "The watchdog is silent, so a test can't be sent until it reports again."


async def test_a_stale_heartbeat_just_after_a_backend_start_is_accepted(api, monkeypatch):
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", datetime.now(timezone.utc).timestamp() - 60)
    await _seed_heartbeat(api.db, 400)
    res = await api.call("POST", TEST_ALERT, role="super_admin")
    assert res.status_code == 200 and res.json()["testAlert"]["state"] == "pending"


@pytest.mark.parametrize("role", ["tenant_admin", "analyst", "platform_support"])
async def test_non_super_admin_identities_get_403(beat, role):
    res = await beat.call("POST", TEST_ALERT, role=role)
    assert res.status_code == 403
    assert await beat.db.oncall_test_requests.count_documents({}) == 0


async def test_an_api_key_cannot_request_a_test_alert(beat):
    res = await beat.call("POST", TEST_ALERT, role="super_admin", auth="api_key", scopes=["control:platform_autonomous_ops"])
    assert res.status_code == 403


async def test_a_request_nobody_picked_up_is_closed_so_a_new_test_can_be_sent(beat):
    first = (await beat.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]
    await beat.db.oncall_test_requests.update_one(
        {"id": first["id"]}, {"$set": {"requestedAt": datetime.now(timezone.utc) - timedelta(minutes=11)}})
    assert await oncall.pending_test(beat.db) is None                           # not handed to a returning watchdog
    second = (await beat.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]
    assert second["id"] != first["id"] and second["state"] == "pending"
    old = await beat.db.oncall_test_requests.find_one({"id": first["id"]})
    assert old["state"] == "failed" and old["error"] == oncall.TEST_NO_ANSWER


def test_the_409_copy_lives_in_health_messages():
    assert health_messages.API_DETAIL == {
        "watchdog_not_installed": "Install the watchdog first.",
        "watchdog_silent": "The watchdog is silent, so a test can't be sent until it reports again."}


# ------------------------------------------------------------------ Task 3: migration, limits, secrecy

migration = importlib.import_module("migrations.026_oncall_outbox")


def _keys(info, name):
    return info[name]["key"]


async def test_migration_creates_the_outbox_and_test_request_indexes(mongo_db):
    await migration.up(mongo_db)
    outbox = await mongo_db.oncall_outbox.index_information()
    assert outbox["id_unique"]["unique"] is True and _keys(outbox, "id_unique") == [("id", 1)]
    assert _keys(outbox, "expires_ttl") == [("expiresAt", 1)] and outbox["expires_ttl"]["expireAfterSeconds"] == 0
    assert _keys(outbox, "delivered") == [("deliveredAt", 1)]
    requests = await mongo_db.oncall_test_requests.index_information()
    assert requests["id_unique"]["unique"] is True and _keys(requests, "id_unique") == [("id", 1)]
    assert _keys(requests, "requested") == [("requestedAt", 1)]


async def test_migration_twice_leaves_the_same_index_set(mongo_db):
    await migration.up(mongo_db)
    first = (await mongo_db.oncall_outbox.index_information(), await mongo_db.oncall_test_requests.index_information())
    await migration.up(mongo_db)
    assert (await mongo_db.oncall_outbox.index_information(),
            await mongo_db.oncall_test_requests.index_information()) == first


def test_migration_describes_itself():
    assert migration.DESCRIPTION and hasattr(migration, "up")


async def test_only_one_request_can_be_pending_at_the_database_level(mongo_db):
    from pymongo.errors import DuplicateKeyError
    await migration.up(mongo_db)
    await mongo_db.oncall_test_requests.insert_one({"id": "a", "requestedAt": NOW, "state": "pending"})
    with pytest.raises(DuplicateKeyError):
        await mongo_db.oncall_test_requests.insert_one({"id": "b", "requestedAt": NOW, "state": "pending"})
    await mongo_db.oncall_test_requests.insert_one({"id": "c", "requestedAt": NOW, "state": "delivered"})
    await mongo_db.oncall_test_requests.insert_one({"id": "d", "requestedAt": NOW, "state": "delivered"})


async def test_twenty_five_pending_messages_list_twenty_oldest_first(wd):
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    for i in range(25):
        await wd.db.oncall_outbox.insert_one({
            "id": f"OB-{i:02d}", "kind": "trigger", "dedupKey": None, "severity": "info", "summary": f"m{i}",
            "details": {}, "tenantId": "t1", "source": "autonomous_ops", "createdAt": base + timedelta(seconds=i),
            "expiresAt": datetime.now(timezone.utc) + timedelta(hours=1), "deliveredAt": None, "ok": None, "error": None})
    outbox = (await wd.post(body=_body())).json()["outbox"]
    assert [m["id"] for m in outbox] == [f"OB-{i:02d}" for i in range(20)]


async def test_a_long_notice_is_capped_at_1024_characters_in_the_summary(wd):
    await oncall.enqueue(wd.db, tenant_id="t1", title="T" * 300, message="M" * 3000, severity="critical")
    doc = await wd.db.oncall_outbox.find_one({})
    assert len(doc["summary"]) == 1024 and doc["severity"] == "critical"
    assert len(doc["details"]["message"]) <= 1024


async def test_metadata_with_credential_like_keys_is_not_stored(wd):
    await oncall.enqueue(wd.db, tenant_id="t1", title="x", message="y", severity="info",
                         metadata={"token": "s3cret", "routing_key": "k", "scope": "platform", "nested": {"a": 1}})
    doc = await wd.db.oncall_outbox.find_one({})
    assert doc["details"]["scope"] == "platform"
    assert "token" not in doc["details"] and "routing_key" not in doc["details"] and "nested" not in doc["details"]


_BANNED = re.compile(r"oncall\.env|PAGERDUTY_ROUTING_KEY|(?<![A-Z_])WEBHOOK_URL|(?<![A-Z_])HEARTBEAT_URL")
_SECRET_KEYS = {"routing_key", "routingkey", "webhookurl", "heartbeaturl", "token"}


def test_no_backend_module_names_the_oncall_secret_file_or_its_variables():
    root = Path(__file__).resolve().parent.parent
    skip = {"venv", ".venv", "tests", "node_modules", "__pycache__", ".git"}
    offenders = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith("venv")]
        for name in files:
            if name.endswith(".py") and _BANNED.search(Path(folder, name).read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(Path(folder, name).relative_to(root)))
    assert offenders == []


def _keys_in(value):
    found = set()
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(str(k).lower())
            found |= _keys_in(v)
    elif isinstance(value, list):
        for v in value:
            found |= _keys_in(v)
    return found


async def test_no_response_or_document_carries_a_routing_key_or_url(beat, monkeypatch, tmp_path):
    await seed_tenant(beat.db, "t1")
    await _notify(beat.db)
    alert = (await beat.call("POST", TEST_ALERT, role="super_admin")).json()
    dog = Watchdog(beat.db, monkeypatch, tmp_path)
    dog.set_token()
    sync = (await dog.post(body=_body())).json()
    assert sync["outbox"] and sync["testRequest"]
    outbox_doc = {k: v for k, v in (await beat.db.oncall_outbox.find_one({}, {"_id": 0})).items()}
    request_doc = await beat.db.oncall_test_requests.find_one({}, {"_id": 0})
    for payload in (sync, alert, json.loads(json.dumps(outbox_doc, default=str)), json.loads(json.dumps(request_doc, default=str))):
        assert not (_keys_in(payload) & _SECRET_KEYS)
        assert "Bearer" not in json.dumps(payload) and "http://" not in json.dumps(payload) and "https://" not in json.dumps(payload)
