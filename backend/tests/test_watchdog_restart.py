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
        self.refuse_text = "Failed to restart %s: Access denied\n"
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
                return 1, self.refuse_text % unit if "%s" in self.refuse_text else self.refuse_text
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


# --- Task 2: the budget - waits, window, gave up once, re-arm, refusals --------------------------

from omni_watchdog import incidents, services  # noqa: E402


def drive(rig, times):
    """Run at each absolute time; one row per run: (t, restarts issued by this run, mongod state, event kinds)."""
    rows = []
    for t in times:
        before = len(rig.world.restart_argvs())
        rig.at(t)
        rows.append((t, len(rig.world.restart_argvs()) - before, rig.svc("mongod")["state"], rig.kinds()))
    return rows


# D-07 / A1, runs one minute apart, MongoDB never comes back:
# time  restarts-issued  state        events
TIMELINE = [
    (0,    0, "checking",   []),
    (60,   1, "restarting", ["service_down", "restart"]),
    (120,  1, "restarting", ["restart"]),
    (180,  0, "restarting", []),
    (240,  1, "restarting", ["restart"]),
    (300,  0, "restarting", []),
    (360,  0, "restarting", []),
    (420,  0, "restarting", []),
    (480,  0, "gave_up",    ["gave_up"]),
    (540,  0, "gave_up",    []),
]


