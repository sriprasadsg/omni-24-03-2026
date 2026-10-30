"""Watchdog on-call delivery (Phase 82, plan 82-05, HEAL-05 and HEAL-02).

Every external effect is faked: ``FakeHttp`` answers the backend, PagerDuty, a webhook and the heartbeat
service; the fake host and clock come from the restart world. Nothing opens a socket except the one test
that points the real urllib client at a loopback server.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests._watchdog_oncall_world import (ENQUEUE, HEARTBEAT_PATH, HEARTBEAT_URL, HOST, ROUTING_KEY, SECRETS, WEBHOOK_PATH,
                                          WEBHOOK_URL, give_up, orig, write_env)  # noqa: F401  (orig is a fixture)
from tests._watchdog_support import FakeClock, FakeHttp

from omni_watchdog import config as config_mod, incidents, paging, run as run_mod  # noqa: E402

PD = "https://events.pagerduty.com/v2/enqueue"


# --- Task 1: the tracer - a gave-up service becomes exactly one page and, when healthy, one resolve ---

def test_a_gave_up_service_sends_exactly_one_trigger_over_many_runs(orig):
    orig.channel("pagerduty")
    next_run = give_up(orig)
    assert len(orig.triggers()) == 1                                # sent in the very run that gave up
    for step in range(5):                                           # five more runs while it is still down
        orig.at(next_run + 60 * step)
    assert len(orig.triggers()) == 1 and orig.resolves() == []
    trigger = orig.triggers()[0]
    assert trigger["routing_key"] == ROUTING_KEY
    assert trigger["event_action"] == "trigger"
    assert trigger["dedup_key"] == "omni:%s:svc:mongod" % HOST
    assert trigger["payload"]["severity"] == "critical"
    assert trigger["payload"]["source"] == HOST
    assert "MongoDB" in trigger["payload"]["summary"] and len(trigger["payload"]["summary"]) <= 1024
    assert set(trigger) == {"routing_key", "event_action", "dedup_key", "payload"}


def test_the_incident_is_marked_sent_with_its_page_key_and_one_page_sent_event_is_reported(orig):
    orig.channel("pagerduty")
    give_up(orig)
    incident = orig.saved()["incidents"]["svc:mongod"]
    assert incident["sent"] is True and incident["pageKey"] == "svc:mongod" and incident["sentAt"] is not None
    sent = orig.sync_events("page_sent")
    assert len(sent) == 1
    assert sent[0]["params"]["channel"] == "pagerduty" and "MongoDB" in sent[0]["params"]["incident"]
    assert orig.saved()["oncallLast"]["ok"] is True and orig.saved()["oncallLast"]["kind"] == "page"


def test_a_service_healthy_for_an_hour_resolves_the_page_once_with_the_same_dedup_key(orig):
    orig.channel("pagerduty")
    next_run = give_up(orig)
    orig.world.down.discard("mongod")
    orig.at(next_run)                                               # healthy again, the hour starts
    assert orig.resolves() == []
    orig.at(next_run + 3599)
    assert orig.resolves() == []
    orig.at(next_run + 3600)                                        # budget re-armed, incident cleared
    assert len(orig.resolves()) == 1
    resolve = orig.resolves()[0]
    assert resolve == {"routing_key": ROUTING_KEY, "event_action": "resolve", "dedup_key": "omni:%s:svc:mongod" % HOST}
    assert len(orig.sync_events("page_resolved")) == 1
    assert "svc:mongod" not in orig.saved()["incidents"]            # the pager dropped it
    orig.at(next_run + 3660)
    assert len(orig.resolves()) == 1 and len(orig.triggers()) == 1


def test_with_no_channel_nothing_is_sent_and_the_incident_stays_as_the_restart_plan_left_it(orig):
    give_up(orig)                                                   # no oncall.env at all
    assert orig.pagerduty() == []
    assert orig.saved()["incidents"]["svc:mongod"]["sent"] is False
    assert orig.saved()["incidents"]["svc:mongod"]["pageKey"] is None


def test_a_channel_set_up_later_pages_an_incident_that_is_still_open_once(orig):
    next_run = give_up(orig)
    orig.at(next_run)
    assert orig.pagerduty() == []
    orig.channel("pagerduty")
    orig.at(next_run + 60)
    orig.at(next_run + 120)
    assert len(orig.triggers()) == 1


def test_the_state_is_saved_with_the_page_key_before_the_trigger_leaves(orig, monkeypatch):
    orig.channel("pagerduty")
    seen = []
    real = orig.http.routes[("POST", ENQUEUE)]

    def spy(request):
        seen.append(orig.saved()["incidents"]["svc:mongod"].copy())
        return real[0]
    orig.http.set("POST", ENQUEUE, spy)
    give_up(orig)
    assert seen[0]["pageKey"] == "svc:mongod" and seen[0]["sent"] is False     # on disk before the send (Pitfall 15)
    assert orig.saved()["incidents"]["svc:mongod"]["sent"] is True


def test_the_pager_uses_the_default_verified_ssl_context_only():
    source = open(paging.__file__, encoding="utf-8").read()
    assert "CERT_NONE" not in source and "_create_unverified_context" not in source
    assert source.count("events.pagerduty.com/v2/enqueue") == 1


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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = write_env(tmp_path / "oncall.env", ONCALL_TYPE="webhook",
                        WEBHOOK_URL="http://127.0.0.1:%d/hook" % server.server_port)
        channel = config_mod.load_oncall(env)
        message = paging.compose(channel, "trigger", "omni:h:k", "critical", "MongoDB is down.", {}, "h", 1_800_000_000.0)
        assert paging.send(run_mod.real_http, channel, message, sleep=lambda s: None) == (True, None)
    finally:
        server.shutdown()
        server.server_close()
    assert received == [("/hook", message)]
    assert message["action"] == "trigger" and message["dedupKey"] == "omni:h:k"
