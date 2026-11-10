"""Agent seat licensing (spec C2).

A tenant buys ``license.maxAgents`` seats. ``license.seatsUsed`` is claimed with a
conditional atomic increment, so concurrent enrollments can never exceed the
limit, and released when an agent stops holding a seat (deleted, uninstalled,
reclaimed as Inactive, replaced). A periodic reconcile recomputes the counter
from the agents collection to repair any drift.

Every query here names its tenant explicitly and runs on the raw collections, so
it behaves the same inside a request and in background jobs.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGENTS = 5
DEFAULT_RECLAIM_DAYS = 30
MAX_RECLAIM_DAYS = 365
MAX_AGENTS_CEILING = 1_000_000

# The platform-admin organization has no seat limit at all (D-26, D-41): it is the operator's own
# tenant, so try_claim_seat always succeeds for it and seats_available reports the ceiling.
EXEMPT_TENANT_ID = "platform-admin"

# Agents in these states hold no seat; every other status (Online, Offline,
# Degraded, ...) does.
NON_SEAT_STATUSES = frozenset({"Pending", "Rejected", "Inactive", "Decommissioned", "Replaced", "Uninstalled"})


def _raw(db):
    return getattr(db, "_db", db)


def manual_status_change_error(current: Any, new: Any) -> Optional[str]:
    """Why an agent status written by hand (PUT/PATCH) is refused, or None.

    Moving an agent into or out of a state that holds no seat would bypass the seat
    counter (e.g. setting a Pending agent Online), so only the licensing flows do that:
    enrollment, heartbeat, approve/reject, reclaim, uninstall, delete."""
    if new == current:
        return None
    if new in NON_SEAT_STATUSES or current in NON_SEAT_STATUSES:
        return (f"Agent status {current!r} -> {new!r} changes whether it holds a license seat; "
                "use the Pending agents screen, the license settings or delete the agent instead")
    return None


def seat_holding_filter(tenant_id: str) -> Dict[str, Any]:
    return {"tenantId": tenant_id, "status": {"$nin": sorted(NON_SEAT_STATUSES)}}


def license_of(tenant: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The tenant's license with defaults; reads the legacy top-level maxAgents too."""
    tenant = tenant or {}
    lic = tenant.get("license") or {}
    max_agents = lic.get("maxAgents")
    if not isinstance(max_agents, int):
        max_agents = tenant.get("maxAgents") if isinstance(tenant.get("maxAgents"), int) else DEFAULT_MAX_AGENTS
    reclaim = lic.get("inactiveReclaimDays")
    return {
        "maxAgents": max_agents,
        "seatsUsed": lic.get("seatsUsed") if isinstance(lic.get("seatsUsed"), int) else None,
        "inactiveReclaimDays": reclaim if isinstance(reclaim, int) else DEFAULT_RECLAIM_DAYS,
        # Spec C4 enrollment controls (see license_rules).
        "allowlistMode": "enforce" if lic.get("allowlistMode") == "enforce" else "off",
        "subLimits": [s for s in lic.get("subLimits") or [] if isinstance(s, dict)],
        "expiresAt": lic.get("expiresAt") if isinstance(lic.get("expiresAt"), str) else None,
    }


async def count_seat_holders(db, tenant_id: str) -> int:
    return await _raw(db).agents.count_documents(seat_holding_filter(tenant_id))


async def ensure_license(db, tenant_id: str) -> Dict[str, Any]:
    """Create the license sub-document from the agents on file if it is missing."""
    raw = _raw(db)
    tenant = await raw.tenants.find_one({"id": tenant_id})
    if tenant is None:
        raise LookupError(f"tenant {tenant_id} not found")
    lic = license_of(tenant)
    if lic["seatsUsed"] is None:
        used = await count_seat_holders(db, tenant_id)
        await raw.tenants.update_one(
            {"id": tenant_id, "license.seatsUsed": {"$exists": False}},
            {"$set": {"license.maxAgents": lic["maxAgents"], "license.seatsUsed": used,
                      "license.inactiveReclaimDays": lic["inactiveReclaimDays"]}},
        )
        lic = license_of(await raw.tenants.find_one({"id": tenant_id}))
    return lic


