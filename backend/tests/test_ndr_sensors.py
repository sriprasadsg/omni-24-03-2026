"""sensor_health and window_deltas (88.1, stage 1).

The six sensor states with their boundaries and precedence, and counter growth across Suricata restarts,
out-of-order samples and a sensor whose clock is off. Every case passes the clock in; nothing sleeps.
"""
from datetime import datetime, timedelta, timezone

import pytest

from ndr_sensors import (AWAITING_FIRST_REPORT, DEGRADED, DROPPING_PACKETS, HEALTH_WINDOW, LIVE, NEVER_REPORTED,
                         NO_PACKET_GROWTH, NO_RECENT_STATS, NO_RULES_LOADED, NO_SENSOR, REMOVED, SILENT,
                         day_coverage, sensor_health, window_deltas)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
GROWING = [(1000, 0), (1100, 0), (1200, 1)]
FLAT = [(1000, 0), (1000, 0), (1000, 0)]


def _samples(points, end=NOW):
    """One sample per minute, the last one at ``end``; a point is (packets, drops) or (packets, drops, uptime)."""
    start = end - timedelta(minutes=len(points) - 1)
    rows = []
    for index, (packets, drops, *uptime) in enumerate(points):
        rows.append({"sampledAt": start + timedelta(minutes=index), "packets": packets, "drops": drops,
                     "uptime": uptime[0] if uptime else 600 + 60 * index})
    return rows


def _sensor(age=timedelta(seconds=10), **fields):
    return {"sensorId": "s1", "lastStatsAt": NOW - age, **fields}


def test_a_tenant_without_a_record_has_no_sensor():
    assert sensor_health(None, [], NOW)["state"] == NO_SENSOR


def test_a_sensor_that_never_sent_stats_is_awaiting_its_first_report():
    assert sensor_health({"sensorId": "s1", "createdAt": NOW}, [], NOW)["state"] == AWAITING_FIRST_REPORT


def test_fresh_stats_with_growing_packets_are_live():
    health = sensor_health(_sensor(), _samples(GROWING), NOW)

    assert health["state"] == LIVE
    assert health["reason"] is None
    assert health["packets"] == 200
    assert health["dropRatio"] == pytest.approx(1 / 200)
    assert health["lastStatsAt"] == NOW - timedelta(seconds=10)


@pytest.mark.parametrize("age, state", [
    (timedelta(minutes=4, seconds=59), LIVE),
    (timedelta(minutes=5), SILENT),
])
def test_a_sensor_turns_silent_when_its_last_stats_are_five_minutes_old(age, state):
    assert sensor_health(_sensor(age), _samples(GROWING, end=NOW - age), NOW)["state"] == state


def test_fresh_stats_with_flat_packets_are_degraded():
    health = sensor_health(_sensor(), _samples(FLAT), NOW)

    assert (health["state"], health["reason"]) == (DEGRADED, NO_PACKET_GROWTH)


@pytest.mark.parametrize("drops, state, reason", [
    (50, LIVE, None),
    (51, DEGRADED, DROPPING_PACKETS),
])
def test_a_sensor_is_degraded_only_above_five_percent_drops(drops, state, reason):
    health = sensor_health(_sensor(), _samples([(0, 0), (1000, drops)]), NOW)

    assert (health["state"], health["reason"]) == (state, reason)
    assert health["dropRatio"] == pytest.approx(drops / 1000)


@pytest.mark.parametrize("sensor, samples", [
    (_sensor(retiredAt=NOW), _samples(GROWING)),
    (_sensor(timedelta(hours=3), retiredAt=NOW), _samples(FLAT)),
    ({"sensorId": "s1", "retiredAt": NOW}, []),
])
def test_a_retired_sensor_is_removed_whatever_else_is_true(sensor, samples):
    assert sensor_health(sensor, samples, NOW)["state"] == REMOVED


def test_silent_wins_over_degraded():
    age = timedelta(minutes=30)

    assert sensor_health(_sensor(age), _samples(FLAT, end=NOW - age), NOW)["state"] == SILENT


