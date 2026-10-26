"""Approvals, denials, expiry and undo for Autonomous Ops (GATE-10, D-12, D-13, D-16).

A card (a ledger row in ``awaiting_approval`` or ``suggested``) is approved with ONE
compare-and-set (``ledger.transition`` with the 24 hour expiry in the filter), so two
concurrent clicks produce one winner; the loser gets ``already_handled``. The winner
re-validates volatile facts (the target still belongs to the tenant, is not on the never-touch
list, and the tenant is still eligible and not Off) and only then dispatches through the
dispatcher named on the row. Dispatch always goes through ``gate.execute`` /
``gate.execute_response_task`` (or a dispatcher registered here that does the same): this
module changes rows only through ``ledger.transition`` and writes no agent document itself.

While a stop is on, approving is frozen and changes nothing (D-12); deny and undo still work.
The expiry clock keeps running during a stop (D-13): ``expire_due`` never looks at a stop, so
a stale card can never fire on resume.

Raw Mongo handle with an explicit tenantId everywhere; the ambient tenant ContextVar is never
used.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from . import APPROVAL_TTL, PLATFORM_TENANT_ID, ledger, messages, protected, registry, settings
from . import breaker, dispatch_check, gate
from .scope import raw

logger = logging.getLogger(__name__)

_OPEN = ("awaiting_approval", "suggested")
_UNDOABLE = ("executed", "verified")
Dispatcher = Callable[[Any, Dict[str, Any], Dict[str, Any]], Awaitable[Dict[str, Any]]]


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)   # BSON datetimes are milliseconds


def _expires_at(row: Dict[str, Any]) -> Optional[datetime]:
    value = (row.get("approval") or {}).get("expiresAt")
    if isinstance(value, datetime):
        return value
    created = row.get("createdAt")
    return created + APPROVAL_TTL if isinstance(created, datetime) else None   # fail closed: never open-ended


# ---------------------------------------------------------------- dispatchers

async def _dispatch_instruction(db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
    return await gate.execute(db, row["tenantId"], row["id"], command=row.get("command"),
                              agent_id=(row.get("targets") or [None])[0], params=row.get("params") or {},
                              kind="action")


async def _dispatch_response_task(db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
    return await gate.execute_response_task(
        db, row["tenantId"], row["id"], action=row.get("command"), agent_id=(row.get("targets") or [None])[0],
        params=row.get("params") or {}, playbook_execution_id=row.get("playbookExecutionId"))


_DISPATCHERS: Dict[str, Dispatcher] = {"instruction": _dispatch_instruction, "response_task": _dispatch_response_task}


def register_dispatcher(name: str, fn: Dispatcher) -> None:
    """Add a dispatcher (plan 81-08 registers remediation). ``fn(db, row, approver)`` is async,
    is called with the row already ``approved`` and returns a dict."""
    _DISPATCHERS[name] = fn


# ---------------------------------------------------------------- approve

async def _revalidate(db, row: Dict[str, Any]) -> Optional[str]:
    """A reason code when the card must not be dispatched any more, else None. Anything
    unreadable refuses (fail closed)."""
    tenant_id = row["tenantId"]
    try:
        tenant = await settings.load(db, tenant_id)
    except Exception as exc:
        logger.error("autonomous_ops: approval re-check could not read settings: %s", exc)
        return "settings_unreadable"
    if tenant_id == PLATFORM_TENANT_ID:
        return "platform_tenant"
    if not tenant.eligible:
        return "not_enabled"
    if settings.effective_level(tenant) == "off":
        return "level_off"
    targets = row.get("targets") or []
    if not targets:
        return "no_target"
    try:
        for target in dict.fromkeys(targets):
            agent = await raw(db).agents.find_one(
                {"id": target}, {"_id": 0, "id": 1, "tenantId": 1, "hostname": 1, "ipAddress": 1})
            if agent is None:
                return "no_target"
            if agent.get("tenantId") != tenant_id:
                return "cross_tenant_target"
            code = await protected.check(db, tenant_id, agent=agent)
            if code:
                return code
        code = await dispatch_check.ip_refusal(db, tenant_id, dispatch_check.row_pairs(row))
        if code:
            return code        # every recorded step and compensation step, each with its own params
    except Exception as exc:
        logger.error("autonomous_ops: approval re-check of the target failed, refusing: %s", exc)
        return "protected_target"
    return None


async def _fail(db, row: Dict[str, Any], reason: str, to_state: str = "failed") -> None:
    await ledger.transition(db, row["tenantId"], row["id"], ("approved", "dispatching"), to_state,
                            reasonCode=reason, reasonText=messages.REASON_TEXT.get(reason, "Nothing was dispatched."))


async def approve(db, tenant_id: str, action_id: str, *, approver: Dict[str, Any],
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Approve a card and dispatch it. Status: dispatched (plus ``dispatch``), stopped, expired,
    already_handled, not_found, refused (plus ``reason``)."""
    now = _now(now)
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return {"status": "not_found"}
    if await gate._stopped(db, tenant_id):          # D-12; an unreadable stop counts as stopped
        return {"status": "stopped"}
    dispatcher = _DISPATCHERS.get(row.get("dispatcher") or "instruction")
    if dispatcher is None:
        return {"status": "refused", "reason": "no_dispatcher"}
    if row.get("state") not in _OPEN:
        return {"status": "already_handled"}
    expires = _expires_at(row)
    if expires is None or now >= expires:
        await ledger.transition(db, tenant_id, action_id, _OPEN, "expired")
        return {"status": "expired"}

    won = await ledger.transition(
        db, tenant_id, action_id, _OPEN, "approved", actor=approver,
        where={"approval.expiresAt": {"$gt": now}},
        **{"approval.approver": dict(approver), "approval.decidedAt": now})
    if won is None:
        latest = await ledger.get(db, tenant_id, action_id)
        if latest is not None and latest.get("state") in _OPEN:     # the clock ran out between read and write
            await ledger.transition(db, tenant_id, action_id, _OPEN, "expired")
            return {"status": "expired"}
        return {"status": "already_handled"}

    reason = await _revalidate(db, won)
    if reason:
        await ledger.transition(db, tenant_id, action_id, ("approved",), "refused", actor=approver,
                                reasonCode=reason, reasonText=messages.REASON_TEXT.get(reason))
        return {"status": "refused", "reason": reason}

    try:
        result = await dispatcher(db, won, approver)
    except Exception as exc:
        logger.error("autonomous_ops: dispatcher %s failed for %s: %s", row.get("dispatcher"), action_id, exc)
        await _fail(db, won, "dispatch_failed")
        return {"status": "refused", "reason": "dispatch_failed"}
    if isinstance(result, dict) and result.get("status") == "refused":
        reason = result.get("reason") or "dispatch_failed"
        if reason == "stopped":                     # a stop landed after the approval: nothing was written
            await _fail(db, won, "platform_stop", to_state="cancelled_by_stop")
            return {"status": "stopped"}
        await _fail(db, won, "dispatch_failed")
        return {"status": "refused", "reason": reason}
    return {"status": "dispatched", "dispatch": result}


