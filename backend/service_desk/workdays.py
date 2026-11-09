"""The tenant's time zone, as the desk reads it (D-08).

The zone is ``maintenance_settings.timeZone`` (the one Phase 84 maintenance windows use); a tenant with none,
or one this host cannot resolve, reads UTC. Days are counted by the calendar in that zone:
Monday to Friday are working days and there is no holiday calendar (a decision of 85-CONTEXT).
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from autonomous_ops.rollout import store

DEFAULT_ZONE = "UTC"


def zone_of(name):
    """The ``ZoneInfo`` for ``name``, or None when it is not a zone this host knows."""
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        return ZoneInfo(name.strip())
    except Exception:           # unknown or malformed name
        return None


def add_working_days(start: datetime, days: int, zone: Any) -> datetime:
    """``start`` plus ``days`` working days, as the same clock time in ``zone`` (UTC when the zone is unknown),
    returned in UTC. Saturday and Sunday are skipped, so Friday 16:00 plus 3 is the next Wednesday 16:00, and a
    start on a weekend counts from the next day. Keeping the local clock time means a change of daylight
    saving time in between does not move the hour the requester was told."""
    tz = zone_of(zone) or ZoneInfo(DEFAULT_ZONE)
    moment = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    local = moment.astimezone(tz)
    day, remaining = local.date(), max(int(days), 0)
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    result = datetime(day.year, day.month, day.day, local.hour, local.minute, local.second, local.microsecond, tzinfo=tz)
    return result.astimezone(timezone.utc)


async def tenant_zone(db, tenant_id: str) -> str:
    """The tenant's zone name, ``UTC`` when none is stored, the stored one is unknown or the read fails."""
    try:
        setting = await store.maintenance_settings(db).find_one({"tenantId": tenant_id}, {"_id": 0, "timeZone": 1})
    except Exception:
        return DEFAULT_ZONE
    name = (setting or {}).get("timeZone")
    return name.strip() if zone_of(name) is not None else DEFAULT_ZONE
