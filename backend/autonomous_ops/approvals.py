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
from . import gate
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
        spec = registry.resolve(row.get("command"))
        params = row.get("params") if isinstance(row.get("params"), dict) else {}
        for key in (spec.ip_params if spec else ()):
            if params.get(key) is not None:
                code = await protected.check(db, tenant_id, ip=params[key])
                if code:
                    return code
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


# ---------------------------------------------------------------- deny, expiry, undo (Task 2)

async def deny(db, tenant_id: str, action_id: str, *, approver: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    raise NotImplementedError


async def expire_due(db, *, now: Optional[datetime] = None, tenant_id: Optional[str] = None) -> int:
    raise NotImplementedError


async def undo(db, tenant_id: str, action_id: str, *, actor: Dict[str, Any]) -> Dict[str, Any]:
    raise NotImplementedError