# ---------------------------------------------------------------- deny, expiry

async def deny(db, tenant_id: str, action_id: str, *, approver: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    """Deny a card. Dispatches nothing, so it stays allowed during a stop."""
    if await ledger.get(db, tenant_id, action_id) is None:
        return {"status": "not_found"}
    row = await ledger.transition(
        db, tenant_id, action_id, _OPEN, "denied", actor=approver,
        **{"approval.approver": dict(approver), "approval.decidedAt": _now(None), "approval.reason": reason or ""})
    return {"status": "denied"} if row else {"status": "already_handled"}


async def expire_due(db, *, now: Optional[datetime] = None, tenant_id: Optional[str] = None) -> int:
    """Expire every open card whose 24 hours have passed (counted as denied). Ignores stops
    (D-13). ``tenant_id`` limits the sweep to one tenant. Returns how many rows expired."""
    now = _now(now)
    flt: Dict[str, Any] = {"state": {"$in": list(_OPEN)}, "approval.expiresAt": {"$lte": now}}
    if tenant_id is not None:
        flt["tenantId"] = tenant_id
    due = [r async for r in raw(db).autonomy_actions.find(flt, {"_id": 0, "id": 1, "tenantId": 1})]
    expired = 0
    for item in due:
        try:
            done = await ledger.transition(db, item["tenantId"], item["id"], _OPEN, "expired",
                                           where={"approval.expiresAt": {"$lte": now}})
        except Exception as exc:
            logger.error("autonomous_ops: could not expire %s: %s", item.get("id"), exc)
            continue
        expired += 1 if done else 0
    return expired


# ---------------------------------------------------------------- undo

async def undo(db, tenant_id: str, action_id: str, *, actor: Dict[str, Any]) -> Dict[str, Any]:
    """Put an executed action back (D-12: works during a stop; the click is the approval)."""
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return {"status": "not_found"}
    if row.get("state") == "undone":
        return {"status": "already_handled"}
    if row.get("state") not in _UNDOABLE:
        return {"status": "refused", "reason": "not_undoable"}
    spec = registry.resolve(row.get("command"))
    if spec is None or not spec.undo:
        return {"status": "no_undo"}
    targets = row.get("targets") or []
    if not targets:
        return {"status": "refused", "reason": "no_target"}
    params = gate._undo_block(spec, row.get("params") or {})["params"]
    block = {"available": True, "action": spec.undo, "params": params, "undoneAt": _now(None),
             "undoneBy": dict(actor)}
    won = await ledger.transition(db, tenant_id, action_id, _UNDOABLE, "undone", actor=actor, undo=block)
    if won is None:
        return {"status": "already_handled"}
    result = await gate.execute(db, tenant_id, action_id, command=spec.undo, agent_id=targets[0], params=params,
                                kind="undo")
    if result.get("status") != "queued":
        # Nothing was written to an agent: do not leave a row claiming it was put back.
        await ledger.transition(db, tenant_id, action_id, ("undone",), row["state"], actor=actor,
                                undo=row.get("undo") or {"available": True, "action": spec.undo, "params": params,
                                                         "undoneAt": None, "undoneBy": None},
                                finishedAt=row.get("finishedAt"))
        return {"status": "refused", "reason": result.get("reason") or "dispatch_failed"}
    tripped = False
    try:
        tripped = bool(await breaker.evaluate(db, tenant_id))
    except Exception as exc:
        logger.error("autonomous_ops: breaker check after undo of %s failed: %s", action_id, exc)
    return {"status": "undone", "dispatch": result, "breaker_tripped": tripped}
