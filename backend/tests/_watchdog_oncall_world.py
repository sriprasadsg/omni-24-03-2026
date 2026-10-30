"""Helpers for the watchdog on-call tests (Phase 82, plan 82-05, HEAL-05).

Builds on the restart world: a fake host, a fake clock and ``FakeHttp``. FakeHttp routes by path, so the
PagerDuty endpoint (``/v2/enqueue``), a webhook path and a heartbeat path are plain routes; every request
keeps its full URL so a test can prove which host it went to. Nothing here opens a socket.
"""
import json

import pytest

from tests._watchdog_restart_world import SYNC, Rig, run_mod

ROUTING_KEY = "R0UTINGKEY-secret-0123456789abcdef"
WEBHOOK_URL = "https://hooks.example.test/services/T000/B000/SECRET-WEBHOOK-PATH"
WEBHOOK_PATH = "/services/T000/B000/SECRET-WEBHOOK-PATH"
HEARTBEAT_URL = "https://hc.example.test/ping/SECRET-HEARTBEAT-UUID"
HEARTBEAT_PATH = "/ping/SECRET-HEARTBEAT-UUID"
ENQUEUE = "/v2/enqueue"
RESULTS = "/api/internal/watchdog/results"
SECRETS = (ROUTING_KEY, WEBHOOK_URL, WEBHOOK_PATH, HEARTBEAT_URL, HEARTBEAT_PATH)

HOST = "omni-test"          # the Rig's configured host


def write_env(path, **values):
    """Write an oncall.env with the given KEY=VALUE pairs; returns the path as text."""
    path.write_text("".join("%s=%s\n" % (key, value) for key, value in values.items()), encoding="utf-8")
    return str(path)


class OncallRig(Rig):
    """A Rig whose oncall.env can be rewritten between runs and whose channel routes are scripted."""

    def __init__(self, tmp_path, monkeypatch, **config):
        super().__init__(tmp_path, monkeypatch, **config)
        self.env = tmp_path / "oncall.env"
        self.cfg["oncall_env_path"] = str(self.env)
        self.http.set("POST", RESULTS, (200, {"ok": True}))

    def channel(self, kind="pagerduty", **extra):
        values = {"ONCALL_TYPE": kind}
        if kind == "pagerduty":
            values["PAGERDUTY_ROUTING_KEY"] = ROUTING_KEY
        elif kind == "webhook":
            values["WEBHOOK_URL"] = WEBHOOK_URL
        values.update(extra)
        write_env(self.env, **values)
        if kind == "pagerduty":
            self.http.set("POST", ENQUEUE, (202, {"status": "success"}))
        elif kind == "webhook":
            self.http.set("POST", WEBHOOK_PATH, (200, "ok"))
        return self

    def sync_says(self, outbox=None, test_request=None):
        """Make the fake backend answer every sync with this outbox and test request."""
        def answer(request):
            status, payload = self.http.accept_all(request)
            payload["outbox"] = list(outbox or [])
            payload["testRequest"] = test_request
            return status, payload
        self.http.set("POST", SYNC, answer)

    def pagerduty(self):
        """Bodies of every request that went to the PagerDuty endpoint, after proving the host."""
        found = [r for r in self.http.requests if r["path"] == ENQUEUE]
        for request in found:
            assert request["url"] == "https://events.pagerduty.com/v2/enqueue"
        return [json.loads(r["body"]) for r in found]

    def triggers(self):
        return [b for b in self.pagerduty() if b["event_action"] == "trigger"]

    def resolves(self):
        return [b for b in self.pagerduty() if b["event_action"] == "resolve"]

    def webhook(self):
        return [json.loads(r["body"]) for r in self.http.requests if r["path"] == WEBHOOK_PATH]

    def results(self):
        return self.http.posted(RESULTS)

    def run_events(self, kind):
        return [e for e in self.summary["events"] if e["kind"] == kind]

    def sync_events(self, kind):
        return [e for e in self.body()["events"] if e["kind"] == kind]


@pytest.fixture
def orig(tmp_path, monkeypatch):
    # certificate and disk warnings (82-04) have their own suite
    monkeypatch.setattr(run_mod.warnings, "evaluate", lambda *args, **kwargs: ([], [], []))
    return OncallRig(tmp_path, monkeypatch)


def give_up(rig, service="mongod"):
    """Run the A1 timeline until the service has given up (run at 480 s); returns the next free run time."""
    rig.world.down.add(service)
    rig.world.heal_delay[service] = None
    for t in (0, 60, 120, 180, 240, 300, 360, 420, 480):
        rig.at(t)
    return 540
