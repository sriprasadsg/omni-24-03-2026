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


# --- Task 2: disk ladder with hysteresis, one entry per filesystem, hourly samples, the 7-day forecast ------

def first_disk(bench, seconds=None):
    return bench.at(seconds)[1][0]


def test_disk_at_81_percent_is_one_entry_listing_both_paths_and_opens_disk_80(bench):
    bench.fs.set("/", 81, dev=7)
    bench.fs.set("/var/lib/mongodb", 81, dev=7)
    certs, disks, events = bench.at(0)
    assert len(disks) == 1
    disk = disks[0]
    assert disk["mount"] == "/" and disk["paths"] == ["/", "/var/lib/mongodb"]
    assert disk["usedPct"] == 81.0 and disk["rung"] == 1 and disk["totalBytes"] == 10_000 and disk["freeBytes"] == 1_900
    assert disk["forecast"] == {"state": "insufficient", "days": None, "rung": 0}
    assert bench.open_keys() == ["disk:/:80"] and bench.incident("disk:/:80")["severity"] == "info"
    assert [e["kind"] for e in events] == ["disk_warning"]
    assert events[0]["params"] == {"target": "/", "rung": 1, "usedPct": 81.0} and events[0]["severity"] == "info"


def test_disk_ladder_moves_up_without_repeating_and_keeps_a_rung_until_two_points_below(bench):
    steps = []
    for seconds, pct in ((0, 81), (60, 89), (120, 90), (180, 88.5), (240, 87.9), (300, 79.0), (360, 77.9)):
        bench.fs.set("/", pct, dev=1)
        _certs, disks, events = bench.at(seconds)
        steps.append((pct, bench.open_keys(), [e["severity"] for e in events], disks[0]["rung"]))
    assert steps == [
        (81, ["disk:/:80"], ["info"], 1),
        (89, ["disk:/:80"], [], 1),                      # nothing changes below the next threshold
        (90, ["disk:/:90"], ["warning"], 2),             # 80 cleared, 90 opened, one event
        (88.5, ["disk:/:90"], [], 2),                    # within 2 points: stays
        (87.9, ["disk:/:80"], ["info"], 1),              # 2 points below 90: clears; 80 is the rung now
        (79.0, ["disk:/:80"], [], 1),                    # 78 and above keeps 80
        (77.9, [], [], 0),
    ]
    assert bench.incident("disk:/:90")["clearedAt"] is not None


def test_disk_two_filesystems_make_two_entries(bench):
    bench.fs.set("/", 10, dev=1)
    bench.fs.set("/var/lib/mongodb", 96, dev=2)
    _certs, disks, events = bench.at(0)
    assert [(d["mount"], d["paths"], d["rung"]) for d in disks] == [("/", ["/"], 0), ("/var/lib/mongodb", ["/var/lib/mongodb"], 3)]
    assert bench.open_keys() == ["disk:/var/lib/mongodb:95"] and bench.incident("disk:/var/lib/mongodb:95")["severity"] == "critical"


def test_disk_percent_uses_df_semantics_reserved_blocks_count_as_used(bench):
    bench.fs.set("/", total=10_000, used=7_000, reserved=1_000, dev=1)          # df: 7000 / (7000 + 2000) = 77.7..
    disk = first_disk(bench, 0)
    assert disk["usedPct"] == pytest.approx(100.0 * 7000 / 9000) and disk["freeBytes"] == 2_000 and disk["totalBytes"] == 10_000


def test_disk_an_unreadable_path_is_skipped_and_the_other_still_reported(bench):
    del bench.fs.disks["/var/lib/mongodb"]
    _certs, disks, _events = bench.at(0)
    assert [d["mount"] for d in disks] == ["/"]


def test_disk_one_sample_per_hour_never_more_and_none_older_than_eight_days(bench):
    for minute in range(120):                                    # runs every 60 s for 2 hours
        bench.at(minute * 60)
    assert [s[0] for s in bench.state["disk"]["/"]] == [T0, T0 + 3600]
    samples = [[T0 - 9 * DAY, 1, 1], [T0 - 8 * DAY + 1, 1, 1]]
    assert wmod.record_sample(samples, T0, 5, 5) is True
    assert [s[0] for s in samples] == [T0 - 8 * DAY + 1, T0]


def test_disk_a_sample_dated_ten_minutes_before_the_previous_one_is_discarded():
    samples = [[T0, 5, 5]]
    assert wmod.record_sample(samples, T0 - 600, 9, 9) is False and samples == [[T0, 5, 5]]
    assert wmod.record_sample(samples, T0 - 299, 9, 9) is False and len(samples) == 1       # still inside the hour
    assert wmod.record_sample(samples, T0 + 3600, 9, 9) is True and len(samples) == 2


def growing(bench, days, rate, avail_at_end, total=10 ** 10, step=3600):
    """Hourly runs for ``days`` days with used growing ``rate`` bytes/s and ``avail_at_end`` free at the end."""
    end = days * DAY
    for seconds in range(0, int(end) + 1, step):
        used = total - avail_at_end - int(rate * (end - seconds))
        bench.fs.set("/", total=total, used=used, dev=1)
        bench.fs.set("/var/lib/mongodb", total=total, used=used, dev=1)
        bench.at(seconds)
    return bench.last[1][0]


