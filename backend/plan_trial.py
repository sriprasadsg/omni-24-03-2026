"""The one per-tenant trial record (Phase 88, D-08, D-22).

A tenant carries a single ``trial`` sub-document: ``{startedAt, endsAt, consumed, extensions,
remindersSent}``. A tenant created on Free starts a trial that lasts the Free plan's ``trialDays``;
a tenant created on any other plan carries a consumed trial that ended the moment it was created
(``startedAt`` None), so moving it to Free later never starts a second trial (D-22).

The record builders and readers are pure. The async functions at the end (``extend``, ``start_for_signup``,
``send_trial_reminders``) are the only database writers of the record; they import licensing, plan_service,
plan_notices, pending_agents and partner_store inside the function, because license_rules and plan_service
import this module at module level. A missing or unparsable record reads as "no trial", never as "ended", so a
tenant with no data is not held (the trial is a soft hold for new machines, never a cut-off, D-21).
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

FIELD = "trial"
MAX_EXTENSION_DAYS = 365
TRIAL_REMINDER_DAYS = (7, 1)


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


# -- the writers (Phase 88 plan 06) ------------------------------------------------------------------------------

class TrialError(ValueError):
    """A trial request that cannot be honoured; ``status`` is the HTTP answer, ``args[0]`` its text."""

    def __init__(self, status: int, code: str, message: Optional[str] = None):
        super().__init__(message or code)
        self.status = status
        self.code = code


def _raw(db):
    return getattr(db, "_db", db)


def _actor_name(actor: Any) -> str:
    if isinstance(actor, dict):
        return str(actor.get("email") or actor.get("username") or "system")
    return actor if isinstance(actor, str) else str(getattr(actor, "username", None) or "system")


async def extend(db, tenant_id: str, days: int, *, actor: Any, via: str) -> Dict[str, Any]:
    """Give a Free tenant ``days`` more trial days (D-15) and return the new trial view.

    The new end is ``days`` after the later of now and the old end (an ended trial reopens from now); reminders
    are re-armed and the extension recorded in ``trial.extensions`` and the tenant's audit ledger. One
    compare-and-set on the stored end: an extension that lost a race answers 409 ``trial_changed``."""
    import plan_notices
    import plan_service
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_EXTENSION_DAYS:
        raise TrialError(422, "invalid_days", f"A trial is extended by 1 to {MAX_EXTENSION_DAYS} days")
    raw = _raw(db)
    tenant = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if tenant is None:
        raise TrialError(404, "not_found", "Tenant not found")
    if plan_service.is_exempt(tenant_id) or tenant.get("type") == "partner" or plan_service.plan_key_of(tenant) != "Free":
        raise TrialError(422, "not_on_trial", "Only a Free trial can be extended")
    now = datetime.now(timezone.utc)
    old = ends_at(tenant)
    new_end = (max(now, old) if old else now) + timedelta(days=days)
    extension = {"at": _iso(now), "by": _actor_name(actor), "days": days,
                 "from": _iso(old) if old else None, "to": _iso(new_end)}
    stored = tenant.get(FIELD)
    if isinstance(stored, dict):
        guard: Dict[str, Any] = {"id": tenant_id, f"{FIELD}.endsAt": stored["endsAt"] if "endsAt" in stored
                                 else {"$exists": False}}
        sets: Dict[str, Any] = {f"{FIELD}.endsAt": _iso(new_end), f"{FIELD}.remindersSent": [],
                                f"{FIELD}.consumed": False}  # more trial time was granted on purpose (D-15)
        if not stored.get("startedAt"):
            sets[f"{FIELD}.startedAt"] = _iso(now)
        update: Dict[str, Any] = {"$set": sets, "$push": {f"{FIELD}.extensions": extension}}
    else:
        guard = {"id": tenant_id, FIELD: stored if FIELD in tenant else {"$exists": False}}
        update = {"$set": {FIELD: {**_record(now, new_end, False), "extensions": [extension]}}}
    won = await raw.tenants.update_one(guard, update)
    if won.matched_count == 0:
        raise TrialError(409, "trial_changed", "The trial changed while you were saving. Try again.")
    name = tenant.get("name") or tenant_id
    await plan_notices.announce(
        db, tenant_id, event="trial.extended", title="Free trial extended",
        message=f"The Free trial of {name} now ends on {new_end.date().isoformat()}.", actor=actor,
        before=_iso(old) if old else None, after=_iso(new_end), days=days, via=via)
    return view(await raw.tenants.find_one({"id": tenant_id}, {"_id": 0}))


async def start_for_signup(db, tenant_id: str) -> bool:
    """Start the trial of a self sign-up when the Super Admin approves it (D-23) and set its seats from the
    Free plan. True when the trial started now; calling it again changes nothing. A tenant on a paid plan,
    a partner or its customer, or one that already has a trial record keeps what it has."""
    import licensing
    import plan_service
    raw = _raw(db)
    tenant = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0, "type": 1, "partnerId": 1,
                                                          "subscriptionTier": 1, FIELD: 1})
    if (tenant is None or plan_service.is_exempt(tenant_id) or tenant.get("type") == "partner"
            or tenant.get("partnerId") or plan_service.plan_key_of(tenant) != "Free"):
        return False
    terms = await plan_service.new_tenant_terms(db, "Free", None)
    started = False
    if FIELD not in tenant:
        won = await raw.tenants.update_one({"id": tenant_id, FIELD: {"$exists": False}}, {"$set": {FIELD: terms["trial"]}})
        started = won.modified_count == 1
    await licensing.set_plan_seats(db, tenant_id, terms["max_agents"])  # skips a tenant with an override
    return started


async def send_trial_reminders(db, now: Optional[datetime] = None) -> int:
    """Remind a running Free trial's administrators 7 and 1 days before it ends, once per threshold (D-16).

    The platform feed and the tenant's admins are told; a partner's customer also lands in the partner's own
    feed (no audience tag: the partner already sees that customer). Mirrors license_rules.send_expiry_reminders:
    the threshold is claimed by one atomic update first, so two overlapping runs never double-send.
    Returns how many reminders went out."""
    import pending_agents
    import plan_service
    raw = _raw(db)
    now = now or datetime.now(timezone.utc)
    sent = 0
    running = {f"{FIELD}.endsAt": {"$type": "string"}, f"{FIELD}.consumed": {"$ne": True},
               "type": {"$ne": "partner"}, "id": {"$ne": plan_service.PLATFORM_TENANT_ID}}
    async for tenant in raw.tenants.find(running, {"_id": 0, "id": 1, "name": 1, "partnerId": 1,
                                                  "subscriptionTier": 1, FIELD: 1}):
        if plan_service.plan_key_of(tenant) != "Free" or ended(tenant, now):
            continue
        at = ends_at(tenant)
        if at is None:
            continue
        done = set(tenant[FIELD].get("remindersSent") or [])
        due = [d for d in TRIAL_REMINDER_DAYS if at - now <= timedelta(days=d) and d not in done]
        if not due:
            continue
        threshold = min(due)  # one reminder for the closest threshold crossed
        won = await raw.tenants.update_one(
            {"id": tenant["id"], f"{FIELD}.remindersSent": {"$nin": [threshold]}},
            {"$addToSet": {f"{FIELD}.remindersSent": {"$each": due}}})
        if won.modified_count != 1:
            continue
        label = tenant.get("name") or tenant["id"]
        left = max(1, math.ceil((at - now) / timedelta(days=1)))
        title = f"Free trial of {label} ends in {left} day{'s' if left > 1 else ''}"
        message = (f"The Free trial of {label} ends on {at.date().isoformat()}. After that, new agents are held "
                   "for approval; running agents and every screen keep working.")
        metadata = {"event": "trial.reminder", "tenantId": tenant["id"], "daysLeft": left,
                    "endsAt": _iso(at), "threshold": threshold}
        await pending_agents.post_to_recipients(raw, tenant, title, message, "warning", metadata)
        if tenant.get("partnerId"):
            await pending_agents._post_in_app(raw, tenant["partnerId"], title, message, "warning",
                                              {**metadata, "customerId": tenant["id"]})
        sent += 1
    return sent
