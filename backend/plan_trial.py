"""The one per-tenant trial record (Phase 88, D-08, D-22).

A tenant carries a single ``trial`` sub-document: ``{startedAt, endsAt, consumed, extensions,
remindersSent}``. A tenant created on Free starts a trial that lasts the Free plan's ``trialDays``;
a tenant created on any other plan carries a consumed trial that ended the moment it was created
(``startedAt`` None), so moving it to Free later never starts a second trial (D-22).

This module is pure: it reads and builds the record and never touches the database. A missing or
unparsable record reads as "no trial", never as "ended", so a tenant with no data is not held (the
trial is a soft hold for new machines, never a cut-off, D-21).
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

FIELD = "trial"


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _record(started: Optional[datetime], ends: datetime, consumed: bool) -> Dict[str, Any]:
    return {"startedAt": _iso(started) if started else None, "endsAt": _iso(ends), "consumed": consumed,
            "extensions": [], "remindersSent": []}


def new_trial(now: datetime, days: int) -> Dict[str, Any]:
    """A running trial of ``days`` days that starts ``now``."""
    return _record(now, now + timedelta(days=days), False)


def consumed_trial(now: datetime) -> Dict[str, Any]:
    """The trial of a tenant created on a paid plan: never started, already used up (D-22)."""
    return _record(None, now, True)


def _parse(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        at = value
    elif isinstance(value, str) and value:
        try:
            at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def ends_at(tenant: Optional[Dict[str, Any]]) -> Optional[datetime]:
    """When the trial ends, or None when there is no readable trial record."""
    record = (tenant or {}).get(FIELD)
    return _parse(record.get("endsAt")) if isinstance(record, dict) else None


def ended(tenant: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """True once ``now`` has reached ``endsAt`` (the same >= rule as license_rules.expired)."""
    at = ends_at(tenant)
    return at is not None and (now or datetime.now(timezone.utc)) >= at


def days_left(tenant: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> Optional[int]:
    """Whole days remaining, rounded up and never below 0; None without a trial."""
    at = ends_at(tenant)
    if at is None:
        return None
    remaining = (at - (now or datetime.now(timezone.utc))) / timedelta(days=1)
    return max(0, math.ceil(remaining))


def view(tenant: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The trial as the licence view reports it, or None when the tenant has none."""
    record = (tenant or {}).get(FIELD)
    if not isinstance(record, dict) or ends_at(tenant) is None:
        return None
    started = _parse(record.get("startedAt"))
    return {"startedAt": _iso(started) if started else None, "endsAt": _iso(ends_at(tenant)),
            "consumed": bool(record.get("consumed")), "ended": ended(tenant, now), "daysLeft": days_left(tenant, now)}
