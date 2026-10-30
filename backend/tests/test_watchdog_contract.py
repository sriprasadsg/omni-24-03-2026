"""End to end: a real watchdog run against the real backend routes (Phase 82, plan 82-05, HEAL-05, D-04, D-21).

The watchdog's ``http`` seam is a bridge: requests for http://127.0.0.1:5000 are served by the real ingest and
platform routers (throwaway MongoDB, client address forced to loopback, token shared through a tmp
CREDENTIALS_DIRECTORY and a tmp ingest.token), requests for events.pagerduty.com go to a recorder that plays
PagerDuty. ``run_once`` is blocking, so it runs in a worker thread while the test's event loop (which owns the
Motor handle) serves the app: the bridge hands each backend request to that loop.

Run these against a private mongod: ``MONGO_TEST_URL=mongodb://127.0.0.1:<port>``.
"""
import asyncio
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._watchdog_oncall_world import ROUTING_KEY, write_env
from tests._watchdog_restart_world import World
from tests._watchdog_support import FakeClock, load_watchdog
from tests.autonomy_support import seed_tenant

load_watchdog()
import watchdog_ingest_endpoints as ingest  # noqa: E402
from autonomous_ops import notify, oncall, selfheal  # noqa: E402
from omni_watchdog import config as config_mod, paging, run as run_mod  # noqa: E402

TOKEN = "contract-token-0123456789"
HOST = "omni-contract"
HEALTH = "/api/platform/autonomous-ops/health"
TEST_ALERT = HEALTH + "/test-alert"
ACTIVITY = "/api/platform/autonomous-ops/actions?bucket=platform_health"


class Bridge:
    """The watchdog's http seam: the real backend routers behind 127.0.0.1:5000, a recorder for PagerDuty."""

    def __init__(self, app, loop):
        self.app, self.loop = app, loop
        self.pagerduty = []
        self.other = []
        self.heartbeat = []

    def __call__(self, method, url, headers, body, timeout):
        parts = urllib.parse.urlsplit(url)
        if parts.netloc == "127.0.0.1:5000":
            if parts.path == "/api/health/ready":
                return 200, b'{"status":"ready"}'
            future = asyncio.run_coroutine_threadsafe(self._backend(method, url, headers, body), self.loop)
            return future.result(timeout=30)
        if parts.netloc == "events.pagerduty.com" and parts.path == "/v2/enqueue":
            self.pagerduty.append(json.loads(body))
            return 202, b'{"status":"success","message":"Event processed"}'
        self.other.append(url)
        raise ConnectionRefusedError("no route")

    async def _backend(self, method, url, headers, body):
        transport = httpx.ASGITransport(app=self.app, client=("127.0.0.1", 50000))
        async with httpx.AsyncClient(transport=transport) as client:
            reply = await client.request(method, url, headers=headers, content=body)
        return reply.status_code, reply.content

    def triggers(self):
        return [b for b in self.pagerduty if b["event_action"] == "trigger"]

    def resolves(self):
        return [b for b in self.pagerduty if b["event_action"] == "resolve"]


class Contract:
    """One watchdog installation talking to the real backend routes."""

    def __init__(self, api, tmp_path, monkeypatch):
        self.api, self.db = api, api.db
        creds = tmp_path / "creds"
        creds.mkdir()
        (creds / "omni-watchdog-token").write_text(TOKEN + "\n", encoding="utf-8")
        monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(creds))
        monkeypatch.setattr(ingest, "get_database", lambda: api.db)
        api.app.include_router(ingest.router)
        self.clock = FakeClock(time.time())
        self.world = World(self.clock, monkeypatch)          # all four services healthy; answers systemctl
        monkeypatch.setattr(run_mod.warnings, "evaluate", lambda *args, **kwargs: ([], [], []))
        token = tmp_path / "ingest.token"
        token.write_text(TOKEN, encoding="utf-8")
        self.env = tmp_path / "oncall.env"
        write_env(self.env, ONCALL_TYPE="pagerduty", PAGERDUTY_ROUTING_KEY=ROUTING_KEY)
        self.cfg = {"ingest_token_path": str(token), "host": HOST, "stop_file": str(tmp_path / "STOP"),
                    "oncall_env_path": str(self.env)}
        self.state_dir = str(tmp_path / "state")
        self.bridge = Bridge(api.app, asyncio.get_running_loop())

    async def run_once(self):
        self.clock.advance(60)
        return await asyncio.to_thread(run_mod.run_once, self.cfg, self.state_dir, run=self.world, http=self.bridge,
                                       now=self.clock, sleep=self.clock.advance)

    async def health(self):
        reply = await self.api.call("GET", HEALTH, role="super_admin")
        assert reply.status_code == 200
        return reply.json()


@pytest.fixture
async def contract(api, monkeypatch, tmp_path):
    await selfheal.ensure_indexes(api.db)
    await oncall.ensure_indexes(api.db)
    await api.db.users.insert_one({"email": "root@example.test", "name": "Ana Root"})
    return Contract(api, tmp_path, monkeypatch)