def test_forecast_six_days_of_samples_is_insufficient_and_opens_nothing(bench):
    disk = growing(bench, 6, 1000, 10 ** 6)
    assert disk["forecast"] == {"state": "insufficient", "days": None, "rung": 0}
    assert [k for k in bench.open_keys() if k.startswith("disk-forecast")] == []


def test_forecast_seven_days_of_flat_usage_is_flat_with_no_forecast(bench):
    disk = growing(bench, 7, 0, 10 ** 9)
    assert disk["forecast"] == {"state": "flat", "days": None, "rung": 0}
    assert [k for k in bench.open_keys() if k.startswith("disk-forecast")] == []


def test_forecast_growth_that_fills_in_ten_days_is_rung_1_with_the_14d_incident(bench):
    disk = growing(bench, 7, 1000, 10 * 86_400 * 1000)
    assert disk["forecast"]["state"] == "ok" and disk["forecast"]["days"] == pytest.approx(10.0, rel=1e-6)
    assert disk["forecast"]["rung"] == 1
    assert "disk-forecast:/:14d" in bench.open_keys() and bench.incident("disk-forecast:/:14d")["severity"] == "info"
    sent = [e for e in bench.last[2] if e["kind"] == "disk_forecast"]
    assert all(e["params"]["rung"] == 1 for e in sent)


def test_forecast_under_a_day_is_critical_with_the_1d_incident(bench):
    disk = growing(bench, 7, 1000, int(0.9 * 86_400 * 1000))
    assert disk["forecast"]["days"] == pytest.approx(0.9, rel=1e-6) and disk["forecast"]["rung"] == 3
    assert bench.incident("disk-forecast:/:1d")["severity"] == "critical"
    assert [k for k in bench.open_keys() if k.startswith("disk-forecast")] == ["disk-forecast:/:1d"]


def test_forecast_needs_exactly_seven_days_of_span_not_a_second_less():
    ok = [[T0 + 0, 0, 0], [T0 + 3.5 * DAY, 350, 0], [T0 + 7 * DAY, 700, 0]]
    assert wmod.forecast(ok, 10_000_000, T0 + 7 * DAY)["state"] == "ok"
    short = [[T0 + 1, 0, 0], [T0 + 3.5 * DAY, 350, 0], [T0 + 7 * DAY, 700, 0]]
    assert wmod.forecast(short, 10_000_000, T0 + 7 * DAY)["state"] == "insufficient"


def test_forecast_days_exactly_on_a_threshold_belong_to_that_rung():
    assert [wmod.forecast_rung(d) for d in (14.0, 14.0000001, 7.0, 7.0000001, 1.0, 1.0000001, 0.0)] == [1, 0, 2, 1, 3, 2, 3]


def test_forecast_slope_is_least_squares_in_float_bytes_per_second():
    samples = [[T0 + h * 3600, 1000 * h * 3600, 0] for h in range(0, 169)]
    result = wmod.forecast(samples, 14 * DAY * 1000, T0 + 7 * DAY)
    assert result["state"] == "ok" and result["days"] == pytest.approx(14.0, rel=1e-9)


def test_forecast_incident_clears_only_when_days_rise_twenty_percent_above_its_threshold(bench, monkeypatch):
    days = {"d": 6.0}
    monkeypatch.setattr(wmod, "forecast", lambda samples, avail, now: {"state": "ok", "days": days["d"], "rung": 0})
    trail = []
    for seconds, d in ((0, 6.0), (60, 8.0), (120, 8.4), (180, 8.5), (240, 13.0), (300, 17.0)):
        days["d"] = d
        bench.at(seconds)
        trail.append((d, [k for k in bench.open_keys() if k.startswith("disk-forecast")]))
    assert trail == [(6.0, ["disk-forecast:/:7d"]), (8.0, ["disk-forecast:/:7d"]), (8.4, ["disk-forecast:/:7d"]),
                     (8.5, ["disk-forecast:/:14d"]), (13.0, ["disk-forecast:/:14d"]), (17.0, [])]


def test_forecast_incident_clears_when_growth_stops_but_stays_when_history_is_missing(bench, monkeypatch):
    state = {"v": {"state": "ok", "days": 5.0, "rung": 2}}
    monkeypatch.setattr(wmod, "forecast", lambda samples, avail, now: state["v"])
    bench.at(0)
    assert "disk-forecast:/:7d" in bench.open_keys()
    state["v"] = {"state": "insufficient", "days": None, "rung": 0}
    _c, disks, events = bench.at(60)
    assert "disk-forecast:/:7d" in bench.open_keys() and events == [] and disks[0]["forecast"]["rung"] == 2
    state["v"] = {"state": "flat", "days": None, "rung": 0}
    bench.at(120)
    assert [k for k in bench.open_keys() if k.startswith("disk-forecast")] == []
