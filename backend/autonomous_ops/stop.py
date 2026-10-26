"""The stop switch (GATE-06, D-11 to D-15): press, clear and the press-time bulk cancel.

A stop is a document, read fresh on every decision and every delivery, so pressing takes effect
on the next read with no restart: a tenant stop lives in ``autonomy_settings.stop`` and the
platform-wide stop in ``system_settings {type: "autonomous_ops"}.stop``. Pressing is
compare-and-set on ``stop.active`` (the second press reads ``already_stopped``); clearing is
compare-and-set the other way. ``clear`` is the only code that sets an active stop inactive
(PROH-81-07): no timer, restart, migration, breaker restore or reconciler tick touches it.

Raw Mongo handle with an explicit tenantId everywhere; the ambient tenant ContextVar is never used.
The HTTP routes that call these functions arrive in plan 81-09 and decide who may press.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import PLATFORM_TENANT_ID, STAMP_SOURCE, ledger, messages, notify, settings
from .scope import raw

logger = logging.getLogger(__name__)

REASON_MAX = 500
_PLATFORM_QUERY = {"type": "autonomous_ops"}
_CANCEL_KINDS = ("action", "probe")           # D-12: undo and compensate are never cancelled
_ROW_STATES = ("approved", "dispatching")     # ledger states a cancelled delivery can leave behind


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


def _who(actor: Optional[Dict[str, Any]]) -> Dict[str, str]:
    actor = actor or {}
    username = str(actor.get("username") or actor.get("display") or "unknown")
    return {"username": username, "display": str(actor.get("display") or username)}


def _clean_reason(reason: Optional[str], *, required: bool) -> Optional[str]:
    """The trimmed reason (None when empty and optional). Raises ValueError when it breaks D-14."""
    if reason is None:
        if required:
            raise ValueError("reason required")
        return None
    if not isinstance(reason, str):
        raise ValueError("reason must be text")
    text = reason.strip()
    if required and not text:
        raise ValueError("reason required")
    if len(text) > REASON_MAX:
        raise ValueError("reason too long")
    return text or None


def _validate_scope(scope: str, tenant_id: Optional[str]) -> None:
    if scope == "platform":
        return
    if scope != "tenant" or not tenant_id or tenant_id == PLATFORM_TENANT_ID:
        raise ValueError("a tenant stop needs a real tenant id")


async def platform_stop_doc(db) -> Optional[Dict[str, Any]]:
    """The platform-wide stop (None when never pressed). Errors propagate."""
    return await settings.platform_stop(db)


async def _current(db, scope: str, tenant_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if scope == "platform":
        return await settings.platform_stop(db)
    return (await settings.load(db, tenant_id)).stop


def can_clear(stop: Optional[Dict[str, Any]], *, actor_is_super_admin: bool, actor_has_manage: bool) -> bool:
    """D-11. The Super Admin may clear any stop. A holder of manage:autonomous_ops for the tenant
    may clear only a tenant stop that was pressed at tenant tier; the platform-wide stop and a
    tenant stop pressed by a Super Admin (or of unknown origin) need the Super Admin."""
    if not isinstance(stop, dict):
        return False
    if actor_is_super_admin:
        return True
    if stop.get("scope") == "platform":
        return False
    return stop.get("pressedByTier") == "tenant" and bool(actor_has_manage)


async def press(db, *, scope: str, tenant_id: Optional[str], actor: Dict[str, Any],
                reason: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Turn a stop on. Returns ``{"status": "stopped" | "already_stopped" | "invalid_reason",
    "stop": dict | None, "cancelled": int}``. A stop on the platform scope covers every tenant."""
    _validate_scope(scope, tenant_id)
    try:
        text = _clean_reason(reason, required=False)
    except ValueError:
        return {"status": "invalid_reason", "stop": None, "cancelled": 0}
    handle = raw(db)
    pressed_at = _now(now)
    tier = "platform" if scope == "platform" else (actor or {}).get("tier") or "tenant"
    stop_doc = {"active": True, "scope": scope, "pressedBy": _who(actor), "pressedByTier": tier,
                "pressedAt": pressed_at, "reason": text}
    if scope == "platform":
        await handle.system_settings.update_one(_PLATFORM_QUERY, {"$setOnInsert": {"type": "autonomous_ops", "stop": None}},
                                                upsert=True)
        won = await handle.system_settings.update_one({**_PLATFORM_QUERY, "stop.active": {"$ne": True}},
                                                      {"$set": {"stop": stop_doc}})
    else:
        await settings.ensure_tenant(db, tenant_id)
        won = await handle.autonomy_settings.update_one(
            {"tenantId": tenant_id, "stop.active": {"$ne": True}},
            {"$set": {"stop": stop_doc, "updatedAt": pressed_at, "updatedBy": _who(actor)["username"]}})
    if won.modified_count != 1:
        return {"status": "already_stopped", "stop": await _current(db, scope, tenant_id), "cancelled": 0}

    cancelled = 0
    try:
        cancelled = await cancel_undelivered(db, None if scope == "platform" else tenant_id)
    except Exception as exc:       # delivery holds the work back anyway; the stop stays on
        logger.error("autonomous_ops: stop pressed but queued work could not be cancelled: %s", exc)

    control_tenant = PLATFORM_TENANT_ID if scope == "platform" else tenant_id
    event = "platform_stop_pressed" if scope == "platform" else "stop_pressed"
    try:
        await ledger.record_control(db, control_tenant, event, scope=scope, actor=dict(actor or {}), reason=text)
    except Exception as exc:       # the stop is already on; say so in the log, never undo it
        logger.error("autonomous_ops: %s not recorded in the ledger: %s", event, exc)

    title, body = messages.NOTICES[event]
    name = ""
    if scope == "tenant":
        name = (await settings.load(db, tenant_id)).name or tenant_id
    await notify.notify(
        db, control_tenant, title=title,
        message=body.format(tenant=name, actor=_who(actor)["display"], reason=f"Reason: {text}." if text else "").strip(),
        severity="warning", metadata={"event": event, "tenantId": control_tenant, "scope": scope})
    return {"status": "stopped", "stop": stop_doc, "cancelled": cancelled}


