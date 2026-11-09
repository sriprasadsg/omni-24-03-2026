"""Working days in the tenant's time zone (Phase 85, plan 85-14, D-08). Pure date maths, plus the zone read
through the throwaway database of tests/_mongo_test_db.py (skips without one).

Value: protects=the day a person from IT picks a silent ticket up is three Monday-to-Friday days after the
answer, at the same local hour, in the tenant's own zone, across a weekend and a daylight saving change, and
UTC when the zone is missing or unknown; fails_when=a weekend day is counted, the hour moves with a clock
change, the zone is ignored, or an unknown zone raises; no_claim=the sweep that acts on the date (85-17) and
public holidays (there is no calendar).
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import workdays
from service_desk.workdays import add_working_days
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


def utc(*parts):
    return datetime(*parts, tzinfo=timezone.utc)


def test_friday_afternoon_plus_three_is_the_next_wednesday_at_the_same_time():
    """protects=D-08 the weekend is skipped; fails_when=the result is the Monday after or a weekend day."""
    assert add_working_days(utc(2026, 11, 13, 16, 0), 3, "UTC") == utc(2026, 11, 18, 16, 0)


@pytest.mark.parametrize("start", [utc(2026, 11, 14, 10, 0), utc(2026, 11, 15, 10, 0)])
def test_a_weekend_start_counts_from_the_next_day(start):
    """protects=D-08 Saturday and Sunday starts both give the Wednesday; fails_when=the weekend day counts."""
    assert add_working_days(start, 3, "UTC") == utc(2026, 11, 18, 10, 0)


def test_midweek_and_zero_and_a_full_week():
    """protects=the arithmetic around the weekend; fails_when=an off-by-one."""
    monday = utc(2026, 11, 9, 8, 30)
    assert add_working_days(monday, 1, "UTC") == utc(2026, 11, 10, 8, 30)
    assert add_working_days(monday, 4, "UTC") == utc(2026, 11, 13, 8, 30)
    assert add_working_days(monday, 5, "UTC") == utc(2026, 11, 16, 8, 30)
    assert add_working_days(monday, 0, "UTC") == monday
    assert add_working_days(monday, -2, "UTC") == monday


def test_the_hour_does_not_move_across_the_autumn_clock_change_in_new_york():
    """protects=D-08 Friday 16:00 local on 2026-10-30 plus 3 is Wednesday 16:00 local after the change on
    2026-11-01, which is 21:00 UTC (it was 20:00 UTC before); fails_when=the local hour shifts to 15:00 or 17:00."""
    start = utc(2026, 10, 30, 20, 0)                     # 16:00 EDT
    assert add_working_days(start, 3, "America/New_York") == utc(2026, 11, 4, 21, 0)


def test_the_hour_does_not_move_across_the_spring_clock_change_in_new_york():
    """protects=D-08 the other direction: Friday 16:00 EST on 2026-03-06 plus 3 is Wednesday 16:00 EDT, 20:00 UTC."""
    assert add_working_days(utc(2026, 3, 6, 21, 0), 3, "America/New_York") == utc(2026, 3, 11, 20, 0)


def test_the_zone_decides_which_day_it_is():
    """protects=D-08 Friday 20:00 UTC is already Saturday in Auckland, so counting starts on Sunday and ends on
    Wednesday 09:00 local (Tuesday 20:00 UTC); in UTC the same instant ends Wednesday 20:00. fails_when=the zone
    is ignored."""
    start = utc(2026, 11, 13, 20, 0)
    assert add_working_days(start, 3, "Pacific/Auckland") == utc(2026, 11, 17, 20, 0)
    assert add_working_days(start, 3, "UTC") == utc(2026, 11, 18, 20, 0)


@pytest.mark.parametrize("zone", [None, "", "  ", "Mars/Olympus", 42])
def test_an_unknown_or_missing_zone_reads_utc(zone):
    """protects=D-08 UTC when the tenant has none; fails_when=an exception or another zone."""
    assert add_working_days(utc(2026, 11, 13, 16, 0), 3, zone) == utc(2026, 11, 18, 16, 0)


def test_a_naive_start_is_read_as_utc_and_the_result_is_utc():
    """protects=Mongo returns naive datetimes; fails_when=the result is naive or shifted."""
    result = add_working_days(datetime(2026, 11, 13, 16, 0), 3, "UTC")
    assert result == utc(2026, 11, 18, 16, 0) and result.utcoffset().total_seconds() == 0


async def test_the_tenant_zone_is_read_from_the_maintenance_settings(mongo_db):  # noqa: F811
    """protects=D-08 the stored zone, UTC for none, a blank or an unknown name; fails_when=an unknown name is
    returned as it is, or another tenant's zone is read."""
    db = mongo_db
    assert await workdays.tenant_zone(db, "t1") == "UTC"
    await db.maintenance_settings.insert_many([
        {"tenantId": "t1", "timeZone": "America/New_York"}, {"tenantId": "t2", "timeZone": "Not/AZone"},
        {"tenantId": "t3", "timeZone": "  "}, {"tenantId": "t4"}])
    assert await workdays.tenant_zone(db, "t1") == "America/New_York"
    for tenant in ("t2", "t3", "t4", "t5"):
        assert await workdays.tenant_zone(db, tenant) == "UTC"