async def try_claim_seat(db, tenant_id: str) -> bool:
    """Atomically take one seat; False when the tenant is at its limit. The platform organization
    (EXEMPT_TENANT_ID) is never at a limit (D-41): it still counts its seats, it just never refuses."""
    await ensure_license(db, tenant_id)
    if tenant_id == EXEMPT_TENANT_ID:
        await _raw(db).tenants.update_one({"id": tenant_id}, {"$inc": {"license.seatsUsed": 1}})
        return True
    res = await _raw(db).tenants.update_one(
        {"id": tenant_id, "$expr": {"$lt": ["$license.seatsUsed", "$license.maxAgents"]}},
        {"$inc": {"license.seatsUsed": 1}},
    )
    return res.modified_count == 1


async def release_seats(db, tenant_id: str, count: int = 1) -> None:
    """Give back ``count`` seats; never drives the counter below zero."""
    if count <= 0:
        return
    raw = _raw(db)
    res = await raw.tenants.update_one(
        {"id": tenant_id, "license.seatsUsed": {"$gte": count}},
        {"$inc": {"license.seatsUsed": -count}},
    )
    if res.modified_count == 0:
        await recount_seats(db, tenant_id)


async def recount_seats(db, tenant_id: str) -> Tuple[Optional[int], int]:
    """Set seatsUsed from the agents on file; returns (before, after)."""
    raw = _raw(db)
    tenant = await raw.tenants.find_one({"id": tenant_id}) or {}
    before = license_of(tenant)["seatsUsed"]
    after = await count_seat_holders(db, tenant_id)
    await raw.tenants.update_one({"id": tenant_id}, {"$set": {"license.seatsUsed": after}})
    return before, after


async def seats_available(db, tenant: Dict[str, Any]) -> int:
    """Read-only: free seats right now (used by the installer download pre-check)."""
    if tenant.get("id") == EXEMPT_TENANT_ID:
        return MAX_AGENTS_CEILING
    lic = license_of(tenant)
    used = lic["seatsUsed"] if lic["seatsUsed"] is not None else await count_seat_holders(db, tenant["id"])
    return max(0, lic["maxAgents"] - used)


_UNSET: Any = object()


async def update_license(db, tenant_id: str, max_agents: Optional[int] = None,
                         reclaim_days: Optional[int] = None, *, allowlist_mode: Any = _UNSET,
                         sub_limits: Any = _UNSET, expires_at: Any = _UNSET) -> Dict[str, Any]:
    """Change the seat count and/or reclaim window. Lowering below seatsUsed is allowed:
    running agents keep their seats, new enrollments are refused until seats free up.
    A seat number written here is a person's choice, so it is also stored as ``license.seatOverride``
    and a later plan edit leaves it alone (D-09); the route sends partner customers through
    partner_pool.change_allotment instead.
    The C4 controls (already validated by the caller) are set when passed; an
    ``expires_at`` of None clears the expiry."""
    if max_agents is not None and not (0 <= max_agents <= MAX_AGENTS_CEILING):
        raise ValueError(f"maxAgents must be between 0 and {MAX_AGENTS_CEILING}")
    if reclaim_days is not None and not (1 <= reclaim_days <= MAX_RECLAIM_DAYS):
        raise ValueError(f"inactiveReclaimDays must be between 1 and {MAX_RECLAIM_DAYS}")
    await ensure_license(db, tenant_id)
    changes: Dict[str, Any] = {}
    if max_agents is not None:
        changes["license.maxAgents"] = max_agents
        changes["maxAgents"] = max_agents  # legacy readers, one release
        changes["license.seatOverride"] = max_agents  # D-09
    if reclaim_days is not None:
        changes["license.inactiveReclaimDays"] = reclaim_days
    if allowlist_mode is not _UNSET:
        changes["license.allowlistMode"] = allowlist_mode
    if sub_limits is not _UNSET:
        changes["license.subLimits"] = sub_limits
    if expires_at is not _UNSET:
        changes["license.expiresAt"] = expires_at
        changes["license.expiryRemindersSent"] = []  # a new date earns new reminders
    if changes:
        await _raw(db).tenants.update_one({"id": tenant_id}, {"$set": changes})
    return await license_summary(db, tenant_id)


# ---- plan-derived seats and the Super Admin override (Phase 88, D-03, D-09, D-10, D-14) ----------------
# Every writer of a seat number lives in this module (or partner_pool for an allotment): a direct tenant's
# number is its plan's seats unless license.seatOverride says a person chose another one.

