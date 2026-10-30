"""Watchdog certificate, disk and disk-forecast warnings (Phase 82, plan 82-04, HEAL-03 and HEAL-04).

Everything runs on fakes (tests/_watchdog_warnings_world.py): certificates from numbers or from a
certificate generated in tmp_path, disks from FakeFs, time from FakeClock. Nothing reads the real
/etc/nginx/ssl/omni.crt or this machine's disks.
"""
import ast
import json
import os
import ssl
import subprocess

import pytest

from tests._watchdog_restart_world import SYNC
from tests._watchdog_warnings_world import (  # noqa: F401  (fixtures are imported for pytest)
    DAY, ENDDATE_ARGV, PINNED, T0, Bench, CertRun, bench, warn_rig, wmod,
)

from omni_watchdog import incidents  # noqa: E402

WATCHDOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "omni-watchdog"))


def kinds(events, kind="cert_warning"):
    return [e for e in events if e["kind"] == kind]


# --- Task 1: tracer - a real certificate 14 days from expiry, through a whole run --------------------

def test_a_certificate_14_days_from_expiry_is_a_rung_1_entry_one_event_and_one_open_incident(tmp_path, warn_rig):
    cert = str(tmp_path / "extra.pem")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-keyout", str(tmp_path / "extra.key"), "-out", cert, "-days", "60", "-subj", "/CN=extra"],
                   check=True, capture_output=True, timeout=30)
    out = subprocess.run(ENDDATE_ARGV + [cert], check=True, capture_output=True, text=True, timeout=30).stdout
    not_after = ssl.cert_time_to_seconds(out.strip().split("=", 1)[1])
    warn_rig.cfg["extra_certs"] = [cert]
    warn_rig.certs.real[cert] = cert
    warn_rig.base = not_after - 14 * DAY                    # the run happens exactly 14 days before notAfter
    warn_rig.certs.days_left(PINNED, 400, warn_rig.base)

    warn_rig.at(0)
    body = warn_rig.body()
    entry = [c for c in body["certs"] if c["path"] == cert][0]
    assert entry["daysLeft"] == 14.0 and entry["rung"] == 1 and entry["pinned"] is False and entry["error"] is None
    assert entry["notAfter"].endswith("Z")
    pinned = [c for c in body["certs"] if c["path"] == PINNED][0]
    assert pinned["pinned"] is True and pinned["rung"] == 0
    events = kinds(body["events"])
    assert len(events) == 1 and events[0]["severity"] == "info" and events[0]["target"] == cert
    assert events[0]["params"]["rung"] == 1 and events[0]["params"]["daysLeft"] == 14
    assert events[0]["params"]["notAfter"] == entry["notAfter"] and events[0]["params"]["target"] == cert
    saved = warn_rig.saved()["incidents"]
    assert list(saved) == ["cert:%s:14d" % cert] and saved["cert:%s:14d" % cert]["severity"] == "info"


def test_the_next_run_at_the_same_clock_opens_nothing_and_emits_no_second_event(warn_rig):
    warn_rig.cfg["extra_certs"] = ["/srv/a.pem"]
    warn_rig.certs.days_left("/srv/a.pem", 14, warn_rig.base)
    warn_rig.at(0)
    warn_rig.at(0)
    sent = [e for body in warn_rig.http.posted(SYNC) for e in body["events"] if e["kind"] == "cert_warning"]
    assert len(sent) == 1
    assert warn_rig.body()["certs"][1]["rung"] == 1                       # still reported on every sync
    assert [i["key"] for i in incidents.open_incidents(warn_rig.saved())] == ["cert:/srv/a.pem:14d"]


def test_the_state_with_the_new_incident_is_on_disk_before_the_sync_is_sent(warn_rig):
    warn_rig.cfg["extra_certs"] = ["/srv/a.pem"]
    warn_rig.certs.days_left("/srv/a.pem", 14, warn_rig.base)
    seen = {}

    def spy(request):
        with open(warn_rig.state_dir + "/state.json", encoding="utf-8") as handle:
            seen["incidents"] = sorted(json.load(handle).get("incidents", {}))
        return warn_rig.http.accept_all(request)

    warn_rig.http.set("POST", SYNC, spy)
    warn_rig.at(0)
    assert seen["incidents"] == ["cert:/srv/a.pem:14d"]


def test_a_certificate_more_than_30_days_out_is_clear(bench):
    bench.run.days_left("/srv/a.pem", 30.5, T0)
    bench.config["extra_certs"] = ["/srv/a.pem"]
    certs, _disks, events = bench.at(0)
    assert [c["rung"] for c in certs] == [0, 0] and events == [] and bench.open_keys() == []
