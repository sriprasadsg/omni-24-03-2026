"""Maintenance windows in the tenant's own time zone (PTCH-05, D-01, D-02).

A tenant keeps one IANA time zone (``maintenance_settings``) and any number of windows
(``maintenance_windows``). A window is stored in one shape only:

    {id, tenantId, name, recurrence none|daily|weekly, startTime, endTime ("HH:MM"), daysOfWeek (ISO, Monday 1
     to Sunday 7, weekly only), startsAt, endsAt (local "YYYY-MM-DDTHH:MM", one-time only), isActive,
     createdAt, updatedAt}

Reading and the open/closed maths live in ``autonomous_ops.rollout.windows`` (past midnight, daylight saving,
legacy rows); this module validates, stores and words the result. The tenant always comes from the caller,
never from a body, and every query carries an explicit tenantId on the raw handle.
"""
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo, available_timezones

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from autonomous_ops.rollout import store, windows
from autonomous_ops.rollout.messages import VALIDATION
from autonomous_ops.scope import raw

MAX_WINDOWS = 50
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class WindowError(ValueError):
    """A refusal that carries the sentence the screen shows."""


class WindowNotFound(LookupError):
    """The window does not exist for this tenant (another tenant's id reads the same)."""


class WindowBody(BaseModel):
    """The only fields a window request may carry; anything else (tenantId included) is ignored."""
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(None, max_length=200)
    recurrence: Optional[str] = Field(None, max_length=16)
    startTime: Optional[str] = Field(None, max_length=16)
    endTime: Optional[str] = Field(None, max_length=16)
    daysOfWeek: Optional[List[StrictInt]] = Field(None, max_length=14)
    startsAt: Optional[str] = Field(None, max_length=40)
    endsAt: Optional[str] = Field(None, max_length=40)
    timeZone: Optional[str] = Field(None, max_length=64)


class TimeZoneBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timeZone: Optional[str] = Field(None, max_length=64)


@lru_cache(maxsize=1)
def _zones() -> frozenset:
    return frozenset(available_timezones())


def valid_zone(name: Any) -> bool:
    return isinstance(name, str) and name in _zones()


# ---------------------------------------------------------------- wording

def _moment(value: datetime) -> str:
    return f"{_DAYS[value.weekday()]} {value.day} {_MONTHS[value.month - 1]}, {value:%H:%M}"


def _day_list(days: Optional[tuple]) -> str:
    names = [_DAYS[d - 1] for d in (days or ())]
    if len(names) == 7:
        return "every day"
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _range(window: "windows.Window") -> str:
    if window.once is not None:
        begin, finish = window.once
        return f"{_moment(begin)} to {_moment(finish)}"
    tail = " the next day" if window.end <= window.start else ""
    return f"{window.start:%H:%M} to {window.end:%H:%M}{tail}"


def _full_text(window: "windows.Window", zone: str) -> str:
    if window.once is not None:
        return f"One-time, {_range(window)} ({zone})"
    if window.recurrence == "weekly":
        return f"Weekly, {_day_list(window.days)}, {_range(window)} ({zone})"
    return f"Daily, {_range(window)} ({zone})"


def _local(value: datetime, zone: str) -> datetime:
    return value.astimezone(ZoneInfo(zone))


def _next_text(window: Optional["windows.Window"], zone: str, now: datetime) -> str:
    upcoming = windows.next_open([window], zone, now) if window is not None else None
    return f"Next: {_moment(_local(upcoming[0], zone))}" if upcoming else "Next: not scheduled"


