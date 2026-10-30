"""A fake host for the watchdog restart tests (Phase 82, plan 82-03, HEAL-01 and HEAL-02).

Nothing here touches the host: ``World`` is a fake machine whose units go down and come back, answers
``systemctl`` through the run seam, serves the backend through the http seam and moves the fake clock
while the watchdog polls. Time is absolute (``Rig.at(seconds)``), so the D-07 timeline is exact.
"""
import json

import pytest

from tests._watchdog_support import FakeClock, FakeHttp, load_watchdog

load_watchdog()
from omni_watchdog import UNITS, checks, run as run_mod  # noqa: E402

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
            return self.ollama_active and "ollama" not in self.down
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
    # The restart tests are about restarts; certificate and disk warnings (82-04) have their own suite.
    monkeypatch.setattr(run_mod.warnings, "evaluate", lambda *args, **kwargs: ([], [], []))
    return Rig(tmp_path, monkeypatch)
