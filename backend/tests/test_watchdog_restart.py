"""Watchdog restart decisions (Phase 82, plan 82-03, HEAL-01 and HEAL-02).

Nothing here touches the host: ``World`` is a fake machine whose units go down and come back, answers
``systemctl`` through the run seam, serves the backend through the http seam and moves the fake clock
while the watchdog polls. Time is absolute (``Rig.at(seconds)``), so the D-07 timeline is exact.
"""
import json
import random

import pytest

from tests._watchdog_support import FakeClock, FakeHttp, load_watchdog

load_watchdog()
from omni_watchdog import UNITS, checks, restart, run as run_mod  # noqa: E402

TOKEN = "t0k3n-restart-tests"
SYNC = "/api/internal/watchdog/sync"
READY = "/api/health/ready"
UNIT_TO_SID = {unit: sid for sid, unit in UNITS.items()}
RESTART_ARGV = {sid: ["systemctl", "restart", "--no-block", unit] for sid, unit in UNITS.items()}


class World:
    """A fake host. ``down`` holds the service ids that fail their checks; a restart heals a service
    after ``heal_delay[sid]`` seconds, never when that is None, and is refused when ``refuse`` is set."""

    def __init__(self, clock, monkeypatch):
        self.clock = clock
        self.down = set()
        self.failed = set()                 # services whose unit answers "failed" to is-active
        self.heal_delay = {sid: 3 for sid in UNITS}
        self.healed_at = {}
        self.refuse = False
        self.demo = False                   # a backend that is down answers 503 demo_mode, not a refusal
        self.ollama_active = False
        self.calls = []
        self.restarts = []                  # (epoch, unit)
        monkeypatch.setattr(checks, "mongo_ping", lambda *a, **k: self.alive("mongod"))
        monkeypatch.setattr(checks, "nginx_probe", lambda *a, **k: self.alive("nginx"))

    def alive(self, sid):
        due = self.healed_at.get(sid)
        if due is not None and self.clock() >= due:
            self.down.discard(sid)
            del self.healed_at[sid]
        if sid == "ollama":
            return self.ollama_active
        return sid not in self.down

    def __call__(self, argv, timeout):
        assert isinstance(argv, list)
        self.calls.append(list(argv))
        verb, unit = (argv[1], argv[-1]) if len(argv) >= 3 else (None, None)
        sid = UNIT_TO_SID.get(unit)
        if verb == "is-active":
            if self.alive(sid):
                return 0, "active\n"
            return 3, ("failed" if sid in self.failed else "inactive") + "\n"
        if verb == "reset-failed":
            self.failed.discard(sid)
            return 0, ""
        if verb == "restart":
            self.restarts.append((self.clock(), unit))
            if self.refuse:
                return 1, "Failed to restart %s: Access denied\n" % unit
            delay = self.heal_delay.get(sid)
            if sid == "omni-backend" and "mongod" in self.down:
                delay = None                # a backend cannot come up without its database
            if delay is not None and sid in self.down:
                self.healed_at[sid] = self.clock() + delay
            return 0, ""
        return 0, ""

    def restart_argvs(self):
        return [c for c in self.calls if c[1:2] == ["restart"]]

    def restarts_of(self, sid):
        return [t for t, unit in self.restarts if unit == UNITS[sid]]

    def backend_ready(self, _request):
        if self.alive("omni-backend"):
            return 200, {"status": "ready"}
        if self.demo:
            return 503, {"status": "not_ready", "demo_mode": True}
        return ConnectionRefusedError("backend down")

    def ollama_root(self, _request):
        if self.alive("ollama"):
            return 200, "Ollama is running"
        return ConnectionRefusedError("ollama down")


class Rig:
    """One watchdog installation on a fake host: run it at absolute times, read what it reported."""

    def __init__(self, tmp_path, monkeypatch, **config):
        self.tmp = tmp_path
        self.clock = FakeClock()
        self.base = self.clock()
        self.world = World(self.clock, monkeypatch)
        self.http = FakeHttp()
        self.http.set("GET", READY, self.world.backend_ready)
        self.http.set("GET", "/", self.world.ollama_root)
        self.http.set("POST", SYNC, FakeHttp.accept_all)
        token = tmp_path / "ingest.token"
        token.write_text(TOKEN)
        self.stop_file = tmp_path / "STOP"
        self.cfg = {"ingest_token_path": str(token), "host": "omni-test", "stop_file": str(self.stop_file)}
        self.cfg.update(config)
        self.state_dir = str(tmp_path / "state")
        self.summary = None

    def at(self, seconds):
        """Run once at ``seconds`` after the first run's clock."""
        self.clock.t = self.base + seconds
        self.summary = run_mod.run_once(self.cfg, self.state_dir, run=self.world, http=self.http,
                                        now=self.clock, sleep=self.clock.advance)
        return self.summary

    def kinds(self):
        return [e["kind"] for e in self.summary["events"]]

    def body(self):
        return self.http.posted(SYNC)[-1]

    def svc(self, sid):
        return self.body()["services"][sid]

    def saved(self):
        with open(self.state_dir + "/state.json", encoding="utf-8") as handle:
            return json.load(handle)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


