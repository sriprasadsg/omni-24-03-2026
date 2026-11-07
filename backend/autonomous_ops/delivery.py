"""Delivery hold-back: the last point where an autonomous instruction can still be stopped (GATE-06).

``hold_back_autonomous`` runs on the instructions an agent is about to receive;
``hold_back_response_tasks`` does the same for the response-task queue (the third queue, D-21).
An item with NO autonomy stamp is looked at only for its command: one naming a gate-only command
(``GATE_ONLY_COMMANDS``, the actions 2.1.16 added) is marked ``refused`` with error
``autonomy_gate_required`` and dropped, whatever wrote it (T-83-25, RESP-11). Any other unstamped item is
returned untouched. With no gate-only item, no stamped item and no ``expiresAt``, the list is returned
unchanged and the database is not touched.

An instruction whose ``expiresAt`` is at or before now (a naive value is read as UTC) was issued for a window
that has closed: it is marked ``refused`` with error ``instruction_expired`` and dropped, before any other check
(PTCH-07, 84 D-04). A value that is not a date is ignored. A stamped undo or compensate is exempt: putting things
back is never held by a clock (84 D-15). For a stamped item:

* a stop (platform or the tenant's) on an action or probe: the item becomes terminal
  ``cancelled_by_stop`` and its ledger row follows, so it is never delivered after the stop is
  cleared (D-12, PROH-81-09). Undo and compensate are exempt: putting things back still works.
* the stop or ledger state cannot be read: the item is withheld and left as it was (fail closed).
* the ledger row is missing, not dispatchable for the kind, or belongs to another tenant than the
  item or the polling agent: the item is withheld and marked ``refused``.

``cancel_unfetched`` is the hold-back for work the platform gave up on: a rollout that abandons an instruction
nobody fetched turns it ``cancelled``, so a computer that comes back later never runs it (84 WR-27).

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

# Commands an agent may run only when the gate decided them (the autonomy stamp). A queue row that names
# one without the stamp was not decided by the gate, so it is never delivered (RESP-11).
GATE_ONLY_COMMANDS = ("quarantine_file", "unquarantine_file", "restart_service", "isolate_host",
                      "restore_host", "reboot_host")
_GATE_REQUIRED = "autonomy_gate_required"
_CANCEL_ROW_STATES = ("approved", "dispatching")
_EXPIRED = "instruction_expired"


class _Unreadable(Exception):
    """The stop or ledger state could not be read; the item must be withheld."""


def _stamp(item: Dict[str, Any]) -> Dict[str, Any]:
    stamp = item.get("autonomy")
    return stamp if isinstance(stamp, dict) and isinstance(stamp.get("actionId"), str) and stamp["actionId"] else {}


def _command_name(value: Any) -> str:
    """The same normalisation the capability check uses: text before ':', lower case, ``_`` for space and ``-``."""
    return str(value or "").split(":", 1)[0].strip().lower().replace(" ", "_").replace("-", "_")


def _gate_only_unstamped(item: Dict[str, Any]) -> bool:
    return not _stamp(item) and any(_command_name(item.get(f)) in GATE_ONLY_COMMANDS
                                    for f in ("type", "instruction", "action"))


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


def _expired(item: Dict[str, Any], now: datetime) -> bool:
    """Whether the item carries an ``expiresAt`` that has passed. Undo and compensate never expire (D-15)."""
    at = item.get("expiresAt")
    if not isinstance(at, datetime):
        return False
    if _stamp(item).get("kind") in STOP_EXEMPT_KINDS:
        return False
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) <= now


async def _refuse(coll, items: List[Dict[str, Any]], why: str) -> None:
    """Mark each pending item refused. A write that fails is logged: the item is dropped from the list anyway."""
    for item in items:
        try:
            await coll.update_one({"_id": item["_id"], "status": "pending"},
                                  {"$set": {"status": _REFUSED, "error": why,
                                            "refused_at": datetime.now(timezone.utc).isoformat()}})
        except Exception as exc:
            logger.error("autonomous_ops: %s %s not marked refused (%s): %s", "agent_instructions",
                         item.get("_id"), why, exc)


async def cancel_unfetched(db, tenant_id: str, instruction_id: Optional[str], now: datetime) -> bool:
    """Abandon an instruction nobody fetched: ``pending`` becomes ``cancelled``, so a computer that comes back later
    can not run a step the platform has already given up on (84 WR-27). One compare-and-set on the status: an
    instruction the agent fetched in the meantime is left alone. Never raises."""
    if not instruction_id:
        return False
    at = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    try:
        done = await raw(db).agent_instructions.update_one(
            {"id": instruction_id, "tenantId": tenant_id, "status": "pending"},
            {"$set": {"status": "cancelled", "error": "rollout_abandoned", "cancelled_at": at.isoformat()}})
    except Exception as exc:
        logger.error("autonomous_ops: instruction %s was not cancelled: %s", instruction_id, exc)
        return False
    return done.modified_count > 0


async def hold_back_autonomous(db, tenant_id: Optional[str], instructions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The agent instructions that may be delivered now (stamped ones filtered per the rules above)."""
    if not instructions:
        return instructions
    now = datetime.now(timezone.utc)
    lapsed = [i for i in instructions if _expired(i, now)]
    if lapsed:
        await _refuse(raw(db).agent_instructions, lapsed, _EXPIRED)
        gone = {id(i) for i in lapsed}
        instructions = [i for i in instructions if id(i) not in gone]
        if not instructions:
            return instructions
    unstamped = [i for i in instructions if _gate_only_unstamped(i)]
    if unstamped:
        await _refuse(raw(db).agent_instructions, unstamped, _GATE_REQUIRED)
        gone = {id(i) for i in unstamped}
        instructions = [i for i in instructions if id(i) not in gone]
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
