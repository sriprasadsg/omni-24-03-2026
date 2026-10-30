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
from tests._watchdog_support import FakeHttp
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


# --- Task 3: boundaries, expired and unreadable certificates, extra paths, caps, budget, never-delete -------

EXTRA = "/srv/extra.pem"


def read_cert(bench, offset_seconds, path=EXTRA):
    """Evaluate once with ``path`` expiring ``offset_seconds`` after the run; returns (entry, open cert keys)."""
    bench.config["extra_certs"] = [path]
    bench.run.not_after[path] = T0 + offset_seconds
    certs, _disks, _events = bench.at(0)
    return [c for c in certs if c["path"] == path][0], [k for k in bench.open_keys() if k.startswith("cert:")]


@pytest.mark.parametrize("offset, key, rung", [
    (30 * DAY, "30d", 1), (30 * DAY + 1, None, 0),
    (14 * DAY, "14d", 1), (14 * DAY + 1, "30d", 1),
    (7 * DAY, "7d", 2), (7 * DAY + 1, "14d", 1),
    (1 * DAY, "1d", 3), (1 * DAY + 1, "7d", 2),
    (0, "1d", 3), (-1 * DAY, "1d", 3),
])
def test_cert_ladder_boundaries_at_most_thresholds(bench, offset, key, rung):
    entry, keys = read_cert(bench, offset)
    assert entry["rung"] == rung and entry["daysLeft"] == offset / DAY
    assert keys == (["cert:%s:%s" % (EXTRA, key)] if key else [])


@pytest.mark.parametrize("used, key, rung", [
    (8000, "80", 1), (7999, None, 0), (9000, "90", 2), (8999, "80", 1), (9500, "95", 3), (9499, "90", 2),
])
def test_disk_ladder_boundaries_exact_threshold_and_one_hundredth_of_a_point_below(bench, used, key, rung):
    bench.fs.set("/", total=10_000, used=used, dev=1)
    disk = first_disk(bench, 0)
    assert disk["usedPct"] == used / 100.0 and disk["rung"] == rung            # a float, never rounded first
    assert [k for k in bench.open_keys() if k.startswith("disk:")] == (["disk:/:%s" % key] if key else [])


def test_cert_days_left_is_a_float_that_is_never_rounded(bench):
    entry, _keys = read_cert(bench, 1.5 * DAY + 1)
    assert entry["daysLeft"] == (1.5 * DAY + 1) / DAY and entry["daysLeft"] > 1.5


def test_cert_walk_down_the_ladder_opens_each_key_once_and_clears_the_old_one(bench):
    bench.config["extra_certs"] = [EXTRA]
    trail, sent = [], []
    for step, days in enumerate((31, 29, 13, 6, 0.5, -1)):
        bench.run.not_after[EXTRA] = T0 + days * DAY
        _c, _d, events = bench.at(step * 60)
        sent += kinds(events)
        trail.append([k.rsplit(":", 1)[1] for k in bench.open_keys()])
    assert trail == [[], ["30d"], ["14d"], ["7d"], ["1d"], ["1d"]]            # one open incident at a time
    assert [(e["params"]["rung"], e["severity"]) for e in sent] == [(1, "info"), (1, "info"), (2, "warning"), (3, "critical")]
    assert bench.incident("cert:%s:30d" % EXTRA)["clearedAt"] is not None and len(sent) == 4


def test_cert_expired_at_first_sight_is_a_critical_expired_incident(bench):
    read_cert(bench, -2 * DAY)
    incident = bench.incident("cert:%s:1d" % EXTRA)
    assert incident["severity"] == "critical" and incident["kind"] == "cert_expired"
    assert bench.last[2][0]["params"]["daysLeft"] == -2.0


def test_cert_unreadable_file_is_a_warning_and_the_others_are_still_checked(bench):
    bench.config["extra_certs"] = ["/srv/missing.pem", "/srv/junk.pem", EXTRA]
    bench.run.garbage.add("/srv/junk.pem")
    bench.run.days_left(EXTRA, 20)
    certs, _d, events = bench.at(0)
    by_path = {c["path"]: c for c in certs}
    for path in ("/srv/missing.pem", "/srv/junk.pem"):
        assert by_path[path]["error"] == "unreadable" and by_path[path]["rung"] == 2
        assert by_path[path]["daysLeft"] is None and by_path[path]["notAfter"] is None
        assert bench.incident("cert:%s:unreadable" % path)["severity"] == "warning"
    assert by_path[EXTRA]["rung"] == 1 and by_path[PINNED]["rung"] == 0
    assert [e["params"].get("error") for e in events if e["target"] != EXTRA] == ["unreadable", "unreadable"]
    bench.run.missing.clear()
    bench.run.days_left("/srv/missing.pem", 400)
    bench.at(60)
    assert bench.incident("cert:/srv/missing.pem:unreadable")["clearedAt"] is not None


