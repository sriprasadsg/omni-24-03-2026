"""One computer, one organization (Phase 88, LIC-06, D-02).

A machine that holds a seat in one tenant must not also enrol in another. Each tenant gives a machine its own
agent id, so nothing else compares across tenants. Every read here runs on the raw collections with explicit
filters (the request's tenant wrapper would scope it to the enrolling tenant), by normalized BIOS serial or
SMBIOS UUID only: a MAC alone, or a firmware placeholder, never counts (D-35).

* A copy that holds a seat elsewhere and was seen in the last 24 hours is live: the new enrollment is held
  Pending ``cross_tenant_duplicate`` for the Super Admin (D-35). The new tenant's notice says only that the
  computer is enrolled in another organization; the other organization sees nothing, and only the platform
  feed and the hold's platform-only ``crossTenant`` field name both organizations (D-36).
* A copy that has been silent for 24 hours is retired when the new enrollment is admitted (D-38): Replaced
  with ``replacedReason`` ``moved_silent`` and no ``replacedBy`` (a cross-tenant link would be readable by the
  old tenant's users), its seat released, its tokens revoked, a platform alert and a platform-ledger entry
  naming both organizations, and an entry in the old tenant's ledger that names neither (D-43).

Hardware identifiers are agent-supplied (A-88-A4): a tenant that knows another organization's serial could
retire that organization's silent agent; the platform alert and the restore in 88-09 are the safeguard. The
check is read-then-write across two tenants, so two organizations enrolling one new machine in the same
second can both be admitted (A-88-RACE); 88-09 reports live pairs hourly.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import audit_ledger
import licensing
import seat_identity

logger = logging.getLogger(__name__)

LIVE_WINDOW = timedelta(hours=24)
MOVED_REASONS = ("moved", "moved_silent")
PLATFORM_TENANT_ID = "platform-admin"
_PROJECTION = {"_id": 0, "agentSecretHash": 0, "uninstallProtection": 0}
_MAX_COPIES = 50


def _raw(db):
    return getattr(db, "_db", db)


async def ensure_indexes(db) -> None:
    """Sparse single-field indexes behind the cross-tenant lookup. Sparse, not partial: a partial $type index
    is not used by an equality query."""
    agents = _raw(db).agents
    await agents.create_index("hardware.serialNumber", name="agents_hw_serial_sparse", sparse=True)
    await agents.create_index("hardware.smbiosUuid", name="agents_hw_uuid_sparse", sparse=True)


async def _copies(db, tenant_id: str, hardware: Dict[str, Any]) -> List[Dict[str, Any]]:
    flt = seat_identity.hardware_match_other_tenants_filter(hardware, tenant_id, licensing.NON_SEAT_STATUSES)
    if flt is None:
        return []
    return await _raw(db).agents.find(flt, _PROJECTION).limit(_MAX_COPIES).to_list(length=_MAX_COPIES)


async def live_owner(db, tenant_id: str, hardware: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The most recently seen seat-holding copy of this machine in another tenant, seen within 24 hours."""
    live = [a for a in await _copies(db, tenant_id, hardware) if seat_identity.seen_within(a, LIVE_WINDOW)]
    return max(live, key=lambda a: str(a.get("lastSeen"))) if live else None


