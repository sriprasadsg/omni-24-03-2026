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

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import audit_ledger
import licensing
import seat_identity
from hold_reasons import REASON_CROSS_TENANT

logger = logging.getLogger(__name__)

LIVE_WINDOW = timedelta(hours=24)
MOVED_REASONS = ("moved", "moved_silent")
PLATFORM_TENANT_ID = "platform-admin"
_PROJECTION = {"_id": 0, "agentSecretHash": 0, "uninstallProtection": 0}
_MAX_COPIES = 50
_MOVE_LIMIT = 20
REPORTS = "cross_tenant_reports"
REPORT_EVERY = timedelta(hours=24)
_REPORT_FIELDS = ("serialNumber", "smbiosUuid")
_REPORT_GROUPS = 200


def _raw(db):
    return getattr(db, "_db", db)


async def ensure_indexes(db) -> None:
    """Sparse single-field indexes behind the cross-tenant lookup. Sparse, not partial: a partial $type index
    is not used by an equality query."""
    agents = _raw(db).agents
    await agents.create_index("hardware.serialNumber", name="agents_hw_serial_sparse", sparse=True)
    await agents.create_index("hardware.smbiosUuid", name="agents_hw_uuid_sparse", sparse=True)
    await _raw(db)[REPORTS].create_index("key", name="cross_tenant_reports_key", unique=True)


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


