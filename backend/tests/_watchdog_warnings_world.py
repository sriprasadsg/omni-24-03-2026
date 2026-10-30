"""A fake host for the watchdog certificate and disk warning tests (Phase 82, plan 82-04, HEAL-03 / HEAL-04).

Nothing here reads the real /etc/nginx/ssl/omni.crt or this machine's disks: ``CertRun`` answers
``openssl x509 -noout -enddate`` from numbers the test chooses (or runs the real openssl on a certificate
generated in tmp_path), ``FakeFs`` answers statvfs/stat, and ``Bench`` calls ``warnings.evaluate`` on a
plain state dict at a chosen fake time.
"""
import subprocess
import time
from types import SimpleNamespace

import pytest

from tests._watchdog_support import FakeClock, FakeHttp, load_watchdog

load_watchdog()
from omni_watchdog import run as run_mod, warnings as wmod  # noqa: E402
from tests._watchdog_restart_world import Rig  # noqa: E402

DAY = 86400.0
T0 = 1_800_000_000.0
PINNED = wmod.PINNED_CERT
ENDDATE_ARGV = ["openssl", "x509", "-noout", "-enddate", "-in"]


def enddate_text(epoch):
    """What ``openssl x509 -enddate`` prints (C locale), second resolution."""
    stamp = time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(epoch))
    if stamp[4] == "0":
        stamp = stamp[:4] + " " + stamp[5:]
    return "notAfter=" + stamp + "\n"


class CertRun:
    """``run(argv, timeout)``: certificates by path -> notAfter epoch. Every openssl call is recorded."""

    def __init__(self, clock=None, per_read=0.0):
        self.not_after = {}
        self.real = {}                  # path -> a real certificate file to hand to the real openssl
        self.missing = set()
        self.garbage = set()
        self.timeouts = set()
        self.clock = clock
        self.per_read = per_read        # fake seconds one openssl read takes
        self.reads = []                 # (path, timeout)
        self.calls = []

    def days_left(self, path, days, now=T0):
        self.not_after[path] = now + days * DAY

    def __call__(self, argv, timeout):
        assert isinstance(argv, list), "subprocess calls must pass an argument list"
        self.calls.append(list(argv))
        if argv[:5] != ENDDATE_ARGV:
            return 0, ""
        path = argv[5]
        self.reads.append((path, timeout))
        if self.clock is not None and self.per_read:
            self.clock.advance(self.per_read)
        if path in self.timeouts:
            return 124, ""
        if path in self.missing or (path not in self.not_after and path not in self.real):
            return 1, "Could not open file or uri\n"
        if path in self.garbage:
            return 0, "this is not a date\n"
        if path in self.real:
            done = subprocess.run(argv[:5] + [self.real[path]], capture_output=True, text=True, timeout=30,
                                  env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"}, check=False)
            return done.returncode, done.stdout
        return 0, enddate_text(self.not_after[path])


class FakeFs:
    """``statvfs(path)`` and ``stat(path)`` with numbers the test sets."""

    def __init__(self):
        self.disks = {}                 # path -> dict(dev, total, used, reserved)

    def set(self, path, pct=None, *, dev=1, total=10_000, used=None, reserved=0):
        if used is None:
            used = int(round(total * pct / 100.0))
        self.disks[path] = {"dev": dev, "total": total, "used": used, "reserved": reserved}

    def statvfs(self, path):
        if path not in self.disks:
            raise FileNotFoundError(path)
        d = self.disks[path]
        free = d["total"] - d["used"]
        return SimpleNamespace(f_frsize=1, f_blocks=d["total"], f_bfree=free, f_bavail=max(free - d["reserved"], 0))

    def stat(self, path):
        if path not in self.disks:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_dev=self.disks[path]["dev"])


class Bench:
    """``evaluate`` on a state dict. ``at(days)`` is a run ``days`` after T0; ``clock`` is the fake clock."""

    def __init__(self, **config):
        self.clock = FakeClock(T0)
        self.run = CertRun(self.clock)
        self.fs = FakeFs()
        self.state = {"services": {}}
        self.config = {"extra_certs": [], "disk_paths": ["/", "/var/lib/mongodb"]}
        self.config.update(config)
        self.run.days_left(PINNED, 400)         # the pinned certificate is fine unless a test says otherwise
        self.fs.set("/", 10, dev=1)
        self.fs.set("/var/lib/mongodb", 10, dev=1)
        self.last = None

    def at(self, seconds=None):
        """Evaluate at T0 + seconds (default: the clock as it stands). Returns (certs, disks, events)."""
        if seconds is not None:
            self.clock.t = T0 + seconds
        self.last = wmod.evaluate(self.state, self.config, self.clock(), self.run, clock=self.clock, fs=self.fs)
        return self.last

    def open_keys(self):
        return sorted(i["key"] for i in wmod.incidents.open_incidents(self.state))

    def incident(self, key):
        return self.state["incidents"][key]


@pytest.fixture
def bench():
    return Bench()


class WarnRig(Rig):
    """The restart-world rig with the real warnings stage: certificates and disks answer from fakes."""

    def __init__(self, tmp_path, monkeypatch, **config):
        super().__init__(tmp_path, monkeypatch, **config)
        self.certs = CertRun(self.clock)
        self.certs.days_left(PINNED, 400, self.base)
        self.fs = FakeFs()
        self.fs.set("/", 10)
        self.fs.set("/var/lib/mongodb", 10)

    def __call__(self, argv, timeout):
        return self.certs(argv, timeout) if argv[:1] == ["openssl"] else self.world(argv, timeout)

    def at(self, seconds):
        self.clock.t = self.base + seconds
        self.summary = run_mod.run_once(self.cfg, self.state_dir, run=self, http=self.http, now=self.clock,
                                        sleep=self.clock.advance, fs=self.fs)
        return self.summary


@pytest.fixture
def warn_rig(tmp_path, monkeypatch):
    return WarnRig(tmp_path, monkeypatch)
