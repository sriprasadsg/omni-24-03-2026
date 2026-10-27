"""Static checks of the watchdog install files (Phase 82, plan 82-06).

Nothing here installs, enables or runs anything on the host. Unit files are copied into a temp
directory for ``systemd-analyze verify``; the polkit rule is evaluated by a node stub harness.
"""
import configparser
import os
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WATCHDOG = os.path.join(ROOT, "deploy", "omni-watchdog")
SYSTEMD = os.path.join(WATCHDOG, "systemd")
SERVICE = os.path.join(SYSTEMD, "omni-watchdog.service")
TIMER = os.path.join(SYSTEMD, "omni-watchdog.timer")


def _parse(path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    with open(path, encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def _text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------- Task 1: service and timer

@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze is not on PATH")
def test_systemd_analyze_verify_is_clean_for_service_and_timer(tmp_path):
    for src in (SERVICE, TIMER):
        shutil.copy(src, tmp_path / os.path.basename(src))
    result = subprocess.run(
        ["systemd-analyze", "verify", str(tmp_path / "omni-watchdog.service"), str(tmp_path / "omni-watchdog.timer")],
        capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert "RuntimeMaxSec" not in output
    # The installed script path does not exist on a build host; that is the only tolerated finding.
    findings = [line for line in output.splitlines()
                if line.strip() and "/usr/local/lib/omni-watchdog" not in line and "omni-watchdog.py" not in line]
    assert findings == [], output
    assert "RuntimeMaxSec" not in _text(SERVICE)


def test_service_is_a_hardened_oneshot_run_as_the_watchdog_user():
    unit = _parse(SERVICE)["Service"]
    assert unit["Type"] == "oneshot"
    assert unit["User"] == "omni-watchdog"
    assert unit["Group"] == "omni-watchdog"
    assert unit["TimeoutStartSec"] == "45"
    assert unit["StateDirectory"] == "omni-watchdog"
    assert unit["StateDirectoryMode"] == "0750"
    assert unit["NoNewPrivileges"] == "yes"
    assert unit["ProtectSystem"] == "strict"
    assert unit["ProtectHome"] == "yes"
    assert unit["PrivateTmp"] == "yes"
    assert unit["RestrictAddressFamilies"].split() == ["AF_UNIX", "AF_INET", "AF_INET6"]
    assert unit["CapabilityBoundingSet"].strip() == ""
    assert unit["UMask"] == "0077"
    assert "ConfigurationDirectory" not in unit


def test_service_runs_the_installed_copy_of_the_entry_script():
    exec_start = _parse(SERVICE)["Service"]["ExecStart"].split()
    assert exec_start[:2] == ["/usr/bin/python3", "-I"]
    script = exec_start[2]
    assert script == "/usr/local/lib/omni-watchdog/omni-watchdog.py"
    assert os.path.isfile(os.path.join(WATCHDOG, os.path.basename(script)))


def test_timer_fires_every_minute_and_is_wanted_by_timers_target():
    parser = _parse(TIMER)
    timer = parser["Timer"]
    assert timer["OnBootSec"] == "60"
    assert timer["OnUnitActiveSec"] == "60"
    assert timer["AccuracySec"] == "5s"
    assert parser["Install"]["WantedBy"] == "timers.target"
