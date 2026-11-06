"""Maintenance windows, read the way a rollout needs them (PTCH-05).

A window is a start and end time of day in the tenant's time zone, daily or on chosen ISO weekdays
(Monday is 1, Sunday is 7), or a one-time window with a start and end date and time. A window that
ends at or before its start runs past midnight and is keyed by the date it starts on. Everything is
built with the standard library's ``zoneinfo`` so a daylight saving change moves the UTC edges instead
of breaking them.

Rows saved by the old maintenance screen (``start_time`` / ``end_time`` ISO strings, ``days_of_week``
with Monday as 0) are converted on read: the time of day as written, the weekday plus one.

Fail closed (PROH-84-05): a tenant with no window, a window this module cannot read, or an unknown
time zone is never treated as open. ``TenantWindows.readable`` is False when anything was skipped.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..scope import raw
from . import store

logger = logging.getLogger(__name__)

DEFAULT_ZONE = "UTC"
Occurrence = Tuple[datetime, datetime]


@dataclass
class Window:
    name: str
    recurrence: str                       # "daily" | "weekly" | "none" (one time)
    start: Optional[time] = None
    end: Optional[time] = None
    days: Optional[Tuple[int, ...]] = None    # ISO weekdays; None means every day
    once: Optional[Tuple[datetime, datetime]] = None   # one-time: naive means local time in the zone


@dataclass
class TenantWindows:
    zone: str = DEFAULT_ZONE
    windows: List[Window] = field(default_factory=list)
    readable: bool = True

    def open_at(self, now: datetime) -> Optional[Occurrence]:
        """The occurrence open at ``now``. No window, or any window that could not be read, means closed:
        a tenant is never treated as always open (PROH-84-05)."""
        if not self.readable or not self.windows:
            return None
        return is_open(self.windows, self.zone, now)


def _zone(name: str) -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(name)
    except Exception:         # unknown or malformed name
        return None


def _hhmm(value: Any) -> Optional[time]:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    try:
        return time(int(value[:2]), int(value[3:]))
    except ValueError:
        return None


def _stamp(value: Any) -> Optional[datetime]:
    """A datetime from a datetime or an ISO string, left naive when it carries no offset."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _clock(value: Any) -> Optional[time]:
    """The time of day as written: "HH:MM", or the clock part of an ISO date and time."""
    plain = _hhmm(value)
    if plain is not None:
        return plain
    stamp = _stamp(value)
    return time(stamp.hour, stamp.minute) if stamp is not None else None


def _weekdays(values: Any, shift: int) -> Optional[Tuple[int, ...]]:
    """Valid weekday numbers as ISO days (``shift`` 0 for ISO input, 1 for Monday-is-0 input), else None."""
    low, high = 1 - shift, 7 - shift
    if (not isinstance(values, list) or not values
            or any(isinstance(d, bool) or not isinstance(d, int) or not low <= d <= high for d in values)):
        return None
    return tuple(sorted({d + shift for d in values}))


def parse_window(row: Dict[str, Any]) -> Optional[Window]:
    """The window a stored row describes (new or old shape), or None when this module cannot read it."""
    legacy = "start_time" in row or "end_time" in row
    recurrence = row.get("recurrence") or ("none" if legacy else None)
    name = str(row.get("name") or "")
    if recurrence == "none":
        first = _stamp(row.get("end_time" if legacy else "endsAt"))
        begin = _stamp(row.get("start_time" if legacy else "startsAt"))
        if begin is None or first is None or (begin.tzinfo is None) != (first.tzinfo is None) or first <= begin:
            return None
        return Window(name=name, recurrence="none", once=(begin, first))
    start = _clock(row.get("start_time" if legacy else "startTime"))
    end = _clock(row.get("end_time" if legacy else "endTime"))
    if recurrence not in ("daily", "weekly") or start is None or end is None or start == end:
        return None
    days = None
    if recurrence == "weekly":
        days = _weekdays(row.get("days_of_week") if legacy else row.get("daysOfWeek"), 1 if legacy else 0)
        if days is None:
            return None
    return Window(name=name, recurrence=recurrence, start=start, end=end, days=days)


def occurrences(zone: str, window: Window, around_utc: datetime, span_days: int = 2) -> Iterator[Occurrence]:
    """The (open, close) UTC pairs of ``window`` that start from yesterday to ``span_days`` ahead of
    ``around_utc``'s local date (a one-time window yields its single pair). An unknown zone yields nothing."""
    tz = _zone(zone)
    if tz is None:
        return
    if window.once is not None:
        begin, finish = (d if d.tzinfo else d.replace(tzinfo=tz) for d in window.once)
        yield begin.astimezone(timezone.utc), finish.astimezone(timezone.utc)
        return
    local = store.aware(around_utc).astimezone(tz)
    for offset in range(-1, span_days + 1):
        day = local.date() + timedelta(days=offset)
        if window.days is not None and day.isoweekday() not in window.days:
            continue
        opens = datetime.combine(day, window.start, tzinfo=tz)
        end_day = day if window.end > window.start else day + timedelta(days=1)
        closes = datetime.combine(end_day, window.end, tzinfo=tz)
        yield opens.astimezone(timezone.utc), closes.astimezone(timezone.utc)


def is_open(windows: List[Window], zone: str, now: datetime) -> Optional[Occurrence]:
    """The (open, close) occurrence in force at ``now``, or None. Overlapping windows give the one that
    closes last (their union stays open until then). Nothing is open for an unknown zone."""
    now = store.aware(now).astimezone(timezone.utc)
    best: Optional[Occurrence] = None
    for window in windows:
        for opens, closes in occurrences(zone, window, now):
            if opens <= now < closes and (best is None or closes > best[1]):
                best = (opens, closes)
    return best


def next_open(windows: List[Window], zone: str, now: datetime) -> Optional[Occurrence]:
    """The next occurrence that opens after ``now`` and is not open already, within the coming 8 days,
    or None. An occurrence that is open now is never returned."""
    now = store.aware(now).astimezone(timezone.utc)
    upcoming = [o for w in windows for o in occurrences(zone, w, now, span_days=8) if o[0] > now]
    return min(upcoming, key=lambda o: o[0]) if upcoming else None


async def load(db, tenant_id: str) -> TenantWindows:
    """The tenant's time zone and readable windows. A window row that is switched off is ignored; a row
    this module cannot read is skipped and makes ``readable`` False; an unknown zone also does."""
    result = TenantWindows()
    try:
        setting = await store.maintenance_settings(db).find_one({"tenantId": tenant_id}, {"_id": 0, "timeZone": 1})
        zone = (setting or {}).get("timeZone")
        result.zone = zone if isinstance(zone, str) and zone else DEFAULT_ZONE
        if _zone(result.zone) is None:
            result.readable = False
        found = raw(db).maintenance_windows.find({"tenantId": tenant_id}, {"_id": 0})
        async for row in found:
            if row.get("isActive") is False or row.get("is_active") is False:
                continue
            window = parse_window(row)
            if window is None:
                result.readable = False
            else:
                result.windows.append(window)
    except Exception as exc:
        logger.error("autonomous_ops: maintenance windows of %s unreadable, treating them as closed: %s",
                     tenant_id, exc)
        return TenantWindows(readable=False)
    return result