async def silent_copies(db, tenant_id: str, hardware: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Seat-holding copies of this machine in other tenants that have not been seen for 24 hours."""
    return [a for a in await _copies(db, tenant_id, hardware) if not seat_identity.seen_within(a, LIVE_WINDOW)]


async def _tenant_name(db, tenant_id: Optional[str]) -> Optional[str]:
    doc = await _raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1}) if tenant_id else None
    return (doc or {}).get("name")


async def hold_detail(db, tenant_id: str, hardware: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Who the live copy belongs to, for the hold's platform-only ``crossTenant`` field; None without one."""
    owner = await live_owner(db, tenant_id, hardware)
    if owner is None:
        return None
    return {"agentId": owner["id"], "tenantId": owner["tenantId"],
            "tenantName": await _tenant_name(db, owner["tenantId"]), "hostname": owner.get("hostname")}


def _label(name: Optional[str], tenant_id: Optional[str]) -> str:
    return name or tenant_id or "unknown"


async def alert_platform_hold(db, tenant: Dict[str, Any], agent: Dict[str, Any], detail: Dict[str, Any]) -> None:
    """One notice in the platform feed (no audience, so no tenant reads it) naming both organizations (D-36, D-43)."""
    import pending_agents  # lazy: pending_agents imports licence modules that import this one
    entering = _label(tenant.get("name"), tenant.get("id"))
    owning = _label(detail.get("tenantName"), detail.get("tenantId"))
    host = agent.get("hostname") or detail.get("hostname")
    try:
        await pending_agents._post_in_app(
            _raw(db), PLATFORM_TENANT_ID, f"Computer enrolled in two organizations: {host}",
            f"{host} tried to enroll in {entering} but is live in {owning} (agent {detail.get('agentId')}, seen in the "
            "last 24 hours). It is held for approval under Agents -> Pending.", "warning",
            {"event": "agent.cross_tenant_duplicate", "tenantId": tenant.get("id"), "tenantName": tenant.get("name"),
             "ownerTenantId": detail.get("tenantId"), "ownerTenantName": detail.get("tenantName"),
             "agentId": agent.get("id"), "ownerAgentId": detail.get("agentId"), "hostname": host})
    except Exception as exc:  # an alert failure must never fail the enrollment
        logger.error("Cross-tenant hold alert failed for %s: %s", agent.get("id"), exc)


async def retire_copy(db, owner: Dict[str, Any], *, reason: str, actor: str, to_tenant: Dict[str, Any],
                      to_agent_id: str) -> bool:
    """Retire ``owner`` (an agent of another tenant) because its machine enrolled elsewhere (D-37, D-38).
    True only for the call that flipped it, so a second call changes and records nothing."""
    import pending_agents
    from authentication_service import revoke_agent_tokens
    raw = _raw(db)
    now = datetime.now(timezone.utc).isoformat()
    res = await raw.agents.update_one(
        {"id": owner["id"], "tenantId": owner["tenantId"], "status": {"$nin": sorted(licensing.NON_SEAT_STATUSES)}},
        {"$set": {"status": "Replaced", "replacedReason": reason, "replacedAt": now, "movedAt": now}})
    if res.modified_count != 1:
        return False
    await licensing.release_seats(raw, owner["tenantId"])
    await revoke_agent_tokens(raw, owner["id"], "machine moved to another organization")
    pending_agents.forget_status(owner["id"])
    who = {"email": actor}
    from_name = await _tenant_name(raw, owner["tenantId"])
    try:  # the old tenant's own ledger names neither the new organization nor its id
        await audit_ledger.event("agent.moved_out", owner["tenantId"], actor=who, agentId=owner["id"],
                                 hostname=owner.get("hostname"), reason=reason)
        await audit_ledger.event("agent.moved", PLATFORM_TENANT_ID, actor=who, fromTenantId=owner["tenantId"],
                                 fromTenantName=from_name, toTenantId=to_tenant.get("id"),
                                 toTenantName=to_tenant.get("name"), agentId=owner["id"], toAgentId=to_agent_id,
                                 reason=reason)
    except Exception as exc:
        logger.warning("Ledger entries for the move of %s were not recorded: %s", owner["id"], exc)
    try:
        await pending_agents._post_in_app(
            raw, PLATFORM_TENANT_ID, f"Computer moved between organizations: {owner.get('hostname')}",
            f"{owner.get('hostname')} enrolled in {_label(to_tenant.get('name'), to_tenant.get('id'))} while its copy "
            f"in {_label(from_name, owner['tenantId'])} had been silent for 24 hours. That copy was retired and its "
            "seat released.", "warning",
            {"event": "agent.moved", "fromTenantId": owner["tenantId"], "fromTenantName": from_name,
             "toTenantId": to_tenant.get("id"), "toTenantName": to_tenant.get("name"), "agentId": owner["id"],
             "toAgentId": to_agent_id, "reason": reason})
    except Exception as exc:
        logger.warning("Platform notice for the move of %s was not stored: %s", owner["id"], exc)
    return True


async def retire_silent_copies(db, tenant: Dict[str, Any], hardware: Dict[str, Any], new_agent_id: str,
                               actor: str) -> int:
    """Retire every silent copy of the machine in other tenants after ``tenant`` admitted it (D-38).
    Returns how many were retired; a failure on one is logged and never fails the enrollment."""
    retired = 0
    to_tenant = {"id": tenant.get("id"), "name": tenant.get("name")}
    for owner in await silent_copies(db, tenant["id"], hardware):
        try:
            if await retire_copy(db, owner, reason="moved_silent", actor=actor, to_tenant=to_tenant,
                                 to_agent_id=new_agent_id):
                retired += 1
        except Exception as exc:
            logger.error("Retiring silent copy %s of a machine enrolled in %s failed: %s",
                         owner.get("id"), tenant.get("id"), exc)
    return retired