def test_cert_extra_paths_are_checked_in_config_order_and_only_the_nginx_cert_is_pinned(bench):
    bench.config["extra_certs"] = ["/srv/b.pem", PINNED, "/srv/a.pem", "/srv/b.pem"]
    bench.run.days_left("/srv/a.pem", 400)
    bench.run.days_left("/srv/b.pem", 400)
    certs, _d, _e = bench.at(0)
    assert [(c["path"], c["pinned"]) for c in certs] == [(PINNED, True), ("/srv/b.pem", False), ("/srv/a.pem", False)]
    assert [path for path, _t in bench.run.reads] == [PINNED, "/srv/b.pem", "/srv/a.pem"]
    assert all(call[:5] == ENDDATE_ARGV and call[5] == path for call, (path, _t) in zip(bench.run.calls, bench.run.reads))


def test_cert_a_long_extra_certs_list_is_capped_at_32_entries_pinned_first(bench, warn_rig):
    extras = ["/srv/c%02d.pem" % i for i in range(40)]
    for path in extras:
        bench.run.days_left(path, 400)
        warn_rig.certs.days_left(path, 400, warn_rig.base)
    bench.config["extra_certs"] = extras
    certs, _d, _e = bench.at(0)
    assert wmod.MAX_CERTS == 32 and [c["path"] for c in certs] == [PINNED] + extras[:31]
    assert len(bench.run.reads) == 32
    warn_rig.cfg["extra_certs"] = extras                      # and the whole body would be accepted by the backend model
    warn_rig.at(0)
    assert len(warn_rig.body()["certs"]) == 32


def test_cert_removed_from_the_config_stops_being_watched_and_its_incident_clears(bench):
    read_cert(bench, 5 * DAY)
    assert bench.open_keys() == ["cert:%s:7d" % EXTRA]
    bench.config["extra_certs"] = []
    certs, _d, events = bench.at(60)
    assert [c["path"] for c in certs] == [PINNED] and bench.open_keys() == [] and events == []


def test_cert_reads_share_a_six_second_allowance_and_an_unreached_one_keeps_its_last_entry(bench):
    extras = ["/srv/a.pem", "/srv/b.pem", "/srv/c.pem", "/srv/d.pem"]
    bench.config["extra_certs"] = extras
    for path in extras:
        bench.run.days_left(path, 14)
    bench.at(0)
    before = {c["path"]: dict(c) for c in bench.last[0]}
    assert sorted(bench.open_keys()) == sorted("cert:%s:14d" % p for p in extras)
    bench.run.reads.clear()
    bench.run.per_read = 2.5                                  # each openssl read now takes 2.5 s of fake time
    for path in extras:
        bench.run.days_left(path, 400)                        # all four have been renewed since
    certs, _d, events = bench.at(60)
    assert [p for p, _t in bench.run.reads] == [PINNED, "/srv/a.pem", "/srv/b.pem"]
    assert [t for _p, t in bench.run.reads] == [3, 3, 1.0] and wmod.CERT_BUDGET == 6 and wmod.READ_TIMEOUT == 3
    by_path = {c["path"]: c for c in certs}
    assert by_path["/srv/a.pem"]["rung"] == 0 and by_path["/srv/b.pem"]["rung"] == 0
    assert by_path["/srv/c.pem"] == before["/srv/c.pem"] and by_path["/srv/d.pem"] == before["/srv/d.pem"]
    assert by_path["/srv/c.pem"]["error"] is None                                 # not reported as unreadable
    assert sorted(bench.open_keys()) == ["cert:/srv/c.pem:14d", "cert:/srv/d.pem:14d"] and events == []
    bench.run.per_read = 0.0
    bench.at(120)
    assert bench.open_keys() == []                                                # the next run catches up


