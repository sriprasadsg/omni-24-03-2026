"""Watchdog service checks, debounce and one run (Phase 82, plan 82-02, HEAL-01).

Standard-library watchdog under deploy/omni-watchdog; every external effect is a fake from
tests/_watchdog_support.py, so nothing here touches systemd, the real MongoDB, nginx or the network
beyond throwaway loopback servers on ephemeral ports.
"""
import json
import os
import subprocess
import sys

import pytest

from tests._watchdog_support import (  # noqa: F401  (fixtures are imported for pytest)
    FakeClock, FakeHttp, FakeRun, WATCHDOG_DIR, _self_signed_cert, fake_mongo_server, fake_tls_server,
    free_port, load_watchdog,
)

wd = load_watchdog()
from omni_watchdog import checks, run as run_mod, services, sync  # noqa: E402

TOKEN = "t0k3n-for-tests"
READY = "/api/health/ready"
SYNC = "/api/internal/watchdog/sync"


def _config(tmp_path, mongo_port, nginx_port, **extra):
    token = tmp_path / "ingest.token"
    token.write_text(TOKEN + "\n")
    cfg = {"ingest_token_path": str(token), "mongo_port": mongo_port, "nginx_port": nginx_port,
           "host": "omni-test", "stop_file": str(tmp_path / "STOP")}
    cfg.update(extra)
    return cfg


def _backend(ok=True):
    http = FakeHttp()
    http.set("GET", READY, (200, {"status": "ready"}) if ok else (503, {"demo_mode": True}))
    http.set("POST", SYNC, FakeHttp.accept_all)
    return http


# --- the checks ---------------------------------------------------------------------------------

def test_mongo_ping_alive_on_a_well_formed_op_msg_reply(fake_mongo_server):
    assert checks.mongo_ping("127.0.0.1", fake_mongo_server.start("ok"), timeout=2.0) is True


def test_mongo_ping_dead_when_the_server_hangs_up_or_nothing_listens(fake_mongo_server):
    assert checks.mongo_ping("127.0.0.1", fake_mongo_server.start("close"), timeout=2.0) is False
    assert checks.mongo_ping("127.0.0.1", fake_mongo_server.start("junk"), timeout=2.0) is False
    assert checks.mongo_ping("127.0.0.1", free_port(), timeout=1.0) is False


def test_backend_ready_ok_on_200():
    http = FakeHttp()
    http.set("GET", READY, (200, {"status": "ready"}))
    assert checks.backend_ready(http, "http://127.0.0.1:5000") == (True, "")
    assert http.requests[0]["url"] == "http://127.0.0.1:5000/api/health/ready"


def test_backend_ready_503_demo_mode_has_its_own_detail():
    http = FakeHttp()
    http.set("GET", READY, (503, {"status": "not_ready", "demo_mode": True}))
    assert checks.backend_ready(http, "http://127.0.0.1:5000") == (False, "demo_mode")


def test_backend_ready_other_503_and_connection_error_are_not_ok():
    http = FakeHttp()
    http.set("GET", READY, (503, {"status": "not_ready", "demo_mode": False}))
    assert checks.backend_ready(http, "http://x") == (False, "http_503")
    assert checks.backend_ready(FakeHttp(), "http://x") == (False, "unreachable")


def test_nginx_probe_ok_on_a_tls_server_that_answers_http(fake_tls_server):
    assert checks.nginx_probe("127.0.0.1", fake_tls_server.start("http"), timeout=3.0) is True


def test_nginx_probe_fails_when_the_peer_never_speaks_tls(fake_tls_server):
    assert checks.nginx_probe("127.0.0.1", fake_tls_server.start("plain"), timeout=0.5) is False
    assert checks.nginx_probe("127.0.0.1", fake_tls_server.start("tls_junk"), timeout=2.0) is False
    assert checks.nginx_probe("127.0.0.1", free_port(), timeout=1.0) is False


def test_is_active_reads_systemctl_output_through_an_argument_list():
    run = FakeRun({"mongod.service": "failed"})
    assert checks.is_active(run, "nginx.service") is True
    assert checks.is_active(run, "mongod.service") is False
    assert run.calls[0] == ["systemctl", "is-active", "nginx.service"]


def test_ollama_expected_off_is_never_started():
    run = FakeRun({"ollama.service": "active"})
    ok, detail = checks.ollama_state(run, FakeHttp(), expected=False)
    assert (ok, detail) == (False, "unexpected_running")
    assert run.mutating() == []
    assert checks.ollama_state(FakeRun(), FakeHttp(), expected=False) == (True, "expected_off")


# --- the debounce -------------------------------------------------------------------------------

def test_debounce_one_failure_is_checking_two_is_down_then_recovered():
    state, events = services.observe(None, False, "inactive", 100.0, target="mongod")
    assert state["state"] == "checking" and state["failedChecks"] == 1 and events == []
    state, events = services.observe(state, False, "inactive", 160.0, target="mongod")
    assert state["state"] == "down" and state["failedChecks"] == 2
    assert [e["kind"] for e in events] == ["service_down"]
    assert events[0]["severity"] == "critical" and events[0]["target"] == "mongod"
    assert len(events[0]["id"]) == 32 and int(events[0]["id"], 16) >= 0
    state, events = services.observe(state, False, "inactive", 220.0, target="mongod")
    assert state["state"] == "down" and events == []        # no second service_down while it stays down
    state, events = services.observe(state, True, "", 280.0, target="mongod")
    assert state["state"] == "healthy" and state["failedChecks"] == 0
    assert [e["kind"] for e in events] == ["service_recovered"]