async def before_approval(db, agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Re-check a held machine before it is approved for any reason but the cross-tenant one (Pitfall 6): when it
    is live in another tenant now, a Pending hold becomes ``cross_tenant_duplicate`` (platform alert included) and
    the detail is returned so the caller refuses the approval. None when nothing is live elsewhere."""
    if agent.get("pendingReason") == REASON_CROSS_TENANT:
        return None  # the decider has seen it; approving it moves the machine (D-37)
    detail = await hold_detail(db, agent["tenantId"], agent.get("hardware") or {})
    if detail is None:
        return None
    raw = _raw(db)
    res = await raw.agents.update_one({"id": agent["id"], "status": "Pending"},
                                      {"$set": {"pendingReason": REASON_CROSS_TENANT, "crossTenant": detail}})
    if res.modified_count == 1:
        tenant = await raw.tenants.find_one({"id": agent["tenantId"]}, {"_id": 0, "id": 1, "name": 1})
        await alert_platform_hold(db, tenant or {"id": agent["tenantId"]}, agent, detail)
    return detail


async def after_admission(db, agent: Dict[str, Any], actor: str) -> int:
    """After an approval admitted ``agent``: the machine now belongs to its tenant. A cross-tenant hold retires
    every seat-holding copy elsewhere as ``moved`` (D-37); any other approval retires the silent ones as
    ``moved_silent`` (D-38). Returns how many were retired; a failure on one copy is logged, never raised."""
    raw = _raw(db)
    tenant_id = agent["tenantId"]
    hardware = agent.get("hardware") or {}
    tenant = await raw.tenants.find_one({"id": tenant_id}, {"_id": 0, "id": 1, "name": 1}) or {"id": tenant_id}
    retired = 0
    if agent.get("pendingReason") == REASON_CROSS_TENANT:
        flt = seat_identity.hardware_match_other_tenants_filter(hardware, tenant_id, licensing.NON_SEAT_STATUSES)
        owners = await raw.agents.find(flt, _PROJECTION).limit(_MOVE_LIMIT).to_list(length=_MOVE_LIMIT) if flt else []
        for owner in owners:
            try:
                if await retire_copy(db, owner, reason="moved", actor=actor, to_tenant=tenant, to_agent_id=agent["id"]):
                    retired += 1
            except Exception as exc:
                logger.error("Retiring copy %s of a machine moved to %s failed: %s", owner.get("id"), tenant_id, exc)
    else:
        retired = await retire_silent_copies(db, tenant, hardware, agent["id"], actor)
    import machine_identity  # lazy, as in agent_registry_endpoints
    await machine_identity.remember(db, tenant_id, agent.get("seatKey") or seat_identity.seat_key(
        hardware, agent.get("deviceId")), agent["id"], agent.get("hostname"))
    return retired


async def restore(db, agent_id: str, actor: str) -> Dict[str, Any]:
    """Turn an agent retired because its computer moved back to Inactive (D-43). It takes a seat again at its next
    check-in, through the same cross-tenant rule. LookupError for an unknown id, ValueError for an agent that is
    not moved. Both ledgers record it; the agent's own tenant's entry names no other organization."""
    import pending_agents
    raw = _raw(db)
    now = datetime.now(timezone.utc).isoformat()
    agent = await raw.agents.find_one_and_update(
        {"id": agent_id, "status": "Replaced", "replacedReason": {"$in": list(MOVED_REASONS)}},
        {"$set": {"status": "Inactive", "restoredAt": now, "restoredBy": actor},
         "$unset": {"replacedReason": "", "movedAt": "", "replacedAt": ""}},
        projection=_PROJECTION, return_document=ReturnDocument.BEFORE)
    if agent is None:
        if not await raw.agents.find_one({"id": agent_id}, {"_id": 1}):
            raise LookupError("Agent not found")
        raise ValueError("not_moved: this agent was not retired because its computer moved")
    pending_agents.forget_status(agent_id)
    who = {"email": actor}
    try:
        await audit_ledger.event("agent.restored", PLATFORM_TENANT_ID, actor=who, agentId=agent_id,
                                 tenantId=agent["tenantId"], tenantName=await _tenant_name(raw, agent["tenantId"]),
                                 hostname=agent.get("hostname"), was=agent.get("replacedReason"))
        await audit_ledger.event("agent.restored", agent["tenantId"], actor=who, agentId=agent_id,
                                 hostname=agent.get("hostname"))
    except Exception as exc:
        logger.warning("Ledger entries for the restore of %s were not recorded: %s", agent_id, exc)
    return {"agentId": agent_id, "status": "Inactive"}


async def list_moved(db, limit: int = 200) -> List[Dict[str, Any]]:
    """Agents retired because their computer moved, newest move first, with their tenant's name (platform only)."""
    raw = _raw(db)
    rows = await raw.agents.find({"status": "Replaced", "replacedReason": {"$in": list(MOVED_REASONS)}},
                                 _PROJECTION).sort("movedAt", -1).limit(limit).to_list(length=limit)
    names = {t["id"]: t.get("name") for t in await raw.tenants.find(
        {"id": {"$in": sorted({r["tenantId"] for r in rows})}}, {"_id": 0, "id": 1, "name": 1}).to_list(length=None)}
    return [{"id": r["id"], "tenantId": r["tenantId"], "tenantName": names.get(r["tenantId"]),
             "hostname": r.get("hostname"), "replacedReason": r.get("replacedReason"), "movedAt": r.get("movedAt"),
             "lastSeen": r.get("lastSeen")} for r in rows]


async def _live_groups(raw, field: str, now: datetime) -> List[Dict[str, Any]]:
    """Machines (by ``field``) held by seat-holding agents seen in the last 24 hours in two or more tenants."""
    path = f"hardware.{field}"
    since = (now - LIVE_WINDOW).isoformat()
    rows = await raw.agents.aggregate([
        {"$match": {path: {"$type": "string"}, "status": {"$nin": sorted(licensing.NON_SEAT_STATUSES)},
                    "lastSeen": {"$gte": since}}},
        {"$group": {"_id": f"${path}", "copies": {"$push": {"tenantId": "$tenantId", "id": "$id",
                                                           "hostname": "$hostname", "lastSeen": "$lastSeen"}}}},
        {"$match": {"copies.1": {"$exists": True}}}]).to_list(length=_REPORT_GROUPS)
    groups = []
    for row in rows:  # the string pre-filter is approximate; seen_within is the exact test
        live = [c for c in row["copies"] if seat_identity.seen_within(c, LIVE_WINDOW, now)]
        if len({c["tenantId"] for c in live}) >= 2:
            groups.append({"value": row["_id"], "copies": live})
    return groups


async def report_live_pairs(db, now: Optional[datetime] = None) -> int:
    """The accepted race of the cross-tenant check (A-88-RACE): one platform notice per machine key per day for
    every serial or SMBIOS UUID held by seat-holding agents seen in the last 24 hours in two or more tenants.
    Returns how many notices were posted."""
    import pending_agents
    raw = _raw(db)
    now = now or datetime.now(timezone.utc)
    await raw[REPORTS].create_index("key", name="cross_tenant_reports_key", unique=True)
    posted = 0
    for field in _REPORT_FIELDS:
        for group in await _live_groups(raw, field, now):
            key = f"{field}:{group['value']}"
            try:  # one claim per key per day: a recent report matches nothing, so the upsert hits the unique key
                await raw[REPORTS].update_one(
                    {"key": key, "$or": [{"reportedAt": {"$exists": False}},
                                         {"reportedAt": {"$lt": (now - REPORT_EVERY).isoformat()}}]},
                    {"$set": {"reportedAt": now.isoformat()}}, upsert=True)
            except DuplicateKeyError:
                continue
            names = {t["id"]: t.get("name") for t in await raw.tenants.find(
                {"id": {"$in": sorted({c["tenantId"] for c in group["copies"]})}}, {"_id": 0, "id": 1, "name": 1}
            ).to_list(length=None)}
            where = ", ".join(f"{_label(names.get(c['tenantId']), c['tenantId'])} ({c.get('hostname')}, agent {c['id']})"
                              for c in group["copies"])
            try:
                await pending_agents._post_in_app(
                    raw, PLATFORM_TENANT_ID, "Computer live in two organizations",
                    f"The computer with {'serial number' if field == 'serialNumber' else 'SMBIOS UUID'} {group['value']} "
                    f"holds a seat and was seen in the last 24 hours in: {where}. Review the agents and restore or "
                    "remove the wrong copy.", "warning",
                    {"event": "agent.live_in_two_organizations", "key": key, "copies": group["copies"]})
                posted += 1
            except Exception as exc:  # release the claim so the next tick tries again
                logger.error("Live-pair notice for %s was not stored: %s", key, exc)
                await raw[REPORTS].delete_one({"key": key})
    return posted
