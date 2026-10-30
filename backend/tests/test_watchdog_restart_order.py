"""Watchdog restart order, stop pause, Ollama registry and the run's polling allowance (Phase 82, plan 82-03).

MongoDB before the backend (D-09), the demo-mode backend, the stop pause (D-11), restarts only where
Ollama is expected, and one shared polling allowance per run. Fake host: _watchdog_restart_world.py.
"""
import inspect
import json

import pytest

from tests._watchdog_support import FakeClock
from tests._watchdog_restart_world import RESTART_ARGV, SYNC, Rig, rig  # noqa: F401  (rig is a fixture)

from omni_watchdog import incidents, restart, services  # noqa: E402

# --- Task 3: MongoDB before the backend, demo mode, the stop pause, the expected-state registry ------

def restarts_in_order(rig):
    return [unit for _t, unit in rig.world.restarts]


def test_mongod_and_backend_down_in_one_run_only_mongod_is_restarted_and_the_backend_waits(rig):
    rig.world.down.update({"mongod", "omni-backend"})
    rig.world.demo = True
    rig.at(0)
    rig.at(60)
    assert restarts_in_order(rig) == ["mongod.service"]
    backend = rig.svc("omni-backend")
    assert backend["waitingOn"] == "mongod" and backend["state"] == "down"
    assert backend["restartsInWindow"] == 0 and backend["nextRestartAt"] is None
    assert rig.saved()["services"]["omni-backend"]["restarts"] == []
    assert rig.svc("mongod")["waitingOn"] is None


def test_next_run_a_backend_stuck_in_demo_mode_is_restarted_under_its_own_budget(rig):
    rig.world.down.update({"mongod", "omni-backend"})
    rig.world.demo = True                  # ready answers 503 demo_mode while the backend is down
    rig.at(0)
    rig.at(60)
    rig.at(120)
    assert restarts_in_order(rig) == ["mongod.service", "omni-backend.service"]
    restart_event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert restart_event["target"] == "omni-backend"
    assert restart_event["params"]["attempt"] == 1 and restart_event["params"]["ok"] is True
    backend = rig.svc("omni-backend")
    assert backend["state"] == "healthy" and backend["waitingOn"] is None and backend["restartsInWindow"] == 1


def test_a_backend_waiting_on_mongodb_spends_no_budget_however_long_it_waits(rig):
    rig.world.down.update({"mongod", "omni-backend"})
    rig.world.heal_delay["mongod"] = None
    for t in range(0, 15 * 60, 60):
        rig.at(t)
    assert set(restarts_in_order(rig)) == {"mongod.service"}
    saved = rig.saved()["services"]["omni-backend"]
    assert saved["restarts"] == [] and saved["waitingOn"] == "mongod"
    assert "gave_up" not in [e["kind"] for e in rig.summary["events"]]


def test_a_healthy_backend_is_not_marked_waiting_when_mongodb_is_down(rig):
    rig.world.down.add("mongod")
    rig.at(0)
    rig.at(60)
    assert rig.svc("omni-backend")["waitingOn"] is None


def test_nginx_down_twice_is_restarted_with_mongod_and_backend_healthy(rig):
    rig.world.down.add("nginx")
    rig.at(0)
    assert rig.world.restart_argvs() == []
    rig.at(60)
    assert rig.world.restart_argvs() == [RESTART_ARGV["nginx"]]
    assert rig.svc("nginx")["state"] == "healthy"


# a stop gates restarts only: file, cached database value, and the database value handed to decide

def test_a_stop_file_pauses_restarts_but_not_checks_events_or_the_incident(rig):
    rig.stop_file.write_text("")
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    rig.at(0)
    rig.at(60)
    assert rig.world.restart_argvs() == []
    assert rig.kinds() == ["service_down", "restart_skipped"]
    assert rig.body()["stop"] == {"effective": True, "source": "file"}
    assert rig.svc("mongod")["state"] == "down"
    for t in (120, 180, 240):
        rig.at(t)
        assert rig.kinds() == [] and rig.world.restart_argvs() == []        # one restart_skipped per episode
    saved = rig.saved()
    assert saved["services"]["mongod"]["restarts"] == [] and saved["services"]["mongod"].get("nextActionAt") is None
    open_now = incidents.open_incidents(saved)
    assert [(i["key"], i["kind"], i["severity"]) for i in open_now] == [("svc:mongod", "service_down", "critical")]
    assert rig.svc("mongod")["pagedAt"] == services.iso(rig.base + 60)