def test_cert_unreached_with_no_earlier_entry_is_left_out_rather_than_made_up(bench):
    bench.config["extra_certs"] = ["/srv/a.pem", "/srv/b.pem", "/srv/c.pem"]
    for path in bench.config["extra_certs"]:
        bench.run.days_left(path, 400)
    bench.run.per_read = 3.5                                  # two reads use up the six seconds
    certs, _d, events = bench.at(0)
    assert [c["path"] for c in certs] == [PINNED, "/srv/a.pem"] and events == []


def test_cert_a_timed_out_read_is_not_a_statement_about_the_file(bench):
    read_cert(bench, 20 * DAY)
    bench.run.timeouts.add(EXTRA)
    certs, _d, events = bench.at(60)
    assert [c for c in certs if c["path"] == EXTRA][0]["error"] is None and events == []
    assert bench.open_keys() == ["cert:%s:30d" % EXTRA]


# the run: stage order and a killed run

def test_restart_and_warning_events_share_one_spool_so_an_outage_loses_neither(warn_rig):
    warn_rig.cfg["extra_certs"] = [EXTRA]
    warn_rig.certs.days_left(EXTRA, 3, warn_rig.base)
    warn_rig.world.down.add("mongod")
    warn_rig.http.set("POST", SYNC, (503, {}))
    warn_rig.at(0)
    warn_rig.at(60)                                           # second failed check: restarted; sync is down for both runs
    assert warn_rig.summary["synced"] is False and warn_rig.summary["spooled"] >= 3
    warn_rig.http.set("POST", SYNC, FakeHttp.accept_all)
    warn_rig.at(120)
    delivered = {e["kind"] for e in warn_rig.body()["events"]}
    assert {"cert_warning", "restart", "service_down"} <= delivered
    assert warn_rig.summary["spooled"] == 0


def test_a_run_that_dies_during_the_warning_stage_leaves_the_previous_complete_state(warn_rig, monkeypatch):
    warn_rig.at(0)
    path = warn_rig.state_dir + "/state.json"
    before = open(path, "rb").read()
    warn_rig.certs.days_left(PINNED, 3, warn_rig.base)

    def killed(state, *args, **kwargs):
        state["incidents"] = {"half": {"written": True}}
        raise KeyboardInterrupt("TimeoutStartSec")

    monkeypatch.setattr(wmod, "evaluate", killed)
    with pytest.raises(KeyboardInterrupt):
        warn_rig.at(60)
    assert open(path, "rb").read() == before
    json.loads(before)                                        # and it is complete JSON


# PROH-82-03: the watchdog can only read

def _watchdog_sources():
    for root, _dirs, files in os.walk(WATCHDOG_DIR):
        for name in files:
            if name.endswith(".py") or name == "omni-watchdog":
                path = os.path.join(root, name)
                yield os.path.relpath(path, WATCHDOG_DIR), open(path, encoding="utf-8").read()


def test_never_deletes_or_renews_a_certificate_or_a_file():
    deleting = {"unlink", "truncate", "rmtree", "rmdir", "removedirs", "ftruncate"}
    found = []
    for name, source in _watchdog_sources():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                func = node.func
                is_os_remove = func.attr == "remove" and isinstance(func.value, ast.Name) and func.value.id in ("os", "shutil")
                if func.attr in deleting or is_os_remove:
                    found.append((name, func.attr))
    assert found and {name for name, _attr in found} == {"omni_watchdog/state.py"}, found     # only the watchdog's own state files


def test_never_runs_openssl_with_any_verb_but_x509_enddate_and_names_no_renewal_tool():
    lists = []
    for name, source in _watchdog_sources():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "openssl":
                lists.append([e.value for e in node.elts[:4] if isinstance(e, ast.Constant)])
        for word in ("certbot", "genrsa", "req -new", "acme"):
            assert word not in source, (name, word)
    assert lists and all(item == ["openssl", "x509", "-noout", "-enddate"] for item in lists)


def test_never_reads_certificates_or_disks_in_the_backend_for_this_feature():
    backend = os.path.join(os.path.dirname(__file__), "..")
    for name in ("watchdog_ingest_endpoints.py", os.path.join("autonomous_ops", "selfheal.py")):
        source = open(os.path.join(backend, name), encoding="utf-8").read()
        assert "statvfs" not in source and "cert_time_to_seconds" not in source and "-enddate" not in source