def _check_seats(value: Any) -> int:
    """A whole number from 0 to MAX_AGENTS_CEILING; anything else (bool, float, str, out of range) is refused."""
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_AGENTS_CEILING:
        raise ValueError(f"seats must be a whole number between 0 and {MAX_AGENTS_CEILING}")
    return value


def _direct_filter(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Direct tenants only: no partner pool decides their seats and they are not the platform organization."""
    flt: Dict[str, Any] = {"type": {"$ne": "partner"}, "partnerId": {"$exists": False},
                           "id": {"$ne": EXEMPT_TENANT_ID}}
    if tenant_id is not None:
        flt["id"] = {"$eq": tenant_id, "$ne": EXEMPT_TENANT_ID}
    return flt


async def _require_direct(db, tenant_id: str) -> None:
    tenant = await _raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "type": 1, "partnerId": 1})
    if tenant is None:
        raise LookupError(f"tenant {tenant_id} not found")
    if tenant_id == EXEMPT_TENANT_ID or tenant.get("type") == "partner" or tenant.get("partnerId"):
        raise ValueError("this organization's seats are not set by a plan or an override")


async def set_seat_override(db, tenant_id: str, seats: int) -> Dict[str, Any]:
    """Store ``seats`` as the tenant's own number (D-09): it survives every plan edit (D-10), even when it
    equals the plan's number. Refused for a partner customer (its allotment decides) and the platform."""
    _check_seats(seats)
    await _require_direct(db, tenant_id)
    await ensure_license(db, tenant_id)
    await _raw(db).tenants.update_one(
        _direct_filter(tenant_id),
        {"$set": {"license.seatOverride": seats, "license.maxAgents": seats, "maxAgents": seats}})
    return await license_summary(db, tenant_id)


async def clear_seat_override(db, tenant_id: str, plan_seats: int) -> Dict[str, Any]:
    """Return the tenant to its plan's seats: drop the override and write ``plan_seats`` (D-10)."""
    _check_seats(plan_seats)
    await _require_direct(db, tenant_id)
    await ensure_license(db, tenant_id)
    await _raw(db).tenants.update_one(
        _direct_filter(tenant_id),
        {"$unset": {"license.seatOverride": ""}, "$set": {"license.maxAgents": plan_seats, "maxAgents": plan_seats}})
    return await license_summary(db, tenant_id)


async def set_plan_seats(db, tenant_id: str, seats: int) -> bool:
    """Write the plan's ``seats`` for one direct tenant that has no override; True when it changed anything
    (used when a tenant changes plan and when a sign-up is approved)."""
    _check_seats(seats)
    await ensure_license(db, tenant_id)
    res = await _raw(db).tenants.update_one(
        {**_direct_filter(tenant_id), "license.seatOverride": {"$exists": False}},
        {"$set": {"license.maxAgents": seats, "maxAgents": seats}})
    return res.modified_count == 1


async def apply_plan_seats(db, plan: str, seats: int) -> List[str]:
    """A plan's seat number changed (D-14): set it on every direct tenant on that plan at once and return
    the ids changed. Partner customers (their allotment is the partner's, D-11), the platform organization
    (D-41) and tenants with a ``seatOverride`` are never touched; a tenant with no ``subscriptionTier``
    counts as Free. Agents already running keep their seats even when the number falls below
    ``seatsUsed`` (D-12): only new machines are held."""
    _check_seats(seats)
    on_plan: List[Dict[str, Any]] = [{"subscriptionTier": plan}]
    if plan == "Free":
        on_plan.append({"subscriptionTier": {"$exists": False}})
    flt: Dict[str, Any] = {
        "$or": on_plan, "type": {"$ne": "partner"}, "partnerId": {"$exists": False},
        "id": {"$ne": EXEMPT_TENANT_ID}, "license.seatOverride": {"$exists": False},
        "license.maxAgents": {"$ne": seats},
    }
    tenants = _raw(db).tenants
    ids = await tenants.distinct("id", flt)
    if not ids:
        return []
    # The second filter repeats every condition, so an override set after the lookup is still respected.
    await tenants.update_many({**flt, "id": {"$in": ids}},
                              {"$set": {"license.maxAgents": seats, "maxAgents": seats}})
    return list(ids)


async def raise_direct_seats(db, tenant_id: str, by: int) -> int:
    """Add ``by`` seats to a direct tenant and keep the result as its override (D-09), in one pipeline
    update so a concurrent plan edit can never separate the number from the override. Returns the new number."""
    if not isinstance(by, int) or isinstance(by, bool) or not 0 < by <= MAX_AGENTS_CEILING:
        raise ValueError(f"the raise must be a whole number between 1 and {MAX_AGENTS_CEILING}")
    current = {"$ifNull": ["$license.maxAgents", {"$ifNull": ["$maxAgents", DEFAULT_MAX_AGENTS]}]}
    doc = await _raw(db).tenants.find_one_and_update(
        _direct_filter(tenant_id),
        [{"$set": {"license.maxAgents": {"$min": [MAX_AGENTS_CEILING, {"$add": [current, by]}]}}},
         {"$set": {"license.seatOverride": "$license.maxAgents", "maxAgents": "$license.maxAgents"}}],
        projection={"_id": 0, "license.maxAgents": 1}, return_document=True)
    if doc is None:
        raise LookupError(f"direct tenant {tenant_id} not found")
    return doc["license"]["maxAgents"]


async def license_summary(db, tenant_id: str) -> Dict[str, Any]:
    lic = await ensure_license(db, tenant_id)
    used = lic["seatsUsed"] or 0
    return {
        "tenantId": tenant_id,
        "maxAgents": lic["maxAgents"],
        "seatsUsed": used,
        "seatsAvailable": max(0, lic["maxAgents"] - used),
        "overBy": max(0, used - lic["maxAgents"]),
        "inactiveReclaimDays": lic["inactiveReclaimDays"],
        "allowlistMode": lic["allowlistMode"],
        "subLimits": lic["subLimits"],
        "expiresAt": lic["expiresAt"],
    }


async def _audit(action: str, tenant_id: str, details: str, resource_id: str = "") -> None:
    try:
        from audit_service import get_audit_service
        await get_audit_service().log_action_async(
            user_name="system:licensing", action=action, resource_type="agent_license",
            resource_id=resource_id or tenant_id, details=details, tenant_id=tenant_id)
    except Exception as exc:  # auditing must never break seat bookkeeping
        logger.warning("License audit write failed (%s): %s", action, exc)


async def reclaim_inactive_agents(db, now: Optional[datetime] = None) -> int:
    """Mark seat-holding agents silent for longer than their tenant's reclaim window as
    Inactive and release their seats. Returns how many agents were reclaimed."""
    raw = _raw(db)
    now = now or datetime.now(timezone.utc)
    total = 0
    # A partner organization holds no seats of its own (D-13); only its customers do.
    async for tenant in raw.tenants.find({"type": {"$ne": "partner"}}, {"_id": 0, "id": 1, "license": 1, "maxAgents": 1}):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        cutoff = (now - timedelta(days=license_of(tenant)["inactiveReclaimDays"])).isoformat()
        stale = {**seat_holding_filter(tenant_id), "lastSeen": {"$lt": cutoff}}
        ids = [a["id"] async for a in raw.agents.find(stale, {"_id": 0, "id": 1}) if a.get("id")]
        if not ids:
            continue
        res = await raw.agents.update_many(
            {**stale, "id": {"$in": ids}},
            {"$set": {"status": "Inactive", "inactiveSince": now.isoformat()}},
        )
        if res.modified_count:
            await release_seats(db, tenant_id, res.modified_count)
            total += res.modified_count
            await _audit("license.seats_reclaimed", tenant_id,
                         f"{res.modified_count} agent(s) silent for over "
                         f"{license_of(tenant)['inactiveReclaimDays']} days marked Inactive: {', '.join(ids[:20])}")
    if total:
        logger.info("[Licensing] Reclaimed %d inactive agent seat(s)", total)
    return total


async def reconcile_all(db) -> List[Dict[str, Any]]:
    """Recompute every tenant's seatsUsed; returns the tenants whose counter had drifted."""
    drifts = []
    # A partner organization holds no seats of its own (D-13); its pool counter is partner_pool's to repair.
    async for tenant in _raw(db).tenants.find({"type": {"$ne": "partner"}}, {"_id": 0, "id": 1}):
        tenant_id = tenant.get("id")
        if not tenant_id:
            continue
        before, after = await recount_seats(db, tenant_id)
        if before is not None and before != after:
            drifts.append({"tenantId": tenant_id, "before": before, "after": after})
            await _audit("license.seats_reconciled", tenant_id, f"seatsUsed {before} -> {after}")
    if drifts:
        logger.warning("[Licensing] Seat counter drift repaired: %s", drifts)
    return drifts
