"""Pending enrollment and over-limit alerts (spec C3).

An enrollment that cannot take a seat is not silently refused: it is held as a
``Pending`` agent that keeps reporting who it is, and platform staff are alerted
with the host details. A super admin approves it (it then claims a seat) or rejects
it (its seat key is denylisted, so re-enrolling the same hardware is refused too).

Pending and Rejected agents are "not admitted": they hold no seat, receive no
tasks, store no capability data, and are hidden from agent lists (the tenant
wrapper in database.py filters them out of list reads). Everything here runs on
the raw collections because it crosses tenants (alerts reach the platform tenant)
and must see the agents the wrapper hides.
"""
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import licensing
import seat_identity

logger = logging.getLogger(__name__)

PENDING = "Pending"
REJECTED = "Rejected"
NOT_ADMITTED = frozenset({PENDING, REJECTED})

REASON_SEAT_LIMIT = "seat_limit"
REASON_DUPLICATE_HARDWARE = "duplicate_hardware_id"

# How often a Pending agent should check back (register poll or heartbeat).
RETRY_AFTER_SECONDS = 300

# Per tenant, the first ALERT_INDIVIDUAL_LIMIT Pending agents in an ALERT_WINDOW each
# get their own alert; the next one raises a single summary that later ones update.
ALERT_INDIVIDUAL_LIMIT = 10
ALERT_WINDOW = timedelta(minutes=60)

PLATFORM_TENANT_ID = "platform-admin"
TENANT_ADMIN_AUDIENCE = "tenant_admins"

_PENDING_FIELDS_UNSET = {"pendingReason": "", "pendingSince": "", "pendingAlertedAt": ""}


def _raw(db):
    return getattr(db, "_db", db)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def supports_pending(data: Dict[str, Any]) -> bool:
    """Agents that understand a 202 pending answer say so; older builds get 403 instead."""
    return data.get("supportsPending") is True


def denyable(seat_key: Optional[str]) -> bool:
    """Seat keys that identify one machine. ``legacy:unknown`` is shared by every agent
    that sent no identity at all, so denying it would block them all."""
    return bool(seat_key) and not seat_key.endswith(":unknown")


# ── Admission gate for agent-token requests ───────────────────────────────────

_STATUS_TTL_SECONDS = 10.0
_STATUS_CACHE_MAX = 50_000
_status_cache: Dict[str, Tuple[float, Optional[str]]] = {}

# Routes a Pending agent still reaches with a token: its heartbeat (answered with 202
# pending) and its uninstaller's report. Everything else needs an admitted agent.
_PENDING_ALLOWED_SUFFIXES = ("/heartbeat", "/uninstall-report")


def forget_status(agent_id: str) -> None:
    _status_cache.pop(agent_id, None)


async def _admission_status(db, agent_id: str) -> Optional[str]:
    hit = _status_cache.get(agent_id)
    now = time.monotonic()
    if hit and now - hit[0] < _STATUS_TTL_SECONDS:
        return hit[1]
    doc = await _raw(db).agents.find_one({"id": agent_id}, {"_id": 0, "status": 1})
    status = (doc or {}).get("status")
    if len(_status_cache) >= _STATUS_CACHE_MAX:
        _status_cache.clear()
    _status_cache[agent_id] = (now, status)
    return status


async def assert_admitted(db, agent_id: Optional[str], path: str) -> None:
    """403 for a Pending or Rejected agent, except a Pending agent's heartbeat and
    uninstall report. Called wherever an agent token is accepted (agent_auth,
    authentication_service.get_current_user_or_agent)."""
    if not agent_id:
        return
    status = await _admission_status(db, agent_id)
    if status == REJECTED:
        raise HTTPException(status_code=403, detail="agent_rejected: this agent was rejected by the platform administrator")
    if status == PENDING and not path.rstrip("/").endswith(_PENDING_ALLOWED_SUFFIXES):
        raise HTTPException(status_code=403, detail="agent_pending: this agent is waiting for approval")


# ── Holding an enrollment as Pending ──────────────────────────────────────────