def test_the_stop_cached_from_the_last_sync_pauses_restarts(rig):
    rig.http.set("POST", SYNC, lambda request: (200, {
        "stop": {"active": True, "scope": "all", "pressedAt": "2026-01-01T00:00:00Z"},
        "acceptedEventIds": [e["id"] for e in json.loads(request["body"]).get("events", [])], "droppedEvents": 0,
        "outbox": [], "testRequest": None}))
    rig.at(0)                                            # the sync tells the watchdog a stop is active
    rig.world.down.add("nginx")
    rig.at(60)
    rig.at(120)
    assert rig.body()["stop"] == {"effective": True, "source": "cache"}
    assert rig.world.restart_argvs() == []
    assert rig.kinds() == ["service_down", "restart_skipped"]
    assert rig.saved()["services"]["nginx"]["restarts"] == []


@pytest.mark.parametrize("source", ["file", "database", "cache"])
def test_decide_issues_no_restart_for_any_stop_source_and_keeps_the_counters(source):
    calls, clock = [], FakeClock()

    def run(argv, timeout):
        calls.append(list(argv))
        return 0, "inactive\n"

    state = {"services": {"nginx": {"state": "down", "failedChecks": 2, "restarts": [clock() - 100]}}}
    health = {sid: (True, "") for sid in ("mongod", "omni-backend", "nginx")}
    health["nginx"] = (False, "inactive")
    events = restart.decide(state, health, {"effective": True, "source": source}, clock(), {}, run=run, clock=clock,
                            sleep=clock.advance, recheck=lambda sid: (False, ""))
    assert [c for c in calls if c[1] != "is-active"] == []
    assert [e["kind"] for e in events] == ["restart_skipped"]
    assert state["services"]["nginx"]["restarts"] == [clock() - 100]
    assert incidents.open_incidents(state)[0]["key"] == "svc:nginx"


def test_when_the_stop_is_cleared_a_service_that_is_still_down_is_restarted_normally(rig):
    rig.stop_file.write_text("")
    rig.world.down.add("nginx")
    rig.at(0)
    rig.at(60)
    rig.at(120)
    assert rig.world.restart_argvs() == []
    rig.stop_file.unlink()
    rig.at(180)
    assert rig.world.restart_argvs() == [RESTART_ARGV["nginx"]]
    event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert event["params"]["attempt"] == 1 and event["params"]["ok"] is True
    assert rig.svc("nginx")["state"] == "healthy"
    assert incidents.open_incidents(rig.saved()) == []               # recovered: the pause incident is cleared


def test_a_new_down_episode_gets_its_own_restart_skipped_event(rig):
    rig.stop_file.write_text("")
    rig.world.down.add("nginx")
    rig.at(0)
    rig.at(60)
    assert "restart_skipped" in rig.kinds()
    rig.world.down.discard("nginx")
    rig.at(120)
    rig.world.down.add("nginx")
    rig.at(180)
    rig.at(240)
    assert rig.kinds() == ["service_down", "restart_skipped"]


def test_a_budget_used_up_during_a_stop_still_gives_up_once(rig):
    rig.world.down.add("mongod")
    rig.world.heal_delay["mongod"] = None
    for t in (0, 60, 120, 180, 240, 300, 360, 420):
        rig.at(t)
    rig.stop_file.write_text("")
    rig.at(480)
    row = (480, 0, rig.svc("mongod")["state"], rig.kinds())
    assert row[2] == "gave_up" and row[3] == ["gave_up"]              # a stop silences nothing (PROH-82-02)
    assert [i["kind"] for i in incidents.open_incidents(rig.saved())] == ["service_gave_up"]


# Ollama: managed only where the operator said it is expected (PROH-82-01)