async def test_a_queued_notice_reaches_the_channel_once_and_is_marked_delivered(contract):
    await seed_tenant(contract.db, "t1")
    await notify.notify(contract.db, "t1", title="Automatic actions stopped", message="Stopped by Ana.", severity="warning")
    summary = await contract.run_once()
    assert summary["synced"] is True
    assert len(contract.bridge.triggers()) == 1 and contract.bridge.resolves() == []
    trigger = contract.bridge.triggers()[0]
    assert "Automatic actions stopped" in trigger["payload"]["summary"]
    assert trigger["payload"]["severity"] == "warning" and trigger["routing_key"] == ROUTING_KEY
    doc = await contract.db.oncall_outbox.find_one({}, {"_id": 0})
    assert trigger["dedup_key"] == "omni:%s:%s" % (HOST, doc["id"])
    assert doc["deliveredAt"] is not None and doc["ok"] is True and doc["error"] is None


async def test_a_super_admin_test_alert_is_delivered_resolved_and_shown_on_the_health_view(contract):
    await contract.run_once()                                         # the first heartbeat arms the watchdog state
    asked = await contract.api.call("POST", TEST_ALERT, role="super_admin", username="root@example.test")
    assert asked.status_code == 200
    request_id = asked.json()["testAlert"]["id"]
    await contract.run_once()
    key = "omni:%s:test:%s" % (HOST, request_id)
    assert [(b["event_action"], b["dedup_key"]) for b in contract.bridge.pagerduty] == [("trigger", key), ("resolve", key)]
    health = await contract.health()
    assert health["testAlert"]["id"] == request_id and health["testAlert"]["state"] == "delivered"
    assert health["testAlert"]["error"] is None and health["testAlert"]["sentAt"] is not None
    assert health["oncall"]["type"] == "pagerduty" and health["oncall"]["status"] == "working"
    await contract.run_once()                                         # the test_alert event arrives with this sync
    rows = [r for r in (await contract.api.call("GET", ACTIVITY, role="super_admin")).json()["items"]
            if r["actionLabel"] == "Test alert"]
    assert len(rows) == 1 and rows[0]["reasonText"] == "Requested by Ana Root." and rows[0]["healthChip"] == "healthy"
    assert rows[0]["id"] == "PH-test-" + request_id


async def test_the_next_run_sends_nothing_new_to_the_channel(contract):
    await seed_tenant(contract.db, "t1")
    await contract.run_once()
    await notify.notify(contract.db, "t1", title="Circuit breaker tripped", message="Paused for an hour.", severity="warning")
    request_id = (await contract.api.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]["id"]
    await contract.run_once()
    assert len(contract.bridge.triggers()) == 2 and len(contract.bridge.resolves()) == 1      # the notice, and the test trigger
    before = list(contract.bridge.pagerduty)
    await contract.run_once()
    await contract.run_once()
    assert contract.bridge.pagerduty == before
    assert (await contract.health())["testAlert"]["id"] == request_id
    assert await contract.db.oncall_outbox.count_documents({"deliveredAt": None}) == 0
    assert contract.bridge.other == []


async def test_a_channel_failure_is_shown_as_not_working_and_the_message_is_not_resent(contract):
    await seed_tenant(contract.db, "t1")
    await contract.run_once()
    request_id = (await contract.api.call("POST", TEST_ALERT, role="super_admin")).json()["testAlert"]["id"]
    write_env(contract.env, ONCALL_TYPE="webhook", WEBHOOK_URL="https://hooks.example.test/hook")   # no route: refused
    await contract.run_once()
    health = await contract.health()
    assert health["testAlert"]["state"] == "failed" and health["testAlert"]["id"] == request_id
    assert health["testAlert"]["error"] == "The webhook could not be reached (ConnectionRefusedError)."
    assert health["oncall"]["status"] == "not_working"
    assert contract.bridge.other.count("https://hooks.example.test/hook") == 3         # one try and two retries, no more
    await contract.run_once()
    assert contract.bridge.other.count("https://hooks.example.test/hook") == 3


# --- the real urllib client against a loopback server ---------------------------------------------------------------

def test_the_real_http_client_posts_a_webhook_to_a_loopback_server_once(tmp_path):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        env = write_env(tmp_path / "oncall.env", ONCALL_TYPE="webhook", WEBHOOK_URL="http://127.0.0.1:%d/hook" % server.server_port)
        channel = config_mod.load_oncall(env)
        message = paging.compose(channel, "trigger", "omni:h:k", "critical", "MongoDB is down.", {}, "h", 1_800_000_000.0)
        assert paging.send(run_mod.real_http, channel, message, sleep=lambda s: None) == (True, None)
    finally:
        server.shutdown()
        server.server_close()
    assert received == [("/hook", message)]
    assert message["action"] == "trigger" and message["dedupKey"] == "omni:h:k"