def identity_fields(data: Dict[str, Any], hardware: Dict[str, Any], source_ip: Optional[str]) -> Dict[str, Any]:
    """What a Pending agent may store about itself: who it is, never capability data."""
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    fields: Dict[str, Any] = {
        "hostname": data.get("hostname"),
        "platform": data.get("platform") or "Unknown",
        "version": data.get("version") or "unknown",
        "ipAddress": data.get("ipAddress"),
        "sourceIp": source_ip,
    }
    public_ip = data.get("publicIp") or meta.get("public_ip")
    if public_ip:
        fields["publicIp"] = public_ip
    if hardware:
        fields["hardware"] = hardware
    logged_in = (hardware or {}).get("loggedInUser") or meta.get("logged_in_user")
    if logged_in:
        fields["loggedInUser"] = str(logged_in)[:200]
    device_id = data.get("device_id") or data.get("deviceId")
    if device_id:
        fields["deviceId"] = device_id
    return {k: v for k, v in fields.items() if v is not None}


async def hold(db, tenant: Dict[str, Any], agent_id: str, fields: Dict[str, Any], reason: str,
               existing: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create or refresh the Pending record for an agent that could not be admitted, and
    alert on its first arrival in Pending. Returns the stored agent document."""
    raw = _raw(db)
    now = _now().isoformat()
    entering = not existing or existing.get("status") != PENDING
    update: Dict[str, Any] = {"$set": {**fields, **(extra or {}), "tenantId": tenant["id"],
                                       "status": PENDING, "pendingReason": reason, "lastSeen": now},
                              "$setOnInsert": {"registeredAt": now}}
    if entering:
        update["$set"]["pendingSince"] = now
        update["$unset"] = {"pendingAlertedAt": ""}
    await raw.agents.update_one({"id": agent_id}, update, upsert=True)
    forget_status(agent_id)
    agent = await raw.agents.find_one({"id": agent_id}, {"_id": 0})
    await notify_pending(db, tenant, agent)
    return agent


_REFUSAL_TEXT = {
    REASON_SEAT_LIMIT: "Agent limit reached ({limit}). This computer is waiting for approval by your provider; "
                       "it will connect once approved.",
    REASON_DUPLICATE_HARDWARE: "duplicate_hardware_id: this machine is already enrolled as another agent that was "
                               "seen in the last 24 hours. It is waiting for approval.",
}


async def answer(db, response, tenant: Dict[str, Any], agent: Dict[str, Any], capable: bool,
                 agent_secret: Optional[str] = None) -> Dict[str, Any]:
    """The reply to a register call held as Pending: 202 for agents that understand it
    (with the secret they check back with, never a token), the old 403 for older builds
    (their record is kept, so it can still be approved)."""
    reason = agent.get("pendingReason") or REASON_SEAT_LIMIT
    if not capable:
        limit = licensing.license_of(await _raw(db).tenants.find_one({"id": tenant["id"]}))["maxAgents"]
        raise HTTPException(status_code=403, detail=_REFUSAL_TEXT.get(reason, reason).format(limit=limit))
    response.status_code = 202
    result = {"success": False, "status": "pending", "agentId": agent["id"], "pendingReason": reason,
              "retryAfterSeconds": RETRY_AFTER_SECONDS}
    if agent_secret:
        result["agentSecret"] = agent_secret
    return result


def heartbeat_identity(payload: Dict[str, Any], existing: Optional[Dict[str, Any]],
                       source_ip: Optional[str]) -> Dict[str, Any]:
    """Identity fields from a heartbeat: its ``hardware`` block, else the serial/MACs the
    meta carries. A hardware block already on file is never replaced by a weaker one."""
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    raw_hw = payload.get("hardware")
    if not isinstance(raw_hw, dict):
        raw_hw = {"serialNumber": meta.get("serial_number"), "macAddresses": meta.get("mac_addresses") or [],
                  "loggedInUser": meta.get("logged_in_user")}
    hardware = seat_identity.normalize_hardware(raw_hw)
    known = hardware.get("serialNumber") or hardware.get("smbiosUuid") or hardware.get("macAddresses")
    return identity_fields(payload, hardware if known and not (existing or {}).get("hardware") else {}, source_ip)


async def answer_heartbeat(db, request, response, tenant: Dict[str, Any], agent_id: str, payload: Dict[str, Any],
                           existing: Optional[Dict[str, Any]], reason: str) -> Dict[str, Any]:
    """Hold a heartbeating agent as Pending (storing only who it is; capability data is
    dropped) and answer 202, or 403 for builds that predate the pending answer."""
    source_ip = request.client.host if request.client else None
    await hold(db, tenant, agent_id, heartbeat_identity(payload, existing, source_ip), reason, existing)
    if not supports_pending(payload):
        raise HTTPException(status_code=403, detail="Agent limit reached. This agent is waiting for approval by your provider.")
    response.status_code = 202
    return {"success": False, "status": "pending", "pendingReason": reason, "retryAfterSeconds": RETRY_AFTER_SECONDS}


async def record_rejected(db, tenant: Dict[str, Any], agent_id: str, fields: Dict[str, Any],
                          existing: Optional[Dict[str, Any]] = None) -> None:
    """A denylisted machine enrolling again goes straight to Rejected (no seat, no token)."""
    now = _now().isoformat()
    await _raw(db).agents.update_one(
        {"id": agent_id},
        {"$set": {**fields, "tenantId": tenant["id"], "status": REJECTED, "lastSeen": now},
         "$setOnInsert": {"registeredAt": now, "rejectedAt": now, "rejectedBy": "denylist"}},
        upsert=True,
    )
    forget_status(agent_id)


async def is_denied(db, tenant_id: str, seat_key: Optional[str]) -> bool:
    if not denyable(seat_key):
        return False
    return bool(await _raw(db).agent_denylist.find_one({"tenantId": tenant_id, "seatKey": seat_key}, {"_id": 1}))


# ── Alerts ───────────────────────────────────────────────────────────────────

def alert_payload(tenant: Dict[str, Any], agent: Dict[str, Any], lic: Dict[str, Any]) -> Dict[str, Any]:
    hw = agent.get("hardware") or {}
    return {
        "event": "agent.pending",
        "tenantId": tenant.get("id"),
        "tenantName": tenant.get("name"),
        "seatsUsed": lic.get("seatsUsed"),
        "maxAgents": lic.get("maxAgents"),
        "reason": agent.get("pendingReason"),
        "agentId": agent.get("id"),
        "hostname": agent.get("hostname"),
        "ipAddress": agent.get("ipAddress"),
        "publicIp": agent.get("publicIp"),
        "sourceIp": agent.get("sourceIp"),
        "macAddresses": hw.get("macAddresses") or [],
        "serialNumber": hw.get("serialNumber"),
        "smbiosUuid": hw.get("smbiosUuid"),
        "osFamily": hw.get("osFamily") or agent.get("platform"),
        "osVersion": hw.get("osVersion"),
        "deviceType": hw.get("deviceType"),
        "loggedInUser": agent.get("loggedInUser") or hw.get("loggedInUser"),
        "agentVersion": agent.get("version"),
        "installKey": agent.get("enrollmentKeyName"),
        "firstSeen": agent.get("pendingSince"),
    }


_REASON_TEXT = {
    REASON_SEAT_LIMIT: "the tenant has no free agent seat",
    REASON_DUPLICATE_HARDWARE: "this machine is already enrolled as another agent that is still active",
    "not_allowlisted": "the machine is not on the tenant's hardware allowlist",
    "key_exhausted": "its install key is used up, expired or revoked",
    "license_expired": "the tenant's agent license has expired",
}


def reason_text(reason: Optional[str]) -> str:
    if reason and reason.startswith("sublimit:"):
        return f"the {reason[len('sublimit:'):]} sub-limit is full"
    return _REASON_TEXT.get(reason or "", reason or "unknown")


async def _post_in_app(raw, tenant_id: str, title: str, message: str, severity: str,
                       metadata: Dict[str, Any]) -> str:
    """One in-app notification in a tenant's feed (read by GET /api/notifications)."""
    now = _now()
    alert_id = f"alert-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    await raw.notifications.insert_one({
        "alert_id": alert_id, "title": title, "message": message, "severity": severity,
        "sent_at": now.isoformat(), "channels": {}, "tenantId": tenant_id, "tenant_id": tenant_id,
        "metadata": metadata,
    })
    try:
        from websocket_manager import broadcast_notification
        await broadcast_notification(tenant_id, {"title": title, "message": message, "severity": severity,
                                                 "alert_id": alert_id, "metadata": metadata})
    except Exception as exc:  # live push is best effort; the feed has the record
        logger.debug("Pending-agent WS broadcast skipped: %s", exc)
    return alert_id


