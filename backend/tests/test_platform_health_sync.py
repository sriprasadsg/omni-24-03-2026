"""Watchdog sync endpoint (Phase 82, plan 82-01): POST /api/internal/watchdog/sync and /results.

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py (skipped when no server
is reachable). The loopback client address is forced by giving httpx's ASGITransport a
``client=("127.0.0.1", 50000)`` scope entry, because the test client's default host is "testclient".
The token credential is a file under a tmp CREDENTIALS_DIRECTORY, read on every call.
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-watchdog-ingest")

import watchdog_ingest_endpoints as ingest
from autonomous_ops import PLATFORM_TENANT_ID, health_messages, ledger, selfheal
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

TOKEN = "t0k3n"
URL = "/api/internal/watchdog/sync"


def _event(kind="service_down", target="mongod", **extra):
    base = {"id": uuid.uuid4().hex, "at": datetime.now(timezone.utc).isoformat(), "kind": kind,
            "severity": "critical", "target": target, "params": {}}
    base.update(extra)
    return base


def _body(events=None, **extra):
    base = {"v": 1, "host": "omni", "sentAt": datetime.now(timezone.utc).isoformat(),
            "services": {"mongod": {"state": "down", "since": None, "failedChecks": 2, "restartsInWindow": 0,
                                    "nextRestartAt": None, "budgetReturnsAt": None, "pagedAt": None,
                                    "waitingOn": None, "detail": ""}},
            "certs": [], "disks": [], "oncall": {"type": "none", "heartbeatConfigured": False, "last": None},
            "stop": {"effective": False, "source": "none"}, "events": events or [], "delivered": []}
    base.update(extra)
    return base


class Watchdog:
    """The sync router on a bare app, called from a chosen client address with a chosen token."""

    def __init__(self, db, monkeypatch, tmp_path):
        self.db = db
        self.cred_dir = tmp_path / "creds"
        self.cred_dir.mkdir()
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(self.cred_dir))
        monkeypatch.setattr(ingest, "get_database", lambda: db)
        self.app = FastAPI()
        self.app.include_router(ingest.router)

    def set_token(self, value=TOKEN):
        (self.cred_dir / "omni-watchdog-token").write_text(value + "\n", encoding="utf-8")

    async def post(self, path=URL, body=None, *, token=TOKEN, client=("127.0.0.1", 50000), headers=None,
                   content=None):
        hdrs = dict(headers or {})
        if token is not None:
            hdrs["Authorization"] = f"Bearer {token}"
        transport = httpx.ASGITransport(app=self.app, client=client)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            if content is not None:
                hdrs.setdefault("Content-Type", "application/json")
                return await http.post(path, content=content, headers=hdrs)
            return await http.post(path, json=body if body is not None else _body(), headers=hdrs)


@pytest.fixture
async def wd(mongo_db, monkeypatch, tmp_path):
    await ledger.ensure_indexes(mongo_db)
    await selfheal.ensure_indexes(mongo_db)
    dog = Watchdog(mongo_db, monkeypatch, tmp_path)
    dog.set_token()
    return dog


async def _rows(db, **flt):
    return [r async for r in db.autonomy_actions.find({"kind": "platform_health", **flt}, {"_id": 0})]


# ------------------------------------------------------------------ Task 1: the tracer

async def test_accepted_event_becomes_one_platform_health_row(wd):
    event = _event()
    res = await wd.post(body=_body([event]))
    assert res.status_code == 200
    assert res.json() == {"stop": {"active": False, "scope": None, "pressedAt": None},
                          "acceptedEventIds": [event["id"]], "droppedEvents": 0, "outbox": [], "testRequest": None}
    rows = await _rows(wd.db)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "PH-" + event["id"]
    assert row["tenantId"] == PLATFORM_TENANT_ID and row["state"] == "recorded"
    assert row["healthEvent"] == "service_down" and row["healthChip"] == "critical"
    assert row["host"] == "omni" and row["reason"]["ruleId"] == "service-down"
    snapshot = await wd.db.platform_health.find_one({"_id": "snapshot"})
    assert snapshot["services"]["mongod"]["state"] == "down"


async def test_resending_the_same_event_creates_no_second_row(wd):
    event = _event()
    first = await wd.post(body=_body([event]))
    second = await wd.post(body=_body([event]))
    assert first.status_code == second.status_code == 200
    assert second.json()["acceptedEventIds"] == [event["id"]]       # acknowledged so the spool can drop it
    assert len(await _rows(wd.db)) == 1
    audit = await wd.db.audit_logs.count_documents({"resourceId": "PH-" + event["id"]})
    assert audit == 1                                                # mirrored once, not per re-send


async def test_first_seen_is_set_once_and_last_seen_advances(wd):
    await wd.post(body=_body())
    first = await wd.db.platform_health.find_one({"_id": "heartbeat"})
    assert first["firstSeenAt"] == first["lastSeenAt"] and first["host"] == "omni"
    await wd.post(body=_body())
    second = await wd.db.platform_health.find_one({"_id": "heartbeat"})
    assert second["firstSeenAt"] == first["firstSeenAt"]
    assert second["lastSeenAt"] > first["lastSeenAt"]


def test_render_service_down_uses_the_agreed_copy():
    out = health_messages.render("service_down", {"target": "mongod"}, "omni")
    assert out == {"actionLabel": "Service check", "source": "Watchdog", "reasonText": "Failed 2 checks in a row.",
                   "ruleId": "service-down", "host": "omni", "target": "mongod", "resultText": "MongoDB is down."}


async def test_platform_stop_is_reported_in_the_response(wd):
    pressed = datetime(2026, 10, 27, 7, 0, tzinfo=timezone.utc)
    await wd.db.system_settings.insert_one({"type": "autonomous_ops", "stop": {
        "active": True, "scope": "platform", "pressedAt": pressed, "pressedBy": {"username": "root"}}})
    res = await wd.post(body=_body())
    stop = res.json()["stop"]
    assert stop["active"] is True and stop["scope"] == "platform" and stop["pressedAt"].startswith("2026-10-27T07:00")


def test_chip_and_rule_tables_cover_every_kind():
    kinds = selfheal.WATCHDOG_EVENT_KINDS | selfheal.BACKEND_EVENT_KINDS
    assert not (selfheal.WATCHDOG_EVENT_KINDS & selfheal.BACKEND_EVENT_KINDS)
    for kind in kinds:
        out = health_messages.render(kind, {"target": "nginx", "rung": 2, "ok": True}, "omni")
        assert out["actionLabel"] and out["reasonText"] and out["ruleId"] in health_messages.RULE_IDS
        assert health_messages.chip_for(kind, {"rung": 2, "ok": True}) in {
            "healthy", "notice", "warning", "critical", "paged", "skipped"}
    assert health_messages.chip_for("restart", {"ok": False}) == "critical"
    assert health_messages.chip_for("cert_warning", {"rung": 1}) == "notice"
    assert health_messages.chip_for("disk_forecast", {"rung": 3}) == "critical"
    assert health_messages.render("service_down", {}, None)["target"] is None   # missing values render as a dash in the UI


# ------------------------------------------------------------------ Task 3: auth, caps, closed vocabulary

async def test_no_credential_answers_503(wd):
    (wd.cred_dir / "omni-watchdog-token").unlink()
    assert (await wd.post()).status_code == 503


async def test_missing_credentials_directory_answers_503(wd, monkeypatch):
    monkeypatch.delenv("CREDENTIALS_DIRECTORY")
    assert (await wd.post()).status_code == 503


async def test_wrong_or_missing_bearer_answers_401(wd):
    assert (await wd.post(token="nope")).status_code == 401
    assert (await wd.post(token=None)).status_code == 401
    assert (await wd.post(token=TOKEN + "x")).status_code == 401
    assert await _rows(wd.db) == []


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
async def test_proxy_headers_answer_403_even_with_the_right_token(wd, header):
    assert (await wd.post(headers={header: "203.0.113.9"})).status_code == 403


async def test_non_loopback_client_answers_403(wd):
    assert (await wd.post(client=("10.0.0.7", 40000))).status_code == 403
    assert (await wd.post(client=("::1", 40000))).status_code == 200


async def test_51_events_answer_422(wd):
    res = await wd.post(body=_body([_event() for _ in range(51)]))
    assert res.status_code == 422
    assert (await wd.post(body=_body([_event() for _ in range(50)]))).status_code == 200


async def test_body_over_256_kb_answers_413(wd):
    big = _body(services={"x": {"detail": "a" * 270_000}})
    assert (await wd.post(body=big)).status_code == 413


async def test_unknown_and_backend_only_kinds_are_dropped_and_counted(wd):
    good, made_up, forged, silent = _event(), _event("made_up"), _event("retention_confirmed"), _event("watchdog_silent")
    res = await wd.post(body=_body([good, made_up, forged, silent]))
    assert res.status_code == 200
    assert res.json()["droppedEvents"] == 3 and res.json()["acceptedEventIds"] == [good["id"]]
    assert [r["healthEvent"] for r in await _rows(wd.db)] == ["service_down"]


async def test_error_strings_are_capped_at_300_characters_and_unknown_params_dropped(wd):
    event = _event("restart", params={"error": "e" * 1000, "attempt": 1, "ok": False, "evil": "<script>",
                                      "nested": {"a": 1}})
    await wd.post(body=_body([event]))
    row = (await _rows(wd.db))[0]
    assert len(row["healthParams"]["error"]) == 300
    assert set(row["healthParams"]) <= set(selfheal.PARAM_KEYS)
    assert "evil" not in row["healthParams"] and "nested" not in row["healthParams"]


async def test_event_time_is_clamped_so_a_replayed_spool_keeps_its_order(wd):
    now = datetime.now(timezone.utc)
    old = _event(at=(now - timedelta(days=30)).isoformat())
    future = _event(at=(now + timedelta(days=3)).isoformat())
    bad = _event(at="not a time")
    await wd.post(body=_body([old, future, bad]))
    by_id = {r["id"]: r for r in await _rows(wd.db)}
    created_old = by_id["PH-" + old["id"]]["createdAt"].replace(tzinfo=timezone.utc)
    created_future = by_id["PH-" + future["id"]]["createdAt"].replace(tzinfo=timezone.utc)
    assert now - timedelta(days=7, minutes=1) <= created_old <= now - timedelta(days=6, hours=23)
    assert created_future <= datetime.now(timezone.utc) + timedelta(seconds=61)
    assert ("PH-" + bad["id"]) in by_id                                  # a bad time falls back to receipt time


async def test_results_route_needs_the_token_and_answers_ok(wd):
    body = {"v": 1, "delivered": [], "testResult": None}
    res = await wd.post("/api/internal/watchdog/results", body)
    assert res.status_code == 200 and res.json() == {"ok": True}
    assert (await wd.post("/api/internal/watchdog/results", body, token="nope")).status_code == 401
    assert (await wd.post("/api/internal/watchdog/results", body, headers={"X-Real-IP": "1.2.3.4"})
            ).status_code == 403


# ------------------------------------------------------------------ 82-16: one poison event never wedges the sync

HUGE = 10 ** 400
POISON = {"@@INF@@": "1e999", "@@NEG@@": "-Infinity", "@@BIG@@": "9" * 400}


def _raw(body):
    """The JSON text of a body, with each marker string replaced by a number Python cannot hold in a row."""
    text = json.dumps(body)
    for marker, literal in POISON.items():
        text = text.replace(json.dumps(marker), literal)
    return text


async def test_a_poison_batch_answers_200_and_the_next_sync_succeeds(wd):
    good = _event()
    bad = [_event("disk_forecast", target="/", params={"rung": 1, "forecastDays": marker})
           for marker in POISON]
    res = await wd.post(content=_raw(_body([good] + bad)))
    assert res.status_code == 200, res.text
    answer = res.json()
    assert good["id"] in answer["acceptedEventIds"]
    sent = [good["id"]] + [e["id"] for e in bad]
    not_accepted = [i for i in sent if i not in answer["acceptedEventIds"]]
    assert len(not_accepted) <= answer["droppedEvents"]               # the test sync_cycle uses to clear the spool
    for row in await _rows(wd.db):
        assert "forecastDays" not in row.get("healthParams", {})
    assert (await wd.post(body=_body([_event()]))).status_code == 200


@pytest.mark.parametrize("value,kept", [
    (float("inf"), False), (float("-inf"), False), (float("nan"), False), (HUGE, False), (-HUGE, False),
    (2 ** 63 - 1, True), (-2 ** 63, True), (2 ** 63, False), (-2 ** 63 - 1, False),
    (1.5, True), (0, True), (True, True), ("x", True)])
def test_clean_params_drops_numbers_a_row_cannot_hold(value, kept):
    out = selfheal.clean_params({"forecastDays": value})
    assert ("forecastDays" in out) is kept
    if kept:
        assert out["forecastDays"] == value


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), HUGE, -HUGE, 2 ** 63, -2 ** 63 - 1])
def test_scrub_stores_none_for_numbers_a_row_cannot_hold(value):
    assert selfheal._scrub(value) is None


@pytest.mark.parametrize("value", [2 ** 63 - 1, -2 ** 63, 1.5, 0, None, "x"])
def test_scrub_keeps_numbers_a_row_can_hold(value):
    assert selfheal._scrub(value) == value


def test_scrub_keeps_bools_and_reaches_every_depth():
    assert selfheal._scrub(True) is True and selfheal._scrub(False) is False
    assert selfheal._scrub({"a": {"b": [float("inf"), 1, {"c": HUGE}]}}) == {"a": {"b": [None, 1, {"c": None}]}}


@pytest.mark.parametrize("value,expected", [
    (float("inf"), None), (float("-inf"), None), (float("nan"), None), (1.4, 1), (2.5, 2), (True, None), ("3", None)])
def test_num_never_raises(value, expected):
    assert health_messages._num(value) == expected


def test_num_returns_without_raising_for_a_huge_integer():
    health_messages._num(HUGE)


def test_render_shows_a_dash_for_a_non_finite_number():
    out = health_messages.render("disk_forecast", {"target": "/", "rung": 1, "forecastDays": float("inf")}, "omni")
    assert health_messages.DASH in out["resultText"]


def _patch_record(monkeypatch, fail_id, exc):
    real = ledger.record_platform_health

    async def record(db, event_id, *args, **kwargs):
        if event_id == fail_id:
            raise exc
        return await real(db, event_id, *args, **kwargs)

    monkeypatch.setattr(ledger, "record_platform_health", record)


async def test_a_render_failure_drops_one_event_and_the_loop_continues(wd, monkeypatch, caplog):
    events = [_event(), _event(), _event()]
    _patch_record(monkeypatch, events[1]["id"], ZeroDivisionError("secret-text"))
    caplog.set_level(logging.ERROR)
    res = await wd.post(body=_body(events))
    assert res.status_code == 200
    assert res.json()["droppedEvents"] == 1
    assert res.json()["acceptedEventIds"] == [events[0]["id"], events[2]["id"]]
    assert events[1]["id"] in caplog.text and "ZeroDivisionError" in caplog.text
    assert "secret-text" not in caplog.text


async def test_a_ledger_outage_stays_neither_accepted_nor_dropped(wd, monkeypatch):
    events = [_event(), _event()]
    _patch_record(monkeypatch, events[0]["id"], ledger.LedgerUnavailable("down"))
    res = await wd.post(body=_body(events))
    assert res.status_code == 200
    assert res.json()["acceptedEventIds"] == [events[1]["id"]] and res.json()["droppedEvents"] == 0


# ------------------------------------------------------------------ 82-16: the certificate rule follows daysLeft

CERT_RULES = [(31, "cert-expiry-30d"), (30, "cert-expiry-30d"), (15, "cert-expiry-30d"), (14, "cert-expiry-14d"),
              (8, "cert-expiry-14d"), (7, "cert-expiry-7d"), (2, "cert-expiry-7d"), (1, "cert-expiry-1d"),
              (0, "cert-expiry-1d"), (-3, "cert-expiry-1d"), (14.4, "cert-expiry-30d"), (7.4, "cert-expiry-14d"),
              (1.4, "cert-expiry-7d"), (0.6, "cert-expiry-1d")]


@pytest.mark.parametrize("rung", [1, 2, 3])
@pytest.mark.parametrize("days,rule", CERT_RULES)
def test_cert_rule_follows_the_days_left(days, rule, rung):
    out = health_messages.render("cert_warning", {"target": "/etc/ssl/x.pem", "rung": rung, "daysLeft": days}, "omni")
    assert out["ruleId"] == rule


def test_an_unreadable_certificate_has_its_own_rule_and_wording():
    params = {"target": "/etc/ssl/gone.pem", "rung": 2, "error": "unreadable"}
    out = health_messages.render("cert_warning", params, "omni")
    assert out["ruleId"] == "cert-unreadable" and "cert-unreadable" in health_messages.RULE_IDS
    assert out["reasonText"] == "Can't read this file."
    assert "/etc/ssl/gone.pem" in out["resultText"] and "read" in out["resultText"]
    assert "expires" not in out["resultText"] and health_messages.DASH not in out["resultText"]
    assert health_messages.chip_for("cert_warning", params) == "warning"


@pytest.mark.parametrize("days", [float("inf"), float("nan")])
def test_a_non_finite_days_left_reads_as_unreadable(days):
    out = health_messages.render("cert_warning", {"target": "/x.pem", "rung": 1, "daysLeft": days}, "omni")
    assert out["ruleId"] == "cert-unreadable"


def test_a_readable_certificate_keeps_its_copy():
    out = health_messages.render("cert_warning", {"target": "/x.pem", "rung": 1, "daysLeft": 12.4,
                                                  "notAfter": "2026-11-11T12:00:00Z"}, "omni")
    assert out["reasonText"] == "Expires in 12 days."
    assert out["resultText"].endswith("Replacing a pinned certificate needs an agent update.")


async def test_the_stored_row_carries_the_right_rule(wd):
    readable = _event("cert_warning", target="/etc/ssl/extra.pem", severity="warning",
                      params={"rung": 1, "daysLeft": 12.5, "notAfter": "2026-11-11T12:00:00Z"})
    unreadable = _event("cert_warning", target="/etc/ssl/gone.pem", severity="warning",
                        params={"rung": 2, "error": "unreadable"})
    assert (await wd.post(body=_body([readable, unreadable]))).status_code == 200
    by_id = {r["id"]: r for r in await _rows(wd.db)}
    row = by_id["PH-" + readable["id"]]
    assert row["reason"]["ruleId"] == "cert-expiry-14d"
    row = by_id["PH-" + unreadable["id"]]
    assert row["reason"]["ruleId"] == "cert-unreadable" and row["healthChip"] == "warning"