def test_debounce_a_pass_after_one_failure_resets_without_going_down():
    state, _ = services.observe(None, False, "x", 100.0, target="nginx")
    state, events = services.observe(state, True, "", 160.0, target="nginx")
    assert state["state"] == "healthy" and state["failedChecks"] == 0
    assert [e["kind"] for e in events] == ["service_recovered"]


def test_first_run_with_no_state_and_a_failure_only_reaches_checking():
    state, events = services.observe({}, False, "unreachable", 5.0, target="omni-backend")
    assert state["state"] == "checking" and events == []


def test_observe_does_not_modify_its_input():
    before = {"state": "checking", "failedChecks": 1, "since": 1.0}
    snapshot = dict(before)
    services.observe(before, False, "x", 9.0, target="mongod")
    assert before == snapshot


def test_unexpected_ollama_emits_one_event_per_episode():
    state, events = services.observe(None, False, "unexpected_running", 1.0, target="ollama")
    assert state["state"] == "unexpected_running" and [e["kind"] for e in events] == ["unexpected_running"]
    state, events = services.observe(state, False, "unexpected_running", 61.0, target="ollama")
    assert events == []
    state, events = services.observe(state, True, "expected_off", 121.0, target="ollama")
    assert state["state"] == "expected_off" and events == []


# --- one run ------------------------------------------------------------------------------------

def test_run_once_reports_the_four_services_in_fixed_order_with_the_bearer_token(tmp_path, fake_mongo_server, fake_tls_server):
    cfg = _config(tmp_path, fake_mongo_server.start("ok"), fake_tls_server.start("http"))
    http, run = _backend(), FakeRun()
    summary = run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=FakeClock())
    assert summary["synced"] is True
    posts = http.posted(SYNC)
    assert len(posts) == 1
    body = posts[0]
    assert body["v"] == 1 and body["host"] == "omni-test"
    assert list(body["services"]) == ["mongod", "omni-backend", "nginx", "ollama"]
    assert {sid: s["state"] for sid, s in body["services"].items()} == {
        "mongod": "healthy", "omni-backend": "healthy", "nginx": "healthy", "ollama": "expected_off"}
    assert body["services"]["mongod"]["failedChecks"] == 0
    request = [r for r in http.requests if r["method"] == "POST"][0]
    assert request["headers"]["Authorization"] == "Bearer " + TOKEN
    assert set(body) >= {"sentAt", "certs", "disks", "oncall", "stop", "events", "delivered"}
    assert body["stop"] == {"effective": False, "source": "none"}


def test_run_once_with_ollama_running_unexpectedly_never_starts_it(tmp_path, fake_mongo_server, fake_tls_server):
    cfg = _config(tmp_path, fake_mongo_server.start("ok"), fake_tls_server.start("http"))
    http, run = _backend(), FakeRun({"ollama.service": "active"})
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=FakeClock())
    body = http.posted(SYNC)[0]
    assert body["services"]["ollama"]["state"] == "unexpected_running"
    assert [e["kind"] for e in body["events"]] == ["unexpected_running"]
    assert body["events"][0]["target"] == "ollama"
    assert run.mutating() == []


def test_a_failing_service_is_checking_on_the_first_run_and_down_on_the_second(tmp_path, fake_mongo_server, fake_tls_server):
    cfg = _config(tmp_path, free_port(), fake_tls_server.start("http"))
    http, run, clock = _backend(), FakeRun(), FakeClock()
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    clock.advance(60)
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    first, second = http.posted(SYNC)
    assert first["services"]["mongod"]["state"] == "checking" and first["events"] == []
    assert second["services"]["mongod"]["state"] == "down"
    assert second["services"]["mongod"]["detail"] == "no_reply"
    assert [e["kind"] for e in second["events"]] == ["service_down"]


def test_events_in_one_run_keep_the_service_order(tmp_path):
    cfg = _config(tmp_path, free_port(), free_port())
    http, run, clock = FakeHttp(), FakeRun(), FakeClock()
    http.set("GET", READY, (503, {"demo_mode": True}))
    http.set("POST", SYNC, FakeHttp.accept_all)
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    clock.advance(60)
    run_mod.run_once(cfg, str(tmp_path), run=run, http=http, now=clock)
    events = http.posted(SYNC)[1]["events"]
    assert [e["target"] for e in events] == ["mongod", "omni-backend", "nginx"]


def test_sync_body_uses_the_frozen_v1_service_fields():
    block = sync.service_block({"state": "down", "since": 1_800_000_000.0, "failedChecks": 2, "detail": "x"})
    assert list(block) == ["state", "since", "failedChecks", "restartsInWindow", "nextRestartAt",
                           "budgetReturnsAt", "pagedAt", "waitingOn", "detail"]
    assert block["since"] == "2027-01-15T08:00:00Z"


def test_no_token_means_no_sync_attempt(tmp_path, fake_mongo_server, fake_tls_server):
    cfg = _config(tmp_path, fake_mongo_server.start("ok"), fake_tls_server.start("http"))
    cfg["ingest_token_path"] = str(tmp_path / "missing.token")
    http = _backend()
    summary = run_mod.run_once(cfg, str(tmp_path), run=FakeRun(), http=http, now=FakeClock())
    assert summary["synced"] is False and http.posted(SYNC) == []


def test_entry_script_prints_help_under_isolated_mode():
    done = subprocess.run([sys.executable, "-I", os.path.join(WATCHDOG_DIR, "omni-watchdog.py"), "--help"],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0 and "--state-dir" in done.stdout


def test_no_shell_true_anywhere_in_the_watchdog():
    for folder, _dirs, files in os.walk(WATCHDOG_DIR):
        for name in files:
            if name.endswith(".py"):
                text = open(os.path.join(folder, name), encoding="utf-8").read()
                assert "shell=True" not in text.replace("shell=False", "")
