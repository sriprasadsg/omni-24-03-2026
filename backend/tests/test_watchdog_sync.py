"""Watchdog offline spool, replay and the three-source stop (Phase 82, plan 82-02, HEAL-01).

The spool is a newline-delimited JSON file in the state directory; ``resolve_stop`` decides whether
automatic actions are stopped from a STOP file, the last backend answer, or the cached copy of it.
Every path is under tmp_path and every external effect is a fake.
"""
import json
import os

import pytest

from tests._watchdog_support import (  # noqa: F401  (fixtures are imported for pytest)
    FakeClock, FakeHttp, FakeRun, _self_signed_cert, fake_mongo_server, fake_tls_server, load_watchdog,
)

load_watchdog()
from omni_watchdog import run as run_mod, state as state_mod, sync  # noqa: E402

TOKEN = "t0k3n-sync-tests"
SYNC = "/api/internal/watchdog/sync"
READY = "/api/health/ready"


def _cfg(tmp_path, **extra):
    token = tmp_path / "ingest.token"
    token.write_text(TOKEN)
    cfg = {"ingest_token_path": str(token), "host": "omni-test", "stop_file": str(tmp_path / "STOP"),
           "mongo_port": 1, "nginx_port": 1}
    cfg.update(extra)
    return cfg


def _down_run():
    """Mongod, nginx and the backend all failing: two runs produce three service_down events."""
    return FakeRun({"mongod.service": "inactive", "nginx.service": "inactive"})


def _http(post):
    http = FakeHttp()
    http.set("GET", READY, ConnectionRefusedError("backend down"))
    http.set("POST", SYNC, post)
    return http


def _spool(tmp_path):
    return state_mod.Spool(str(tmp_path / "spool.ndjson"))


def _ids(tmp_path):
    return [e["id"] for e in _spool(tmp_path).read(10_000)]


def _event(n):
    return {"id": "%032x" % n, "at": "2027-01-15T08:00:00Z", "kind": "service_down", "severity": "critical",
            "target": "mongod", "params": {}}


def _two_runs(tmp_path, cfg, http, run=None):
    run, clock = run or _down_run(), FakeClock()
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    clock.advance(60)
    return run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock), clock, run


# --- spool and replay ---------------------------------------------------------------------------

def test_backend_down_keeps_the_events_in_the_spool(tmp_path):
    http = _http(ConnectionRefusedError("backend down"))
    summary, _clock, _run = _two_runs(tmp_path, _cfg(tmp_path), http)
    assert summary["synced"] is False
    assert [e["target"] for e in _spool(tmp_path).read(10)] == ["mongod", "omni-backend", "nginx"]
    assert os.path.exists(tmp_path / "spool.ndjson")


def test_replay_sends_spooled_events_before_new_ones_and_empties_the_spool(tmp_path):
    cfg = _cfg(tmp_path)
    down = _http(ConnectionRefusedError("backend down"))
    _summary, clock, run = _two_runs(tmp_path, cfg, down)
    spooled = _ids(tmp_path)
    assert len(spooled) == 3

    up = _http(FakeHttp.accept_all)
    # the backend comes back, so omni-backend recovers: that is this run's own new event
    up.set("GET", READY, (200, {"status": "ready"}))
    clock.advance(60)
    result = run_mod.run_once(cfg, str(tmp_path), run=run, http=up, now=clock)
    assert result["synced"] is True
    sent = up.posted(SYNC)[0]["events"]
    assert [e["id"] for e in sent[:3]] == spooled                 # spooled events first, in order
    assert [e["kind"] for e in sent[3:]] == ["service_recovered"]  # then this run's own event
    assert _ids(tmp_path) == []


def test_at_most_50_events_per_call_and_the_rest_stay(tmp_path):
    spool = _spool(tmp_path)
    spool.append([_event(n) for n in range(120)])
    http = FakeHttp()
    http.set("POST", SYNC, FakeHttp.accept_all)
    state = state_mod.empty_state()
    cfg = {"backend_url": "http://127.0.0.1:5000"}
    for expected_sent, expected_left in ((50, 70), (50, 20), (20, 0)):
        ok, _resp = sync.sync_cycle(http, cfg, TOKEN, {"v": 1}, spool, state)
        assert ok is True
        assert len(http.posted(SYNC)[-1]["events"]) == expected_sent
        assert len(spool) == expected_left
    assert [e["id"] for e in http.posted(SYNC)[1]["events"]][0] == "%032x" % 50


def test_spool_cap_drops_the_oldest_and_counts_them(tmp_path):
    spool = _spool(tmp_path)
    assert spool.append([_event(n) for n in range(2000)]) == 0
    assert spool.append([_event(2000)]) == 1
    ids = [e["id"] for e in spool.read(5000)]
    assert len(ids) == 2000 and ids[0] == "%032x" % 1 and ids[-1] == "%032x" % 2000


def test_run_counts_cap_drops_in_state(tmp_path):
    cfg = _cfg(tmp_path)
    http = _http(ConnectionRefusedError("backend down"))
    run, clock = _down_run(), FakeClock()
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    _spool(tmp_path).append([_event(n) for n in range(2000)])
    clock.advance(60)
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    saved = state_mod.load_state(state_mod.state_path(str(tmp_path)))
    assert saved["spoolDropped"] == 3 and len(_spool(tmp_path)) == 2000


