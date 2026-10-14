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
    """Atomically take one seat; False when the tenant is at its limit."""
    await ensure_license(db, tenant_id)
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
    lic = license_of(tenant)
    used = lic["seatsUsed"] if lic["seatsUsed"] is not None else await count_seat_holders(db, tenant["id"])
    return max(0, lic["maxAgents"] - used)


_UNSET: Any = object()


async def update_license(db, tenant_id: str, max_agents: Optional[int] = None,
                         reclaim_days: Optional[int] = None, *, allowlist_mode: Any = _UNSET,
                         sub_limits: Any = _UNSET, expires_at: Any = _UNSET) -> Dict[str, Any]:
    """Change the seat count and/or reclaim window. Lowering below seatsUsed is allowed:
    running agents keep their seats, new enrollments are refused until seats free up.
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
    async for tenant in raw.tenants.find({}, {"_id": 0, "id": 1, "license": 1, "maxAgents": 1}):
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
    async for tenant in _raw(db).tenants.find({}, {"_id": 0, "id": 1}):
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
