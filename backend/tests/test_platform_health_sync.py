"""Watchdog sync endpoint (Phase 82, plan 82-01): POST /api/internal/watchdog/sync and /results.

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py (skipped when no server
is reachable). The loopback client address is forced by giving httpx's ASGITransport a
``client=("127.0.0.1", 50000)`` scope entry, because the test client's default host is "testclient".
The token credential is a file under a tmp CREDENTIALS_DIRECTORY, read on every call.
"""
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