async def clear(db, *, scope: str, tenant_id: Optional[str], actor: Dict[str, Any], reason: str,
                actor_is_super_admin: bool, actor_has_manage: bool,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """Turn a stop off (D-11, D-14). Needs a typed reason (non-empty after trimming, at most
    REASON_MAX) and an authorized actor. Returns ``{"status": "cleared" | "not_stopped" |
    "forbidden" | "invalid_reason", "stop": dict | None}``."""
    _validate_scope(scope, tenant_id)
    try:
        text = _clean_reason(reason, required=True)
    except ValueError:
        return {"status": "invalid_reason", "stop": await _safe_current(db, scope, tenant_id)}
    current = await _current(db, scope, tenant_id)
    if not settings.stop_active(current):
        return {"status": "not_stopped", "stop": current}
    if not can_clear(current, actor_is_super_admin=actor_is_super_admin, actor_has_manage=actor_has_manage):
        return {"status": "forbidden", "stop": current}
    cleared_at = _now(now)
    fields = {"stop.active": False, "stop.clearedBy": _who(actor), "stop.clearedAt": cleared_at,
              "stop.clearReason": text}
    handle = raw(db)
    if scope == "platform":
        won = await handle.system_settings.update_one({**_PLATFORM_QUERY, "stop.active": True}, {"$set": fields})
    else:
        won = await handle.autonomy_settings.update_one(
            {"tenantId": tenant_id, "stop.active": True},
            {"$set": {**fields, "updatedAt": cleared_at, "updatedBy": _who(actor)["username"]}})
    if won.modified_count != 1:
        return {"status": "not_stopped", "stop": await _current(db, scope, tenant_id)}
    control_tenant = PLATFORM_TENANT_ID if scope == "platform" else tenant_id
    event = "platform_stop_cleared" if scope == "platform" else "stop_cleared"
    try:
        await ledger.record_control(db, control_tenant, event, scope=scope, actor=dict(actor or {}), reason=text)
    except Exception as exc:
        logger.error("autonomous_ops: %s not recorded in the ledger: %s", event, exc)
    return {"status": "cleared", "stop": await _current(db, scope, tenant_id)}


async def _safe_current(db, scope: str, tenant_id: Optional[str]):
    try:
        return await _current(db, scope, tenant_id)
    except Exception:
        return None


async def cancel_undelivered(db, tenant_id: Optional[str]) -> int:
    """Mark every stamped action/probe instruction still pending, and every stamped response
    task still queued, as ``cancelled_by_stop`` and move its ledger row to cancelled_by_stop
    (D-12, A6). ``tenant_id`` None covers every tenant (the platform stop). Returns how many
    instructions and response tasks were cancelled."""
    handle = raw(db)
    stamp = {"autonomy.actionId": {"$type": "string"}, "triggered_by": STAMP_SOURCE}
    scope = {"tenantId": tenant_id} if tenant_id else {}
    now = datetime.now(timezone.utc).isoformat()
    mark = {"status": "cancelled_by_stop", "cancelled_at": now, "error": "cancelled_by_stop"}
    count = 0
    plans = (
        (handle.agent_instructions, "pending", {"autonomy.kind": {"$in": list(_CANCEL_KINDS)}}),
        (handle.response_tasks, "queued", {}),
    )
    for coll, pending, extra in plans:
        docs = await coll.find({**stamp, **scope, **extra, "status": pending}).to_list(length=None)
        for doc in docs:
            hit = await coll.update_one({"_id": doc["_id"], "status": pending}, {"$set": mark})
            if hit.modified_count != 1:
                continue                      # delivered or cancelled by a poll in the meantime
            count += 1
            stamp_info = doc.get("autonomy") or {}
            row_tenant = stamp_info.get("tenantId") or doc.get("tenantId")
            try:
                await ledger.transition(db, row_tenant, stamp_info["actionId"], _ROW_STATES, "cancelled_by_stop",
                                        cancelReason="stop")
            except Exception as exc:
                logger.error("autonomous_ops: ledger row %s not marked cancelled_by_stop: %s",
                             stamp_info.get("actionId"), exc)
    return count
