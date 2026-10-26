"""Delivery hold-back: the last point where an autonomous instruction can still be stopped (GATE-06).

``hold_back_autonomous`` runs on the instructions an agent is about to receive;
``hold_back_response_tasks`` does the same for the response-task queue (the third queue, D-21).
Only items carrying the autonomy stamp (``autonomy.actionId``) are looked at: with none, the list
is returned unchanged and the database is not touched. For a stamped item:

* a stop (platform or the tenant's) on an action or probe: the item becomes terminal
  ``cancelled_by_stop`` and its ledger row follows, so it is never delivered after the stop is
  cleared (D-12, PROH-81-09). Undo and compensate are exempt: putting things back still works.
* the stop or ledger state cannot be read: the item is withheld and left as it was (fail closed).
* the ledger row is missing, not dispatchable for the kind, or belongs to another tenant than the
  item or the polling agent: the item is withheld and marked ``refused``.

Stop state is read fresh on every call (never cached); the raw Mongo handle and explicit tenant
ids are used throughout.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import INSTRUCTION_KINDS, STOP_EXEMPT_KINDS, ledger, settings
from .gate import _DISPATCHABLE
from .scope import raw

logger = logging.getLogger(__name__)

_CANCELLED = "cancelled_by_stop"
_REFUSED = "refused"
_CANCEL_ROW_STATES = ("approved", "dispatching")


class _Unreadable(Exception):
    """The stop or ledger state could not be read; the item must be withheld."""


def _stamp(item: Dict[str, Any]) -> Dict[str, Any]:
    stamp = item.get("autonomy")
    return stamp if isinstance(stamp, dict) and isinstance(stamp.get("actionId"), str) and stamp["actionId"] else {}


async def _stopped(db, tenant_id: str, cache: Dict[str, bool]) -> bool:
    """Whether a platform or tenant stop is on. Raises ``_Unreadable`` when it cannot be told."""
    if tenant_id in cache:
        return cache[tenant_id]
    try:
        if settings.stop_active(await settings.platform_stop(db)):
            cache[tenant_id] = True
            return True
        s = await settings.load(db, tenant_id)
    except Exception as exc:
        logger.error("autonomous_ops: stop state unreadable at delivery, withholding: %s", exc)
        raise _Unreadable() from exc
    if not s.readable:
        raise _Unreadable()
    cache[tenant_id] = settings.stop_active(s.stop)
    return cache[tenant_id]


async def _row(db, action_id: str) -> Optional[Dict[str, Any]]:
    """The ledger row by id alone (so another tenant's row is seen, not hidden). Raises
    ``_Unreadable`` when the read fails."""
    try:
        row = await raw(db).autonomy_actions.find_one({"id": action_id}, {"_id": 0, "id": 1, "tenantId": 1, "state": 1})
    except Exception as exc:
        logger.error("autonomous_ops: ledger unreadable at delivery, withholding: %s", exc)
        raise _Unreadable() from exc
    return row


async def _screen(db, tenant_id: Optional[str], items: List[Dict[str, Any]], *, coll_name: str,
                  key: str, pending: str, default_kind: Optional[str]) -> List[Dict[str, Any]]:
    stamped = [i for i in items if _stamp(i)]
    if not stamped:
        return items
    coll = getattr(raw(db), coll_name)
    stops: Dict[str, bool] = {}
    withheld = set()

    async def mark(item, status, why, row_tenant=None, row_state_from=()):
        withheld.add(id(item))
        try:
            await coll.update_one({key: item[key], "status": pending},
                                  {"$set": {"status": status, "error": why,
                                            ("cancelled_at" if status == _CANCELLED else "refused_at"):
                                                datetime.now(timezone.utc).isoformat()}})
        except Exception as exc:
            logger.error("autonomous_ops: %s %s not marked %s: %s", coll_name, item.get(key), status, exc)
        if row_state_from:
            try:
                await ledger.transition(db, row_tenant, _stamp(item)["actionId"], row_state_from, status,
                                        cancelReason="stop")
            except Exception as exc:
                logger.error("autonomous_ops: ledger row %s not marked %s: %s", _stamp(item)["actionId"], status, exc)

    for item in stamped:
        stamp = _stamp(item)
        item_tenant = item.get("tenantId") or stamp.get("tenantId")
        kind = stamp.get("kind") or default_kind
        try:
            # Whose item is this? Every tenant named on it, and the polling agent's, must agree.
            named = {t for t in (item.get("tenantId"), stamp.get("tenantId"), tenant_id) if t}
            if not item_tenant or len(named) != 1 or kind not in INSTRUCTION_KINDS:
                await mark(item, _REFUSED, "autonomy_tenant_or_kind_mismatch")
                continue
            if kind not in STOP_EXEMPT_KINDS and await _stopped(db, item_tenant, stops):
                await mark(item, _CANCELLED, _CANCELLED, row_tenant=item_tenant, row_state_from=_CANCEL_ROW_STATES)
                continue
            row = await _row(db, stamp["actionId"])
            if row is None:
                await mark(item, _REFUSED, "autonomy_ledger_row_missing")
            elif row.get("tenantId") != item_tenant:
                await mark(item, _REFUSED, "autonomy_ledger_tenant_mismatch")
            elif row.get("state") not in _DISPATCHABLE[kind]:
                await mark(item, _REFUSED, "autonomy_not_dispatchable")
        except _Unreadable:
            withheld.add(id(item))          # left as it was: pending, retried at the next poll
    return [i for i in items if id(i) not in withheld]


async def hold_back_autonomous(db, tenant_id: Optional[str], instructions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The agent instructions that may be delivered now (stamped ones filtered per the rules above)."""
    if not instructions:
        return instructions
    return await _screen(db, tenant_id, instructions, coll_name="agent_instructions", key="_id",
                         pending="pending", default_kind=None)


async def hold_back_response_tasks(db, tenant_id: Optional[str], tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The queued response tasks that may be delivered now, under the same rules."""
    if not tasks:
        return tasks
    return await _screen(db, tenant_id, tasks, coll_name="response_tasks", key="task_id",
                         pending="queued", default_kind="action")
