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


# ---------------------------------------------------------------- Task 2: polkit rule, drop-ins, examples

RULE = os.path.join(WATCHDOG, "polkit", "49-omni-watchdog.rules")
HARNESS = os.path.join(ROOT, "backend", "tests", "polkit_rule_harness.js")
BACKEND_DROPIN = os.path.join(SYSTEMD, "omni-backend.service.d", "10-omni-watchdog.conf")
MONGOD_DROPIN = os.path.join(SYSTEMD, "mongod.service.d", "50-omni-restart.conf")
NGINX_DROPIN = os.path.join(SYSTEMD, "nginx.service.d", "50-omni-restart.conf")
CONF_EXAMPLE = os.path.join(WATCHDOG, "etc", "watchdog.conf.example")
ONCALL_EXAMPLE = os.path.join(WATCHDOG, "etc", "oncall.env.example")
UNITS = ("mongod.service", "omni-backend.service", "nginx.service")
VERBS = ("restart", "start", "reset-failed")


def _run_harness():
    import json
    result = subprocess.run(["node", HARNESS, RULE], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MISMATCH" not in result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_polkit_rule_harness_passes_every_case():
    cases = _run_harness()
    for unit in UNITS:
        for verb in VERBS:
            assert cases["yes %s %s" % (unit, verb)] == {"expected": "YES", "actual": "YES"}
    for name in ("no stop", "no ssh.service", "no missing unit detail", "no missing verb detail",
                 "no manage-unit-files", "no other systemd1 action"):
        assert cases[name]["actual"] == "NO" == cases[name]["expected"], name
    for name in ("not handled other user", "not handled login1.reboot"):
        assert cases[name]["actual"] == "NOT_HANDLED" == cases[name]["expected"], name
    assert all(case["expected"] == case["actual"] for case in cases.values())


def test_polkit_rule_uses_ecmascript_5_only():
    text = _text(RULE)
    for banned in ("=>", "let ", "const ", "`"):
        assert banned not in text, "polkit rules run on Duktape (ES5): %r found" % banned
    assert "org.freedesktop.systemd1.manage-units" in text
    units_line = [line for line in text.splitlines() if line.strip().startswith("var UNITS")]
    assert len(units_line) == 1 and "ollama.service" not in units_line[0]


def test_backend_dropin_delivers_only_the_ingest_token_credential():
    parser = _parse(BACKEND_DROPIN)
    assert list(parser.sections()) == ["Service"]
    assert dict(parser["Service"]) == {"LoadCredential": "omni-watchdog-token:/etc/omni-watchdog/ingest.token"}


@pytest.mark.parametrize("path", [MONGOD_DROPIN, NGINX_DROPIN])
def test_restart_dropins_only_set_restart_policy(path):
    parser = _parse(path)
    assert list(parser.sections()) == ["Service"]
    assert dict(parser["Service"]) == {"Restart": "on-failure", "RestartSec": "5s"}


def test_dropins_use_new_file_names_and_never_set_environment():
    names = []
    for dirpath, _dirs, files in os.walk(SYSTEMD):
        for name in files:
            full = os.path.join(dirpath, name)
            names.append(name)
            assert "Environment=" not in _text(full), full
    assert "kernel-rseq-check.conf" not in names
    assert os.listdir(os.path.join(SYSTEMD, "mongod.service.d")) == ["50-omni-restart.conf"]
    assert os.listdir(os.path.join(SYSTEMD, "nginx.service.d")) == ["50-omni-restart.conf"]
    assert os.listdir(os.path.join(SYSTEMD, "omni-backend.service.d")) == ["10-omni-watchdog.conf"]


def _load_watchdog_package():
    sys_path = os.path.join(ROOT, "backend", "tests")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from _watchdog_support import load_watchdog
    load_watchdog()
    import importlib
    return importlib.import_module("omni_watchdog.config"), importlib.import_module("omni_watchdog")


def test_watchdog_conf_example_parses_and_matches_the_defaults():
    config_mod, package = _load_watchdog_package()
    # Every key is commented out in the example, so loading it must give exactly the defaults.
    loaded = config_mod.load_config(CONF_EXAMPLE)
    assert loaded == config_mod.load_config(os.path.join(os.path.dirname(CONF_EXAMPLE), "does-not-exist"))
    text = _text(CONF_EXAMPLE)
    assert "[watchdog]" in text
    for key in ("backend_url", "ingest_token_path", "oncall_env_path", "stop_file", "extra_certs",
                "disk_paths", "ollama_expected"):
        assert "# %s =" % key in text, key
    assert "# backend_url = %s" % package.DEFAULTS["backend_url"] in text
    assert "# ollama_expected = false" in text


def test_oncall_example_parses_to_no_channel_and_holds_no_secret():
    config_mod, _package = _load_watchdog_package()
    oncall = config_mod.load_oncall(ONCALL_EXAMPLE)
    assert (oncall.type, oncall.routing_key, oncall.webhook_url, oncall.heartbeat_url) == ("none", "", "", "")
    keys = {}
    for line in _text(ONCALL_EXAMPLE).splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _sep, value = line.partition("=")
            keys[key.strip()] = value.strip()
    assert set(keys) == {"ONCALL_TYPE", "PAGERDUTY_ROUTING_KEY", "WEBHOOK_URL", "WEBHOOK_FORMAT", "HEARTBEAT_URL"}
    assert all(value == "" for value in keys.values())