# --- Task 1: the tracer - mongod fails twice, is restarted through systemctl, comes back ----------

def test_mongod_failing_two_checks_is_restarted_and_reported_healthy_in_the_sync_body(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = 4
    rig.at(0)
    assert rig.world.restart_argvs() == []                  # first failed check: debounce, nothing yet
    assert rig.svc("mongod")["state"] == "checking"

    rig.at(60)
    assert rig.world.restart_argvs() == [["systemctl", "restart", "--no-block", "mongod.service"]]
    body = rig.body()
    restart_events = [e for e in body["events"] if e["kind"] == "restart"]
    assert len(restart_events) == 1
    assert restart_events[0]["target"] == "mongod"
    assert restart_events[0]["params"] == {"attempt": 1, "ok": True, "seconds": 4}
    assert body["services"]["mongod"]["state"] == "healthy"
    assert body["services"]["mongod"]["restartsInWindow"] == 1
    assert [e["kind"] for e in body["events"]] == ["service_down", "restart", "service_recovered"]


def test_a_unit_that_answers_failed_is_reset_before_it_is_restarted(rig):
    rig.world.down.add("nginx")
    rig.world.failed.add("nginx")
    rig.at(0)
    rig.at(60)
    mutating = [c for c in rig.world.calls if c[1:2] in (["restart"], ["reset-failed"])]
    assert mutating == [["systemctl", "reset-failed", "nginx.service"], RESTART_ARGV["nginx"]]


def test_a_unit_that_is_merely_inactive_is_not_reset(rig):
    rig.world.down.add("nginx")
    rig.at(0)
    rig.at(60)
    assert [c for c in rig.world.calls if c[1:2] == ["reset-failed"]] == []
    assert rig.world.restart_argvs() == [RESTART_ARGV["nginx"]]


def test_a_service_that_does_not_come_back_in_20_seconds_stays_restarting(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    rig.at(0)
    rig.at(60)
    event = [e for e in rig.body()["events"] if e["kind"] == "restart"][0]
    assert event["params"]["ok"] is False and event["params"]["attempt"] == 1
    assert "20 s" in event["params"]["error"]
    mongod = rig.svc("mongod")
    assert mongod["state"] == "restarting"
    assert mongod["restartsInWindow"] == 1
    assert mongod["nextRestartAt"] is not None


def test_polling_checks_every_2_seconds_for_at_most_20_seconds():
    clock, slept, checks_made = FakeClock(), [], []

    def sleep(seconds):
        slept.append(seconds)
        clock.advance(seconds)

    def never():
        checks_made.append(clock())
        return False

    assert restart.poll_healthy(never, clock, sleep) == (False, None)
    assert slept == [2] * 10 and len(checks_made) == 10


def test_polling_cannot_spin_when_the_clock_never_moves():
    slept = []
    assert restart.poll_healthy(lambda: False, FakeClock(), slept.append) == (False, None)
    assert len(slept) == 10


def test_restart_unit_refuses_a_unit_outside_the_fixed_list():
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return 0, ""

    with pytest.raises(ValueError):
        restart.restart_unit(run, "ssh.service")
    with pytest.raises(ValueError):
        restart.restart_unit(run, "mongod.service; reboot")
    assert calls == []


def test_restart_unit_reports_a_non_zero_exit_with_capped_one_line_error_text():
    def run(argv, timeout):
        if argv[1] == "restart":
            return 1, "Failed to restart x.service:\n\tAccess denied\x07 " + "z" * 600
        return 3, "inactive\n"

    ok, error = restart.restart_unit(run, "nginx.service")
    assert ok is False
    assert error.startswith("Failed to restart x.service: Access denied")
    assert len(error) == 300 and "\n" not in error and "\x07" not in error


def test_every_systemctl_call_is_an_argument_list_on_a_known_unit(rig):
    rig.world.down.update({"mongod", "nginx"})
    rig.at(0)
    rig.at(60)
    for argv in rig.world.calls:
        assert argv[0] == "systemctl" and argv[1] in ("is-active", "restart", "reset-failed")
        assert argv[-1] in UNITS.values()
    for argv in rig.world.restart_argvs():
        assert argv[2] == "--no-block"