@pytest.mark.parametrize("status", [401, 503, 500])
def test_non_200_answers_keep_events_and_fall_back_to_the_cached_stop(tmp_path, status):
    cfg = _cfg(tmp_path)
    saved = state_mod.empty_state()
    saved["stopCache"] = {"active": True, "pressedAt": "2027-01-15T08:00:00Z", "at": 1.0}
    state_mod.save_state(state_mod.state_path(str(tmp_path)), saved)
    http = _http((status, {"detail": "no"}))
    summary, _clock, _run = _two_runs(tmp_path, cfg, http)
    assert summary["synced"] is False and len(_spool(tmp_path)) == 3
    assert summary["stop"] == {"effective": True, "source": "cache"}
    assert http.posted(SYNC)[-1]["stop"] == {"effective": True, "source": "cache"}


def test_unaccepted_events_are_kept_then_abandoned_after_three_hand_overs(tmp_path):
    spool = _spool(tmp_path)
    spool.append([_event(1)])
    http = FakeHttp()
    http.set("POST", SYNC, (200, {"acceptedEventIds": [], "droppedEvents": 0}))
    state, cfg = state_mod.empty_state(), {"backend_url": "http://x"}
    for _ in range(2):
        sync.sync_cycle(http, cfg, TOKEN, {"v": 1}, spool, state)
        assert len(spool) == 1
    sync.sync_cycle(http, cfg, TOKEN, {"v": 1}, spool, state)
    assert len(spool) == 0 and state["spoolAbandoned"] == 1


def test_events_the_backend_dropped_leave_the_spool(tmp_path):
    spool = _spool(tmp_path)
    spool.append([_event(1), _event(2)])
    http = FakeHttp()
    http.set("POST", SYNC, (200, {"acceptedEventIds": ["%032x" % 1], "droppedEvents": 1}))
    sync.sync_cycle(http, {"backend_url": "http://x"}, TOKEN, {"v": 1}, spool, state_mod.empty_state())
    assert len(spool) == 0


def test_spool_survives_an_unreadable_line_and_removes_by_id(tmp_path):
    spool = _spool(tmp_path)
    spool.append([_event(1), _event(2), _event(3)])
    with open(tmp_path / "spool.ndjson", "a") as handle:
        handle.write("{broken\n")
    assert [e["id"] for e in spool.read(10)] == ["%032x" % n for n in (1, 2, 3)]
    spool.remove({"%032x" % 2})
    assert [e["id"] for e in spool.read(10)] == ["%032x" % 1, "%032x" % 3]


# --- the three-source stop ----------------------------------------------------------------------

def test_stop_file_wins_even_when_the_database_says_inactive(tmp_path):
    stop_file = tmp_path / "STOP"
    stop_file.write_text("")
    state = state_mod.empty_state()
    response = {"stop": {"active": False, "scope": None, "pressedAt": None}}
    assert sync.resolve_stop(str(stop_file), response, state) == (True, "file")
    assert state["stopCache"]["active"] is False             # the database answer is still cached


def test_database_stop_is_returned_and_cached(tmp_path):
    state = state_mod.empty_state()
    response = {"stop": {"active": True, "scope": "platform", "pressedAt": "2027-01-15T08:00:00Z"}}
    assert sync.resolve_stop(str(tmp_path / "STOP"), response, state, now=5.0) == (True, "database")
    assert state["stopCache"] == {"active": True, "pressedAt": "2027-01-15T08:00:00Z", "at": 5.0}


def test_cached_stop_is_used_when_the_backend_is_unreachable(tmp_path):
    state = state_mod.empty_state()
    state["stopCache"] = {"active": True, "pressedAt": None, "at": 1.0}
    assert sync.resolve_stop(str(tmp_path / "STOP"), None, state) == (True, "cache")
    state["stopCache"] = {"active": False, "pressedAt": None, "at": 1.0}
    assert sync.resolve_stop(str(tmp_path / "STOP"), None, state) == (False, "cache")


def test_no_file_no_sync_no_cache_means_not_stopped(tmp_path):
    assert sync.resolve_stop(str(tmp_path / "STOP"), None, state_mod.empty_state()) == (False, "none")
    assert sync.resolve_stop(str(tmp_path / "STOP"), {"stop": "garbage"}, state_mod.empty_state()) == (False, "none")


def test_stop_pressed_in_the_database_is_cached_by_a_run_and_used_by_the_next(tmp_path):
    cfg = _cfg(tmp_path)
    pressed = {"stop": {"active": True, "scope": "platform", "pressedAt": "2027-01-15T08:00:00Z"},
               "acceptedEventIds": [], "droppedEvents": 0, "outbox": [], "testRequest": None}
    http = _http((200, pressed))
    run, clock = FakeRun(), FakeClock()
    first = run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    assert first["stop"] == {"effective": False, "source": "none"}
    clock.advance(60)
    second = run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    assert second["stop"] == {"effective": True, "source": "cache"}
    assert http.posted(SYNC)[1]["stop"] == {"effective": True, "source": "cache"}


def test_stop_file_shows_in_the_sync_body(tmp_path):
    (tmp_path / "STOP").write_text("")
    http = _http(FakeHttp.accept_all)
    run_mod.run_once(_cfg(tmp_path), str(tmp_path), run=FakeRun(), http=http, now=FakeClock())
    assert http.posted(SYNC)[0]["stop"] == {"effective": True, "source": "file"}