def test_the_a1_timeline_restarts_at_60_120_240_and_gives_up_at_480(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    rows = drive(rig, [row[0] for row in TIMELINE])
    assert rows == TIMELINE
    assert [round(t - rig.base) for t in rig.world.restarts_of("mongod")] == [60, 120, 240]


def test_gave_up_is_reported_once_and_no_restart_follows_even_after_the_window_ages_out(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    drive(rig, [0, 60, 120, 180, 240, 300, 360, 420, 480])
    later = drive(rig, list(range(540, 600 + 12 * 60, 60)) + [1860, 1920, 2400, 3000, 3600, 5400])
    assert [row[1] for row in later] == [0] * len(later)
    assert [row[3] for row in later] == [[]] * len(later)       # no second gave_up event, ever
    assert {row[2] for row in later} == {"gave_up"}
    assert len(rig.world.restarts_of("mongod")) == 3            # the restarts leave the window; still not restarted
    mongod = rig.svc("mongod")
    assert mongod["restartsInWindow"] == 0 and mongod["nextRestartAt"] is None


def test_gave_up_opens_exactly_one_critical_incident_with_the_documented_shape(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    drive(rig, [0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600])
    store = rig.saved()["incidents"]
    assert list(store) == ["svc:mongod"]
    assert store["svc:mongod"] == {
        "key": "svc:mongod", "severity": "critical", "kind": "service_gave_up", "target": "mongod",
        "params": {"restarts": 3}, "openedAt": rig.base + 480, "pageKey": None, "sent": False, "clearedAt": None}
    assert rig.svc("mongod")["pagedAt"] == services.iso(rig.base + 480)
    assert len(incidents.open_incidents(rig.saved())) == 1


@pytest.mark.parametrize("seed", [20260101, 7, 99991])
def test_property_at_most_three_restarts_in_any_window_and_none_between_gave_up_and_rearm(tmp_path, monkeypatch, seed):
    rig = Rig(tmp_path, monkeypatch)
    rng = random.Random(seed)
    given_up = False
    for step in range(200):
        if rng.random() < 0.35:
            if "mongod" in rig.world.down:
                rig.world.down.discard("mongod")
            else:
                rig.world.down.add("mongod")
        rig.world.heal_delay["mongod"] = rng.choice([None, None, 3, 30])
        before = len(rig.world.restarts_of("mongod"))
        rig.at(step * 60)
        issued = len(rig.world.restarts_of("mongod")) - before
        kinds = rig.kinds()
        assert rig.svc("mongod")["restartsInWindow"] <= 3
        if given_up:
            assert issued == 0, "restarted while gave up (step %d)" % step
        if "budget_rearmed" in kinds:
            given_up = False
        if "gave_up" in kinds:
            given_up = True
    times = rig.world.restarts_of("mongod")
    for i, first in enumerate(times):
        assert len([t for t in times[i:] if t - first < 1800]) <= 3


def test_an_hour_of_health_returns_the_budget_exactly_at_3600_seconds_not_at_3599(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    drive(rig, [0, 60, 120, 180, 240, 300, 360, 420, 480])
    rig.world.down.discard("mongod")                    # MongoDB comes back by itself
    rig.at(540)
    assert rig.svc("mongod")["state"] == "healthy"
    assert "service_recovered" in rig.kinds()
    assert rig.svc("mongod")["budgetReturnsAt"] == services.iso(rig.base + 540 + 3600)
    rig.at(540 + 3599)
    assert "budget_rearmed" not in rig.kinds()
    assert rig.saved()["services"]["mongod"]["gaveUp"] is True
    assert incidents.open_incidents(rig.saved())[0]["key"] == "svc:mongod"
    assert rig.svc("mongod")["budgetReturnsAt"] == services.iso(rig.base + 540 + 3600)
    rig.at(540 + 3600)
    assert rig.kinds() == ["budget_rearmed"]
    saved = rig.saved()
    assert saved["services"]["mongod"]["gaveUp"] is False and saved["services"]["mongod"]["restarts"] == []
    assert incidents.open_incidents(saved) == []
    assert saved["incidents"]["svc:mongod"]["clearedAt"] == rig.base + 540 + 3600
    body = rig.body()["services"]["mongod"]
    assert body["budgetReturnsAt"] is None and body["pagedAt"] is None and body["restartsInWindow"] == 0
    rig.at(540 + 3600 + 60)                             # one budget_rearmed event only
    assert "budget_rearmed" not in rig.kinds()


def test_after_the_budget_returns_the_service_is_restarted_again(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    drive(rig, [0, 60, 120, 180, 240, 300, 360, 420, 480])
    rig.world.down.discard("mongod")
    rig.at(540)
    rig.at(540 + 3600)
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = 3
    rig.at(540 + 3660)
    rig.at(540 + 3720)
    event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert event["params"] == {"attempt": 1, "ok": True, "seconds": 4}     # healed at 3 s, seen by the 2 s poll at 4 s


def test_a_gave_up_service_that_is_down_again_stays_gave_up_and_the_hour_starts_over(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    drive(rig, [0, 60, 120, 180, 240, 300, 360, 420, 480])
    rig.world.down.discard("mongod")
    rig.at(540)                                         # healthy again, budget not back yet
    rig.world.down.add("mongod")
    rows = drive(rig, [600, 660, 720, 1200, 1800])
    assert [row[1] for row in rows] == [0] * 5
    assert [row[2] for row in rows] == ["checking"] + ["gave_up"] * 4       # first failed check is only debounced
    assert all("gave_up" not in row[3] for row in rows)
    rig.world.down.discard("mongod")
    rig.at(1860)                                        # the hour counts from here, not from 540
    rig.at(1860 + 3599)
    assert "budget_rearmed" not in rig.kinds()
    rig.at(1860 + 3600)
    assert rig.kinds() == ["budget_rearmed"]


def test_restarts_age_out_of_the_window_without_a_gave_up(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = 3
    rig.at(0)
    rig.at(60)
    assert rig.svc("mongod")["restartsInWindow"] == 1
    rig.at(1000)
    assert rig.svc("mongod")["restartsInWindow"] == 1
    rig.at(60 + 1800)
    assert rig.svc("mongod")["restartsInWindow"] == 0
    assert not rig.saved()["services"]["mongod"].get("gaveUp")


def test_a_refused_restart_is_a_failed_attempt_that_ends_in_gave_up_and_one_incident(rig):
    rig.world.down.add("mongod")
    rig.world.refuse = True
    rig.at(0)
    rig.at(60)
    event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert event["params"]["attempt"] == 1 and event["params"]["ok"] is False
    assert "Access denied" in event["params"]["error"] and len(event["params"]["error"]) <= 300
    assert rig.svc("mongod")["restartsInWindow"] == 1
    attempts = [1]
    for t in (120, 240):
        rig.at(t)
        attempts.append([e for e in rig.summary["events"] if e["kind"] == "restart"][0]["params"]["attempt"])
    assert attempts == [1, 2, 3]
    gave_up = 0
    for t in (480, 540, 600, 660, 720, 780, 840, 900, 960, 1020, 1080):
        rig.at(t)
        gave_up += rig.kinds().count("gave_up")
    assert gave_up == 1
    assert len(rig.world.restarts_of("mongod")) == 3
    assert [i["key"] for i in incidents.open_incidents(rig.saved())] == ["svc:mongod"]


def test_the_error_text_of_a_refusal_is_capped_at_300_characters(rig):
    rig.world.down.add("nginx")
    rig.world.refuse = True
    rig.world.refuse_text = "Failed: " + "x" * 900
    rig.at(0)
    rig.at(60)
    event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert len(event["params"]["error"]) == 300


# --- incidents.py ----------------------------------------------------------------------------------

def test_open_incident_on_an_open_key_is_a_no_op_and_clear_marks_it_cleared():
    state = {}
    first = incidents.open_incident(state, "svc:nginx", "critical", "service_gave_up", "nginx", {"restarts": 3}, 100.0)
    assert first == {"key": "svc:nginx", "severity": "critical", "kind": "service_gave_up", "target": "nginx",
                     "params": {"restarts": 3}, "openedAt": 100.0, "pageKey": None, "sent": False, "clearedAt": None}
    assert incidents.open_incident(state, "svc:nginx", "warning", "other", "nginx", {}, 200.0) is None
    assert state["incidents"]["svc:nginx"]["openedAt"] == 100.0 and state["incidents"]["svc:nginx"]["severity"] == "critical"
    assert incidents.clear_incident(state, "svc:nginx", 300.0)["clearedAt"] == 300.0
    assert incidents.clear_incident(state, "svc:nginx", 400.0) is None          # already cleared: untouched
    assert state["incidents"]["svc:nginx"]["clearedAt"] == 300.0
    assert incidents.clear_incident(state, "svc:never", 1.0) is None
    assert incidents.open_incidents(state) == []


def test_a_cleared_key_can_open_again_as_a_new_incident_and_open_incidents_lists_oldest_first():
    state = {}
    incidents.open_incident(state, "b", "info", "k", "t", None, 20.0)
    incidents.open_incident(state, "a", "info", "k", "t", None, 10.0)
    incidents.open_incident(state, "c", "info", "k", "t", None, 30.0)
    incidents.clear_incident(state, "c", 31.0)
    assert [i["key"] for i in incidents.open_incidents(state)] == ["a", "b"]
    again = incidents.open_incident(state, "c", "warning", "k", "t", {}, 40.0)
    assert again["openedAt"] == 40.0 and again["clearedAt"] is None and again["sent"] is False
    with pytest.raises(ValueError):
        incidents.open_incident(state, "d", "fatal", "k", "t", {}, 1.0)