def _view(row: Dict[str, Any], zone: str, now: datetime) -> Dict[str, Any]:
    """A stored window as the screens read it: the stored fields (an old-shape row converted) plus the texts
    and whether it is open now, all in the tenant's zone."""
    parsed = windows.parse_window(row)
    active = row.get("isActive", row.get("is_active")) is not False
    shown: Dict[str, Any] = {
        "id": row.get("id"), "name": row.get("name") or "", "recurrence": row.get("recurrence") or "none",
        "startTime": None, "endTime": None, "daysOfWeek": None, "startsAt": None, "endsAt": None,
        "isActive": active, "scheduleText": "", "fullScheduleText": "",
        "openNow": False, "nextText": _next_text(None, zone, now),
    }
    if parsed is None:
        return shown
    shown["recurrence"] = parsed.recurrence
    if parsed.once is not None:
        shown["startsAt"], shown["endsAt"] = (d.strftime("%Y-%m-%dT%H:%M") for d in parsed.once)
    else:
        shown["startTime"], shown["endTime"] = f"{parsed.start:%H:%M}", f"{parsed.end:%H:%M}"
        shown["daysOfWeek"] = list(parsed.days) if parsed.days is not None else None
    shown["scheduleText"] = _range(parsed)
    shown["fullScheduleText"] = _full_text(parsed, zone)
    shown["nextText"] = _next_text(parsed, zone, now)
    shown["openNow"] = active and windows.is_open([parsed], zone, now) is not None
    return shown


# ---------------------------------------------------------------- validation

def _local_stamp(value: Optional[str], zone: ZoneInfo) -> datetime:
    """A naive local datetime from an ISO string (an offset, if given, is converted into the zone)."""
    try:
        stamp = datetime.fromisoformat((value or "").strip().replace("Z", "+00:00"))
    except ValueError:
        raise WindowError(VALIDATION["window_dates"])
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(zone).replace(tzinfo=None)
    return stamp.replace(second=0, microsecond=0)


def _checked(body: WindowBody, zone_name: str) -> Dict[str, Any]:
    """The window fields to store, or a WindowError with the screen's sentence. ``zone_name`` only measures a
    one-time window's length."""
    name = (body.name or "").strip()
    if not name:
        raise WindowError(VALIDATION["window_name"])
    if len(name) > 60:
        raise WindowError(VALIDATION["window_name_long"])
    fields: Dict[str, Any] = {"name": name, "recurrence": body.recurrence, "startTime": None, "endTime": None,
                              "daysOfWeek": None, "startsAt": None, "endsAt": None}
    if body.recurrence in ("daily", "weekly"):
        for given in (body.startTime, body.endTime):
            if not isinstance(given, str) or not _HHMM.match(given):
                raise WindowError(VALIDATION["window_times"])
        if body.startTime == body.endTime:
            raise WindowError(VALIDATION["window_same_time"])
        fields["startTime"], fields["endTime"] = body.startTime, body.endTime
        if body.recurrence == "weekly":
            days = body.daysOfWeek or []
            if not days:
                raise WindowError(VALIDATION["window_days"])
            if any(not 1 <= d <= 7 for d in days):
                raise WindowError(VALIDATION["window_days_range"])
            fields["daysOfWeek"] = sorted(set(days))
    elif body.recurrence == "none":
        zone = ZoneInfo(zone_name)
        begin, finish = _local_stamp(body.startsAt, zone), _local_stamp(body.endsAt, zone)
        if finish <= begin:
            raise WindowError(VALIDATION["window_end_before_start"])
        span = finish.replace(tzinfo=zone).astimezone(timezone.utc) - begin.replace(tzinfo=zone).astimezone(timezone.utc)
        if span.total_seconds() > 24 * 3600:
            raise WindowError(VALIDATION["window_too_long"])
        fields["startsAt"], fields["endsAt"] = begin.strftime("%Y-%m-%dT%H:%M"), finish.strftime("%Y-%m-%dT%H:%M")
    else:
        raise WindowError(VALIDATION["window_repeats"])
    return fields