async def post_to_recipients(raw, tenant: Dict[str, Any], title: str, message: str, severity: str,
                              metadata: Dict[str, Any]) -> None:
    """Platform staff (the platform tenant's feed) and the agent's tenant admins."""
    await _post_in_app(raw, PLATFORM_TENANT_ID, title, message, severity, metadata)
    if tenant.get("id") and tenant["id"] != PLATFORM_TENANT_ID:
        await _post_in_app(raw, tenant["id"], title, message, severity,
                           {**metadata, "audience": TENANT_ADMIN_AUDIENCE})


async def _window_count(raw, tenant_id: str, now: datetime) -> Tuple[int, Dict[str, Any]]:
    """Count this Pending arrival in the tenant's current alert window."""
    coll = raw.agent_pending_alert_windows
    await coll.update_one(
        {"tenantId": tenant_id, "windowStart": {"$lt": (now - ALERT_WINDOW).isoformat()}},
        {"$set": {"windowStart": now.isoformat(), "count": 0}, "$unset": {"summaryKey": ""}},
    )
    for attempt in range(2):
        try:
            doc = await coll.find_one_and_update(
                {"tenantId": tenant_id},
                {"$inc": {"count": 1}, "$setOnInsert": {"windowStart": now.isoformat()}},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
            return doc["count"], doc
        except DuplicateKeyError:  # two first arrivals raced the upsert; the retry updates
            if attempt:
                raise
    raise RuntimeError("unreachable")


async def notify_pending(db, tenant: Dict[str, Any], agent: Dict[str, Any]) -> bool:
    """Alert once per Pending episode of an agent. Returns whether this call alerted."""
    raw = _raw(db)
    now = _now()
    claimed = await raw.agents.update_one(
        {"id": agent["id"], "status": PENDING, "pendingAlertedAt": None},
        {"$set": {"pendingAlertedAt": now.isoformat()}},
    )
    if claimed.modified_count != 1:
        return False
    try:
        lic = licensing.license_of(await raw.tenants.find_one({"id": tenant["id"]}) or tenant)
        payload = alert_payload(tenant, agent, lic)
        count, window = await _window_count(raw, tenant["id"], now)
        tenant_label = tenant.get("name") or tenant["id"]
        if count <= ALERT_INDIVIDUAL_LIMIT:
            await post_to_recipients(
                raw, tenant, f"Agent waiting for approval: {agent.get('hostname')} ({tenant_label})",
                f"{agent.get('hostname')} tried to enroll in {tenant_label} but {reason_text(payload['reason'])} "
                f"({payload['seatsUsed']}/{payload['maxAgents']} seats used). Approve or reject it under Agents → Pending.",
                "warning", payload)
            return True
        summary_text = (f"{count} agents went Pending in {tenant_label} within the last hour "
                        f"({payload['seatsUsed']}/{payload['maxAgents']} seats used). Review them under Agents → Pending.")
        if count == ALERT_INDIVIDUAL_LIMIT + 1:
            key = f"pending-summary-{tenant['id']}-{window['windowStart']}"
            await raw.agent_pending_alert_windows.update_one({"tenantId": tenant["id"]}, {"$set": {"summaryKey": key}})
            await post_to_recipients(
                raw, tenant, f"Many agents waiting for approval in {tenant_label}", summary_text, "warning",
                {"event": "agent.pending.summary", "summaryKey": key, "tenantId": tenant["id"],
                 "tenantName": tenant.get("name"), "count": count})
        elif window.get("summaryKey"):
            await raw.notifications.update_many(
                {"metadata.summaryKey": window["summaryKey"]},
                {"$set": {"message": summary_text, "metadata.count": count}})
        return True
    except Exception as exc:  # an alert failure must never fail the enrollment
        logger.error("Pending-agent alert failed for %s: %s", agent.get("id"), exc)
        return False


# ── Decisions (super admin) ───────────────────────────────────────────────────

async def _audit(action: str, agent: Dict[str, Any], actor: str, details: str) -> None:
    try:
        from audit_service import get_audit_service
        await get_audit_service().log_action_async(
            user_name=actor, action=action, resource_type="agent", resource_id=agent.get("id", ""),
            details=details, tenant_id=agent.get("tenantId"))
    except Exception as exc:
        logger.warning("Pending-agent audit write failed (%s): %s", action, exc)


class DecisionError(Exception):
    def __init__(self, status_code: int, detail: str, extra: Optional[Dict[str, Any]] = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.extra = extra or {}


async def _undecided(raw, agent_id: str) -> Dict[str, Any]:
    agent = await raw.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise DecisionError(404, "Agent not found")
    if agent.get("status") not in NOT_ADMITTED:
        raise DecisionError(409, f"Agent is {agent.get('status')}, not pending")
    return agent


async def approve(db, agent_id: str, actor: str, raise_limit_by: int = 0) -> Dict[str, Any]:
    """Admit a Pending (or previously Rejected) agent: it claims a seat and goes Offline
    until its next check-in brings it Online. With ``raise_limit_by`` the tenant's seat
    limit grows first. Raises DecisionError 409 ``no_free_seat`` when no seat is free."""
    raw = _raw(db)
    agent = await _undecided(raw, agent_id)
    tenant_id = agent["tenantId"]
    if raise_limit_by:
        await licensing.ensure_license(db, tenant_id)
        await raw.tenants.update_one({"id": tenant_id},
                                     {"$inc": {"license.maxAgents": raise_limit_by, "maxAgents": raise_limit_by}})
    if not await licensing.try_claim_seat(db, tenant_id):
        raise DecisionError(409, "no_free_seat: the tenant has no free agent seat; raise its limit to approve",
                            await licensing.license_summary(db, tenant_id))
    now = _now().isoformat()
    res = await raw.agents.update_one(
        {"id": agent_id, "status": agent["status"]},
        {"$set": {"status": "Offline", "approvedAt": now, "approvedBy": actor},
         "$unset": {**_PENDING_FIELDS_UNSET, "rejectedAt": "", "rejectedBy": ""}},
    )
    if res.modified_count != 1:  # decided concurrently: give the seat back
        await licensing.release_seats(db, tenant_id)
        raise DecisionError(409, "Agent was decided by someone else; refresh")
    if agent["status"] == REJECTED and denyable(agent.get("seatKey")):
        await raw.agent_denylist.delete_one({"tenantId": tenant_id, "seatKey": agent["seatKey"]})
    forget_status(agent_id)
    if agent.get("enrollmentGroupId"):  # the install key's default group (spec C4)
        import license_rules
        await license_rules.join_group(db, tenant_id, agent["enrollmentGroupId"], agent_id, actor)
    await _audit("agent.approved", agent, actor,
                 f"Approved {agent.get('hostname')} (was {agent['status']}, reason {agent.get('pendingReason')})"
                 + (f"; seat limit raised by {raise_limit_by}" if raise_limit_by else ""))
    return {"agentId": agent_id, "status": "Offline", "license": await licensing.license_summary(db, tenant_id)}


async def reject(db, agent_id: str, actor: str) -> Dict[str, Any]:
    """Refuse a Pending agent for good: Rejected, and its machine denylisted in the tenant."""
    raw = _raw(db)
    agent = await _undecided(raw, agent_id)
    if agent["status"] == REJECTED:
        return {"agentId": agent_id, "status": REJECTED}
    now = _now().isoformat()
    res = await raw.agents.update_one(
        {"id": agent_id, "status": PENDING},
        {"$set": {"status": REJECTED, "rejectedAt": now, "rejectedBy": actor},
         "$unset": _PENDING_FIELDS_UNSET},
    )
    if res.modified_count != 1:
        raise DecisionError(409, "Agent was decided by someone else; refresh")
    # A duplicate's seat key is the live agent's too: denylisting it would lock that agent out.
    if denyable(agent.get("seatKey")) and agent.get("pendingReason") != REASON_DUPLICATE_HARDWARE:
        try:
            await raw.agent_denylist.insert_one({
                "tenantId": agent["tenantId"], "seatKey": agent["seatKey"], "agentId": agent_id,
                "hostname": agent.get("hostname"), "rejectedAt": now, "rejectedBy": actor})
        except DuplicateKeyError:
            pass
    forget_status(agent_id)
    await _audit("agent.rejected", agent, actor,
                 f"Rejected {agent.get('hostname')} (reason {agent.get('pendingReason')}, seat key {agent.get('seatKey')})")
    return {"agentId": agent_id, "status": REJECTED}


async def list_not_admitted(db, tenant_id: Optional[str], status: Optional[str] = None,
                            reason: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """Pending/Rejected agents, newest first; all tenants when ``tenant_id`` is None."""
    query: Dict[str, Any] = {"status": status if status in NOT_ADMITTED else {"$in": sorted(NOT_ADMITTED)}}
    if tenant_id:
        query["tenantId"] = tenant_id
    if reason:
        query["pendingReason"] = reason
    projection = {"_id": 0, "agentSecretHash": 0, "uninstallProtection": 0}
    cursor = _raw(db).agents.find(query, projection).sort("lastSeen", -1).limit(limit)
    return await cursor.to_list(length=limit)