@pytest.mark.parametrize("running", [False, True])
def test_ollama_expected_off_is_never_started_or_restarted(rig, running):
    rig.world.ollama_active = running
    rig.world.down.update({"mongod", "nginx"})              # a busy run, so restarts do happen for the others
    for t in (0, 60, 120, 180):
        rig.at(t)
    touching_ollama = [c for c in rig.world.calls if c[-1] == "ollama.service"]
    assert touching_ollama and all(c[:2] == ["systemctl", "is-active"] for c in touching_ollama)
    assert "ollama.service" not in restarts_in_order(rig)
    state = rig.svc("ollama")["state"]
    assert state == ("unexpected_running" if running else "expected_off")


def test_restart_source_has_no_hard_coded_ollama_unit():
    assert "ollama.service" not in inspect.getsource(restart)


def test_ollama_expected_on_and_down_twice_is_restarted_under_the_same_budget(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, ollama_expected=True)
    rig.world.ollama_active = True
    rig.at(0)
    assert rig.svc("ollama")["state"] == "healthy"
    rig.world.down.add("ollama")
    rig.at(60)
    assert rig.world.restart_argvs() == []
    rig.at(120)
    assert rig.world.restart_argvs() == [RESTART_ARGV["ollama"]]
    event = [e for e in rig.summary["events"] if e["kind"] == "restart"][0]
    assert event["target"] == "ollama" and event["params"]["attempt"] == 1 and event["params"]["ok"] is True


def test_ollama_expected_on_without_a_polkit_grant_ends_in_one_gave_up(tmp_path, monkeypatch):
    # The shipped polkit rule omits ollama.service until the operator adds it (82-06), so a refusal is the default.
    rig = Rig(tmp_path, monkeypatch, ollama_expected=True)
    rig.world.ollama_active = True
    rig.world.down.add("ollama")
    rig.world.refuse = True
    gave_up = 0
    for t in (0, 60, 120, 240, 300, 360, 480, 540, 600):
        rig.at(t)
        gave_up += rig.kinds().count("gave_up")
    assert gave_up == 1
    assert restarts_in_order(rig) == ["ollama.service"] * 3


# one shared polling allowance per run, so the run fits inside TimeoutStartSec=45

def test_polling_allowance_is_below_the_unit_start_timeout():
    assert restart.POLL_FOR <= restart.POLL_BUDGET <= 30


def test_three_services_restarted_in_one_run_share_the_polling_allowance_and_all_events_are_returned(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, ollama_expected=True)
    rig.world.ollama_active = True
    rig.at(0)
    for sid in ("mongod", "nginx", "ollama"):
        rig.world.down.add(sid)
        rig.world.heal_delay[sid] = None
    rig.at(30)
    start = rig.base + 90
    rig.at(90)
    assert restarts_in_order(rig) == ["mongod.service", "nginx.service", "ollama.service"]
    elapsed = rig.clock() - start
    assert elapsed <= restart.POLL_BUDGET and elapsed >= restart.POLL_FOR   # 20 s + 10 s + nothing
    restart_events = [e for e in rig.body()["events"] if e["kind"] == "restart"]
    assert [(e["target"], e["params"]["attempt"], e["params"]["ok"]) for e in restart_events] == [
        ("mongod", 1, False), ("nginx", 1, False), ("ollama", 1, False)]
    assert "20 s" in restart_events[0]["params"]["error"]
    assert "10 s" in restart_events[1]["params"]["error"]
    assert restart_events[2]["params"]["error"] == restart.NOT_CONFIRMED
    saved = rig.saved()["services"]
    for sid in ("mongod", "nginx", "ollama"):
        assert len(saved[sid]["restarts"]) == 1 and saved[sid]["state"] == "restarting"


def test_a_restart_the_allowance_could_not_cover_is_judged_on_the_next_run(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch, ollama_expected=True)
    rig.world.ollama_active = True
    rig.at(0)
    for sid in ("mongod", "nginx"):
        rig.world.down.add(sid)
        rig.world.heal_delay[sid] = None
    rig.world.down.add("ollama")
    rig.world.heal_delay["ollama"] = 3
    rig.at(30)
    rig.at(90)                                       # ollama was restarted last, with no polling left
    assert rig.world.restart_argvs()[-1] == RESTART_ARGV["ollama"]
    rig.at(150)
    assert "service_recovered" in rig.kinds()
    assert rig.svc("ollama")["state"] == "healthy"
    assert len(rig.world.restarts_of("ollama")) == 1       # not restarted a second time