def test_one_sample_alone_never_reads_as_live():
    health = sensor_health(_sensor(), _samples([(5000, 0)]), NOW)

    assert (health["state"], health["reason"]) == (DEGRADED, NO_PACKET_GROWTH)


def test_a_sensor_whose_clock_is_ten_minutes_behind_still_reads_live():
    samples = _samples(GROWING, end=NOW - timedelta(minutes=10))

    assert sensor_health(_sensor(), samples, NOW)["state"] == LIVE


def test_naive_datetimes_from_the_database_read_as_utc():
    sensor = {"sensorId": "s1", "lastStatsAt": (NOW - timedelta(seconds=10)).replace(tzinfo=None)}
    samples = [{**row, "sampledAt": row["sampledAt"].replace(tzinfo=None)} for row in _samples(GROWING)]

    assert sensor_health(sensor, samples, NOW)["state"] == LIVE


def test_the_window_covers_five_full_minutes_ending_at_the_newest_sample():
    seven_minutes = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0), (50, 0), (60, 0)]

    assert window_deltas(_samples(seven_minutes), HEALTH_WINDOW) == (50, 0)


def test_growth_before_the_window_does_not_count():
    points = [(100, 0), (500, 0), (900, 0)] + [(900, 0)] * 6

    assert window_deltas(_samples(points), HEALTH_WINDOW) == (0, 0)
    assert sensor_health(_sensor(), _samples(points), NOW)["state"] == DEGRADED


def test_a_suricata_restart_starts_a_new_segment_counted_from_zero():
    points = [(1000, 10, 600), (1100, 10, 660), (50, 0, 20), (120, 2, 80)]

    assert window_deltas(_samples(points), HEALTH_WINDOW) == (100 + 50 + 70, 2)


def test_a_restart_is_seen_from_uptime_even_when_packets_did_not_fall():
    assert window_deltas(_samples([(100, 0, 600), (150, 0, 30)]), HEALTH_WINDOW) == (150, 0)


def test_sample_order_does_not_change_the_result():
    points = [(1000, 10, 600), (1100, 10, 660), (50, 0, 20), (120, 2, 80)]
    ordered = _samples(points)

    assert window_deltas(list(reversed(ordered)), HEALTH_WINDOW) == window_deltas(ordered, HEALTH_WINDOW)


def test_no_samples_means_no_growth():
    assert window_deltas([], HEALTH_WINDOW) == (0, 0)


@pytest.mark.parametrize("sensor, points, reason", [
    ({"sensorId": "s1", "rulesLoaded": 100}, GROWING, NEVER_REPORTED),
    (_sensor(timedelta(hours=24), rulesLoaded=100), GROWING, NO_RECENT_STATS),
    (_sensor(timedelta(hours=23, minutes=59, seconds=59), rulesLoaded=100), GROWING, None),
    (_sensor(rulesLoaded=0), GROWING, NO_RULES_LOADED),
    (_sensor(), GROWING, NO_RULES_LOADED),
    (_sensor(rulesLoaded=100), FLAT, NO_PACKET_GROWTH),
    (_sensor(rulesLoaded=100), [(0, 0), (1000, 49)], None),
    (_sensor(rulesLoaded=100), [(0, 0), (1000, 50)], DROPPING_PACKETS),
])
def test_day_coverage_names_what_kept_a_sensor_from_watching(sensor, points, reason):
    assert day_coverage(sensor, _samples(points, end=sensor.get("lastStatsAt", NOW)), NOW)["reason"] == reason


def test_day_coverage_measures_the_whole_day_not_the_last_five_minutes():
    day = [(index * 100, 0) for index in range(24 * 60 + 1)]

    cover = day_coverage(_sensor(rulesLoaded=100), _samples(day), NOW)

    assert (cover["reason"], cover["packets"], cover["dropRatio"]) == (None, 24 * 60 * 100, 0.0)
