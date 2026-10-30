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


@pytest.fixture(autouse=True)
def _no_restart_decisions(monkeypatch):
    """These tests are about the checks and the debounce; a service that stays down would now also be restarted (82-03).
    The restart decision has its own tests in test_watchdog_restart.py."""
    monkeypatch.setattr(run_mod.restart, "decide", lambda *args, **kwargs: [])


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


# --- configuration, crash-safe state, run lock, stdlib-only (task 3) -------------------------------

import ast  # noqa: E402
import fcntl  # noqa: E402

from omni_watchdog import config as config_mod, state as state_mod  # noqa: E402


def test_load_config_without_a_file_returns_the_defaults(tmp_path):
    cfg = config_mod.load_config(str(tmp_path / "missing.conf"))
    assert cfg["backend_url"] == "http://127.0.0.1:5000" and cfg["ollama_expected"] is False
    assert cfg["certs"] == ["/etc/nginx/ssl/omni.crt"] and cfg["disk_paths"] == ["/", "/var/lib/mongodb"]
    cfg["certs"].append("/x")                                   # callers cannot corrupt the shared defaults
    assert wd.DEFAULTS["certs"] == ["/etc/nginx/ssl/omni.crt"]


def test_load_config_reads_the_watchdog_section_and_ignores_unknown_keys(tmp_path):
    conf = tmp_path / "watchdog.conf"
    conf.write_text("[watchdog]\nextra_certs = /a.crt, /b.crt\nollama_expected = true\nbogus = 1\n"
                    "disk_paths = /, /data\nbackend_url = http://127.0.0.1:5001/\n")
    cfg = config_mod.load_config(str(conf))
    assert cfg["extra_certs"] == ["/a.crt", "/b.crt"]
    assert cfg["certs"] == ["/etc/nginx/ssl/omni.crt", "/a.crt", "/b.crt"]
    assert cfg["ollama_expected"] is True and cfg["disk_paths"] == ["/", "/data"]
    assert cfg["backend_url"] == "http://127.0.0.1:5001" and "bogus" not in cfg


def test_load_config_non_boolean_or_bad_values_fall_back(tmp_path):
    conf = tmp_path / "watchdog.conf"
    conf.write_text("[watchdog]\nollama_expected = maybe\nbackend_url = file:///etc/passwd\n")
    cfg = config_mod.load_config(str(conf))
    assert cfg["ollama_expected"] is False and cfg["backend_url"] == "http://127.0.0.1:5000"
    conf.write_text("this is not an ini file\n")
    assert config_mod.load_config(str(conf))["ollama_expected"] is False


def test_load_oncall_parses_key_value_lines_and_hides_secrets_from_repr(tmp_path):
    env = tmp_path / "oncall.env"
    env.write_text("# comment\n\nONCALL_TYPE=pagerduty\nPAGERDUTY_ROUTING_KEY=RK-SECRET-123\n"
                   "WEBHOOK_URL=https://hooks.example/SECRET-PATH\nWEBHOOK_FORMAT=slack\n"
                   "HEARTBEAT_URL=\"https://beat.example/SECRET-BEAT\"\n")
    oncall = config_mod.load_oncall(str(env))
    assert (oncall.type, oncall.routing_key, oncall.webhook_format) == ("pagerduty", "RK-SECRET-123", "slack")
    assert oncall.heartbeat_url == "https://beat.example/SECRET-BEAT"
    for text in (repr(oncall), str(oncall), "%s" % oncall):
        assert "SECRET" not in text and "pagerduty" in text


def test_load_oncall_missing_or_invalid_means_none(tmp_path):
    assert config_mod.load_oncall(str(tmp_path / "nope")).type == "none"
    env = tmp_path / "oncall.env"
    env.write_text("ONCALL_TYPE=carrier-pigeon\nWEBHOOK_FORMAT=xml\n")
    oncall = config_mod.load_oncall(str(env))
    assert oncall.type == "none" and oncall.webhook_format == "json"
    assert config_mod.read_token(str(tmp_path / "nope")) == ""


def test_a_crash_between_the_temp_write_and_the_replace_keeps_the_old_state(tmp_path, monkeypatch):
    path = str(tmp_path / "state.json")
    state_mod.save_state(path, {"v": 1, "services": {"mongod": {"state": "down"}}})

    def boom(src, dst):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(state_mod.os, "replace", boom)
    with pytest.raises(RuntimeError):
        state_mod.save_state(path, {"v": 1, "services": {"mongod": {"state": "healthy"}}})
    monkeypatch.undo()
    assert json.load(open(path))["services"]["mongod"]["state"] == "down"
    assert not os.path.exists(path + ".tmp")


def test_corrupt_state_is_quarantined_and_one_state_reset_event_is_emitted(tmp_path, fake_mongo_server, fake_tls_server):
    (tmp_path / "state.json").write_text("{not json")
    cfg = _config(tmp_path, fake_mongo_server.start("ok"), fake_tls_server.start("http"))
    http, clock = _backend(), FakeClock()
    run_mod.run_once(cfg, str(tmp_path), run=FakeRun(), http=http, now=clock)
    bad = [n for n in os.listdir(tmp_path) if n.startswith("state.json.bad-")]
    assert bad == ["state.json.bad-%d" % int(clock())]
    assert [e["kind"] for e in http.posted(SYNC)[0]["events"]] == ["state_reset"]
    clock.advance(60)
    run_mod.run_once(cfg, str(tmp_path), run=FakeRun(), http=http, now=clock)
    assert http.posted(SYNC)[1]["events"] == []                 # exactly one, and only once
    assert json.load(open(tmp_path / "state.json"))["services"]["mongod"]["state"] == "healthy"


def test_a_second_concurrent_run_exits_at_once_on_the_lock(tmp_path):
    http, run = _backend(), FakeRun()
    fd = os.open(str(tmp_path / "state.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        summary = run_mod.run_once(_config(tmp_path, free_port(), free_port()), str(tmp_path),
                                   run=run, http=http, now=FakeClock())
    finally:
        os.close(fd)
    assert summary == {"skipped": "locked"}
    assert run.calls == [] and http.requests == []


def test_the_lock_is_released_after_a_run(tmp_path):
    cfg = _config(tmp_path, free_port(), free_port())
    for _ in range(2):
        assert "skipped" not in run_mod.run_once(cfg, str(tmp_path), run=FakeRun(), http=_backend(), now=FakeClock())


def _watchdog_sources():
    for folder, _dirs, files in os.walk(WATCHDOG_DIR):
        for name in sorted(files):
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                yield path, ast.parse(open(path, encoding="utf-8").read())


def test_every_module_imports_only_the_standard_library_and_its_own_package():
    seen = 0
    for path, tree in _watchdog_sources():
        seen += 1
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module.split(".")[0]]
            for top in names:
                assert top in sys.stdlib_module_names or top == "omni_watchdog", "%s imports %s" % (path, top)
    assert seen >= 8


def test_mongodb_is_only_ever_contacted_by_the_ping():
    for path, tree in _watchdog_sources():
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            calls = {c.func.attr for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
            if "create_connection" in calls or "connect" in calls:
                assert os.path.basename(path) == "checks.py" and fn.name in ("mongo_ping", "nginx_probe"), (path, fn.name)
        text = open(path, encoding="utf-8").read()
        assert "pymongo" not in text and "motor" not in text


def test_every_module_stays_under_500_lines():
    for path, _tree in _watchdog_sources():
        assert len(open(path, encoding="utf-8").read().splitlines()) < 500, path