class MaintenanceService:
    def __init__(self, db):
        self.db = db
        self._raw = raw(db)

    # -- time zone

    async def get_time_zone(self, tenant_id: str) -> Optional[str]:
        found = await store.maintenance_settings(self.db).find_one({"tenantId": tenant_id}, {"_id": 0, "timeZone": 1})
        zone = (found or {}).get("timeZone")
        return zone if isinstance(zone, str) and zone else None

    async def set_time_zone(self, tenant_id: str, zone: Any) -> str:
        if not valid_zone(zone):
            raise WindowError(VALIDATION["time_zone"])
        await store.maintenance_settings(self.db).update_one(
            {"tenantId": tenant_id},
            {"$set": {"tenantId": tenant_id, "timeZone": zone, "updatedAt": datetime.now(timezone.utc)}},
            upsert=True)
        return zone

    async def _zone_for_save(self, tenant_id: str, body: WindowBody) -> tuple:
        """(zone to use, zone to store). A stored zone wins; otherwise the body must name a real one."""
        stored = await self.get_time_zone(tenant_id)
        if body.timeZone is not None and not valid_zone(body.timeZone):
            raise WindowError(VALIDATION["time_zone"])
        if stored:
            return stored, None
        return (body.timeZone, body.timeZone) if body.timeZone else (None, None)

    # -- windows

    def _collection(self):
        return self._raw.maintenance_windows

    async def create_window(self, tenant_id: str, body: WindowBody) -> Dict[str, Any]:
        zone, to_store = await self._zone_for_save(tenant_id, body)
        fields = _checked(body, zone or "UTC")
        if zone is None:
            raise WindowError(VALIDATION["time_zone"])
        if await self._collection().count_documents({"tenantId": tenant_id}) >= MAX_WINDOWS:
            raise WindowError(VALIDATION["window_limit"])
        if to_store:
            await self.set_time_zone(tenant_id, to_store)
        now = datetime.now(timezone.utc)
        row = {"id": str(uuid.uuid4()), "tenantId": tenant_id, **fields, "isActive": True,
               "createdAt": now, "updatedAt": now}
        await self._collection().insert_one(dict(row))
        return _view(row, zone, now)

    async def update_window(self, tenant_id: str, window_id: str, body: WindowBody) -> Dict[str, Any]:
        current = await self._collection().find_one({"id": window_id, "tenantId": tenant_id}, {"_id": 0})
        if current is None:
            raise WindowNotFound(window_id)
        zone, to_store = await self._zone_for_save(tenant_id, body)
        fields = _checked(body, zone or "UTC")
        if zone is None:
            raise WindowError(VALIDATION["time_zone"])
        if to_store:
            await self.set_time_zone(tenant_id, to_store)
        now = datetime.now(timezone.utc)
        active = current.get("isActive", current.get("is_active"))
        row = {"id": window_id, "tenantId": tenant_id, **fields, "isActive": active is not False,
               "createdAt": current.get("createdAt") or current.get("created_at") or now, "updatedAt": now}
        # a whole-document replace, so the old UTC-shape fields of a converted row do not linger beside the new ones
        replaced = await self._collection().replace_one({"id": window_id, "tenantId": tenant_id}, dict(row))
        if replaced.matched_count == 0:
            raise WindowNotFound(window_id)
        return _view(row, zone, now)

    async def list_windows(self, tenant_id: str, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        zone = await self.get_time_zone(tenant_id) or windows.DEFAULT_ZONE
        found = await self._collection().find({"tenantId": tenant_id}, {"_id": 0}).sort("createdAt", 1) \
            .to_list(length=MAX_WINDOWS + 50)
        return [_view(row, zone, now) for row in found]

    async def delete_window(self, window_id: str, tenant_id: str) -> bool:
        gone = await self._collection().delete_one({"id": window_id, "tenantId": tenant_id})
        return gone.deleted_count > 0

    # -- status and the legacy question

    async def status(self, tenant_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        tenant = await windows.load(self.db, tenant_id)
        zone = tenant.zone
        stored = await self.get_time_zone(tenant_id)
        base = {"timeZone": stored}
        if not tenant.windows and tenant.readable:
            return {"state": "none", "text": "No maintenance windows yet.", **base}
        current = tenant.open_at(now)
        if current is not None:
            return {"state": "open", "text": f"Open until {_local(current[1], zone):%H:%M} ({zone}).", **base}
        upcoming = windows.next_open(tenant.windows, zone, now) if tenant.readable else None
        if upcoming is None:
            return {"state": "closed", "text": "No upcoming window.", **base}
        return {"state": "closed", "text": f"Next window opens {_moment(_local(upcoming[0], zone))} ({zone}).",
                **base}

    async def is_in_maintenance_window(self, tenant_id: str, now: Optional[datetime] = None) -> bool:
        """True only when a readable window of the tenant is open now; no window, an unreadable one or an
        unknown zone reads closed."""
        tenant = await windows.load(self.db, tenant_id)
        return tenant.open_at(now or datetime.now(timezone.utc)) is not None


def get_maintenance_service(db):
    return MaintenanceService(db)
